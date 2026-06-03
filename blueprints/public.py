"""
Public blueprint — user-facing routes.
Users join a session via a 6-char code, set up a profile, then track their drinks.
Cookie `beer_sessions` is a JSON dict {session_code: user_uuid} stored in the browser.
"""
import os
import json
import uuid
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    jsonify, current_app, make_response
)
from werkzeug.utils import secure_filename
from PIL import Image

from models import db, DrinkSession, User, Team, Drink

public_bp = Blueprint('public', __name__)

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'}

# ─── Cookie helpers ───────────────────────────────────────────────────────────

def _read_cookie():
    """Parse the beer_sessions JSON cookie → {code: user_id}."""
    try:
        return json.loads(request.cookies.get('beer_sessions', '{}'))
    except (ValueError, TypeError):
        return {}


def _get_current_user(code):
    """Return the User for this session code from the browser cookie, or None."""
    sessions = _read_cookie()
    user_id = sessions.get(code)
    if not user_id:
        return None
    ds = DrinkSession.query.filter_by(code=code).first()
    if not ds:
        return None
    return User.query.filter_by(id=user_id, session_id=ds.id).first()


def _attach_user_cookie(response, code, user_id):
    """Persist the user's identity for this session code in the browser cookie."""
    sessions = _read_cookie()
    sessions[code] = user_id
    response.set_cookie(
        'beer_sessions',
        json.dumps(sessions),
        max_age=365 * 24 * 3600,
        httponly=True,
        samesite='Lax',
    )
    return response


# ─── Rate limiting ────────────────────────────────────────────────────────────

def _rate_limited(user_id, session_id):
    """
    Return (is_limited: bool, cooldown_seconds: int).
    Checks each time window from config; the first exceeded window triggers cooldown.
    Cooldown ends when the oldest drink in that window expires.
    """
    limits = current_app.config['RATE_LIMITS']
    now    = datetime.utcnow()

    windows = [
        (timedelta(seconds=20), limits['per_20s']),
        (timedelta(minutes=3),  limits['per_3min']),
        (timedelta(minutes=20), limits['per_20min']),
        (timedelta(hours=1),    limits['per_hour']),
    ]

    for delta, max_count in windows:
        since = now - delta
        recent = (
            Drink.query
            .filter(
                Drink.user_id    == user_id,
                Drink.session_id == session_id,
                Drink.kind       == 'beer',
                Drink.timestamp  >= since,
            )
            .order_by(Drink.timestamp.asc())
            .all()
        )
        if len(recent) >= max_count:
            # Cooldown ends when the oldest drink in this window expires
            cooldown_end = recent[0].timestamp + delta
            cooldown = max(1, int((cooldown_end - now).total_seconds()) + 1)
            return True, cooldown

    return False, 0


# ─── Photo helpers ────────────────────────────────────────────────────────────

def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[-1].lower() in ALLOWED_EXTENSIONS


def _save_photo(file_obj, session_code, user):
    """
    Compress an uploaded selfie and save it + thumbnail.
    Returns the filename, or None if the file is missing/invalid.
    Files are stored in uploads/{session_code}/ and thumbnails/{session_code}/.
    """
    if not file_obj or not _allowed_file(file_obj.filename):
        return None

    cfg      = current_app.config
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
    safe_username = secure_filename((user.username or '').strip()) or 'user'
    filename = f"{safe_username}_{ts}_{user.id}.jpg"

    upload_dir = os.path.join(cfg['UPLOAD_FOLDER'],    session_code)
    thumb_dir  = os.path.join(cfg['THUMBNAIL_FOLDER'], session_code)
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(thumb_dir,  exist_ok=True)

    try:
        img = Image.open(file_obj).convert('RGB')
        img.thumbnail((cfg['COMPRESS_MAX_W'], cfg['COMPRESS_MAX_H']))
        img.save(os.path.join(upload_dir, filename), 'JPEG', quality=cfg['COMPRESS_QUALITY'])

        thumb = img.copy()
        thumb.thumbnail(cfg['THUMB_SIZE'])
        thumb.save(os.path.join(thumb_dir, filename), 'JPEG', quality=75)

        return filename
    except Exception:
        return None


# ─── Public routes ────────────────────────────────────────────────────────────

@public_bp.route('/')
def home():
    """Landing page — enter a session code to join."""
    return render_template('home.html')


