from . import socketio
from flask_socketio import emit, join_room, leave_room
from app.models import Game, Player, Word, db
import random
from flask import request
from datetime import datetime
from sqlalchemy.orm import joinedload

# Globalna mapa dla połączonych graczy (używana do obsługi disconnect)
connected_players = {}

# 🟢 ZAKTUALIZOWANA FUNKCJA: Emitowanie listy graczy z punktami
def emit_player_list(game):
    """Pobiera i wysyła aktualną listę graczy wraz z punktami do pokoju gry."""
    room_name = f"game_{game.id}"
    
    # Wczytujemy grę z rysującym, by wiedzieć, kogo wyróżnić
    game_with_drawer = Game.query.options(joinedload(Game.current_drawer)).get(game.id)
    
    # Zapytanie o graczy, posortowane po punktach malejąco
    players = Player.query.filter_by(game_id=game.id).order_by(Player.score.desc()).all()
    
    # Ustalenie, kto rysuje
    drawer_username = game_with_drawer.current_drawer.username if game_with_drawer.current_drawer else None
    
    # Przygotowanie danych
    players_data = [
        {'username': p.username, 'score': p.score, 'is_drawer': p.username == drawer_username}
        for p in players
    ]
    
    # Emitowanie aktualizacji do klienta
    emit('update_player_list', {'players': players_data}, room=room_name)

# 🟢 FUNKCJA PLACEHOLDERA: Będzie używana do rotacji rysującego
def _next_round_setup(game):
    """Rotuje rysującego, resetuje słowo/timer i emituje 'drawer_changed' do pokoju."""
    db.session.refresh(game)
    # 1. Pobierz wszystkich graczy w grze, posortowanych po ID dla stabilnej rotacji
    players = Player.query.filter_by(game_id=game.id).order_by(Player.id.asc()).all()
    
    if not players:
        # Brak graczy, nie ma kogo rotować
        game.current_word = None
        game.current_drawer = None
        db.session.commit()
        return

    # 2. Znajdź indeks aktualnego rysującego
    current_drawer_index = -1
    if game.current_drawer:
        try:
            # Użyjemy prostej pętli, zakładając, że lista graczy jest relatywnie krótka
            # To jest bardziej niezawodne niż poleganie na Player.id pasującym do indeksu
            current_drawer_index = next(
                (i for i, p in enumerate(players) if p.id == game.current_drawer.id), 
                -1
            )
        except AttributeError:
            # Rysujący mógł zostać usunięty, ale referencja w Game pozostała
            current_drawer_index = -1

    # 3. Ustal następnego rysującego
    if current_drawer_index == -1:
        # Jeśli nie ma obecnego rysującego (np. pierwszy raz lub stary rysujący odszedł)
        next_drawer = players[0]
    else:
        # Następny gracz w kolejności, zawijamy listę
        next_index = (current_drawer_index + 1) % len(players)
        next_drawer = players[next_index]

    # 4. Zapisz nowy stan gry
    game.current_word = None # Wyczyść hasło
    game.current_drawer = next_drawer # Ustaw nowego rysującego
    db.session.commit()
    
    room_name = f"game_{game.id}"
    
    # 5. Emituj nowemu rysującemu i wszystkim o zmianie (spowoduje to wyświetlenie przycisku Start)
    emit('drawer_changed', {
        'new_drawer': next_drawer.username, 
        'word_length': 0 
    }, room=room_name)
    
    print(f"INFO: Rotacja rysującego dla gry {game.id}: Nowy rysujący to {next_drawer.username}")
    
    # 6. Wyślij zaktualizowaną listę graczy (choć technicznie niepotrzebne przy "drawer_changed", 
    # to jest bezpieczne, by utrzymać stan po każdym zdarzeniu rundy)
    emit_player_list(game)


# Poniższe funkcje zostały zaktualizowane, aby wykorzystywać nowe funkcje i logikę

