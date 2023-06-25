from flask import render_template, flash, redirect, url_for, request, abort, session
from flask_socketio import SocketIO, join_room, leave_room, close_room, send, emit
from chitchat import app, db, bcrypt, socketio
from chitchat.forms import LoginForm, RegistrationForm, ConnectForm, UpdateAccountForm, MessageForm
from chitchat.models import User, Room, Message
from flask_login import login_user, current_user, logout_user, login_required
import os
import secrets
from PIL import Image
from flask import current_app
from datetime import datetime
#room id current username + opponent username. In alphabetical order.
def save_picture(form_picture, quality=60, max_width=300, max_height=300):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(current_app.root_path, 'static/profile_pics', picture_fn)

    i = Image.open(form_picture)
    width, height = i.size
    ratio = min(max_width/width, max_height/height)
    new_width = int(width * ratio)
    new_height = int(height * ratio)
    i = i.resize((new_width, new_height), resample=Image.LANCZOS)
    i.save(picture_path, optimize=True, quality=quality)

    return picture_fn

@app.route('/', methods=['GET', 'POST'])
@app.route("/home")
def home():
    return render_template('home.html')

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You are now able to log in','success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('chatlist'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('Your profile has been updated!', 'success')
        return redirect('profile')
    elif request.method == "GET":
        form.username.data = current_user.username
        form.email.data = current_user.email
    image_file = url_for('static', filename='profile_pics/' + current_user.image_file)
    user = current_user
    return render_template('profile.html', title='profile', image_file=image_file, user=user, form=form)



@app.route("/chatlist", methods=["GET", "POST"])
@login_required
def chatlist():
    form = ConnectForm()
    rooms = Room.query.all()
    user_rooms = []
    opponents = []
    for room in rooms:
        if current_user.id == room.user1_id or current_user.id == room.user2_id:
            user_rooms.append(room)
    for room in user_rooms:
        if current_user.username == room.user1.username:
            opponent = User.query.filter_by(username=room.user2.username).first()
            opponent.room_id = room.id  # Add room ID to opponent object
            opponents.append(opponent)
        else:
            opponent = User.query.filter_by(username=room.user1.username).first()
            opponent.room_id = room.id  # Add room ID to opponent object
            opponents.append(opponent)

    opponents.sort(key=lambda x: x.username.lower())

    if form.validate_on_submit():
        username = form.opponent.data
        user = User.query.filter_by(username=username).first()

        if user:
            if current_user == user:
                flash("You cannot create a room with yourself!", "warning")
            else:
                room = current_user.get_or_create_room(user)
                if room:
                    session['room_id'] = room.id
                    session['user_id'] = current_user.id
                    return redirect(url_for("room", room=room.id))
                else:
                    flash("An error occurred while creating the room.", "danger")
        else:
            flash("User does not exist.", "warning")
    return render_template("chatlist.html", title="Chats", form=form, opponents=opponents)
@app.route("/room/<int:room>", methods=["GET", "POST"])
@login_required
def room(room):
    room = Room.query.filter_by(id=room).first()
    if current_user != room.user1 and current_user != room.user2:
        abort(403)
    if current_user == room.user1:
        opponent = room.user2
    else:
        opponent = room.user1

    message_form = MessageForm()

    if message_form.validate_on_submit():
        # Send the message to the room
        room.send_message(sender=current_user, message=message_form.message.data)
        flash("Message sent!", "success")
        return redirect(url_for("room", room=room.id))

    messages = Message.query.filter_by(room_id=room.id).order_by(Message.timestamp.asc()).all()
    
    session['room_id'] = room.id  # Set the room ID in the session

    return render_template("room.html", room=room, message_form=message_form, messages=messages, opponent=opponent, datetime=datetime.utcnow())

@socketio.on("connect")
def connect():
    room_id = session.get('room_id')
    print(room_id)
    room = Room.query.filter_by(id=room_id).first()
    join_room(room_id)
    if room and current_user == room.user1 or current_user == room.user2:
        # Send a message to the room to notify that a user has joined
        emit("message", {"username": current_user.username, "message": "has entered the room."}, room=room_id)
        db.session.commit()
        print(f"{current_user.username} has joined the room.")

@socketio.on("disconnect")
def disconnect():
    room_id = session.get('room_id')
    leave_room(room_id)
    emit("message", {"username": current_user.username, "message": "has left the room."}, room=room_id)
    print(f"{current_user.username} has left the room.")

@socketio.on("message")
def message(data):
    room_id = session.get('room_id')
    room = Room.query.filter_by(id=room_id).first()
    if not room:
        return
    content = {
        "name": current_user.username,
        "message": data["data"]
    }
    new_message = Message(author=current_user, room=room, text=data["data"])  # Use the room object instead of room_id
    db.session.add(new_message)
    db.session.commit()
    emit("new_message", {"name": current_user.username, "message": data["data"], "timestamp": new_message.timestamp.strftime('%Y-%m-%d %H:%M:%S'), "room_id": room_id}, room=room_id)  # Emit "new_message" event instead of "message" and specify the room ID
    print(f"{current_user.username} said: {data['data']}")

@app.route("/about")
def about():
    return render_template('about.html')

