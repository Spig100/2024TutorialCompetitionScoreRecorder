from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room, ConnectionRefusedError
from flask_login import LoginManager, UserMixin, login_user, current_user, login_required, logout_user
from threading import Timer
from module.match import Match, recorderIdToObjectNameTable
from module.db_operator import DBOperator
from module.utils import get_nested_attribute, set_nested_attribute
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

login_manager = LoginManager()
login_manager.init_app(app)

match = Match()

db = DBOperator()

# users = {
#     'admin': {
#         'password': 'admin',
#         'role': '0',
#         'alliance': 'admin'
#     },
#     'r1': {
#         'password': '1',
#         'role': '1',
#         'alliance': 'red'
#     },
#     'r2': {
#         'password': '1',
#         'role': '1',
#         'alliance': 'red'
#     },
#     'b1': {
#         'password': '1',
#         'role': '1',
#         'alliance': 'blue'
#     },
#     'b2': {
#         'password': '1',
#         'role': '1',
#         'alliance': 'blue'
#     }
# }


# def debug_decorator(func):
#     def wrapper(*args, **kwargs):
#         print("function", func.__name__, "called")
#         print("args", *args)
#         print("kwargs", **kwargs)
#         return func(*args, **kwargs)
#     return wrapper

debug_counter = 0


def debug_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        global debug_counter
        debug_counter += 1
        # print("------------------------------------")
        print("function", func.__name__, "called", debug_counter)
        # print("args", *args)
        # print("kwargs", **kwargs)
        re = func(*args, **kwargs)
        print("function", func.__name__, "end", debug_counter)
        # print("------------------------------------")
        return re
    return wrapper


class User(UserMixin):
    pass


@login_manager.user_loader
@debug_decorator
def user_loader(username):
    """  
 設置二： 透過這邊的設置讓flask_login可以隨時取到目前的使用者id   
 :param email:官網此例將email當id使用，賦值給予user.id    
 """
    print("user_loader", username)
    # usernames = db.get_all_username()
    usernames = ["r1", "r2", "b1", "b2"]
    if not username in usernames:
        return None
    print("get_user_start")
    user_info = db.get_user(username)
    print("get_user_end")

    user = User()
    user.id = user_info[1]
    user.role = user_info[3]
    user.alliance = user_info[4]

    return user


@login_manager.unauthorized_handler
@debug_decorator
def unauthorized_callback():
    print("request.path", request.path)
    return redirect(url_for("login"))
    # return redirect('/login?next=' + request.path)


@app.route('/login', methods=['GET', 'POST'])
@debug_decorator
def login():
    """  
 官網git很給力的寫了一個login的頁面，在GET的時候回傳渲染     
 """
    if request.method == 'GET':
        return render_template('login.html')

    username = request.form['account']
    password = request.form['password']

    result = db.login_query(username, password)
    if not result:
        return render_template('login.html', wrong_account_or_password=True)

    #  實作User類別
    user = User()
    user.id = result[0][1]
    user.role = result[0][3]
    user.alliance = result[0][4]

    login_user(user)

    return redirect(url_for('index'))


@app.route('/logout')
@debug_decorator
def logout():
    """  
 logout\_user會將所有的相關session資訊給pop掉 
 """
    logout_user()
    # return 'Logged out'
    return redirect(url_for('index'))


@app.route('/')
@debug_decorator
def index():
    return redirect(url_for("counter"))


@app.route('/counter')
@login_required
@debug_decorator
def counter():
    return render_template("counter.html")


@app.route('/scoreboard')
@debug_decorator
def scoreboard():
    return render_template("scoreboard.html")


@app.route('/simpleManagement')
@debug_decorator
def simpleManagement():
    print(db.get_matches_info())
    return render_template("simpleManagement.html", matches_info=db.get_matches_info())


@app.route('/management')
@debug_decorator
def control():
    if int(current_user.role) > 0:
        return "", 403
    return render_template("management.html")


@app.route('/test')
@debug_decorator
def test():
    return render_template("login copy.html")
    # return render_template("test2.html")


@app.route('/test2')
@debug_decorator
def test2():
    return render_template("test2.html")


@debug_decorator
def sync_match_info(alliance):
    socketio.emit('sync_match_info', {
        "matchLevel": match.level,
        "matchNumber": match.id,
        "matchState": match.state,
        "alliance": alliance,
        "team1": match.alliance[alliance].team1,
        "team2": match.alliance[alliance].team2,
    }, to=alliance)