@socketio.on('join')
def handle_join(data):
    game_id = str(data.get('game_id'))
    username = data.get('username')

    if not game_id or not username:
        print("Join rejected:", data)
        return

    join_room(game_id)
    emit('system_message', {'msg': f'{username} dołączył do pokoju.'}, to=game_id)


@socketio.on('chat_message')
def handle_chat(data):
    username = data.get('username')
    game_id_raw = data.get('room')
    msg = data.get('msg')
    sid = request.sid

    if not username or not game_id_raw or not msg:
        print("chat_message missing data:", data)
        return

    try:
        game_id = int(game_id_raw)
    except (ValueError, TypeError):
        print(f"Invalid game ID format: {game_id_raw}")
        return
        
    game = Game.query.get(game_id)
    
    if not game:
        return
        
    room_name = f"game_{game_id}"
    timestamp = datetime.now().strftime("%H:%M")

    # 1. Emituj wiadomość czatu do wszystkich (zanim zostanie sprawdzona jako hasło)
    emit('chat_message', {'username': username, 'msg': msg, 'time': timestamp}, to=room_name)

    # 2. Sprawdź, czy wiadomość jest poprawnym hasłem
    if game.current_word and msg.strip().lower() == game.current_word.lower():
        
        # 3. Sprawdź, czy zgadującym nie jest rysujący
        current_drawer_username = game.current_drawer.username if game.current_drawer else None
        
        if username == current_drawer_username:
            emit('system_message', {'msg': f'🚫 Nie możesz zgadywać własnego hasła!'}, to=sid)
            return

        # 4. Dodaj punkt i zapisz
        guesser = Player.query.filter_by(username=username, game_id=game.id).first()
        if guesser:
            db.session.refresh(guesser)
            guesser.score += 1
            db.session.commit()
            
        # 5. Zakończenie rundy
        emit_player_list(game) 
            
        emit('system_message', {'msg': f'✅ {username} odgadł słowo "{game.current_word}"!'}, to=room_name)
        emit('round_ended', {'winner': username, 'word': game.current_word}, to=room_name)
        
        _next_round_setup(game)


@socketio.on('start_game')
def handle_start_game(data):
    game_id_raw = data.get('game_id')
    sid = request.sid

    if sid not in connected_players:
        return

    info = connected_players[sid]
    username = info['username']
    
    try:
        game_id = int(game_id_raw)
    except (ValueError, TypeError):
        print(f"Invalid game ID format: {game_id_raw}")
        return

    game = Game.query.options(joinedload(Game.current_drawer)).get(game_id)

    if not game:
        print(f"Game {game_id} not found")
        return
        
    current_drawer_username = game.current_drawer.username if game.current_drawer else None
    if username != current_drawer_username:
        emit('system_message', {'msg': "🚫 Nie jesteś rysującym! Nie możesz rozpocząć rundy."}, to=sid)
        return


    words = Word.query.all()
    if not words:
        emit('system_message', {'msg': "Brak dostępnych słów w bazie!"}, room=f"game_{game_id}")
        return

    selected_word = random.choice(words).text
    game.current_word = selected_word
    db.session.commit()

    emit('game_started', {
        'drawer': username, 
        'word_length': len(selected_word), 
        'round_time': game.round_time
    }, room=f"game_{game_id}")

    emit('your_word', {
        'word': selected_word, 
        'round_time': game.round_time
    }, to=sid) # Zmieniono 'room=sid' na 'to=sid'


@socketio.on('end_round')
def handle_end_round(data):
    game_id_raw = data.get('game_id')
    
    try:
        game_id = int(game_id_raw)
    except (ValueError, TypeError):
        return

    game = Game.query.get(game_id)

    if not game:
        return

    room_name = f"game_{game_id}"

    emit('system_message', {'msg': '⏱ Runda zakończona!'}, room=room_name)
    emit('round_ended', {'word': game.current_word or 'Brak hasła'}, room=room_name)
    
    _next_round_setup(game)


