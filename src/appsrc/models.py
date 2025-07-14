"""
This file contains base models like User
as well as abstract models inherited by blueprints
"""


import os
import datetime
import logging
from random import choice
from string import ascii_lowercase
from flask_login import UserMixin, current_user
from sqlalchemy import func as sqlfunc
from sqlalchemy.ext.declarative import declared_attr
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.datastructures import ImmutableDict
from .main import app, db


SYSTEM_ID = 999 # ID For built-in system user
PERMISSION_MAP = {
    1 : "EVERYONE",
    5 : "USER",
    10: "ADMIN",
    15: "OWNER",
    99 : "NOACCESS"
}


class PERMISSION_ENUM:
    _NAMES = {
        (EVERYONE := 1) : "everyone",
        (USER := 5)     : "users",
        (ADMIN := 10)   : "admins",
        (OWNER := 15)   : "owners",
        (NOACCESS := 99): "NOACCESS"
    } 
    _LOOKUP = {v:k for k,v in _NAMES.items()}


class ACTION_ENUM:
    _NAMES = {
        (ERROR := 0) : "ERROR",
        (CREATE:= 1) : "CREATE",
        (MODIFY:= 2) : "MODIFY",
        (DELETE:= 3) : "DELETE",
    }
    _LOOKUP = {v:k for k,v in _NAMES.items()}


class STATUS_ENUM:
    _NAMES = {
        (RUNNING:= -1) : "RUNNING",
        (SUCCESS:=  0) : "SUCCESS",
        (FAILURE:=  1) : "FAILURE",
        (HEADERS:=  2) : "HEADERS",
        (CLEANUP:=  3) : "CLEANUP",
        (TASK   :=  4) : "TASK",
    }
    _LOOKUP = {v:k for k,v in _NAMES.items()}