@socketio.on('connect')
@debug_decorator
def connect():
    if not current_user.is_authenticated:
        raise ConnectionRefusedError('unauthorized!')

    print("connected", match.state)
    join_room(current_user.alliance)
    if current_user.role == 1:
        match.recorder.add(request.sid)
    # sync_match_info(current_user.alliance)
    emit('sync_match_info', {
        "matchLevel": match.level,
        "matchNumber": match.id,
        "matchState": match.state,
        "alliance": current_user.alliance,
        "team1": match.alliance[current_user.alliance].team1,
        "team2": match.alliance[current_user.alliance].team2,
    })
    emit('update_value', {
        "from": "host",
        "data": match.get_all_recorder_data(current_user.alliance)
    })


@socketio.on('disconnect')
@debug_decorator
def disconnect():
    if current_user.role == 1:
        match.recorder.remove(request.sid)
        if request.sid in match.commitedRecorder:
            match.commitedRecorder.remove(request.sid)


@socketio.on('update_value')
@debug_decorator
def update_score(msg):
    emit('update_value', msg, to=current_user.alliance)
    for data in msg["data"]:
        attr_name = current_user.alliance + "." + \
            recorderIdToObjectNameTable[data["id"]]
        set_nested_attribute(match, attr_name, data["value"])
    match.countScore()
    print(match.red.score)


@socketio.on('commit')
@debug_decorator
def commit(msg):
    match.commitedRecorder.add(request.sid)
    print(match.recorder)
    print(match.commitedRecorder)
    print(match.allCommited)
    if match.allCommited:
        match.state = "All Commited"
        db.change_match_state(match.level, match.id, match.state)
        socketio.emit('all_commited', {
                      "level": match.level, "id": match.id}, namespace='/management')
        return


@socketio.on('sync_match_state', namespace='/management')
@debug_decorator
def sync_match_state():
    emit('sync_match_state', match.state)


@socketio.on('load_match', namespace='/management')
@debug_decorator
def load_match(data):
    match.reset()
    match_data = db.load_match_data(data["level"], data["id"])
    print(match_data)
    match.loadMatch(match_data)
    match.state = "Preparing"
    db.change_match_state(match.level, match.id, match.state)
    db.reset_other_loaded_match_state(match.level, match.id)
    sync_match_info("red")
    sync_match_info("blue")


@socketio.on('start_match', namespace='/management')
@debug_decorator
def start_match(data):
    global gameTimer
    if match.state != "Preparing":
        emit('wrong_state', 'Match is not in preparing state')
        print("wrong state")
        return
    if data["level"] != match.level or int(data["id"]) != match.id:
        emit('wrong_match', 'Match level or number is not correct')
        print("wrong match")
        print(data["level"], match.level, data["id"], match.id)
        return
    match.state = "Running"
    db.change_match_state(match.level, match.id, match.state)
    # emit('match_start', brocast=True)
    socketio.emit('match_start')
    emit('match_start', namespace='/management')
    gameTimer = Timer(10, end_match)
    gameTimer.start()
    print("match started")


@socketio.on('interrupt_match', namespace='/management')
@debug_decorator
def match_interrupted(data):
    global gameTimer
    gameTimer.cancel()
    match.state = "Interrupted"
    db.change_match_state(match.level, match.id, match.state)
    socketio.emit('match_interrupted')
    socketio.emit('match_interrupted', {"level": match.level,
                  "id": match.id}, namespace='/management')
    match.reset()


@debug_decorator
def end_match():
    match.state = "Ended"
    db.change_match_state(match.level, match.id, match.state)
    socketio.emit('match_end')
    socketio.emit('match_end', {"level": match.level,
                  "id": match.id}, namespace='/management')
    # match.reset()


@socketio.on('save_and_show', namespace='/management')
@debug_decorator
def save_and_show(data):
    match.state = "Saved"
    db.change_match_state(match.level, match.id, match.state)
    # TODO: save match data to database
    # match_result = match.get_result()
    # socketio.emit('show_result', match_result, to="board")
    # tmp = match_result.copy()
    # dict_style_data = match.get_dict_style_data()
    # tmp.update(dict_style_data)
    # db.save_match_data(tmp)
    print("\n\n\nsimulated save and show\n\n\n")


if __name__ == '__main__':
    app.debug = True
    socketio.run(app, host='0.0.0.0', port=5000)