@socketio.on('join_game')
def on_join_game(data):
    game_id_raw = data.get('game_id')
    username = data.get('username')
    sid = request.sid

    if not game_id_raw or not username:
        print("join_game missing data:", data)
        return

    try:
        game_id = int(game_id_raw)
    except (ValueError, TypeError):
        print(f"Invalid game ID format: {game_id_raw}")
        return

    # Wczytujemy grę wraz z aktualnym rysującym
    game = Game.query.options(joinedload(Game.current_drawer)).get(game_id)
    if not game:
        print("Game not found:", game_id)
        return

    room_name = f"game_{game_id}"
    join_room(room_name)

    connected_players[sid] = {'username': username, 'game_id': game_id}

    # Sprawdzamy/dodajemy gracza do bazy
    player = Player.query.filter_by(username=username, game_id=game_id).first()
    if not player:
        new_player = Player(username=username, game_id=game_id, score=0)
        db.session.add(new_player)
        db.session.commit()
        player = new_player
    
    # 🟢 KLUCZOWA ZMIANA: Ustawienie pierwszego rysującego, jeśli nie jest ustawiony
    current_drawer_username = game.current_drawer.username if game.current_drawer else None
    
    if not current_drawer_username:
        # Ustaw tego gracza jako pierwszego rysującego
        game.current_drawer = player 
        db.session.commit()
        
        # Poinformuj klienta (w tym Ciebie) o zmianie rysującego.
        # Spowoduje to wyświetlenie przycisku START dla Ciebie.
        emit('drawer_changed', {
            'new_drawer': username, 
            'word_length': 0 
        }, room=room_name)
    
    # 🟢 Jeśli rysujący jest już ustawiony, poinformuj nowego gracza, kto nim jest
    elif username != current_drawer_username:
        emit('drawer_changed', {
            'new_drawer': current_drawer_username, 
            'word_length': 0 
        }, to=request.sid)

    emit('system_message', {'msg': f'{username} dołączył do gry.'}, room=room_name)
    
    emit_player_list(game)


@socketio.on('leave_game')
def on_leave_game(data):
    # ... (kod pobierający game_id, username, sid, room_name) ...
    game_id_raw = data.get('game_id')
    username = data.get('username')
    sid = request.sid
    
    # ... (kod walidacji)

    room_name = f"game_{game_id}"

    leave_room(room_name)
    connected_players.pop(sid, None)
    
    game = Game.query.options(joinedload(Game.current_drawer)).get(game_id)
    player = Player.query.filter_by(username=username, game_id=game_id).first()
    
    if player and game:
        
        # 🟢 KLUCZOWA POPRAWKA: Najpierw zeruj klucz obcy w obiekcie Game
        if game.current_drawer_id == player.id:
            game.current_drawer = None 
            
        # 2. Usuń gracza. Obie operacje są teraz w tej samej sesji.
        db.session.delete(player)
        
        # 3. ZATWIERDŹ RAZ.
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"BŁĄD ZASAD ZMIANY BAZY DANYCH: {e}")
            return

        # 4. Wyczyść pustą grę (z commit() w środku)
        is_deleted = _cleanup_empty_game(game)
        
        if not is_deleted:
            emit_player_list(game) 
            emit('system_message', {'msg': f'{username} opuścił grę.'}, room=room_name)

    
