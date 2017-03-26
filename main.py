import asyncio
import math
import random
import string
import threading
import time

import flask
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, send, join_room

import pymunk
from pymunk.vec2d import Vec2d


# How long between pings before a player is considered disconnected
TIMEOUT = 10 # NYI

# Physics parameters
UPDATE_PERIOD = 0.025
BOOST_DURATION = 1.5
BOOST_COOLDOWN = 5

BOOST_FORCE = 50.0
NORMAL_FORCE = 25.0

FRICTION = 20

BOOST_MAX_SPEED = 600
BRAKE_MAX_SPEED = 100
DEAD_MAX_SPEED = 1500
MAX_SPEED = 250.0
MIN_SPEED = 5

PLAYER_MASS = 1.0

# Dimensions
ARENA_WIDTH = 1000
ARENA_HEIGHT = 500
ARENA_THICKNESS = 100

TRUCK_PLOW_WIDTH = 30
TRUCK_PLOW_LENGTH = 20
TRUCK_BODY_SPACING = 0 	# How much empty space between the plow and the body
TRUCK_BODY_WIDTH = 10
TRUCK_BODY_LENGTH = 30

# Collision detection types
TRUCK_PLOW_TYPE = 100
TRUCK_CORE_TYPE = 101
ARENA_BORDER_TYPE = 102
DEAD_BODY_TYPE = 103

# Matchmaking Parameters
PEOPLE_PER_GAME = 3 # TODO: CHANGE THIS BACK WHEN DONE DEBUGGING
ROOM_NAME_LENGTH = 16
TOKEN_LENGTH = 8


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

	def get_boost_level(self):
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
	
	def __init__(self):
		super(GameRoom, self).__init__()
		self.players = []
		self.space = pymunk.Space()
		self.room_name = randomString(ROOM_NAME_LENGTH)

	def init(self):
		
		# Create collision handler
		## Between a plow and a truck body
		pb_handler = self.space.add_collision_handler(TRUCK_PLOW_TYPE, TRUCK_CORE_TYPE)
		db_handler = self.space.add_collision_handler(DEAD_BODY_TYPE, TRUCK_CORE_TYPE)
		def kill_pre_solve(arbiter, space, data): 
			plow, truck = arbiter.shapes 	 # Extract the shapes
			for s in truck.body.shapes:
				s.collision_type = DEAD_BODY_TYPE
			if truck.body.player.living:	 # If he is alive
				truck.body.player.living = False # Kill the guy that got t-boned
				socketio.emit('death', {}, namespace='/game', room=truck.body.player.sid) # And tell him he died
				'''living = self.stillLiving()
				print(living)
				if (len(living) == 1):
					socketio.emit('gg', {"winner": living[0].sid}, namespace='/game', room=truck.body.player.sid);
				elif (len(living) <= 0):
					socketio.emit('gg', {"winner": "No one won rip gg m80s"}, namespace='/game', room=truck.body.player.sid);'''

			return True # Then let his body fly across the map stupidly fast
		pb_handler.pre_solve = kill_pre_solve
		db_handler.pre_solve = kill_pre_solve

		## Between the arena and a dead player
		ad_handler = self.space.add_collision_handler(ARENA_BORDER_TYPE, DEAD_BODY_TYPE)
		def ad_pre_solve(arbiter, space, data):
			arbiter.restitution = 0.1 # Dead players shouldn't be flying around that fast...
			return True
		ad_handler.pre_solve = ad_pre_solve


		# Create borders
		body = pymunk.Body(body_type=pymunk.Body.STATIC)
		shapes = [
			pymunk.Poly(body, offsetBox(ARENA_WIDTH/2 ,						-ARENA_THICKNESS/2,	 				ARENA_WIDTH + 2*ARENA_THICKNESS, 	ARENA_THICKNESS)),
			pymunk.Poly(body, offsetBox(ARENA_WIDTH/2 ,						ARENA_HEIGHT + 3*ARENA_THICKNESS/4, ARENA_WIDTH + 2*ARENA_THICKNESS, 	ARENA_THICKNESS)),
			pymunk.Poly(body, offsetBox(-ARENA_THICKNESS/2,					ARENA_HEIGHT/2,						ARENA_THICKNESS, 					ARENA_HEIGHT + 2*ARENA_THICKNESS)),
			pymunk.Poly(body, offsetBox(ARENA_WIDTH + 3*ARENA_THICKNESS/4,	ARENA_HEIGHT/2,						ARENA_THICKNESS, 					ARENA_HEIGHT + 2*ARENA_THICKNESS))			
		]
		for s in shapes:
			s.elasticity = 0.8
			s.collision_type = ARENA_BORDER_TYPE
		self.space.add(body, *shapes)

	'''def stillLiving(self):
		living = []
		for player in self.players:
			if (player.living):
				living.append(player)

		return living'''

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
				if not body.player.living:
					max_speed = DEAD_MAX_SPEED
				elif body.player.is_boosting():
					max_speed = BOOST_MAX_SPEED
				elif body.player.braking:
					max_speed = BRAKE_MAX_SPEED
				else:
					max_speed = MAX_SPEED
				body.velocity = max_speed * body.velocity.normalized()

		self.space.step(dt)

		socketio.emit('entities', self.getEncodedPositions(), namespace='/game', room=self.room_name)

	def getEncodedPositions(self):
		return [
			{
				'id': player.sid,
				'x': player.get_pos().x,
				'y': player.get_pos().y,
				'living': player.living,
				'direction': player.rotation,
				'isBoosting': player.is_boosting(),
				'boostLevel': player.get_boost_level(),
			} for player in self.players
		]

	def player_by_sid(self, sid):
		for p in self.players:
			if p.sid == sid:
				return p
		return None

	def createPlayer(self, socket_sid):

		body = pymunk.Body(PLAYER_MASS, 1666)

		front_physical = pymunk.Poly(body, offsetBox(TRUCK_PLOW_LENGTH/2 - TRUCK_BODY_SPACING/2, 0, TRUCK_PLOW_LENGTH, TRUCK_PLOW_WIDTH), radius=2.0)
		front_physical.elasticity = 1.5
		front_physical.collision_type = TRUCK_PLOW_TYPE

		back_physical = pymunk.Poly(body, offsetBox(-TRUCK_BODY_LENGTH/2 - TRUCK_BODY_SPACING/2, 0, TRUCK_BODY_LENGTH - TRUCK_BODY_SPACING, TRUCK_BODY_WIDTH), radius=2.0)
		back_physical.elasticity = 5.0
		back_physical.collision_type = TRUCK_CORE_TYPE

		body.position = ARENA_WIDTH*random.random(), ARENA_HEIGHT*random.random()
		body.angle = 2*math.pi*random.random()

		self.space.add(body, front_physical, back_physical)
		player = Player(socket_sid, self, body)
		self.players.append(player)
		body.player = player

	def removePlayer(self, sid):
		for p in self.players:
			if p.sid == sid:
				self.space.remove(p.body, *p.body.shapes)
				self.players.remove(p)
				return


