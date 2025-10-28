from flask import flash, Blueprint, render_template, request, redirect, url_for, session, current_app, jsonify
from .models import Game, Player, Word
from . import db
from sqlalchemy.orm import joinedload

bp = Blueprint('main', __name__)

@bp.route('/', methods=['GET','POST'])
def index():
    if request.method == 'POST':
        username = request.form.get('username')
        if username:
            session["username"] = username
            return redirect(url_for('main.lobby'))       
    return render_template('index.html')

@bp.route('/lobby')
def lobby():
    username = session.get('username')
    if not username:
        return redirect(url_for('main.index'))
    games = Game.query.options(joinedload(Game.players)).all()
    return render_template('lobby.html', games=games, username=username)

@bp.route('/create', methods=['GET','POST'])
def create_game():
    if request.method == 'POST':
        # Pobierz username z sesji
        username = session.get('username')
        if not username:
            return "Nie jesteś zalogowany", 400  # albo redirect na stronę logowania
            
        name = request.form.get('name') or "Gra"
        private = bool(request.form.get('is_private'))
        pwd = request.form.get('password')
        max_players = int(request.form.get('max_players') or 8)
        round_time = int(request.form.get('round_time') or 90)
        g = Game(name=name, is_private=private, max_players=max_players,round_time=round_time, creator=username)
        if private and pwd:
            g.set_password(pwd)
        db.session.add(g)
        db.session.commit()
        return redirect(url_for('main.lobby'))
    return render_template('create_game.html')
    
    
@bp.route('/join/<int:game_id>', methods=['GET', 'POST'])
def join_game(game_id):
    username = session.get('username')
    if not username:
        return redirect(url_for('main.index'))

    game = Game.query.get(game_id)
    if not game:
        return "No such game", 404

    # Sprawdź czy użytkownik już jest w grze
    player = Player.query.filter_by(username=username, game_id=game_id).first()
    if player:
        return redirect(url_for('main.game_view', game_id=game_id))

    if game.is_private:
        if request.method == 'POST':
            password = request.form.get('password')
            if game.check_password(password):
                p = Player(username=username, game_id=game_id)
                db.session.add(p)
                db.session.commit()
                return redirect(url_for('main.game_view', game_id=game_id))
            else:
                return render_template('enter_password.html', game=game, error="Błędne hasło")
        return render_template('enter_password.html', game=game)
    else:
        # Gra publiczna
        p = Player(username=username, game_id=game_id)
        db.session.add(p)
        db.session.commit()
        return redirect(url_for('main.game_view', game_id=game_id))

@bp.route('/delete_game/<int:game_id>', methods=['POST'])
def delete_game(game_id):
    username = session.get('username')
    if not username:
        flash("Musisz być zalogowany, aby usunąć grę.", "danger")
        return redirect(url_for('main.index'))

    # Upewnij się, że ładujemy Game, aby ORM mogło śledzić relacje
    # Użycie get_or_404 jest tutaj optymalne
    game = Game.query.options(
        joinedload(Game.players)
    ).get_or_404(game_id)
    
    if game.creator != username:
        flash("Tylko twórca może usunąć ten pokój.", "danger")
        return redirect(url_for('main.lobby'))
        
    try:
        # 1. Ręczne zerowanie klucza obcego (FK) z Game do Player.
        #    To jest niezbędne, ponieważ usuwanie obiektu 'game' przez ORM 
        #    aktywuje usuwanie graczy (Player), a to z kolei naruszyłoby FK 
        #    Game.current_drawer_id -> Player.id.
        if game.current_drawer_id:
            game.current_drawer_id = None
            
        # 2. Usuwamy obiekt Game. Kaskadowe usuwanie (cascade='all, delete-orphan')
        #    usuwa wszystkich graczy powiązanych z tą grą.
        db.session.delete(game)
        
        # 3. Pojedyncze zatwierdzenie transakcji.
        db.session.commit()
        
        flash(f"Pokój '{game.name}' został pomyślnie usunięty.", "success")
        
    except Exception as e:
        db.session.rollback()
        # Logowanie błędu serwera
        current_app.logger.error(f"Błąd podczas usuwania gry {game_id}: {e}")
        # Informacja dla użytkownika
        flash("Wystąpił błąd podczas usuwania pokoju. Spróbuj ponownie.", "danger")
    
    return redirect(url_for('main.lobby'))

@bp.route('/game/<int:game_id>')
def game_view(game_id):
    username = session.get('username')
    if not username:
        return redirect(url_for('main.index'))

    # 🛑 POPRAWKA 1: Użyj joinedload dla Game.current_drawer
    g = Game.query.options(
        joinedload(Game.players),
        joinedload(Game.current_drawer) # <-- ZAŁADUJ RELACJĘ DO RYSUJĄCEGO
    ).get(game_id)

    if not g:
        # Użycie funkcji 404 w Flasku jest bardziej idiomatyczne
        return "Nie znaleziono takiej gry.", 404

    # 🟢 KLUCZOWA ZMIANA 1: Weryfikacja członkostwa w grze
    player_in_game = Player.query.filter_by(username=username, game_id=g.id).first()
    if not player_in_game:
        # Przekierowujemy do lobby, jeśli gracz nie jest w pokoju
        flash("Musisz dołączyć do gry, aby zobaczyć ten pokój.", "warning")
        return redirect(url_for('main.lobby'))
        
    # Tworzenie słownika danych do przekazania szablonowi
    game_data = {
        'id': g.id,
        'name': g.name,
        'round_time': g.round_time,
        # current_word będzie None, jeśli runda się nie rozpoczęła, ale dzięki
        # zabezpieczeniu w game.html (mojej poprzedniej poprawce) nie wywoła błędu.
        'current_word': g.current_word,
        'players': [p.username for p in g.players],
        # Upewniamy się, że rysujący jest bezpiecznie pobrany
        'drawer': g.current_drawer.username if g.current_drawer else None, 
        # 🟢 POPRAWKA 2: Używamy 'creator' zamiast 'owner' dla spójności
        'creator': g.creator
    }

    return render_template('game.html', game=game_data, username=username)


@bp.route('/words', methods=['GET', 'POST'])
def manage_words():
    if request.method == 'POST':
        new_word = request.form.get('word', '').strip()

        if not new_word:
            flash("Nie podano żadnego hasła.", "warning")
        else:
            existing = Word.query.filter_by(text=new_word).first()
            if existing:
                flash("To hasło już istnieje!", "danger")
            else:
                word = Word(text=new_word)
                db.session.add(word)
                db.session.commit()
                flash("Hasło zostało dodane pomyślnie ✅", "success")

        return redirect(url_for('main.manage_words'))

    words = Word.query.order_by(Word.id.desc()).all()
    return render_template('manage_words.html', words=words)
    
@bp.route('/delete_word/<int:word_id>', methods=['POST'])
def delete_word(word_id):
    from app import db
    word = Word.query.get_or_404(word_id)
    db.session.delete(word)
    db.session.commit()
    return redirect(url_for('main.manage_words'))