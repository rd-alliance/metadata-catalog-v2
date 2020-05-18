# Dependencies
# ============
# Non-standard
# ------------
# See http://tinydb.readthedocs.io/
from tinydb import TinyDB
from tinydb.database import Document
# See https://flask.palletsprojects.com/en/1.1.x/
from flask import current_app, g
from itsdangerous import (TimedJSONWebSignatureSerializer
                          as Serializer, BadSignature, SignatureExpired)
# See https://flask-login.readthedocs.io/
from flask_login import LoginManager
# See https://passlib.readthedocs.io/
from passlib.apps import custom_app_context as pwd_context

# Local
# -----
from .db_utils import JSONStorageWithGit


class User(Document):
    '''This provides implementations for the methods that Flask-Login
    expects user objects to have.
    '''
    __hash__ = Document.__hash__

    @property
    def is_active(self):
        if self.get('blocked'):
            return False
        return True

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.doc_id)

    def __eq__(self, other):  # pragma: no cover
        '''
        Checks the equality of two `UserMixin` objects using `get_id`.
        '''
        if isinstance(other, User):
            return self.get_id() == other.get_id()
        return NotImplemented

    def __ne__(self, other):  # pragma: no cover
        '''
        Checks the inequality of two `UserMixin` objects using `get_id`.
        '''
        equal = self.__eq__(other)
        if equal is NotImplemented:
            return NotImplemented
        return not equal


class ApiUser(User):
    '''For objects representing an application using the API. Source:
    https://blog.miguelgrinberg.com/post/restful-authentication-with-flask
    '''
    def hash_password(self, password):
        user_db = get_user_db()
        self['password_hash'] = pwd_context.encrypt(password)
        user_db.table('api_users').update(
            {'password_hash': self.get('password_hash')}, doc_ids=[self.doc_id])
        return True

    def verify_password(self, password):
        return pwd_context.verify_and_update(
            password, self.get('password_hash'))

    def generate_auth_token(self, expiration=600):
        s = Serializer(current_app.config['SECRET_KEY'], expires_in=expiration)
        return s.dumps({'id': self.doc_id})

    @staticmethod
    def verify_auth_token(token):
        user_db = get_user_db()
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except SignatureExpired:
            return None  # valid token, but expired
        except BadSignature:
            return None  # invalid token
        api_users = user_db.table('api_users')
        user_record = api_users.get(doc_id=int(data['id']))
        if not user_record:
            return None
        user = ApiUser(value=user_record, doc_id=user_record.doc_id)
        return user


def get_user_db():
    if 'user_db' not in g:
        g.user_db = TinyDB(
            current_app.config['USER_DATABASE_PATH'],
            storage=JSONStorageWithGit,
            indent=2,
            ensure_ascii=False)

    return g.user_db
