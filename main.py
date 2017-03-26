import math
import threading
import time

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, send

import pymunk

app = Flask(__name__)

players = []

room = None

BOOST_FORCE = 20
NORMAL_FORCE = 5
BRAKE_FRICTION = 0.1
NORMAL_FRICTION = 0.75
PLAYER_MASS = 1


class Vector:

	def __init__(self, x, y):
		self.x = x
		self.y = y

	def __add__(self, other):
		return Vector(self.x + other.x, self.y + other.y)

	def __sub__(self, other):
		return Vector(self.x - other.x, self.y - other.y)

	def __mul__(self, other):
		return Vector(self.x * other.x, self.y * other.y)

	def __truediv__(self, other):
		return Vector(self.x / other.x, self.y / other.y)

	def __abs__(self):
		return (self.x**2 + self.y**2)**0.5

	def __iter__(self, other):
		yield this.x
		yield this.y

class Player:

	def __init__(self, socket_id, room, body):
		self.socket_id = socket_id
		self.room = room
		self.body = body

		self.boosting = False
		self.boost_left = 3
		self.braking = False

	def get_pos(self):
		return self.body.position

	def get_rot(self):
		return self.body.angle

class GameRoom:
	
	def __init__(self, players):
		super(GameRoom, self).__init__()
		self.players = players[:]
		self.space = pymunk.Space()
	
	def update(self, dt, socketio):
		#self.space.step(dt)
		socketio.emit('entities', self.getEncodedPositions(), callback=lambda: print('asdf'))

	def getEncodedPositions(self):
		return [
			{
				'id': player.socket_id,
				'x': player.get_pos().x,
				'y': player.get_pos().y,
				'direction': player.get_rot(),
				'isBoosting': player.boosting,
				'boostRemaining': player.boost_left
			} for player in self.players
		]

	def player_by_sid(self, sid):
		for p in self.players:
			if p.socket_id == sid:
				return sid
		return None

	def createPlayer(self, socket_sid):
		body = pymunk.Body(PLAYER_MASS, 1666)
		front_physical = pymunk.Poly(body, offsetBox(0, 60, 60, 30), radius=5.0)
		front_physical.elasticity = 1.5
		back_physical = pymunk.Poly(body, offsetBox(0, 0, 60, 90), radius=5.0)
		back_physical.elasticity = 3.0
		back_sensor = pymunk.Poly(body, offsetBox(0, 0, 70, 100), radius=5.0) 
		back_sensor.contact = True
		self.space.add(body, front_physical, back_physical, back_sensor)
		self.players.append(Player(socket_sid, self, body))

	def removePlayer(self, sid):
		for p in self.players:
			if p.socket_id == sid:
				for s in p.body.shapes:
					self.space.remove(s)
				self.space.remove(p.body)
				self.players.remove(p)
				return

def offsetBox(cx, cy, length, width):
	hl = length / 2
	hw = width / 2
	x1 = float(cx - hl)
	x2 = float(cx + hl)
	y1 = float(cy - hw)
	y2 = float(cy + hw)
	return [(x1, y1), (x1, y2), (x2, y2), (x2, y1)]


@app.route('/')
def index():
	return render_template('index.html')

@app.route('/game')
def game():
	return render_template('game.html')

socketio = SocketIO(app)

@socketio.on('connect')
def on_connect():
	sid = request.sid
	room.createPlayer(sid)

@socketio.on('disconnect')
def on_disconnect():
	sid = request.sid
	room.removePlayer(sid)

@socketio.on('direction')
def on_direction(data):
	pass

@socketio.on('boost')
def on_boost(data):
	print(data)
	send('asdf')

@socketio.on('brake')
def on_boost(data):
	pass


if __name__ == '__main__':
	room = GameRoom([])
	def game_update_loop():
		while True:
			room.update(0.05, socketio)
			print('asdf')
			time.sleep(1)
	game_updater = threading.Thread(target=game_update_loop)
	web_server = threading.Thread(target=lambda: socketio.run(app, host='0.0.0.0'))
	web_server.start()
	game_updater.start()
	#web_server.join()
	