@public_bp.route('/join', methods=['POST'])
def join():
    """Validate the session code and redirect to setup or counter."""
    code = request.form.get('code', '').strip().upper()
    if not code:
        return render_template('home.html', error='Please enter a session code.')

    ds = DrinkSession.query.filter_by(code=code).first()
    if not ds:
        return render_template('home.html', error='Session not found. Check your code.')
    if not ds.is_open:
        return render_template('home.html', error='This session is currently closed.')

    user = _get_current_user(code)
    if user:
        return redirect(url_for('public.counter', code=code))
    return redirect(url_for('public.setup', code=code))


@public_bp.route('/s/<code>/')
def session_redirect(code):
    """Convenience URL — redirect to counter or setup based on cookie."""
    ds = DrinkSession.query.filter_by(code=code).first_or_404()
    if not ds.is_open:
        return render_template('home.html', error='This session is currently closed.')
    user = _get_current_user(code)
    if user:
        return redirect(url_for('public.counter', code=code))
    return redirect(url_for('public.setup', code=code))


@public_bp.route('/s/<code>/setup', methods=['GET', 'POST'])
def setup(code):
    """User registration: choose name, color, and team for this session."""
    ds    = DrinkSession.query.filter_by(code=code).first_or_404()
    teams = Team.query.filter_by(session_id=ds.id).all()
    labels = current_app.config.get('LABELS', {})

    if not ds.is_open:
        return render_template('home.html', error='This session is currently closed.')

    if request.method == 'POST':
        username       = request.form.get('username', '').strip()
        color          = request.form.get('color', '#3f51b5').strip()
        team_id        = request.form.get('team_id') or None
        new_team_name  = request.form.get('new_team', '').strip()
        new_team_color = request.form.get('new_team_color', '#3b82f6')

        if not username:
            error_msg = labels.get('setup_error_name', 'Name is required.')
            return render_template('setup.html', ds=ds, teams=teams, labels=labels,
                                   error=error_msg)

        # Create a new team if the user filled in the "create team" field
        if new_team_name:
            team = Team(session_id=ds.id, name=new_team_name, color=new_team_color)
            db.session.add(team)
            db.session.flush()
            team_id = team.id

        user = User(
            id=str(uuid.uuid4()),
            session_id=ds.id,
            username=username,
            color=color,
            team_id=int(team_id) if team_id else None,
        )
        db.session.add(user)
        db.session.commit()

        response = make_response(redirect(url_for('public.counter', code=code)))
        _attach_user_cookie(response, code, user.id)
        return response

    return render_template('setup.html', ds=ds, teams=teams, labels=labels)


@public_bp.route('/s/<code>/counter')
def counter(code):
    """Main beer counter page."""
    ds   = DrinkSession.query.filter_by(code=code).first_or_404()
    user = _get_current_user(code)
    if not user:
        return redirect(url_for('public.setup', code=code))

    beer_count = Drink.query.filter_by(user_id=user.id, kind='beer').count()
    vomit_count = Drink.query.filter_by(user_id=user.id, kind='vomit').count()
    drink_label = ds.drink_label or current_app.config.get('DRINK_LABEL_DEFAULT', 'Beers')
    labels = current_app.config.get('LABELS', {})
    return render_template(
        'counter.html',
        ds=ds, user=user,
        beer_count=beer_count,
        vomit_count=vomit_count,
        drink_label=drink_label,
        labels=labels
    )


@public_bp.route('/s/<code>/chart')
def chart(code):
    """Analytics page — drink charts and leaderboard."""
    ds = DrinkSession.query.filter_by(code=code).first_or_404()
    labels = current_app.config.get('LABELS', {})
    chart_title = ds.chart_title or current_app.config.get('CHART_TITLE_DEFAULT', ds.name)
    drink_label = ds.drink_label or current_app.config.get('DRINK_LABEL_DEFAULT', 'Beers')
    return render_template(
        'chart.html',
        ds=ds,
        labels=labels,
        chart_title=chart_title,
        drink_label=drink_label
    )


# ─── User API ─────────────────────────────────────────────────────────────────

