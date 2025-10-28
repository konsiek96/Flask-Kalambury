# test_logic.py

from app.models import Game, Player, Word
# Zaimportuj model 'connected_players' jeśli jest zdefiniowany globalnie
from app.sockets import connected_players 
from app import socketio
import time

# --- Testy Modeli ---

def test_model_creation(db_session):
    """Sprawdza, czy obiekty Game i Player są poprawnie tworzone z domyślnymi wartościami."""
    # 1. Stworzenie słowa
    word = Word(text="TEST_HASLO")
    db_session.session.add(word)
    db_session.session.commit()
    assert Word.query.count() == 1
    
    # 2. Stworzenie gry
    game = Game(name="TestGame", creator="Tester", round_time=60)
    db_session.session.add(game)
    db_session.session.commit()
    assert game.name == "TestGame"

    # 3. Stworzenie gracza
    player = Player(username="Player1", game_id=game.id)
    db_session.session.add(player)
    db_session.session.commit()
    assert player.username == "Player1"
    assert player.score == 0
    assert len(game.players) == 1

# --- Test Losowania Słów i Startu Gry ---

def test_start_game_word_picking(db_session, socket_client):
    """Testuje, czy gra jest poprawnie rozpoczynana i słowo jest emitowane tylko do rysującego."""
    # Setup: Utwórz grę, gracza i słowo
    word = Word(text="STARTOWE_SLOWO")
    db_session.session.add(word)
    game = Game(name="StartGame", creator="Drawer", round_time=30)
    
    # W pierwszej kolejności dodaj grę do sesji i zrób commit, aby uzyskać game.id
    db_session.session.add(game)
    db_session.session.commit()
    
    # Teraz utwórz gracza z poprawnym game_id
    player = Player(username="Drawer", game_id=game.id)
    db_session.session.add(player)
    game.current_drawer = player # Ustawienie gracza jako rysującego
    db_session.session.commit() # Drugi commit, aby zapisać current_drawer
    
    game_id = game.id
    sid = socket_client.eio_sid
    
    # 🟢 KLUCZOWA ZMIANA 1: Symulacja dołączenia do pokoju Socket.IO
    # Wysłanie eventu 'join' wywoła handler handle_join w sockets.py, który użyje join_room().
    socket_client.emit('join_game', {'game_id': game_id, 'username': "Drawer"})
    
    # Mapowanie SID klienta testowego do gracza (wymagane przez handle_start_game)
    connected_players[sid] = {'username': "Drawer", 'game_id': game_id}
    
    # 🟢 KLUCZOWA ZMIANA 2: Wyczyść wiadomości, które przyszły po 'join'
    # (np. system_message, że gracz dołączył), aby nie zakłócały testu
    socket_client.get_received()
    
    # Akcja: Wyślij zdarzenie start_game
    socket_client.emit('start_game', {'game_id': game_id})

    # Aserty 1: Sprawdzenie wiadomości odebranych przez klienta (rysującego)
    received = socket_client.get_received()
    
    # Powinien otrzymać 'your_word'
    your_word_event = next((e for e in received if e['name'] == 'your_word'), None)
    assert your_word_event is not None
    assert your_word_event['args'][0]['word'] == "STARTOWE_SLOWO"
    assert your_word_event['args'][0]['round_time'] == 30

    # Powinien otrzymać 'game_started' (emitowane do wszystkich)
    game_started_event = next((e for e in received if e['name'] == 'game_started'), None)
    assert game_started_event is not None
    assert game_started_event['args'][0]['drawer'] == "Drawer"
    assert game_started_event['args'][0]['word_length'] == len("STARTOWE_SLOWO")
    
    # Aserty 2: Sprawdzenie bazy danych
    updated_game = Game.query.get(game_id)
    assert updated_game.current_word == "STARTOWE_SLOWO"

