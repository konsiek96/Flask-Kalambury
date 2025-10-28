from app import create_app, socketio

app = create_app()

if __name__ == '__main__':
    # Ważne: używamy socketio.run(), a nie app.run()
    socketio.run(app, host='0.0.0.0', port=5000)
