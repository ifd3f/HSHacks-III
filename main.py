from flask import Flask, render_template, request
from flask_socketio import SocketIO

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

	def get_pos(self):
		return self.body.position

class GameRoom:
	
	def __init__(self, players):
		super(GameRoom, self).__init__()
		self.players = players[:]
		self.space = pymunk.Space()
	
	def update(self, dt):
		self.space.step(dt)

	def getEncodedPositions(self, dt):
		return {
			player.id: player.get_pos()
			for player in self.players
		}

	def createPlayer(self, socket_sid):
		body = pymunk.Body(PLAYER_MASS, 1666)
		print(offsetBox(0, 60, 60, 30))
		front_physical = pymunk.Poly.create_box(body, offsetBox(0, 60, 60, 30), radius=1.0)
		front_physical.elasticity = 1.5
		back_physical = pymunk.Poly.create_box(body, offsetBox(0, 0, 60, 90), radius=1.0)
		back_physical.elasticity = 3.0
		back_sensor = pymunk.Poly.create_box(body, offsetBox(0, 0, 70, 100), radius=1.0) 
		back_sensor.contact = True
		space.add(body, front_physical)
		space.add(body, back_physical)
		space.add(body, back_sensor)
		self.players.append(Player(socket_sid, self, body))


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

socketio = SocketIO(app)

@socketio.on('connect')
def on_connect():
	currentSocketId = request.sid
	room.createPlayer(currentSocketId)


if __name__ == '__main__':
	room = GameRoom([])
	socketio.run(app)