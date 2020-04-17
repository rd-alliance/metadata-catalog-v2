# Dependencies
# ============
# Standard
# --------
from typing import (
    Mapping,
)

# Non-standard
# ------------
# See http://tinydb.readthedocs.io/
from tinydb import TinyDB
from tinydb.database import Document
# See https://flask.palletsprojects.com/en/1.1.x/
from flask import current_app, g

# Local
# -----
from .db_utils import JSONStorageWithGit


class Record (Document):
    '''Abstract class with common methods for the helper classes
    for different types of record.'''
    def __init__(self, value: Mapping, doc_id: int, table: str):
        super().__init__(value, doc_id)
        self.table = table

    @classmethod
    def load(cls, doc_id: int):
        db = get_data_db()
        tb = db.table(cls.table)
        doc = tb.get(doc_id=doc_id)
        if doc:
            return cls(value=doc, doc_id=doc.doc_id)

    def get_mscid(self):
        return f"msc:{self.table}{self.doc_id}"


class Scheme (Record):
    table = 'm'

    '''Object representing a metadata scheme.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


class Tool (Record):
    table = 't'

    '''Object representing a tool.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


class Crosswalk (Record):
    table = 'c'

    '''Object representing a mapping.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


class Group (Record):
    table = 'g'

    '''Object representing an organization.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


class Endorsement (Record):
    table = 'e'

    '''Object representing an endorsement.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


def get_data_db():
    if 'data_db' not in g:
        g.data_db = TinyDB(
            current_app.config['MAIN_DATABASE_PATH'],
            storage=JSONStorageWithGit,
            indent=2,
            ensure_ascii=False)

    return g.data_db
