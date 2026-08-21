# Dependencies
# ============
# Standard
# --------
import time
from collections.abc import Mapping

from flask import current_app, g

# Non-standard
# ------------
from joserfc import jwt
from joserfc.errors import (
    BadSignatureError,
    ClaimError,
    DecodeError,
)
from joserfc.jwk import OctKey
from passlib.context import LazyCryptContext
from passlib.utils import sys_bits
from tinydb import Query, TinyDB
from tinydb.operations import delete
from tinydb.table import Document
from tinyrecord import transaction

# Local
# -----
from .db_utils import JSONStorageWithGit

pwd_context = LazyCryptContext(
    # In due course, may update to safer algorithms:
    schemes=["sha512_crypt", "sha256_crypt"],
    default="sha256_crypt" if sys_bits < 64 else "sha512_crypt",
    sha512_crypt__min_rounds=535000,
    sha256_crypt__min_rounds=535000,
    admin__sha512_crypt__min_rounds=1024000,
    admin__sha256_crypt__min_rounds=1024000,
)


class User(Document):
    """This provides implementations for the methods that Flask-Login
    expects user objects to have.
    """

    __hash__ = Document.__hash__
    table = "_default"

    @classmethod
    def get_db(cls) -> TinyDB:
        return get_user_db()

    @classmethod
    def load_by_userid(cls, userid: str):
        """Returns an instance of the class, either blank or the existing
        record with the given userid.
        """

        db = cls.get_db()
        tb = db.table(cls.table)
        doc = tb.get(Query().userid == userid)

        if isinstance(doc, Document) and doc:
            return cls(value=doc, doc_id=doc.doc_id)
        return cls(value=dict(), doc_id=0)

    @property
    def is_active(self) -> bool:
        if self.doc_id == 0 or self.get("blocked"):
            return False
        return True

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def __eq__(self, other) -> bool:  # pragma: no cover
        """
        Checks the equality of two `UserMixin` objects using `get_id`.
        """
        if isinstance(other, User):
            return self.get_id() == other.get_id()
        return NotImplemented

    def __ne__(self, other) -> bool:  # pragma: no cover
        """
        Checks the inequality of two `UserMixin` objects using `get_id`.
        """
        equal = self.__eq__(other)
        if equal is NotImplemented:
            return NotImplemented
        return not equal

    def _save(self, mapping: Mapping) -> str:
        """Adds the mapping as a new record, or updates an existing record with
        the mapping. Note that a key will only be removed from an existing
        record if given a value of None. Missing keys will not be affected.
        TODO: check for and return error message on known error.
        """

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

        return ""

    def get_id(self) -> str:
        """Returns User serial number ID as a string."""
        return str(self.doc_id)


class ApiUser(User):
    """For objects representing an application using the API."""

    table = "api_users"

    @classmethod
    def load_by_token(cls, token: bytes | str, expiration: int | float = 600):
        """If the token is valid, loads and returns the API user with the
        doc_id encoded by the token. Otherwise returns a blank instance.
        """
        try:
            key = OctKey.import_key(current_app.config["SECRET_KEY"])
            payload = jwt.decode(token, key)
            claims_requests = jwt.JWTClaimsRegistry(
                id={"essential": True},
                exp={"essential": True},
            )
            claims_requests.validate(payload.claims)
        except DecodeError:
            # invalid token
            return cls(value=dict(), doc_id=0)
        except BadSignatureError:
            # invalid token
            return cls(value=dict(), doc_id=0)
        except ClaimError:  # pragma: no cover
            # invalid, missing, expired claim
            return cls(value=dict(), doc_id=0)
        doc_id = int(payload.claims.get("id", 0))
        if not doc_id:
            return cls(value=dict(), doc_id=0)

        db = cls.get_db()
        tb = db.table(cls.table)
        doc = tb.get(doc_id=doc_id)

        if isinstance(doc, Document) and doc:
            return cls(value=doc, doc_id=doc.doc_id)
        return cls(value=dict(), doc_id=0)

    def hash_password(self, password: str | bytes) -> bool:
        """Saves hash of password to record, returning True on success
        and False on error.
        """
        new_hash = pwd_context.hash(password)
        error = self._save({"password_hash": new_hash})
        if error:  # pragma: no cover
            current_app.logger.error(f"ApiUser could not save hash: {error}.")
            return False
        return True

    def verify_password(self, password: str | bytes) -> bool:
        """Verifies that password matches currently stored hash. If so,
        updates the hash to a stronger one if necessary and returns
        True. Otherwise returns False.
        """
        is_verified, new_hash = pwd_context.verify_and_update(
            password, self.get("password_hash")
        )
        if new_hash:
            error = self._save({"password_hash": new_hash})
            if error:  # pragma: no cover
                current_app.logger.error(
                    f"ApiUser could not save hash on verify: {error}."
                )
                return False
        return is_verified

    def generate_auth_token(self, expiration: int | float = 600) -> str:
        """Returns a time-limited, encoded authorization token for this
        user.
        """
        key = OctKey.import_key(current_app.config["SECRET_KEY"])
        s = jwt.encode(
            {"alg": "HS256"},
            {"id": self.doc_id, "exp": time.time() + expiration},
            key,
        )
        return s


def get_user_db() -> TinyDB:
    """Returns the user database as a TinyDB object. The object is
    cached so further calls return the same one.
    """
    if "user_db" not in g:
        g.user_db = TinyDB(
            current_app.config["USER_DATABASE_PATH"],
            storage=JSONStorageWithGit,
            indent=2,
            ensure_ascii=False,
        )

    return g.user_db