@public_bp.route('/s/<code>/api/drink', methods=['POST'])
def api_drink(code):
    """
    Record a beer for the current user.
    Enforces rate limits. Accepts optional multipart/form-data photo.
    Returns JSON: {success, beer_count} or {error, cooldown}.
    """
    ds = DrinkSession.query.filter_by(code=code).first_or_404()
    if not ds.is_open:
        return jsonify({'error': 'Session is closed'}), 403

    user = _get_current_user(code)
    if not user:
        return jsonify({'error': 'Not registered'}), 401

    limited, cooldown = _rate_limited(user.id, ds.id)
    if limited:
        return jsonify({'error': 'Rate limited', 'cooldown': cooldown}), 429

    photo_filename = None
    if 'photo' in request.files:
        photo_filename = _save_photo(request.files['photo'], code, user)

    db.session.add(Drink(
        session_id=ds.id,
        user_id=user.id,
        kind='beer',
        photo=photo_filename,
    ))
    db.session.commit()

    beer_count = Drink.query.filter_by(user_id=user.id, kind='beer').count()
    return jsonify({'success': True, 'beer_count': beer_count})


@public_bp.route('/s/<code>/api/vomit', methods=['POST'])
def api_vomit(code):
    """Record a vomit event (separate counter, no rate limit)."""
    ds = DrinkSession.query.filter_by(code=code).first_or_404()
    if not ds.is_open:
        return jsonify({'error': 'Session is closed'}), 403

    user = _get_current_user(code)
    if not user:
        return jsonify({'error': 'Not registered'}), 401

    if not ds.vomit_enabled:
        return jsonify({'error': 'Vomit disabled'}), 403

    db.session.add(Drink(session_id=ds.id, user_id=user.id, kind='vomit'))
    db.session.commit()
    vomit_count = Drink.query.filter_by(user_id=user.id, kind='vomit').count()
    return jsonify({'success': True, 'vomit_count': vomit_count})


@public_bp.route('/s/<code>/api/photo', methods=['POST'])
def api_photo(code):
    """Upload a standalone photo (not tied to a drink event). Stored in admin photo gallery."""
    ds = DrinkSession.query.filter_by(code=code).first_or_404()
    if not ds.is_open:
        return jsonify({'error': 'Session is closed'}), 403

    user = _get_current_user(code)
    if not user:
        return jsonify({'error': 'Not registered'}), 401

    if 'photo' not in request.files:
        return jsonify({'error': 'No photo provided'}), 400

    photo_filename = _save_photo(request.files['photo'], code, user)
    if not photo_filename:
        return jsonify({'error': 'Invalid photo file'}), 400

    db.session.add(Drink(session_id=ds.id, user_id=user.id, kind='photo', photo=photo_filename))
    db.session.commit()
    return jsonify({'success': True})


@public_bp.route('/s/<code>/api/data')
def api_data(code):
    """
    Return all chart data for the session.
    Includes per-user beer timelines, team totals, and top-10 leaderboard.
    """
    ds    = DrinkSession.query.filter_by(code=code).first_or_404()
    users = User.query.filter_by(session_id=ds.id).all()

    user_data = []
    for u in users:
        beers = (
            Drink.query
            .filter_by(user_id=u.id, kind='beer')
            .order_by(Drink.timestamp)
            .all()
        )
        vomits = Drink.query.filter_by(user_id=u.id, kind='vomit').count()
        user_data.append({
            'username':   u.username,
            'color':      u.color,
            'team':       u.team.name if u.team else None,
            'team_color': u.team.color if u.team else None,
            'total':      len(beers),
            'vomits':     vomits,
            'timestamps': [d.timestamp.isoformat() for d in beers],
        })

    teams     = Team.query.filter_by(session_id=ds.id).all()
    team_data = []
    for t in teams:
        total_beers  = sum(Drink.query.filter_by(user_id=u.id, kind='beer').count()  for u in t.users)
        total_vomits = sum(Drink.query.filter_by(user_id=u.id, kind='vomit').count() for u in t.users)
        team_data.append({'name': t.name, 'color': t.color, 'total': total_beers, 'vomits': total_vomits})

    top10 = sorted(user_data, key=lambda x: x['total'], reverse=True)[:10]
    chart_title = ds.chart_title or current_app.config.get('CHART_TITLE_DEFAULT', ds.name)
    return jsonify({
        'users': user_data,
        'teams': team_data,
        'top10': top10,
        'is_open': ds.is_open,
        'chart_title': chart_title,
        'vomit_enabled': bool(ds.vomit_enabled),
        'drink_label': ds.drink_label or current_app.config.get('DRINK_LABEL_DEFAULT', 'Beers'),
    })


@public_bp.route('/s/<code>/api/status')
def api_status(code):
    ds = DrinkSession.query.filter_by(code=code).first_or_404()
    return jsonify({'is_open': ds.is_open})
