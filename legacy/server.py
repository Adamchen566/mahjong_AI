from flask import Flask, request  # 只从 flask 导入 request
from flask_socketio import SocketIO, join_room, emit

app = Flask(__name__, static_folder='static')
socketio = SocketIO(app, cors_allowed_origins="*")

rooms = {}

@app.route('/')
def index():
    return app.send_static_file('index.html')

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    if room not in rooms:
        rooms[room] = []
    sid = request.sid  # 这个 sid 只在 socketio 事件里用是没问题的
    if sid not in rooms[room]:
        rooms[room].append(sid)
    emit('player_joined', {'players': rooms[room]}, room=room)

@socketio.on('action')
def on_action(data):
    room = data['room']
    emit('game_update', data, room=room)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
