from . import db
from datetime import datetime
import enum
from sqlalchemy.dialects.postgresql import UUID
import uuid
from werkzeug.security import generate_password_hash, check_password_hash

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), default="Gra")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_private = db.Column(db.Boolean, default=False)
    password_hash = db.Column(db.String(512), nullable=True)
    max_players = db.Column(db.Integer, default=8)
    round_time = db.Column(db.Integer, default=120)
    current_word = db.Column(db.String(200), nullable=True)
    current_drawer_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='SET NULL'), nullable=True)
    creator = db.Column(db.String(64), nullable=False)

# 👇 Główna relacja kaskadowego usuwania
    players = db.relationship(
        'Player',
        back_populates='game',
        cascade='all, delete-orphan',
        foreign_keys='Player.game_id'
    )

    # 👇 relacja do aktualnego rysującego gracza
    # 🟢 KLUCZOWA ZMIANA: passive_deletes='all'
    current_drawer = db.relationship(
        'Player', 
        foreign_keys=[current_drawer_id],
        passive_deletes='all' 
    )

    def set_password(self, pwd):
        self.password_hash = generate_password_hash(pwd)

    def check_password(self, pwd):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, pwd)


class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    score = db.Column(db.Integer, default=0)
    sid = db.Column(db.String(120), nullable=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))

    # 👇 Dodaj foreign_keys=[game_id]
    game = db.relationship('Game', back_populates='players', foreign_keys=[game_id])

class Word(db.Model):
    __tablename__ = "word"
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(100), nullable=False, unique=True)
