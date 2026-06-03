"""
Beer Counter — SQLAlchemy database models.

Naming note: the session model is DrinkSession (not Session) to avoid shadowing
Flask's `session` context-local, which is always imported as `session` from `flask`.
"""
import uuid
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class DrinkSession(db.Model):
    """A drinking event. Users join by entering the session's unique 6-char code."""
    __tablename__ = 'drink_session'

    id             = db.Column(db.Integer,    primary_key=True)
    code           = db.Column(db.String(6),  unique=True, nullable=False, index=True)
    name           = db.Column(db.String(100), nullable=False)
    chart_title    = db.Column(db.String(140), nullable=True)
    drink_label    = db.Column(db.String(60),  nullable=True)
    vomit_enabled  = db.Column(db.Boolean,    default=True, nullable=True)
    password_hash  = db.Column(db.String(256), nullable=False)
    is_open        = db.Column(db.Boolean,    default=True,  nullable=False)
    created_at     = db.Column(db.DateTime,   default=datetime.utcnow, nullable=False)

    users  = db.relationship('User',  back_populates='session', cascade='all, delete-orphan')
    teams  = db.relationship('Team',  back_populates='session', cascade='all, delete-orphan')
    drinks = db.relationship('Drink', back_populates='session', cascade='all, delete-orphan')

    def set_admin_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_admin_password(self, password):
        return check_password_hash(self.password_hash, password)


class Team(db.Model):
    """A named group within a DrinkSession."""
    __tablename__ = 'team'

    id         = db.Column(db.Integer,   primary_key=True)
    session_id = db.Column(db.Integer,   db.ForeignKey('drink_session.id'), nullable=False)
    name       = db.Column(db.String(80), nullable=False)
    color      = db.Column(db.String(7),  nullable=False, default='#3b82f6')

    session = db.relationship('DrinkSession', back_populates='teams')
    users   = db.relationship('User', back_populates='team')

    __table_args__ = (
        db.UniqueConstraint('session_id', 'name', name='uq_team_name_per_session'),
    )


class User(db.Model):
    """A participant. Their UUID is stored in the browser's beer_sessions cookie."""
    __tablename__ = 'user'

    id         = db.Column(db.String(36),  primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = db.Column(db.Integer,     db.ForeignKey('drink_session.id'), nullable=False)
    team_id    = db.Column(db.Integer,     db.ForeignKey('team.id'),          nullable=True)
    username   = db.Column(db.String(80),  nullable=False)
    color      = db.Column(db.String(7),   nullable=False, default='#3f51b5')
    joined_at  = db.Column(db.DateTime,    default=datetime.utcnow, nullable=False)

    session = db.relationship('DrinkSession', back_populates='users')
    team    = db.relationship('Team',         back_populates='users')
    drinks  = db.relationship('Drink',        back_populates='user', cascade='all, delete-orphan')


class Drink(db.Model):
    """
    A single drink event.
    kind = 'beer'  → counts up
    kind = 'vomit' → tracked separately (not subtracted from beer count)
    photo stores the filename only; full path is assembled at runtime from config.
    """
    __tablename__ = 'drink'

    id         = db.Column(db.Integer,    primary_key=True)
    session_id = db.Column(db.Integer,    db.ForeignKey('drink_session.id'), nullable=False)
    user_id    = db.Column(db.String(36), db.ForeignKey('user.id'),          nullable=False)
    kind       = db.Column(db.String(6),  nullable=False)      # 'beer' | 'vomit'
    photo      = db.Column(db.String(200), nullable=True)      # filename, None if no selfie
    timestamp  = db.Column(db.DateTime,   default=datetime.utcnow, nullable=False)

    session = db.relationship('DrinkSession', back_populates='drinks')
    user    = db.relationship('User',         back_populates='drinks')

    __table_args__ = (
        # Composite index for fast rate-limit queries (filter by user + timestamp range)
        db.Index('ix_drink_user_ts', 'user_id', 'timestamp'),
    )


class SuperAdmin(db.Model):
    """Global super administrator. Created once from config.json on first run."""
    __tablename__ = 'super_admin'

    id            = db.Column(db.Integer,    primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at    = db.Column(db.DateTime,    default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