class RoomThread(threading.Thread):
	
	def __init__(self, room):
		super().__init__()
		self.room = room

	def run(self):
		self.room.init()
		while True:
			self.room.update(UPDATE_PERIOD, socketio)
			time.sleep(UPDATE_PERIOD)		


def offsetBox(cx, cy, length, width):
	hl = length / 2
	hw = width / 2
	x1 = float(cx - hl)
	x2 = float(cx + hl)
	y1 = float(cy - hw)
	y2 = float(cy + hw)
	return [(x1, y1), (x1, y2), (x2, y2), (x2, y1)]


def randomString(n):
	return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(n))

async def lobby_manager(socketio):
	while True:  # Every 2 seconds
		socketio.emit('ping', {}, namespace='/lobby')
		while len(searching) >= PEOPLE_PER_GAME:  # If there are enough people for a game
			room = GameRoom()	# Create a new room
			rooms[room.room_name] = room
			for _ in range(0, PEOPLE_PER_GAME): # For each person
				token = randomString(TOKEN_LENGTH) # Generate a token for each person
				tokens[token] = room.room_name # Link the token to the room
				sid = searching.pop(0)
				socketio.emit('found', {'token': token}, namespace='/lobby', room=sid) # Tell the client the token
		await asyncio.sleep(2)

app = Flask(__name__)

searching = []
tokens = {} # token: room_name
rooms = {}  # room_name: room
client2room = {}

@app.route('/')
@app.route('/lobby')
def index():
	return render_template('index.html')

@app.route('/game', methods=['POST'])
def game():
	try:
		token = request.form['token']
		room_name = tokens[token]
		del tokens[token]
		return render_template('game.html', room=room_name)
	except KeyError:
		flask.abort(403)

socketio = SocketIO(app)

@socketio.on('connect', namespace='/game')
def on_connect():  # Request the player to send the room name
	emit('gibroomname', {})

@socketio.on('room_name', namespace='/game')
def on_room_name(data):  # Initialize the room
	sid = request.sid
	join_room(data['room_name'])
	room = rooms[data['room_name']]
	room.createPlayer(sid)
	client2room[sid] = room
	emit('hello', {'id': sid})
	if len(room.players) >= PEOPLE_PER_GAME:
		RoomThread(room).start()

@socketio.on('disconnect', namespace='/game')
def on_disconnect():
	sid = request.sid
	room = client2room[sid]

@socketio.on('direction', namespace='/game')
def on_direction(data):
	room = client2room[request.sid]
	player = room.player_by_sid(request.sid)
	if player.living:
		player.rotation = data['angle']

@socketio.on('boost', namespace='/game')
def on_boost(data):
	room = client2room[request.sid]
	player = room.player_by_sid(request.sid)
	if time.time() - player.began_boost > BOOST_COOLDOWN:
		player.began_boost = time.time()

@socketio.on('brake', namespace='/game')
def on_brake(data):
	room = client2room[request.sid]
	player = room.player_by_sid(request.sid)
	player.braking = data['brake']

@socketio.on('ping', namespace='/game')
def on_ping(data):
	pass

@socketio.on('ping', namespace='/lobby')
def on_lobby_ping(data):
	pass

@socketio.on('search', namespace='/lobby')
def on_search(data):
	if data['running']:
		searching.append(request.sid)
	else:
		try:
			searching.remove(request.sid)
		except ValueError:
			pass
	socketio.emit('update', {'people': len(searching)}, namespace='/lobby')

if __name__ == '__main__':
	webserver = threading.Thread(target=lambda: socketio.run(app, host='0.0.0.0'))
	webserver.start()
	loop = asyncio.get_event_loop()
	asyncio.async(lobby_manager(socketio))
	loop.run_forever()
