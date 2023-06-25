from datetime import datetime
from chitchat import db, login_manager
from flask_login import UserMixin
from flask_socketio import emit

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

room_users = db.Table('room_users',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('room_id', db.Integer, db.ForeignKey('room.id'), primary_key=True),
    db.UniqueConstraint('user_id', 'room_id', name='unique_user_room')
)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    image_file = db.Column(db.String(20), nullable=False, default='default.jpg')
    password = db.Column(db.String(60), nullable=False)
    rooms = db.relationship('Room', secondary=room_users, backref=db.backref('users', lazy=True), uselist=True)


    def __repr__(self):
        return f"User('{self.username}', '{self.email}', '{self.image_file}')"

    def get_or_create_room(self, user):
        # Check if a room already exists for the two users
        print(self.rooms)
        for room in self.rooms:
            if user in room.users:
                return room
        
        # If no room exists, create a new one
        room = Room.query.filter(
            (Room.user1_id == self.id) & (Room.user2_id == user.id) | 
            (Room.user1_id == user.id) & (Room.user2_id == self.id)
        ).first()
        if room is None:
            room = Room(user1=self, user2=user, name=f"{self.username} and {user.username}")
            db.session.add(room)
            db.session.commit()
        return room



class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user2_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    messages = db.relationship('Message', backref='room', lazy=True)
    def __init__(self, user1, user2, name):
        if user1.username < user2.username:
            self.user1_id = user1.id
            self.user2_id = user2.id
        else:
            self.user1_id = user2.id
            self.user2_id = user1.id
        self.name = name
    def __repr__(self):
        return f"Room('{self.name}', '{self.user1.username}', '{self.user2.username}')"
    @property
    def get_users(self):
        return [self.user1, self.user2]
    @property
    def is_full(self):
        return len(self.get_users) >= 2
    @property
    def user1(self):
        return User.query.get(self.user1_id)
    @property
    def user2(self):
        return User.query.get(self.user2_id)
    def send_message(self, sender, message):
        # Create a new message object and add it to the room's messages
        new_message = Message(sender=sender, room_id=self.id, message=message)
        db.session.add(new_message)
        db.session.commit()

        # Send the message to the room using SocketIO
        emit("message", {"username": sender.username, "message": message}, room=self.id)
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    author = db.relationship('User', backref='messages')
    def __init__(self, author, room, text):
        self.author = author
        self.room = room
        self.text = text
    def __repr__(self):
        return f"Message('{self.author.username}', '{self.room.name}', '{self.text}', '{self.timestamp}')"


