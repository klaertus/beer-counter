"""
Admin blueprint — session-scoped dashboard.
Session admins log in with username + password and manage users, teams, drinks,
photos, and session settings. Auth is stored in Flask's signed-cookie session
under the key 'session_admin' as {code, session_id}.
"""
import os
import uuid
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, jsonify, current_app, send_from_directory
)

from models import db, DrinkSession, User, Team, Drink

admin_bp = Blueprint('admin', __name__)


# ─── Auth ─────────────────────────────────────────────────────────────────────

def session_admin_required(f):
    """Redirect to login if the caller isn't the admin for the requested session code."""
    @wraps(f)
    def decorated(*args, **kwargs):
        code = kwargs.get('code', '')
        if session.get('superadmin'):
            return f(*args, **kwargs)
        if session.get('session_admin', {}).get('code') != code:
            return redirect(url_for('admin.login', code=code))
        return f(*args, **kwargs)
    return decorated


# ─── Login / Logout ───────────────────────────────────────────────────────────

@admin_bp.route('/')
def admin_index():
    """Landing page for session admins who don't know their login URL."""
    return render_template('admin/enter_code.html')


@admin_bp.route('/<code>/login', methods=['GET', 'POST'])
def login(code):
    ds = DrinkSession.query.filter_by(code=code).first_or_404()

    if session.get('superadmin'):
        return redirect(url_for('admin.dashboard', code=code))

    if request.method == 'POST':
        password = request.form.get('password', '')
        if ds.check_admin_password(password):
            session['session_admin'] = {'code': code, 'session_id': ds.id}
            return redirect(url_for('admin.dashboard', code=code))
        flash('Incorrect password.', 'danger')

    return render_template('admin/login.html', ds=ds)


@admin_bp.route('/<code>/logout')
def logout(code):
    session.pop('session_admin', None)
    return redirect(url_for('admin.login', code=code))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@admin_bp.route('/<code>/')
@admin_bp.route('/<code>/dashboard')
@session_admin_required
def dashboard(code):
    ds           = DrinkSession.query.filter_by(code=code).first()
    users        = User.query.filter_by(session_id=ds.id).all()
    teams        = Team.query.filter_by(session_id=ds.id).all()
    total_beers  = Drink.query.filter_by(session_id=ds.id, kind='beer').count()
    total_vomits = Drink.query.filter_by(session_id=ds.id, kind='vomit').count()
    recent       = (Drink.query
                    .filter_by(session_id=ds.id)
                    .order_by(Drink.timestamp.desc())
                    .limit(20).all())

    return render_template('admin/dashboard.html',
                           ds=ds, users=users, teams=teams,
                           total_beers=total_beers, total_vomits=total_vomits,
                           recent=recent)


# ─── Users ────────────────────────────────────────────────────────────────────

@admin_bp.route('/<code>/users')
@session_admin_required
def users(code):
    ds        = DrinkSession.query.filter_by(code=code).first()
    all_users = User.query.filter_by(session_id=ds.id).all()
    all_teams = Team.query.filter_by(session_id=ds.id).all()
    for u in all_users:
        u.beer_count = Drink.query.filter_by(user_id=u.id, kind='beer').count()
    return render_template('admin/users.html', ds=ds, users=all_users, teams=all_teams)


