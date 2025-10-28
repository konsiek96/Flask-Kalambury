import pytest
from app import create_app, db, socketio # Załóżmy, że masz create_app() i obiekty app, db, socketio
from app.models import Game, Player, Word


@pytest.fixture(scope='session')
def app():
    """Tworzy instancję aplikacji Flask dla testów."""
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', # Użycie bazy in-memory
        'SQLALCHEMY_TRACK_MODIFICATIONS': False
    })
    return app

@pytest.fixture(scope='function')
def db_session(app):
    """Tworzy kontekst aplikacji i sesję bazy danych dla każdego testu."""
    with app.app_context():
        db.create_all()
        yield db
        db.session.remove()
        db.drop_all()

@pytest.fixture(scope='function')
def socket_client(app):
    """Tworzy klienta testowego Socket.IO."""
    # Użycie klienta testowego z flask_socketio
    return socketio.test_client(app)