@socketio.on('disconnect')
def on_disconnect(reason=None): # Upewnij się, że argument jest poprawnie odbierany
    sid = request.sid
    info = connected_players.pop(sid, None)

    if not info:
        return

    username = info['username']
    game_id_int = int(info['game_id'])
    room_name = f"game_{game_id_int}"

    # Wczytaj Grę i Gracza (użycie joinedload jest nadal dobre)
    game = Game.query.options(joinedload(Game.current_drawer)).get(game_id_int)
    player = Player.query.filter_by(username=username, game_id=game_id_int).first()
    
    if player and game:
        
        # 🟢 KLUCZOWA POPRAWKA: Najpierw zeruj klucz obcy w obiekcie Game
        if game.current_drawer_id == player.id:
            # Ustawienie na None zeruje KLUCZ OBCY w bazie, jeśli jest commit
            game.current_drawer = None  
        
        # 2. Usuń gracza. Obie operacje są teraz w tej samej sesji (db.session).
        db.session.delete(player)
        
        # 3. ZATWIERDŹ RAZ. SQLAlchemy zoptymalizuje operacje:
        #    UPDATE game SET current_drawer_id = NULL WHERE ...;
        #    DELETE FROM player WHERE ...;
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"BŁĄD ZASAD ZMIANY BAZY DANYCH: {e}")
            return

        # 4. Wyczyść pustą grę (z commit() w środku)
        is_deleted = _cleanup_empty_game(game)
        
        if not is_deleted:
            # Jeśli gra istnieje, zaktualizuj listę i wyślij wiadomość
            emit_player_list(game)
            emit('system_message', {'msg': f'{username} rozłączył się.'}, room=room_name)
    
@socketio.on('drawing_data')
def handle_drawing_data(data):
    """Przekazuje dane rysowania do wszystkich graczy w pokoju gry."""
    game_id_raw = data.get('game_id')
    
    try:
        game_id = int(game_id_raw)
    except (ValueError, TypeError):
        return

    room_name = f"game_{game_id}"
    
    # Emitujemy dane do wszystkich W POKOJU, z wyłączeniem nadawcy (broadcast=True, ale lepiej użyć 'to' i pominąć sid)
    # W tym przypadku wystarczy, że upewnimy się, że odbiorcami są inni gracze w pokoju.
    # W naszym przypadku, użyjemy `room` i po prostu nie odfiltrujemy nadawcy, 
    # ponieważ klient (rysujący) ignoruje własne wiadomości `draw_line` (nie jest to wymagane, 
    # ale jest bezpieczne, gdyż rysujący już ma to narysowane lokalnie).
    
    # Używamy `include_self=False` w emit do pokoju, aby rysujący nie dostawał swoich danych z powrotem,
    # co jest optymalniejsze i zapobiega podwójnemu rysowaniu/migotaniu.
    emit('draw_line', {
        'x1': data['x1'], 
        'y1': data['y1'],
        'x2': data['x2'], 
        'y2': data['y2'],
        'color': data['color'],
        'width': data['width']
    }, room=room_name, include_self=False)


@socketio.on('clear_canvas')
def handle_clear_canvas(data):
    """Przekazuje polecenie czyszczenia płótna do wszystkich graczy w pokoju gry."""
    game_id_raw = data.get('game_id')
    
    try:
        game_id = int(game_id_raw)
    except (ValueError, TypeError):
        return
        
    room_name = f"game_{game_id}"
    
    # Emitujemy polecenie do wszystkich W POKOJU, z wyłączeniem nadawcy (rysującego).
    emit('clear_drawing', {}, room=room_name, include_self=False)
    
    
# 🟢 NOWA FUNKCJA POMOCNICZA: Zarządzanie usuwaniem pustych gier
def _cleanup_empty_game(game):
    """Usuwa grę z bazy danych, jeśli nie ma w niej graczy i powiadamia o tym lobby."""
    
    # Liczenie graczy
    player_count = Player.query.filter_by(game_id=game.id).count()
    
    if player_count == 0:
        game_id = game.id
        game_name = game.name
        
        # 1. Usuń grę
        db.session.delete(game)
        db.session.commit()
        
        print(f"INFO: Usunięto pustą grę: ID {game_id}, Nazwa: {game_name}")
        
        # 2. Emituj zdarzenie do CAŁEGO SERWERA, by lobby się odświeżyło
        # Używamy `broadcast=True` bez pokoju, aby dotrzeć do wszystkich podłączonych do SocketIO
        socketio.emit('game_deleted', {'game_id': game_id}, broadcast=True)
        
        return True # Gra została usunięta
    return False # Gra nie została usunięta