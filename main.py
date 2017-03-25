import flask

app = flask.Flask(__name__)

@app.route('/')
def index():
	return flask.render_template('home.html')

@app.route('/game')
def game():
	return flask.render_template('game.html')

if __name__ == '__main__':
	app.run()