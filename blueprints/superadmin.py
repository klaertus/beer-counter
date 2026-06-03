"""
Superadmin blueprint — global oversight dashboard.
Creates and manages all DrinkSessions, views cross-session statistics.
Auth is stored in Flask's signed-cookie session under the key 'superadmin'.
"""
import random
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, jsonify, current_app
)

from models import db, DrinkSession, User, Drink, SuperAdmin, Team

superadmin_bp = Blueprint('superadmin', __name__)

# Characters used for session codes — ambiguous chars (I, O, 1, 0) removed
_CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


# ─── Auth ─────────────────────────────────────────────────────────────────────

def superadmin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('superadmin'):
            return redirect(url_for('superadmin.login'))
        return f(*args, **kwargs)
    return decorated


def _generate_unique_code(length=6):
    """Generate a random, unique session code (retries up to 10 times)."""
    for _ in range(10):
        code = ''.join(random.choices(_CODE_ALPHABET, k=length))
        if not DrinkSession.query.filter_by(code=code).first():
            return code
    raise RuntimeError('Could not generate a unique session code after 10 attempts.')


# ─── Login / Logout ───────────────────────────────────────────────────────────

@superadmin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        admin    = SuperAdmin.query.first()
        if admin and admin.check_password(password):
            session['superadmin'] = True
            return redirect(url_for('superadmin.dashboard'))
        flash('Invalid credentials.', 'danger')
    return render_template('superadmin/login.html')


@superadmin_bp.route('/logout')
def logout():
    session.pop('superadmin', None)
    return redirect(url_for('superadmin.login'))


# ─── Dashboard ────────────────────────────────────────────────────────────────

@superadmin_bp.route('/')
@superadmin_bp.route('/dashboard')
@superadmin_required
def dashboard():
    all_sessions   = DrinkSession.query.order_by(DrinkSession.created_at.desc()).all()
    total_users    = User.query.count()
    total_beers    = Drink.query.filter_by(kind='beer').count()
    active_sessions = sum(1 for s in all_sessions if s.is_open)

    # Attach per-session stats for the dashboard table
    for s in all_sessions:
        s.user_count = User.query.filter_by(session_id=s.id).count()
        s.beer_count = Drink.query.filter_by(session_id=s.id, kind='beer').count()

    return render_template('superadmin/dashboard.html',
                           sessions=all_sessions,
                           total_users=total_users,
                           total_beers=total_beers,
                           active_sessions=active_sessions,
                           total_sessions=len(all_sessions))


# ─── Session management ───────────────────────────────────────────────────────

@superadmin_bp.route('/sessions')
@superadmin_required
def sessions():
    all_sessions = DrinkSession.query.order_by(DrinkSession.created_at.desc()).all()
    for s in all_sessions:
        s.user_count = User.query.filter_by(session_id=s.id).count()
        s.beer_count = Drink.query.filter_by(session_id=s.id, kind='beer').count()
    return render_template(
        'superadmin/sessions.html',
        sessions=all_sessions,
        chart_title_default=current_app.config.get('CHART_TITLE_DEFAULT', 'Beer Counter'),
        drink_label_default=current_app.config.get('DRINK_LABEL_DEFAULT', 'Beers'),
        vomit_enabled_default=current_app.config.get('VOMIT_ENABLED_DEFAULT', True)
    )


@superadmin_bp.route('/sessions/create', methods=['POST'])
@superadmin_required
def create_session():
    name           = request.form.get('name', '').strip()
    admin_password = request.form.get('admin_password', '')
    chart_title    = request.form.get('chart_title', '').strip()
    drink_label    = request.form.get('drink_label', '').strip()
    vomit_enabled  = request.form.get('vomit_enabled') == 'on'

    if not name or not admin_password:
        flash('Session name and password are required.', 'danger')
        return redirect(url_for('superadmin.sessions'))

    code = _generate_unique_code()
    if not chart_title:
        chart_title = current_app.config.get('CHART_TITLE_DEFAULT', 'Beer Counter')
    if not drink_label:
        drink_label = current_app.config.get('DRINK_LABEL_DEFAULT', 'Beers')
    ds   = DrinkSession(
        name=name,
        code=code,
        chart_title=chart_title,
        drink_label=drink_label,
        vomit_enabled=vomit_enabled
    )
    ds.set_admin_password(admin_password)
    db.session.add(ds)
    db.session.commit()

    flash(f'Session "{name}" created — code: {code}', 'success')
    return redirect(url_for('superadmin.sessions'))


@superadmin_bp.route('/api/sessions/<int:session_id>/toggle', methods=['POST'])
@superadmin_required
def toggle_session(session_id):
    ds = DrinkSession.query.get_or_404(session_id)
    ds.is_open = not ds.is_open
    db.session.commit()
    return jsonify({'is_open': ds.is_open})


@superadmin_bp.route('/api/sessions/<int:session_id>', methods=['DELETE'])
@superadmin_required
def delete_session(session_id):
    ds = DrinkSession.query.get_or_404(session_id)
    name = ds.name
    db.session.delete(ds)
    db.session.commit()
    return jsonify({'success': True, 'deleted': name})


# ─── Settings ─────────────────────────────────────────────────────────────────

@superadmin_bp.route('/settings', methods=['GET', 'POST'])
@superadmin_required
def settings():
    admin = SuperAdmin.query.first()

    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw     = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not admin.check_password(current_pw):
            flash('Current password is incorrect.', 'danger')
        elif new_pw != confirm_pw:
            flash('New passwords do not match.', 'danger')
        elif len(new_pw) < 8:
            flash('Password must be at least 8 characters.', 'danger')
        else:
            admin.set_password(new_pw)
            db.session.commit()
            flash('Super admin password updated.', 'success')

    return render_template('superadmin/settings.html', admin=admin)