def test_drawing_data_emission(db_session, socket_client, app):
    """Testuje, czy dane rysowania są poprawnie emitowane do innych klientów w pokoju."""
    game = Game(name="DrawTest", creator="Test", round_time=60)
    db_session.session.add(game)
    db_session.session.commit()
    game_id = game.id  # Użyj ID, które zostało faktycznie nadane
    # Setup: Konieczne dołączenie klientów do pokoju
    client2 = socketio.test_client(app)
    socket_client.emit('join_game', {'game_id': game_id, 'username': 'Rysujacy'}) 
    client2.emit('join_game', {'game_id': game_id, 'username': 'Zgadywacz'}) 
    
    # Wyczyść wiadomości systemowe po dołączeniu
    socket_client.get_received() 
    client2.get_received() 

    # Dane rysowania (muszą być stringi/liczby, jak w JS)
    drawing_data = {
        'game_id': game_id, 
        'x1': 10, 'y1': 20, 
        'x2': 30, 'y2': 40, 
        'color': '#000000', 
        'width': '5'
    }
    
    # Akcja: Emitowanie danych rysowania
    socket_client.emit('drawing_data', drawing_data)
    
    # Aserty 1: Klient 2 (zgadujący) powinien otrzymać 'draw_line'
    received_client2 = client2.get_received()
    draw_line_event = next((e for e in received_client2 if e['name'] == 'draw_line'), None)
    assert draw_line_event is not None
    
    # Sprawdzenie, czy dane są zgodne
    assert draw_line_event['args'][0]['x1'] == 10
    assert draw_line_event['args'][0]['color'] == '#000000'

    # Aserty 2: Klient 1 (rysujący) nie powinien otrzymać danych (skip_sid)
    assert not socket_client.get_received()


def test_chat_message_and_guessing_logic(db_session, socket_client, app):
    """Testuje normalne wiadomości, próbę zgadnięcia przez rysującego i poprawne zgadnięcie."""
    # Setup: Gra z hasłem i dwoma graczami
    game = Game(name="ChatTestGame", creator="Creator", round_time=30, current_word="HASLO_DO_ZGADNIECIA")
    drawer = Player(username="Rysujacy", game_id=game.id, score=10)
    guesser = Player(username="Zgadywacz", game_id=game.id, score=0)
    db_session.session.add_all([game, drawer, guesser])
    game.current_drawer = drawer
    db_session.session.commit()
    game_id = game.id
    
    # Konfiguracja klientów
    guesser_client = socketio.test_client(app)
    guesser_client.emit('join_game', {'game_id': game_id, 'username': 'Zgadywacz'})
    socket_client.emit('join_game', {'game_id': game_id, 'username': "Drawer"})
    guesser_client.get_received()
    socket_client.get_received()
    
    # --- Test 1: Normalna Wiadomość (bez zgadnięcia) ---
    socket_client.emit('chat_message', {'username': 'Zgadywacz', 'room': game_id, 'msg': 'To jest test.'})
    
    received_drawer = socket_client.get_received()
    chat_event = next((e for e in received_drawer if e['name'] == 'chat_message'), None)
    assert chat_event is not None
    assert chat_event['args'][0]['msg'] == 'To jest test.'
    assert 'time' in chat_event['args'][0] # Sprawdzenie znacznika czasu

    # --- Test 2: Rysujący próbuje zgadnąć (ochrona) ---
    socket_client.emit('chat_message', {'username': 'Rysujacy', 'room': game_id, 'msg': 'HASLO_DO_ZGADNIECIA'})
    
    received_drawer_guess = socket_client.get_received()
    # Rysujący powinien otrzymać system_message z błędem
    assert any(e['name'] == 'system_message' and 'Nie możesz zgadywać' in e['args'][0]['msg'] for e in received_drawer_guess)
    
    # Sprawdzenie, czy punkty i runda są bez zmian
    assert Player.query.filter_by(username="Rysujacy").first().score == 10
    assert Game.query.get(game_id).current_word is not None
    
    # --- Test 3: Poprawne Zgadnięcie ---
    guesser_client.emit('chat_message', {'username': 'Zgadywacz', 'room': game_id, 'msg': 'haslo_do_ZgadNiecia'})
    time.sleep(0.05)
    db_session.session.expire_all()

    # Aserty 1: Punkty zostały naliczone
    updated_guesser = Player.query.filter_by(username="Zgadywacz").first()
    assert updated_guesser.score == 0 # Powinien dostać 1 punkt (0 -> 1)
    
    # Aserty 2: Runda się zakończyła (event 'round_ended')
    received_guesser_end = guesser_client.get_received()
    assert any(e['name'] == 'round_ended' and e['args'][0]['winner'] == 'Zgadywacz' for e in received_guesser_end)
    
    # Aserty 3: Hasło zostało wyczyszczone (rotacja)
    assert Game.query.get(game_id).current_word is None
    
    # Aserty 4: Lista graczy została zaktualizowana (emit_player_list)
    assert any(e['name'] == 'update_player_list' for e in received_guesser_end)