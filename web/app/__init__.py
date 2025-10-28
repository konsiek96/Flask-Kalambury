import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

db = SQLAlchemy()
socketio = SocketIO(async_mode='eventlet', cors_allowed_origins="*")

def create_app(test_config=None):
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.secret_key = "kalamburro"
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'kalambur')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL') or 'sqlite:///kalambury.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # 🟢 ZMIANA 2: Załaduj konfigurację testową, jeśli istnieje
    if test_config is not None:
        app.config.update(test_config)
    db.init_app(app)
    socketio.init_app(app)

    from . import routes, sockets 
    app.register_blueprint(routes.bp)
    '''
    with app.app_context():
        # Upewnij się, że modele są zaimportowane przed tworzeniem tabel
        from .models import Game, Player 
        
        # ⚠️ Opcja deweloperska: Usuń istniejące tabele i utwórz je ponownie
        # BARDZO WAŻNE: To spowoduje usunięcie WSZYSTKICH danych!
        #if os.environ.get('FLASK_ENV') == 'development' and os.environ.get('RECREATE_DB') == 'true':
        #    print("[SYSTEM] Usuwanie wszystkich tabel...")
        #    db.drop_all()
            
        #print("[SYSTEM] Tworzenie tabel...")
        #db.create_all()
        
        # 🟢 OPZONALNIE: Po utworzeniu bazy, wyczyść stare dane
        try:
            # Wyczyść tylko dane o graczach i grach na wypadek nieczystego zamknięcia
            # Upewnij się, że nie ma referencji przed usuwaniem Player/Game
            db.session.execute(db.update(Game).values(current_drawer_id=None))
            Player.query.delete() 
            Game.query.delete()
            db.session.commit()
            print(f"[SYSTEM] Wyczyściliśmy stare dane z bazy (Gracze i Gry).")
        except Exception as e:
            # Może się zdarzyć, jeśli nie ma jeszcze tabel.
            db.session.rollback()
            # print(f"[SYSTEM] Błąd podczas czyszczenia danych startowych: {e}")
    '''   
    return app