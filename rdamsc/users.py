# Dependencies
# ============
# Standard
# --------
from typing import (
    List,
    Mapping,
    Tuple,
    Type,
)

# Non-standard
# ------------
# See http://tinydb.readthedocs.io/
from tinydb import TinyDB, Query
from tinydb.database import Document
from tinydb.operations import delete
from tinyrecord import transaction
# See https://flask.palletsprojects.com/en/1.1.x/
from flask import current_app, g
from itsdangerous import (TimedJSONWebSignatureSerializer
                          as JWS, BadSignature, SignatureExpired)
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
    table = '_default'

    @classmethod
    def get_db(cls):
        return get_user_db()

    @classmethod
    def load_by_userid(cls, userid: str):
        '''Returns an instance of the class, either blank or the existing
        record with the given userid.
        '''

        db = cls.get_db()
        tb = db.table(cls.table)
        doc = tb.get(Query().userid == userid)

        if doc:
            return cls(value=doc, doc_id=doc.doc_id)
        return cls(value=dict(), doc_id=0)

    @property
    def is_active(self):
        if self.doc_id == 0 or self.get('blocked'):
            return False
        return True

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

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

    def _save(self, mapping: Mapping):
        '''Adds the mapping as a new record, or updates an existing record with
        the mapping. Note that a key will only be removed from an existing
        record if given a value of None. Missing keys will not be affected.
        '''

        # Update or insert record as appropriate
        db = self.get_db()
        tb = db.table(self.table)
        if self.doc_id:
            with transaction(tb) as t:
                for key in (k for k in self if mapping.get(k, False) is None):
                    t.update(delete(key), doc_ids=[self.doc_id])
                t.update(mapping, doc_ids=[self.doc_id])
        else:
            self.doc_id = tb.insert(mapping)

        return ''

    def get_id(self):
        return str(self.doc_id)


class ApiUser(User):
    '''For objects representing an application using the API.
    '''
    table = 'api_users'

    @classmethod
    def load_by_token(cls, token):
        '''If the token is valid, loads and returns the API user with the
        doc_id encoded by the token. Otherwise returns a blank instance.
        '''

        s = JWS(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except SignatureExpired:
            # valid token, but expired
            return cls(value=dict(), doc_id=0)
        except BadSignature:
            # invalid token
            return cls(value=dict(), doc_id=0)
        doc_id = int(data.get('id', 0))
        if not doc_id:
            return cls(value=dict(), doc_id=0)

        db = cls.get_db()
        tb = db.table(cls.table)
        doc = tb.get(doc_id=doc_id)

        if doc:
            return cls(value=doc, doc_id=doc.doc_id)
        return cls(value=dict(), doc_id=0)

    def hash_password(self, password):
        try:
            new_hash = pwd_context.hash(password)
        except ValueError:
            # Invalid parameter value:
            return False
        except TypeError:
            # Invalid parameter type:
            return False
        error = self._save({'password_hash': new_hash})
        if error:  # pragma: no cover
            print(f"ApiUser: could not save hash: {error}.")
            return False
        return True

    def verify_password(self, password):
        try:
            is_verified, new_hash = pwd_context.verify_and_update(
                password, self.get('password_hash'))
        except ValueError:
            # Unsupported scheme or invalid parameter value:
            return False
        except TypeError:
            # Invalid parameter type:
            return False
        if new_hash:
            error = self._save({'password_hash': new_hash})
            if error:  # pragma: no cover
                print(f"ApiUser: could not save hash: {error}.")
                return False
        return is_verified

    def generate_auth_token(self, expiration=600):
        s = JWS(current_app.config['SECRET_KEY'], expires_in=expiration)
        return s.dumps({'id': self.doc_id})


def get_user_db():
    if 'user_db' not in g:
        g.user_db = TinyDB(
            current_app.config['USER_DATABASE_PATH'],
            storage=JSONStorageWithGit,
            indent=2,
            ensure_ascii=False)

    return g.user_db