class User(UserMixin, db.Model):
    """User object with flask_login UserMixin"""
    __tablename__ = "User"
    __bind_key__ = "cetadash_db"
    id = db.Column(db.Integer, primary_key=True)
    permission_integer = db.Column(db.Integer, default=PERMISSION_ENUM.USER)
    name = db.Column(db.String(100), unique=True, nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    selected_theme = db.Column(db.String(100), default="default")
    
    @property
    def is_admin(self):
        return self.permission_integer >= PERMISSION_ENUM.ADMIN


class SecretKey(db.Model):
    __tablename__ = "SecretKey"
    __bind_key__ = "cetadash_db"
    """Table to store wtf secret key and flask secret key"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(24), nullable=False)


####################
# Abstract
####################
def make_changelog(before:dict, after:dict, width:int=32) -> str:
    """Generate a value changelog"""
    changelog = ""
    for k, v in before.items():
        changed = after.get(k)
        if not v == changed:
            changelog += ""+f"{k}".center(width, "=")+"\n"
            changelog += "="*width+"\n\n"
            changelog += f"{v}\n\n"
            changelog += "↓"*(width)+"\n\n"
            changelog += f"{changed}"+"\n\n"
    return changelog

def handle_log(log_cls, user_id: int = None, **kw) -> object:
    """Helper for both run and edit logs"""
    if not user_id:
        raise ValueError("Unknown user")
    log = log_cls(user_id=user_id, **kw)
    db.session.add(log)
    return log


class BaseEditable(db.Model):
    """Base class for cetadash tasks, workflows, and triggers db tables"""
    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    details = db.Column(db.Text)

    @declared_attr
    def creator_id(cls):
        return db.Column(db.Integer, db.ForeignKey(User.id))
    @declared_attr
    def creator(cls):
        return db.relationship("User", foreign_keys=[cls.creator_id])
    @declared_attr
    def last_editor_id(cls):
        return db.Column(db.Integer, db.ForeignKey(User.id))
    @declared_attr
    def last_editor(cls):
        return db.relationship("User", foreign_keys=[cls.last_editor_id])
    @declared_attr
    def last_run_by_id(cls):
        return db.Column(db.Integer, db.ForeignKey(User.id))
    @declared_attr
    def last_run_at(cls):
        return db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    @declared_attr
    def last_runner(cls):
        return db.relationship("User", foreign_keys=[cls.last_run_by_id])
    @declared_attr
    def created_at(cls):
        return db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    @declared_attr
    def edited_at(cls):
        return db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    @property
    def created_at_local(self):
        return app.wtf.localize(self.created_at)
    @property
    def created_at_pretty(self):
        return app.wtf.pretty_date(self.created_at_local)
    @property
    def edited_at_local(self):
        return app.wtf.localize(self.edited_at)
    @property
    def edited_at_pretty(self):
        return app.wtf.pretty_date(self.edited_at_local)
    
    def log_edit(self, log_cls, user_id:int = None, action:int = ACTION_ENUM.MODIFY, **kw):
        return handle_log(log_cls, user_id, action=action, **kw)
    
    def log_run(self, log_cls, user_id:int = None, status:int = STATUS_ENUM.RUNNING, **kw):
        return handle_log(log_cls, user_id, status=status, **kw)
        
class BaseLog(db.Model):
    """Base class for Cetadash Run and Edit logs"""
    __abstract__ = True
    id = db.Column(db.Integer, primary_key=True)

    @declared_attr
    def user_id(cls):
        return db.Column(db.Integer, db.ForeignKey(User.id))
    @declared_attr
    def user(cls):
        return db.relationship("User", foreign_keys=[cls.user_id])
    @declared_attr
    def timestamp(cls):
        return db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    @declared_attr
    def message(cls):
        return db.Column(db.Text)
    @property
    def timestamp_local(self):
        return app.wtf.localize(self.timestamp)
    @property
    def timestamp_pretty(self):
        return app.wtf.pretty_date(self.timestamp_local)


class BaseEditLog(BaseLog):
    __abstract__ = True
    action = db.Column(db.Integer, nullable=False, default=ACTION_ENUM.CREATE)


class BaseActionLog(BaseLog):
    __abstract__ = True
    status = db.Column(db.Integer, nullable=False, default=STATUS_ENUM.RUNNING)


def init_db(app):
    with app.app_context():
        logging.info("Initializing Users db")
        db.create_all(bind_key=["cetadash_db"])
        # Check if secret key exists in database, generate one if necessary
        # This key is used to maintain user sessions across application restarts
        # It is also used to reduce the chance of impersonation attacks
        secret_key = SecretKey.query.get(1)
        if secret_key is None:
            key_value = ''.join([choice(ascii_lowercase) for _ in range(24)])
            secret_key = SecretKey(id=1, key=str(key_value))
            db.session.add(secret_key)
            db.session.commit()
        key_value = secret_key.key
        app.secret_key = key_value
        # Do the same as described above for flask wtf forms CSRF protection 
        wtf_secret_key = SecretKey.query.get(2)
        if wtf_secret_key is None:
            wtf_key_value = ''.join([choice(ascii_lowercase) for _ in range(24)])
            wtf_secret_key = SecretKey(id=2, key=wtf_key_value)
            db.session.add(wtf_secret_key)
            db.session.commit()
        wtf_key_value = wtf_secret_key.key
        app.config["WTF_CSRF_SECRET_KEY"] = wtf_key_value
        
        if not User.query.get(1):
            logging.info("Creating default user with id=1")
            user = User(id=1, name="admin", permission_integer=PERMISSION_ENUM.ADMIN)
            db.session.add(user)
            db.session.commit()

        if not User.query.get(SYSTEM_ID):
            logging.info(f"Creating system user with id={SYSTEM_ID}")
            user = User(id=SYSTEM_ID, name="system", permission_integer=PERMISSION_ENUM.ADMIN)
            db.session.add(user)
            db.session.commit()
            
        db.session.commit()

        app.models.core = ImmutableDict()
        for obj in (
            User,
            SecretKey,
            PERMISSION_ENUM,
            ACTION_ENUM,
            STATUS_ENUM,
            make_changelog
        ):
            setattr(app.models.core, obj.__name__, obj)
        app.models.core.PERMISSION_MAP = PERMISSION_MAP