@admin_bp.route('/<code>/api/users', methods=['POST'])
@session_admin_required
def create_user(code):
    ds   = DrinkSession.query.filter_by(code=code).first()
    data = request.json or {}
    user = User(
        id=str(uuid.uuid4()),
        session_id=ds.id,
        username=data.get('username', 'New User'),
        color=data.get('color', '#3f51b5'),
        team_id=data.get('team_id'),
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({'id': user.id, 'username': user.username, 'color': user.color})


@admin_bp.route('/<code>/api/users/<user_id>', methods=['PUT'])
@session_admin_required
def update_user(code, user_id):
    ds   = DrinkSession.query.filter_by(code=code).first()
    user = User.query.filter_by(id=user_id, session_id=ds.id).first_or_404()
    data = request.json or {}
    user.username = data.get('username', user.username)
    user.color    = data.get('color', user.color)
    user.team_id  = data.get('team_id', user.team_id)
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/<code>/api/users/<user_id>', methods=['DELETE'])
@session_admin_required
def delete_user(code, user_id):
    ds   = DrinkSession.query.filter_by(code=code).first()
    user = User.query.filter_by(id=user_id, session_id=ds.id).first_or_404()
    db.session.delete(user)
    db.session.commit()
    return jsonify({'success': True})


# ─── Teams ────────────────────────────────────────────────────────────────────

@admin_bp.route('/<code>/teams')
@session_admin_required
def teams(code):
    ds        = DrinkSession.query.filter_by(code=code).first()
    all_teams = Team.query.filter_by(session_id=ds.id).all()
    for t in all_teams:
        t.member_count = User.query.filter_by(team_id=t.id).count()
    return render_template('admin/teams.html', ds=ds, teams=all_teams)


@admin_bp.route('/<code>/api/teams', methods=['POST'])
@session_admin_required
def create_team(code):
    ds   = DrinkSession.query.filter_by(code=code).first()
    data = request.json or {}
    team = Team(session_id=ds.id,
                name=data.get('name', 'New Team'),
                color=data.get('color', '#3b82f6'))
    db.session.add(team)
    db.session.commit()
    return jsonify({'id': team.id, 'name': team.name, 'color': team.color})


@admin_bp.route('/<code>/api/teams/<int:team_id>', methods=['PUT'])
@session_admin_required
def update_team(code, team_id):
    ds   = DrinkSession.query.filter_by(code=code).first()
    team = Team.query.filter_by(id=team_id, session_id=ds.id).first_or_404()
    data = request.json or {}
    team.name  = data.get('name', team.name)
    team.color = data.get('color', team.color)
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/<code>/api/teams/<int:team_id>', methods=['DELETE'])
@session_admin_required
def delete_team(code, team_id):
    ds   = DrinkSession.query.filter_by(code=code).first()
    team = Team.query.filter_by(id=team_id, session_id=ds.id).first_or_404()
    User.query.filter_by(team_id=team_id).update({'team_id': None})
    db.session.delete(team)
    db.session.commit()
    return jsonify({'success': True})


# ─── Drinks ───────────────────────────────────────────────────────────────────

@admin_bp.route('/<code>/drinks')
@session_admin_required
def drinks(code):
    ds         = DrinkSession.query.filter_by(code=code).first()
    all_drinks = (Drink.query
                  .filter_by(session_id=ds.id)
                  .order_by(Drink.timestamp.desc())
                  .all())
    users_map  = {u.id: u for u in User.query.filter_by(session_id=ds.id).all()}
    return render_template('admin/drinks.html', ds=ds, drinks=all_drinks, users_map=users_map)


@admin_bp.route('/<code>/api/drinks/<int:drink_id>', methods=['DELETE'])
@session_admin_required
def delete_drink(code, drink_id):
    ds    = DrinkSession.query.filter_by(code=code).first()
    drink = Drink.query.filter_by(id=drink_id, session_id=ds.id).first_or_404()
    db.session.delete(drink)
    db.session.commit()
    return jsonify({'success': True})


# ─── Photos ───────────────────────────────────────────────────────────────────

@admin_bp.route('/<code>/photos')
@session_admin_required
def photos(code):
    ds          = DrinkSession.query.filter_by(code=code).first()
    photo_drinks = (Drink.query
                    .filter_by(session_id=ds.id)
                    .filter(Drink.photo.isnot(None))
                    .order_by(Drink.timestamp.desc())
                    .all())
    users_map = {u.id: u for u in User.query.filter_by(session_id=ds.id).all()}
    return render_template('admin/photos.html', ds=ds,
                           photo_drinks=photo_drinks, users_map=users_map)


@admin_bp.route('/<code>/uploads/<filename>')
@session_admin_required
def serve_photo(code, filename):
    """Serve an original photo (admin only)."""
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], code)
    return send_from_directory(upload_dir, filename)


@admin_bp.route('/<code>/thumbnails/<filename>')
@session_admin_required
def serve_thumbnail(code, filename):
    """Serve a thumbnail (admin only)."""
    thumb_dir = os.path.join(current_app.config['THUMBNAIL_FOLDER'], code)
    return send_from_directory(thumb_dir, filename)


@admin_bp.route('/<code>/api/photos/<filename>', methods=['DELETE'])
@session_admin_required
def delete_photo(code, filename):
    """Delete photo + thumbnail files and remove the reference from the drink row."""
    ds    = DrinkSession.query.filter_by(code=code).first()
    drink = Drink.query.filter_by(session_id=ds.id, photo=filename).first_or_404()

    for folder_key in ('UPLOAD_FOLDER', 'THUMBNAIL_FOLDER'):
        path = os.path.join(current_app.config[folder_key], code, filename)
        if os.path.exists(path):
            os.remove(path)

    drink.photo = None
    db.session.commit()
    return jsonify({'success': True})


# ─── Settings ─────────────────────────────────────────────────────────────────

@admin_bp.route('/<code>/settings', methods=['GET', 'POST'])
@session_admin_required
def settings(code):
    ds = DrinkSession.query.filter_by(code=code).first()

    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'rename':
            name = request.form.get('name', '').strip()
            if name:
                ds.name = name
                db.session.commit()
                flash('Session name updated.', 'success')
            else:
                flash('Name cannot be empty.', 'danger')

        elif action == 'change_password':
            current_pw = request.form.get('current_password', '')
            new_pw     = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')
            if not ds.check_admin_password(current_pw):
                flash('Current password is incorrect.', 'danger')
            elif new_pw != confirm_pw:
                flash('New passwords do not match.', 'danger')
            elif len(new_pw) < 6:
                flash('Password must be at least 6 characters.', 'danger')
            else:
                ds.set_admin_password(new_pw)
                db.session.commit()
                flash('Password updated.', 'success')

        elif action == 'toggle':
            ds.is_open = not ds.is_open
            db.session.commit()
            flash(f'Session {"opened" if ds.is_open else "closed"}.', 'success')

    return render_template('admin/settings.html', ds=ds)
