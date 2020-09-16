# Dependencies
# ============
# Non-standard
# ------------
# See http://tinydb.readthedocs.io/
from tinydb import TinyDB, Query
from tinydb.database import Document
# See https://flask.palletsprojects.com/en/1.1.x/
from flask import (
    current_app,
    g,
    Blueprint,
    abort,
    jsonify,
    request)
from itsdangerous import (
    TimedJSONWebSignatureSerializer as Serializer,
    BadSignature,
    SignatureExpired)
# See https://flask-login.readthedocs.io/
from flask_login import LoginManager
# See https://passlib.readthedocs.io/
from passlib.apps import custom_app_context as pwd_context
# See https://flask-httpauth.readthedocs.io/
from flask_httpauth import HTTPBasicAuth


# Local
# -----
from .db_utils import JSONStorageWithGit

bp = Blueprint('api2_user', __name__)
auth = HTTPBasicAuth()


# Classes
# =======
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
    '''For objects representing an application using the API. Adapted from
    https://blog.miguelgrinberg.com/post/restful-authentication-with-flask
    '''
    def hash_password(self, password):
        '''Takes password, hashes it and saves it to database.'''
        self['password_hash'] = pwd_context.hash(password)
        self.save_password()
        return True

    def save_password(self):
        '''Saves user's current password hash to database.'''
        user_db = get_user_db()
        user_db.table('api_users').update(
            {'password_hash': self.get('password_hash')},
            doc_ids=[self.doc_id])

    def verify_password(self, password):
        '''Verifies password. If verified, checks to see if the hash
        needs upgrading to more secure algorithm, and if so, saves
        the upgraded hash to the database.'''
        result, new_hash = pwd_context.verify_and_update(
            password, self.get('password_hash'))
        if new_hash:
            self['password_hash'] = new_hash
            self.save_password()
        return result

    def generate_auth_token(self, expiration=600):
        '''Generates a new time-limited token from dict containing doc_id of
        current user.
        '''
        s = Serializer(current_app.config['SECRET_KEY'], expires_in=expiration)
        return s.dumps({'id': self.doc_id})

    @staticmethod
    def verify_auth_token(token):
        '''Extracts doc_id of a user from a previously generated token, and
        uses it to look up and return the user's record. If the token is
        invalid or expired, or the doc_id is invalid, returns None instead.
        '''
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
            return None  # invalid doc_id
        user = ApiUser(value=user_record, doc_id=user_record.doc_id)
        return user


# Handy functions
# ===============
def get_user_db():
    if 'user_db' not in g:
        g.user_db = TinyDB(
            current_app.config['USER_DATABASE_PATH'],
            storage=JSONStorageWithGit,
            indent=2,
            ensure_ascii=False)

    return g.user_db


@auth.verify_password
def verify_password(userid_or_token, password):
    # First try to authenticate by token:
    user = ApiUser.verify_auth_token(userid_or_token)
    if not user:
        # Not a valid token, so try to authenticate as username/password
        user_db = get_user_db()
        api_users = user_db.table('api_users')
        user_record = api_users.get(Query().userid == userid_or_token)
        if not user_record:
            # User not found
            return False
        user = ApiUser(value=user_record, doc_id=user_record.doc_id)
        if not user.verify_password(password):
            # Password incorrect
            return False
    if not user.is_active:
        # Credentials okay, but user blocked
        return False
    g.user = user
    return True


# Routes
# ======
@bp.route('/token')
@auth.login_required
def get_auth_token():
    token = g.user.generate_auth_token()
    return jsonify({'token': token.decode('ascii')})


@bp.route('/reset-password', methods=['POST'])
@auth.login_required
def reset_api_password():
    new_password = request.json.get('new_password')
    if g.user.hash_password(new_password):
        return jsonify(
            {'username': g.user.get('userid'), 'password_reset': True})
    else:
        abort(500)
