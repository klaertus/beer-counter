"""
Beer Counter — Flask application factory.
Loads config.json, initialises the database, registers the three blueprints.
"""
import json
import os

from flask import Flask
from sqlalchemy import text

from models import db, SuperAdmin
from blueprints.public     import public_bp
from blueprints.admin      import admin_bp
from blueprints.superadmin import superadmin_bp


def load_config(path='config.json'):
    """Read and return the JSON config file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_labels(cfg, base_dir):
    """Load labels from a JSON file if configured."""
    labels_file = cfg.get('labels_file')
    if not labels_file:
        return {}
    path = labels_file if os.path.isabs(labels_file) else os.path.join(base_dir, labels_file)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def create_app(config_path='config.json'):
    """Flask application factory — call this to get a configured app instance."""
    app = Flask(__name__)
    cfg = load_config(config_path)
    base_dir = os.path.dirname(os.path.abspath(config_path)) or os.getcwd()

    # ── Core Flask settings ────────────────────────────────────────────────────
    app.config['SECRET_KEY']               = cfg['secret_key']
    app.config['SQLALCHEMY_DATABASE_URI']  = cfg['database_url']
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH']       = cfg['max_upload_bytes']

    # ── App-specific settings (accessed via current_app.config in blueprints) ─
    app.config['UPLOAD_FOLDER']    = cfg['upload_folder']
    app.config['THUMBNAIL_FOLDER'] = cfg.get('thumbnail_folder', 'thumbnails')
    app.config['COMPRESS_QUALITY'] = cfg.get('compress_quality', 85)
    app.config['COMPRESS_MAX_W']   = cfg.get('compress_max_width', 800)
    app.config['COMPRESS_MAX_H']   = cfg.get('compress_max_height', 600)
    app.config['THUMB_SIZE']       = tuple(cfg.get('thumbnail_size', [300, 200]))
    app.config['RATE_LIMITS']      = cfg['rate_limits']
    app.config['CHART_TITLE_DEFAULT'] = cfg.get('chart_title_default', 'Beer Counter')
    app.config['DRINK_LABEL_DEFAULT'] = cfg.get('drink_label_default', 'Beers')
    app.config['VOMIT_ENABLED_DEFAULT'] = cfg.get('vomit_enabled_default', True)
    app.config['LABELS'] = load_labels(cfg, base_dir)

    db.init_app(app)

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp,      url_prefix='/admin')
    app.register_blueprint(superadmin_bp, url_prefix='/superadmin')

    with app.app_context():
        db.create_all()
        _seed_superadmin(cfg['superadmin'])
        _ensure_chart_title_column(app)
        _ensure_drink_settings_columns(app)
        _seed_chart_titles(app)
        _seed_drink_settings(app)
        os.makedirs(cfg['upload_folder'],                      exist_ok=True)
        os.makedirs(cfg.get('thumbnail_folder', 'thumbnails'), exist_ok=True)

    return app


def _seed_superadmin(sa_cfg):
    """Create the super admin account on first run (credentials from config.json)."""
    if not SuperAdmin.query.first():
        admin = SuperAdmin(username=sa_cfg['username'])
        admin.set_password(sa_cfg['password'])
        db.session.add(admin)
        db.session.commit()


def _ensure_chart_title_column(app):
    """Add chart_title column for existing SQLite databases without migrations."""
    if db.engine.dialect.name != 'sqlite':
        return
    cols = db.session.execute(text('PRAGMA table_info(drink_session)')).fetchall()
    column_names = {row[1] for row in cols}
    if 'chart_title' not in column_names:
        db.session.execute(text('ALTER TABLE drink_session ADD COLUMN chart_title VARCHAR(140)'))
        db.session.commit()


def _seed_chart_titles(app):
    """Backfill chart titles for existing sessions with the configured default."""
    default_title = app.config.get('CHART_TITLE_DEFAULT')
    if not default_title:
        return
    db.session.execute(
        text('UPDATE drink_session SET chart_title = :title WHERE chart_title IS NULL OR chart_title = ""'),
        {'title': default_title}
    )
    db.session.commit()


def _ensure_drink_settings_columns(app):
    """Add drink_label and vomit_enabled columns for existing SQLite databases."""
    if db.engine.dialect.name != 'sqlite':
        return
    cols = db.session.execute(text('PRAGMA table_info(drink_session)')).fetchall()
    column_names = {row[1] for row in cols}
    if 'drink_label' not in column_names:
        db.session.execute(text('ALTER TABLE drink_session ADD COLUMN drink_label VARCHAR(60)'))
        db.session.commit()
    if 'vomit_enabled' not in column_names:
        db.session.execute(text('ALTER TABLE drink_session ADD COLUMN vomit_enabled BOOLEAN'))
        db.session.commit()


def _seed_drink_settings(app):
    """Backfill drink settings for existing sessions with configured defaults."""
    default_label = app.config.get('DRINK_LABEL_DEFAULT', 'Beers')
    default_vomit = 1 if app.config.get('VOMIT_ENABLED_DEFAULT', True) else 0
    db.session.execute(
        text('UPDATE drink_session SET drink_label = :label WHERE drink_label IS NULL OR drink_label = ""'),
        {'label': default_label}
    )
    db.session.execute(
        text('UPDATE drink_session SET vomit_enabled = :vomit WHERE vomit_enabled IS NULL'),
        {'vomit': default_vomit}
    )
    db.session.commit()


if __name__ == '__main__':
    app = create_app()
    app.run(
        host=os.environ.get('HOST', '0.0.0.0'),
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('DEBUG', 'false').lower() == 'true',
    )
