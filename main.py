import math
import random
import threading
import time

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, send

import pymunk
from pymunk.vec2d import Vec2d


TIMEOUT = 3
BOOST_DURATION = 1.5
BOOST_COOLDOWN = 5
BOOST_FORCE = 50.0
NORMAL_FORCE = 25.0
FRICTION = 20
BOOST_MAX_SPEED = 600
BRAKE_MAX_SPEED = 100
MAX_SPEED = 250.0
MIN_SPEED = 5
PLAYER_MASS = 1.0

ARENA_WIDTH = 1000
ARENA_HEIGHT = 500
ARENA_THICKNESS = 100

# Collision detection types
TRUCK_PLOW_TYPE = 100
TRUCK_CORE_TYPE = 101


class Player:

	def __init__(self, sid, room, body, living=True):
		self.sid = sid
		self.room = room
		self.body = body
		self.living = living

		self.began_boost = 0
		self.braking = False

	def get_pos(self):
		return self.body.position

	def is_boosting(self):
		return self.began_boost + BOOST_DURATION > time.time()

	def get_percent(self):
		if self.is_boosting():
			return 1 - min(1, (time.time() - self.began_boost) / BOOST_DURATION)
		else:
			return min(1, (time.time() - (self.began_boost + BOOST_DURATION)) / BOOST_COOLDOWN)

	@property
	def rotation(self):
		return self.body.angle

	@rotation.setter
	def rotation(self, val):
		self.body.angle = val


class GameRoom:
	
	def __init__(self, players):
		super(GameRoom, self).__init__()
		self.players = players[:]
		self.space = pymunk.Space()

	def init(self):
		
		# Create collision handler
		handler = self.space.add_collision_handler(TRUCK_PLOW_TYPE, TRUCK_CORE_TYPE)
		def begin(arbiter, space, data):
			plow, truck = arbiter.shapes # Between a plow and the core
			truck.body.player.living = False
			return True
		handler.begin = begin

		# Create borders
		body = pymunk.Body(body_type=pymunk.Body.STATIC)
		shapes = [
			pymunk.Poly(body, offsetBox(ARENA_WIDTH/2, 						-ARENA_THICKNESS/2, 					ARENA_WIDTH + 2*ARENA_THICKNESS, 	ARENA_THICKNESS)),
			pymunk.Poly(body, offsetBox(ARENA_WIDTH/2, 						ARENA_HEIGHT + ARENA_THICKNESS, 		ARENA_WIDTH + 2*ARENA_THICKNESS, 	ARENA_THICKNESS)),
			pymunk.Poly(body, offsetBox(-ARENA_THICKNESS/2, 				ARENA_HEIGHT/2, 						ARENA_THICKNESS, 					ARENA_HEIGHT + 2*ARENA_THICKNESS)),
			pymunk.Poly(body, offsetBox(ARENA_WIDTH + ARENA_THICKNESS/2,	ARENA_HEIGHT/2 + ARENA_THICKNESS/2, 	ARENA_THICKNESS, 					ARENA_HEIGHT + 2*ARENA_THICKNESS))			
		]
		self.space.add(body, *shapes)

	def update(self, dt, socketio):

		for p in self.players:
			force = (BOOST_FORCE if p.is_boosting() else NORMAL_FORCE) * Vec2d.unit()
			force.angle = p.rotation
			if p.living:
				p.body.velocity += force/p.body.mass
				p.body.angular_velocity = 0

		for body in self.space.bodies:
			speed = body.velocity.get_length()
			if speed > 0:
				fricDir = -body.velocity.normalized()
				fricAmount = body.mass * FRICTION
				frictionForce = fricDir * fricAmount * dt
				if speed < MIN_SPEED:
					body.velocity = Vec2d.zero()
				else:
					body.velocity += frictionForce/body.mass
			if body.velocity.get_length() > MAX_SPEED:
				if body.player.is_boosting():
					max_speed = BOOST_MAX_SPEED
				elif body.player.braking:
					max_speed = BRAKE_MAX_SPEED
				else:
					max_speed = MAX_SPEED
				body.velocity = max_speed * body.velocity.normalized()

		self.space.step(dt)
		socketio.emit('entities', self.getEncodedPositions())

	def getEncodedPositions(self):
		return [
			{
				'id': player.sid,
				'x': player.get_pos().x,
				'y': player.get_pos().y,
				'living': player.living,
				'direction': player.rotation,
				'isBoosting': player.is_boosting(),
				'boostRemaining': player.get_percent(),
			} for player in self.players
		]

	def player_by_sid(self, sid):
		for p in self.players:
			if p.sid == sid:
				return p
		return None

	def createPlayer(self, socket_sid):

		body = pymunk.Body(PLAYER_MASS, 1666)

		front_physical = pymunk.Poly(body, offsetBox(5, 0, 10, 20), radius=5.0)
		front_physical.elasticity = 1.5
		front_physical.collision_type = TRUCK_PLOW_TYPE

		back_physical = pymunk.Poly(body, offsetBox(-15, 0, 30, 20), radius=5.0)
		back_physical.elasticity = 5.0
		back_physical.collision_type = TRUCK_CORE_TYPE

		back_sensor = pymunk.Poly(body, offsetBox(-15, 0, 40, 30), radius=5.0) 
		back_sensor.sensor = True

		body.position = ARENA_WIDTH*random.random(), ARENA_HEIGHT*random.random()
		body.angle = 2*math.pi*random.random()

		self.space.add(body, front_physical, back_physical, back_sensor)
		player = Player(socket_sid, self, body)
		self.players.append(player)
		body.player = player

	def removePlayer(self, sid):
		for p in self.players:
			if p.sid == sid:
				self.space.remove(p.body, *p.body.shapes)
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


app = Flask(__name__)

players = []

room = None

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
	emit('hello', {'id': sid})

@socketio.on('disconnect')
def on_disconnect():
	sid = request.sid
	room.removePlayer(sid)

@socketio.on('direction')
def on_direction(data):
	player = room.player_by_sid(request.sid)
	if player.living:
		player.rotation = data['angle']

@socketio.on('boost')
def on_boost(data):
	player = room.player_by_sid(request.sid)
	if time.time() - player.began_boost > BOOST_COOLDOWN:
		player.began_boost = time.time()

@socketio.on('brake')
def on_brake(data):
	player = room.player_by_sid(request.sid)
	player.braking = data['brake']

@socketio.on('ping')
def on_ping(data):
	print('pong')
	pass

if __name__ == '__main__':
	room = GameRoom([])
	webserver = threading.Thread(target=lambda: socketio.run(app, host='0.0.0.0'))
	webserver.start()
	room.init()
	while True:
		room.update(0.05, socketio)
		time.sleep(0.05)
