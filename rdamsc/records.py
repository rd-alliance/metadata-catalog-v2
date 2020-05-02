# Dependencies
# ============
# Standard
# --------
import json
import re
import os
from typing import (
    List,
    Mapping,
    Tuple,
    Type,
)
from urllib.parse import urlparse

# Non-standard
# ------------
# See http://tinydb.readthedocs.io/
from tinydb import TinyDB, Query, where
from tinydb.database import Document
from tinydb.operations import delete
# See https://github.com/eugene-eeo/tinyrecord
from tinyrecord import transaction
# See https://flask.palletsprojects.com/en/1.1.x/
from flask import (
    abort, Blueprint, current_app, flash, g, redirect, render_template, request,
    session, url_for
)
# See https://flask-login.readthedocs.io/
from flask_login import login_required
# See https://flask-wtf.readthedocs.io/ and https://wtforms.readthedocs.io/
from flask_wtf import FlaskForm
from wtforms import (
    FieldList, Form, FormField, HiddenField, SelectField, SelectMultipleField,
    StringField, TextAreaField, ValidationError, validators, widgets
)
from wtforms.compat import string_types

# Local
# -----
from .db_utils import JSONStorageWithGit
from .utils import Pluralizer, to_file_slug
from .vocab import get_thesaurus, get_vocab_db

bp = Blueprint('main', __name__)
mscid_prefix = 'msc:'
allowed_tags = {
    'p': [],
    'blockquote': [],
    'ol': [],
    'ul': [],
    'li': [],
    'dl': [],
    'dt': [],
    'dd': [],
    'a': ['href'],
    'em': [],
    'strong': [],
    'q': [],
    'abbr': ['title'],
    'code': [],
    'i': [],
    'sup': [],
    'sub': [],
    'bdi': [],
    'bdo': ['dir'],
    'br': [],
    'wbr': [],
    }


# Database wrapper classes
# ========================
class Relation(object):
    '''Utility class for handling common operations on the relations table.
    Relations are stored using MSCIDs to identify records.'''
    def __init__(self):
        db = get_data_db()
        self.tb = db.table('rel')

    def add(self, relations: Mapping[str, Mapping[str, List[str]]]):
        '''Adds relations to the table.'''
        n = len(mscid_prefix) + 1
        with transaction(self.tb) as t:
            for s, properties in relations.items():
                rel_record = self.tb.get(Query()['@id'] == s)
                if rel_record is None:
                    properties['@id'] = s
                    t.insert(properties)
                    continue
                for p, objects in properties.items():
                    if p not in rel_record:
                        rel_record[p] = objects
                        continue
                    for o in objects:
                        if o not in rel_record[p]:
                            rel_record[p].append(o)
                            rel_record[p].sort(
                                key=lambda k: k[:n] + k[n:].zfill(5))
                t.update(rel_record, doc_ids=[rel_record.doc_id])

    def remove(self, relations: Mapping[str, Mapping[str, List[str]]]):
        '''Removes relations from table, and returns those successfully
        removed for comparison.'''
        removed_relations = dict()
        with transaction(self.tb) as t:
            for s, properties in relations.items():
                relation = self.tb.get(Query()['@id'] == s)
                print(f"DEBUG Relation.remove: processing {relation}")
                if relation is None:
                    continue
                for p, objects in properties.items():
                    if p not in relation:
                        continue
                    for o in objects:
                        if o not in relation[p]:
                            continue
                        if s not in removed_relations:
                            removed_relations[s] = dict()
                        if p not in removed_relations:
                            removed_relations[s][p] = list()
                        relation[p].remove(o)
                        removed_relations[s][p].append(o)
                    if not relation[p]:
                        print(f"DEBUG Relation.remove: removing empty key {p}")
                        del relation[p]
                        t.update_callable(delete(p), doc_ids=[relation.doc_id])
                    else:
                        print(f"DEBUG Relation.remove: not removing non-empty key {p} = {relation[p]}")
                t.update(relation, doc_ids=[relation.doc_id])
        return removed_relations

    def subjects(self, predicate=None, object=None):
        '''Returns list of MSCIDs for all records that are subjects in the
        relations database, optionally filtered by predicate and object.'''
        mscids = set()
        Q = Query()
        if object is None:
            if predicate is None:
                relations = self.tb.all()
            else:
                relations = self.tb.search(Q[predicate].exists())
            for relation in relations:
                if len(relation.keys()) == 1:
                    continue
                mscids.add(relation.get('@id'))
        else:
            if predicate is None:
                relations = self.tb.all()
                for relation in relations:
                    for objects in relation.values():
                        if isinstance(objects, list) and object in objects:
                            mscids.add(relation.get('@id'))
            else:
                relations = self.tb.search(Q[predicate].any(object))
                mscids = [relation.get('@id') for relation in relations]
        n = len(mscid_prefix) + 1
        return sorted(mscids, key=lambda k: k[:n] + k[n:].zfill(5))

    def subject_records(self, predicate=None, object=None):
        '''Returns list of Records that are subjects in the relations database,
        optionally filtered by predicate and object.'''
        mscids = self.subjects(predicate, object)
        return [Record.load_by_mscid(mscid) for mscid in mscids]

    def objects(self, subject=None, predicate=None):
        '''Returns list of MSCIDs for all records that are objects in the
        relations database, optionally filtered by subject and predicate.'''
        mscids = set()
        Q = Query()
        if predicate is None:
            if subject is None:
                relations = self.tb.all()
            else:
                relations = self.tb.search(Q['@id'] == subject)
            for relation in relations:
                for key, objects in relation.items():
                    if key == '@id':
                        continue
                    for object in objects:
                        mscids.add(object)
        else:
            if subject is None:
                relations = self.tb.search(Q[predicate].exists())
            else:
                relations = self.tb.search(Q['@id'] == subject)
            for relation in relations:
                for object in relation.get(predicate, list()):
                    mscids.add(object)
        n = len(mscid_prefix) + 1
        return sorted(mscids, key=lambda k: k[:n] + k[n:].zfill(5))

    def object_records(self, subject=None, predicate=None):
        '''Returns list of Records that are objects in the relations database,
        optionally filtered by subject and predicate.'''
        mscids = self.objects(subject, predicate)
        return [Record.load_by_mscid(mscid) for mscid in mscids]


class Record(Document):
    '''Abstract class with common methods for the helper classes
    for different types of record.'''

    @staticmethod
    def cleanup(data):
        """Takes dictionary and recursively removes entries where the value is (a)
        an empty string, (b) an empty list, (c) a dictionary wherein all the
        values are empty, (d) null. Values of 0 are not removed. Also strips
        out csrf_token.
        """
        for key, value in data.copy().items():
            if isinstance(value, dict):
                new_value = Record.cleanup(value)
                if not new_value:
                    del data[key]
                else:
                    data[key] = new_value
            elif isinstance(value, list):
                if not value:
                    del data[key]
                else:
                    clean_list = list()
                    for item in value:
                        if isinstance(item, dict):
                            new_item = Record.cleanup(item)
                            if new_item:
                                clean_list.append(new_item)
                        elif item:
                            clean_list.append(item)
                    if clean_list:
                        data[key] = clean_list
                    else:
                        del data[key]
            elif value == '':
                del data[key]
            elif value is None:
                del data[key]
            elif key in ['csrf_token', 'old_relations']:
                del data[key]
        return data

    @classmethod
    def get_choices(cls):
        choices = [('', '')]
        for record in cls.search(Query().slug.exists()):
            choices.append(
                (record.mscid, record.name))

        choices.sort(key=lambda k: k[1].lower())
        return choices

    @classmethod
    def get_db(cls):
        return get_data_db()

    @classmethod
    def get_vocabs(cls):
        '''Gets controlled vocabularies for use as hints in unconstrained
        StringFields.'''
        raise NotImplementedError

    @classmethod
    def load(cls, doc_id: int, table: str=None):
        '''Returns an instance of the Record subclass that corresponds to the
        given table, either blank or the existing record with the given doc_id.
        '''

        # We need to get the table to look up and the class to return the
        # record as. If called from subclass, this comes direct from the class.
        # If called on Record, we get it from the table string.
        subclass = cls
        if table is None:
            if not hasattr(cls, 'table'):
                return None
            table = cls.table
        else:
            valid_tables = list()
            for subcls in cls.__subclasses__():
                valid_tables.append(subcls.table)
                if subcls.table == table:
                    subclass = subcls

            if table not in valid_tables:
                return None

        db = subclass.get_db()
        tb = db.table(table)
        doc = tb.get(doc_id=doc_id)

        if doc:
            return subclass(value=doc, doc_id=doc.doc_id)
        return subclass(value=dict(), doc_id=0)

    @classmethod
    def load_by_mscid(cls, mscid: str):
        '''Returns an instance of the Record subclass that corresponds to the
        given MSCID, or None if the MSCID was not syntactically correct.
        '''
        mscid_format = re.compile(
            mscid_prefix
            + r'(?P<table>[a-z]+)'
            + r'(?P<doc_id>\d+)'
            + r'(#v(?P<version>.*))?$')
        m = mscid_format.match(mscid)
        if m:
            return cls.load(int(m.group('doc_id')), m.group('table'))
        return None

    @classmethod
    def all(cls):
        '''Should only be called on subclasses of Record. Returns a list of all
        instances of that subclass from the database.'''
        db = cls.get_db()
        tb = db.table(cls.table)
        docs = tb.all()
        return [cls(value=doc, doc_id=doc.doc_id) for doc in docs]

    @classmethod
    def search(cls, cond: Query):
        '''Should only be called on subclasses of Record. Performs a TinyDB
        search on the corresponding table, converts the results into
        instances of the given subclass.'''
        db = cls.get_db()
        tb = db.table(cls.table)
        docs = tb.search(cond)
        return [cls(value=doc, doc_id=doc.doc_id) for doc in docs]

    def __init__(self, value: Mapping, doc_id: int, table: str):
        super().__init__(value, doc_id)
        self.table = table

    @property
    def form(self):
        raise NotImplementedError

    @property
    def mscid(self):
        return f"{mscid_prefix}{self.table}{self.doc_id}"

    @property
    def name(self):
        return "Generic record"

    @property
    def slug(self):
        return self.get('slug')

    @property
    def vform(self):
        raise NotImplementedError

    def _save(self, value: Mapping):
        '''Saves record to database. Returns error message if a problem
        arises.'''

        # Remove empty and noisy fields
        value = self.cleanup(value)

        # Update or insert record as appropriate
        db = self.get_db()
        tb = db.table(self.table)
        if self.doc_id:
            with transaction(tb) as t:
                for key in (k for k in self if k not in value):
                    t.update_callable(delete(key), doc_ids=[self.doc_id])
                t.update(value, doc_ids=[self.doc_id])
        else:
            self.doc_id = tb.insert(value)

        return ''

    def _save_relations(self, forward: List[Tuple[bool, str, List[str]]],
                        inverted: List[Tuple[str, str, bool]]):
        '''Saves relation edits to the Relations table.'''
        rel = Relation()
        additions = dict()
        deletions = dict()

        for is_addition, p, objects in forward:
            if is_addition:
                if self.mscid in objects:
                    objects.remove(self.mscid)
                if not objects:
                    continue
                if self.mscid not in additions:
                    additions[self.mscid] = dict()
                if p not in additions[self.mscid]:
                    additions[self.mscid][p] = list()
                additions[self.mscid][p].extend(objects)
            else:
                if not objects:
                    continue
                if self.mscid not in deletions:
                    deletions[self.mscid] = dict()
                if p not in deletions[self.mscid]:
                    deletions[self.mscid][p] = list()
                deletions[self.mscid][p].extend(objects)

        for s, p, is_addition in inverted:
            if is_addition:
                if s not in additions:
                    additions[s] = dict()
                if p not in additions[s]:
                    additions[s][p] = list()
                additions[s][p].append(self.mscid)
            else:
                if s not in deletions:
                    deletions[s] = dict()
                if p not in deletions[s]:
                    deletions[s][p] = list()
                deletions[s][p].append(self.mscid)

        rel.add(additions)
        rel.remove(deletions)

        return ''

    def get_form(self):
        raise NotImplementedError

    def get_vform(self):
        raise NotImplementedError

    def save_gui_input(self, formdata: Mapping):
        '''Processes form input and saves it. Returns error message if a problem
        arises.'''

        # Insert slug:
        formdata['slug'] = self.slug

        # Restore version information:
        formdata['versions'] = self.get('versions', list())

        # Get list of fields we can iterate over:
        fields = self.form()

        # Sanitize HTML input:
        for field in fields:
            if field.type != 'TextHTMLField':
                continue
            html_in = formdata.get(field.name)
            if not html_in:
                continue
            # TODO: apply filtering
            html_safe = html_in
            formdata[field.name] = html_safe

        # Convert subjects to URIs:
        if 'keywords' in formdata:
            keyword_uris = list()
            th = get_thesaurus()
            for keyword in formdata['keywords']:
                keyword_uri = th.get_uri(keyword)
                if keyword_uri:
                    keyword_uris.append(keyword_uri)
            formdata['keywords'] = keyword_uris

        # Remove form inputs containing relatedEntities information, and save
        # them separately. Things to note:
        # - If a field is missing from formdata, no values are set and user has
        #   not interacted with it (nothing to do).
        # - If the field is present but the value is a list containing just the
        #   empty string, the user has deliberately cleared any existing
        #   relationships.
        # - If the field is present and has a list of actual values, these are
        #   the only values that should be set.

        # Forward relationships are List[Tuple[Boolean, predicate, List[object]]]
        # Inverse relationships are List[Tuple[subject, predicate, Boolean]]

        # where True indicates an addition and False indicates a deletion
        forward = list()
        inverted = list()

        # Previously stored relationships (falling back to databases if not
        # available from form data):
        rel = Relation()
        old_relations = dict
        old_relation_json = formdata.get('old_relations')
        if old_relation_json:
            try:
                old_relations = json.loads(old_relation_json)
            except json.JSONDecodeError:
                print("DEBUG save_gui_input: ignoring bad JSON in"
                      " old_relations.")

        for field in fields:
            if field.type != 'SelectRelatedField':
                continue
            if field.name not in formdata:
                continue

            predicate = field.description
            if '' in formdata[field.name]:
                formdata[field.name].remove('')

            # What do we need to do?
            if field.flags.inverse:
                # Base state to compare against:
                old_subjects = old_relations.get(
                    field.name,
                    rel.subjects(predicate=predicate, object=self.mscid))
                for s in formdata[field.name]:
                    if s not in old_subjects:
                        inverted.append((s, predicate, True))
                for s in old_subjects:
                    if s not in formdata[field.name]:
                        inverted.append((s, predicate, False))
            else:
                old_objects = old_relations.get(
                    field.name,
                    rel.objects(subject=self.mscid, predicate=predicate))
                additions = list()
                for o in formdata[field.name]:
                    if o not in old_objects:
                        additions.append(o)
                if additions:
                    forward.append((True, predicate, additions))
                deletions = list()
                for o in old_objects:
                    if o not in formdata[field.name]:
                        deletions.append(o)
                if deletions:
                    forward.append((False, predicate, deletions))

            # Clear from formdata
            del formdata[field.name]

        # Save the main record:
        error = self._save(formdata)
        if error:
            return error

        # Update relations
        return self._save_relations(forward, inverted)

    def save_gui_vinput(self, formdata: Mapping, index: int=None):
        '''Processes form input and saves it. Returns error message if a problem
        arises.'''

        # Get list of fields we can iterate over:
        fields = self.vform()

        # Sanitize HTML input:
        for field in fields:
            if field.type != 'TextHTMLField':
                continue
            html_in = formdata.get(field.name)
            if not html_in:
                continue
            # TODO: apply filtering
            html_safe = html_in
            formdata[field.name] = html_safe

        alldata = dict(self)

        if index is None:
            if 'versions' not in self:
                alldata['versions'] = list()
            alldata['versions'].append(formdata)
        elif index < 0 or index >= len(self['versions']):
            return ("You tried to edit a version that does not exist in the"
                    " database yet.")
        else:
            alldata['versions'][index] = formdata

        # Save the main record:
        error = self._save(alldata)
        if error:
            return error


class Scheme(Record):
    table = 'm'
    series = 'scheme'

    @classmethod
    def get_vocabs(cls):
        '''Gets controlled vocabularies for use as hints in unconstrained
        StringFields.'''
        vocabs = dict()

        th = get_thesaurus()
        vocabs['subjects'] = th.get_choices()
        vocabs['idSchemes'] = list()
        for tuple in IDScheme.get_choices(cls):
            if tuple[0]:
                vocabs['idSchemes'].append(tuple[0])

        return vocabs

    '''Object representing a metadata scheme.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def form(self):
        return SchemeForm

    @property
    def name(self):
        return self.get('title', "Untitled")

    @property
    def slug(self):
        slug = self.get('slug')
        if slug:
            return slug
        if self.name:
            return to_file_slug(self.name)
        return None

    @property
    def vform(self):
        return SchemeVersionForm

    def get_form(self):
        # Get data from database:
        data = json.loads(json.dumps(self))

        # Strip out version info, this is handled separately:
        if 'versions' in data:
            del data['versions']

        # Populate with relevant relations
        rel = Relation()
        rel_summary = dict()
        for field in self.form():
            if field.type != 'SelectRelatedField':
                continue
            predicate = field.description
            mscids = list()
            if field.flags.inverse:
                object = self.mscid
                mscids.extend(rel.subjects(
                    predicate=predicate, object=object))
            else:
                subject = self.mscid
                mscids.extend(rel.objects(
                    subject=subject, predicate=predicate))
            rel_summary[field.name] = mscids

        for key, value in rel_summary.items():
            if value:
                data[key] = value

        data['old_relations'] = json.dumps(rel_summary)

        # Translate keywords from URI to string
        th = get_thesaurus()
        if 'keywords' in data:
            keywords = list()
            for keyword_uri in data['keywords']:
                keywords.append(th.get_long_label(keyword_uri))
            data['keywords'] = keywords

        # Populate form:
        form = self.form(data=data)
        for field in form:
            if field.type == 'FieldList' and field.name in data:
                last_entry = data[field.name][-1]
                if not last_entry:
                    continue
                if isinstance(last_entry, dict):
                    for value in last_entry.values():
                        if value:
                            break
                    else:
                        continue
                field.append_entry()

        # Assign validators to current choices:
        for field in form.keywords:
            if len(field.validators) == 1:
                field.validators.append(
                    validators.AnyOf(
                        th.get_valid(),
                        'Value must be drawn from the UNESCO Thesaurus.'))
        form.parent_schemes.omit_mscid(self.mscid)
        form.child_schemes.omit_mscid(self.mscid)
        form.dataTypes.choices = Datatype.get_choices()
        for f in form.locations:
            f['type'].choices = Location.get_choices(self.__class__)
        for f in form.identifiers:
            f.scheme.choices = IDScheme.get_choices(self.__class__)

        return form

    def get_vform(self, index: int=None):
        # Get data from database:
        main_data = json.loads(json.dumps(self))

        # Strip out version info, this is handled separately:
        data = dict()
        if index is not None:
            try:
                data = main_data.get('versions', list())[index]
            except IndexError:
                index = None
                pass

        # Populate form:
        form = self.vform(data=data)
        for field in form:
            if field.type == 'FieldList' and field.name in data:
                last_entry = data[field.name][-1]
                if not last_entry:
                    continue
                if isinstance(last_entry, dict):
                    for value in last_entry.values():
                        if value:
                            break
                    else:
                        continue
                field.append_entry()

        # Assign validators to current choices:
        for f in form.locations:
            f['type'].choices = Location.get_choices(self.__class__)
        for f in form.identifiers:
            f.scheme.choices = IDScheme.get_choices(self.__class__)

        return form


class Tool(Record):
    table = 't'
    series = 'tool'

    '''Object representing a tool.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def name(self):
        return self.get('title')

    @property
    def slug(self):
        slug = self.get('slug')
        if slug:
            return slug
        if self.name:
            return to_file_slug(self.name)
        return None


class Crosswalk(Record):
    table = 'c'
    series = 'mapping'

    '''Object representing a mapping.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def name(self):
        return self.get('name')

    @property
    def slug(self):
        slug = self.get('slug')
        if slug:
            return slug
        if self.name:
            return to_file_slug(self.name)
        return None


class Group(Record):
    table = 'g'
    series = 'organization'

    @classmethod
    def get_choices(cls):
        choices = [('', '')]
        for scheme in cls.search(Query().slug.exists()):
            choices.append(
                (scheme.mscid, scheme.get('name', 'Unnamed')))

        choices.sort(key=lambda k: k[1].lower())
        return choices

    '''Object representing an organization.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def name(self):
        return self.get('name')

    @property
    def slug(self):
        slug = self.get('slug')
        if slug:
            return slug
        if self.name:
            return to_file_slug(self.name)
        return None


class Endorsement(Record):
    table = 'e'
    series = 'endorsement'

    '''Object representing an endorsement.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def name(self):
        return self.get('title')

    @property
    def slug(self):
        slug = self.get('slug')
        if slug:
            return slug
        if self.name:
            return to_file_slug(self.name)
        return None


class Datatype(Record):
    table = 'datatype'
    series = 'datatype'

    @classmethod
    def get_db(cls):
        return get_vocab_db()

    @classmethod
    def get_choices(cls):
        '''Returns choices as tuples.'''
        choices = [('', '')]
        for record in cls.search(Query().id.exists()):
            choices.append(
                (record.mscid, record['label']))

        choices.sort(key=lambda k: k[1])
        return choices

    @classmethod
    def get_types_used(cls):
        labels = list()
        for record in cls.all():
            labels.append(record['label'])
        labels.sort()
        return labels

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def form(self):
        return DatatypeForm

    def get_form(self):
        # Get data from database:
        data = json.loads(json.dumps(self))

        # Populate form:
        form = self.form(data=data)

        # Add validators:
        if self.doc_id == 0 and len(form.label.validators) == 1:
            form.label.validators.append(
                validators.NoneOf(
                    self.get_types_used(),
                    message="That descriptor is already in use." +
                    " Please make it distinct in some way."))

        return form

    def save_gui_input(self, formdata: Mapping):
        '''Processes form input and saves it. Returns error message if a problem
        arises.'''

        # Save the main record:
        error = self._save(formdata)
        if error:
            return error


class VocabTerm(Document):
    '''Abstract class with common methods for the helper classes
    for different types of vocabulary terms.'''
    @classmethod
    def get_db(cls):
        return get_term_db()

    @classmethod
    def get_choices(cls, filter: Type[Record]=None):
        '''Returns choices as tuples.'''
        choices = [('', '')]

        if filter:
            Q = Query()
            records = cls.search(Q.applies.any(filter.series))
            records.sort(key=lambda k: k.doc_id)
            for record in records:
                choices.append(
                    (record['id'], record['label']))
        else:
            records = cls.all()
            records.sort(key=lambda k: k.doc_id)
            for record in records:
                choices.append(
                    (record['id'], record['label']))

        return choices

    @classmethod
    def populate(cls):
        db = cls.get_db()
        tables = db.tables()
        missing_tables = list()

        for subcls in cls.__subclasses__():
            if subcls.table not in tables:
                missing_tables.append(subcls.table)

        if missing_tables:
            moddir = os.path.dirname(__file__)
            data_file = os.path.join(
                moddir, 'data', 'vocabulary.json')
            if not os.path.isfile(data_file):
                return

            with open(data_file, 'r') as f:
                data = json.load(f)
            for table in missing_tables:
                terms = data.get(table)
                if terms:
                    tb = db.table(table)
                    with transaction(tb) as t:
                        for term in terms:
                            t.insert(term)

    def get_form(self):
        # Get data from database:
        data = json.loads(json.dumps(self))

        # Populate form:
        form = self.form(data=data)

        if self.doc_id != 0:
            form.id

        return form

    def save_gui_input(self, formdata: Mapping):
        '''Processes form input and saves it. Returns error message if a problem
        arises.'''

        # Override id
        old_id = self.get('id')
        if old_id:
            formdata['id'] = old_id

        # Save the main record:
        error = self._save(formdata)
        if error:
            return error


class Location(VocabTerm, Record):
    '''Abstract class with common methods for the helper classes
    for different types of vocabulary terms.'''
    table = 'location'
    series = 'location'

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def form(self):
        return VocabLocationForm


class EntityType(VocabTerm, Record):
    '''Abstract class with common methods for the helper classes
    for different types of vocabulary terms.'''
    table = 'type'
    series = 'type'

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


class IDScheme(VocabTerm, Record):
    '''Abstract class with common methods for the helper classes
    for different types of vocabulary terms.'''
    table = 'id_scheme'
    series = 'id_scheme'

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


# Form components
# ===============
# Custom validators
# -----------------
def EmailOrURL(form, field):
    """Raise error if URL/email address is not well-formed."""
    result = urlparse(field.data)
    if result.scheme == 'mailto':
        if not re.match(r'[^@\s]+@[^@\s\.]+\.[^@\s]+', result.path):
            raise ValidationError(
                'That email address does not look quite right.')
    else:
        if not result.scheme:
            raise ValidationError(
                'Please provide the protocol (e.g. "http://", "mailto:").')
        if not result.netloc:
            return ValidationError('That URL does not look quite right.')


class RequiredIf(object):
    """A validator which makes a field required if another field is set and has
    a truthy value, and optional otherwise.
    """
    field_flags = ('optional', )

    def __init__(self, other_field_list, message=None, strip_whitespace=True):
        self.other_field_list = other_field_list
        self.message = message
        if strip_whitespace:
            self.string_check = lambda s: s.strip()
        else:
            self.string_check = lambda s: s

    def __call__(self, form, field):
        other_fields_empty = True
        for other_field_name in self.other_field_list:
            other_field = form._fields.get(other_field_name)
            if other_field is None:
                raise Exception(
                    'No field named "{}" in form'.format(other_field_name))
            if bool(other_field.data):
                if not field.raw_data or not field.raw_data[0]:
                    if self.message is None:
                        message = field.gettext('This field is required.')
                    else:
                        message = self.message
                    field.errors[:] = []
                    other_fields_empty = False
                    raise validators.StopValidation(message)
            elif (not field.raw_data) or (
                    isinstance(field.raw_data[0], string_types) and
                    not self.string_check(field.raw_data[0])):
                field.errors[:] = []
        if other_fields_empty:
            raise validators.StopValidation()


def W3CDate(form, field):
    """Raise error if a string is not a valid W3C-formatted date."""
    if re.search(r'^\d{4}(-\d{2}){0,2}$', field.data) is None:
        raise ValidationError('Please provide the date in yyyy-mm-dd format.')


# Custom elements
# ---------------
class SelectRelatedField(SelectMultipleField):
    def __init__(self, label='', record: Type[Record]=Scheme, inverse=False,
                 **kwargs):
        choices = record.get_choices()
        super(SelectMultipleField, self).__init__(
            label, choices=choices, **kwargs)
        setattr(self.flags, 'inverse', inverse)

    def omit_mscid(self, mscid: str):
        filtered_choices = [choice for choice in self.choices
                            if choice[0] != mscid]
        self.choices = filtered_choices


class TextHTMLField(TextAreaField):
    pass


# Reusable subforms
# -----------------
class NativeDateField(StringField):
    validators = [validators.Optional(), W3CDate]


class LocationForm(Form):
    url = StringField('URL', validators=[RequiredIf(['type']), EmailOrURL])
    type = SelectField('Type', validators=[RequiredIf(['url'])], default='')


class FreeLocationForm(Form):
    url = StringField('URL', validators=[RequiredIf(['type']), EmailOrURL])
    type = StringField('Type', validators=[RequiredIf(['url'])], default='')


class SampleForm(Form):
    title = StringField('Title', validators=[RequiredIf(['url'])])
    url = StringField('URL', validators=[RequiredIf(['title']), EmailOrURL])


class IdentifierForm(Form):
    id = StringField('ID')
    scheme = SelectField('ID scheme')


class DateRangeForm(Form):
    start = NativeDateField('from')
    end = NativeDateField('until')


class CreatorForm(Form):
    fullName = StringField('Full name')
    givenName = StringField('Given name(s)')
    familyName = StringField('Family name')


# Top-level forms
# ---------------
class SchemeForm(FlaskForm):
    title = StringField('Name of metadata scheme')
    description = TextHTMLField('Description')
    keywords = FieldList(
        StringField('Subject area', validators=[
            validators.Optional(),
            ]),
        'Subject areas', min_entries=1)
    dataTypes = SelectMultipleField(
        'Types of data described by this scheme')
    locations = FieldList(
        FormField(LocationForm), 'Relevant links', min_entries=1)
    identifiers = FieldList(
        FormField(IdentifierForm), 'Identifiers for this scheme',
        min_entries=1)
    parent_schemes = SelectRelatedField(
        'Parent metadata schemes', Scheme,
        description='parent scheme')
    child_schemes = SelectRelatedField(
        'Profiles of this scheme', Scheme,
        description='parent scheme', inverse=True)
    input_to_mappings = SelectRelatedField(
        'Mappings that take this scheme as input', Crosswalk,
        description='input scheme', inverse=True)
    output_from_mappings = SelectRelatedField(
        'Mappings that give this scheme as output', Crosswalk,
        description='output scheme', inverse=True)
    maintainers = SelectRelatedField(
        'Organizations that maintain this scheme', Group,
        description='maintainer')
    funders = SelectRelatedField(
        'Organizations that funded this scheme', Group,
        description='funder')
    users = SelectRelatedField(
        'Organizations that use this scheme', Group,
        description='user')
    tools = SelectRelatedField(
        'Tools that support this scheme', Tool,
        description='supported scheme', inverse=True)
    endorsements = SelectRelatedField(
        'Endorsements of this scheme', Endorsement,
        description='endorsed scheme', inverse=True)
    old_relations = HiddenField()


class SchemeVersionForm(FlaskForm):
    number = StringField(
        'Version number',
        validators=[validators.Length(max=20)])
    title = StringField('Name of metadata scheme')
    note = TextHTMLField('Note')
    issued = NativeDateField('Date published')
    available = NativeDateField('Date released as draft/proposal')
    valid = FormField(DateRangeForm, 'Date considered current', separator='_')
    locations = FieldList(
        FormField(LocationForm), 'Relevant links', min_entries=1)
    samples = FieldList(
        FormField(SampleForm), 'Sample records conforming to this scheme',
        min_entries=1)
    identifiers = FieldList(
        FormField(IdentifierForm), 'Identifiers for this scheme',
        min_entries=1)


class DatatypeForm(FlaskForm):
    id = StringField(
        'URL identifying this type of data',
        validators=[validators.Optional(), EmailOrURL])
    label = StringField(
        'Descriptor for this type of data',
        validators=[validators.InputRequired()])


class VocabLocationForm(FlaskForm):
    id = StringField(
        'Database value',
        validators=[validators.InputRequired()])
    label = StringField(
        'Displayed value',
        validators=[validators.InputRequired()])
    applies = SelectMultipleField(
        choices=[
            (Scheme.series, Scheme.series),
            (Tool.series, Tool.series),
            (Crosswalk.series, Crosswalk.series),
            (Endorsement.series, Endorsement.series),
            (Group.series, Group.series)],
        render_kw={'size': 5})


def get_data_db():
    if 'data_db' not in g:
        g.data_db = TinyDB(
            current_app.config['MAIN_DATABASE_PATH'],
            storage=JSONStorageWithGit,
            indent=2,
            ensure_ascii=False)

    return g.data_db


def get_term_db():
    if 'term_db' not in g:
        g.term_db = TinyDB(
            current_app.config['TERM_DATABASE_PATH'],
            ensure_ascii=False)

    return g.term_db


@bp.route('/edit/<string(length=1):table><int:number>',
          methods=['GET', 'POST'])
@login_required
def edit_record(table, number):
    # Look up record to edit, or get new:
    record = Record.load(number, table)

    # Abort if series was wrong:
    if record is None:
        abort(404)

    # If number is wrong, we reinforce the point by redirecting to 0:
    if record.doc_id != number:
        flash("You are trying to update a record that doesn't exist."
              "Try filling out this new one instead.", 'error')
        return redirect(url_for('main.edit_record', series=table, number=0))

    # Instantiate edit form
    form = record.get_form()

    # Form-specific value lists
    params = record.get_vocabs()

    # Processing the request
    if request.method == 'POST' and form.validate():
        form_data = form.data
        if table == 'e':
            # Here is where we automatically insert the URL type
            filtered_locations = list()
            for f in form.locations:
                if f.url.data:
                    location = {'url': f.url.data, 'type': 'document'}
                    filtered_locations.append(location)
            form_data['locations'] = filtered_locations
        # Save form data to database
        error = record.save_gui_input(form_data)
        if record.doc_id:
            # Editing an existing record
            if error:
                flash(error, 'error')
                return redirect(
                    url_for('main.edit_record', series=table, number=number))
            else:
                flash('Successfully updated record.', 'success')
                return redirect(
                    url_for('main.display', series=table, number=number))
        else:
            # Adding a new record
            if error:
                flash(error, 'error')
                return redirect(
                    url_for('main.edit_record', series=table, number=number))
            else:
                number = record.doc_id
                flash('Successfully added record.', 'success')
                return redirect(
                    url_for('main.display', series=table, number=number))
    if form.errors:
        flash('Could not save changes as there {:/was an error/were N errors}.'
              ' See below for details.'.format(Pluralizer(len(form.errors))),
              'error')
        for field, errors in form.errors.items():
            if len(errors) > 0:
                print(f"DEBUG edit_record: field: {field}, errors: {errors}.")
                if isinstance(errors[0], dict):
                    # Subform
                    for subform in errors:
                        for subfield, suberrors in subform.items():
                            for f in form[field]:
                                f[subfield].errors = clean_error_list(f[subfield])
                else:
                    # Simple field
                    form[field].errors = clean_error_list(form[field])
    return render_template(
        f"edit-{record.series}.html", form=form, doc_id=number, version=None,
        safe_tags=allowed_tags, **params)


@bp.route('/edit/<string(length=1):table><int:number>/<int:index>',
          methods=['GET', 'POST'])
@bp.route('/edit/<string(length=1):table><int:number>/add',
          methods=['GET', 'POST'])
@login_required
def edit_version(table, number, index=None):
    # Look up record to edit, or get new:
    record = Record.load(number, table)

    # Abort if series was wrong:
    if not hasattr(record, 'vform'):
        abort(404)
    if record is None:
        abort(404)

    # If number is wrong, we reinforce the point by redirecting to 0:
    if record.doc_id != number:
        flash("You are trying to update a record that doesn't exist."
              "Try filling out this new one instead.", 'error')
        return redirect(url_for('main.edit_record', series=table, number=0))

    # Instantiate edit form
    form = record.get_vform(index)

    # Form-specific value lists
    params = record.get_vocabs()
    params['index'] = index
    vno = form.number.data
    if vno:
        params['version'] = vno

    # Processing the request
    if request.method == 'POST' and form.validate():
        form_data = form.data
        if table == 'e':
            # Here is where we automatically insert the URL type
            filtered_locations = list()
            for f in form.locations:
                if f.url.data:
                    location = {'url': f.url.data, 'type': 'document'}
                    filtered_locations.append(location)
            form_data['locations'] = filtered_locations
        # Save form data to database
        error = record.save_gui_vinput(form_data)
        if record.doc_id:
            # Editing an existing record
            if error:
                flash(error, 'error')
                return redirect(
                    url_for('main.edit_version', series=table, number=number,
                            index=index))
            else:
                flash('Successfully updated version.', 'success')
                return redirect(
                    url_for('main.display', series=table, number=number))
        else:
            # Adding a new record
            if error:
                flash(error, 'error')
                return redirect(
                    url_for('main.edit_version', series=table, number=number,
                            index=index))
            else:
                number = record.doc_id
                flash('Successfully added version.', 'success')
                return redirect(
                    url_for('main.display', series=table, number=number))
    if form.errors:
        flash('Could not save changes as there {:/was an error/were N errors}.'
              ' See below for details.'.format(Pluralizer(len(form.errors))),
              'error')
        for field, errors in form.errors.items():
            if len(errors) > 0:
                print(f"DEBUG edit_version: field: {field}, errors: {errors}.")
                if isinstance(errors[0], dict):
                    # Subform
                    for subform in errors:
                        for subfield, suberrors in subform.items():
                            for f in form[field]:
                                f[subfield].errors = clean_error_list(f[subfield])
                else:
                    # Simple field
                    form[field].errors = clean_error_list(form[field])
    return render_template(
        f"edit-{record.series}-version.html", form=form, doc_id=number,
        safe_tags=allowed_tags, **params)


@bp.route('/edit/<any(datatype, location, type, id_scheme):vocab><int:number>',
          methods=['GET', 'POST'])
@login_required
def edit_vocabterm(vocab, number):
    # Look up record to edit, or get new:
    record = Record.load(number, vocab)

    # If number is wrong, we reinforce the point by redirecting to 0:
    if record.doc_id != number:
        flash("You are trying to update a record that doesn't exist."
              "Try filling out this new one instead.", 'error')
        return redirect(url_for('main.edit_vocabterm', vocab=vocab, number=0))

    # Instantiate edit form
    form = record.get_form()

    # Processing the request
    if request.method == 'POST' and form.validate():
        form_data = form.data
        # Save form data to database
        error = record.save_gui_input(form_data)
        if record.doc_id:
            # Editing an existing record
            if error:
                flash(error, 'error')
                return redirect(
                    url_for('main.edit_vocabterm', vocab=vocab, number=number))
            else:
                flash('Successfully updated record.', 'success')
                return redirect(url_for('hello'))
        else:
            # Adding a new record
            if error:
                flash(error, 'error')
                return redirect(
                    url_for('main.edit_vocabterm', vocab=vocab, number=number))
            else:
                number = record.doc_id
                flash('Successfully added record.', 'success')
                return redirect(url_for('hello'))
    if form.errors:
        flash('Could not save changes as there {:/was an error/were N errors}.'
              ' See below for details.'.format(Pluralizer(len(form.errors))),
              'error')
        for field, errors in form.errors.items():
            if len(errors) > 0:
                if isinstance(errors[0], dict):
                    # Subform
                    for subform in errors:
                        for subfield, suberrors in subform.items():
                            for f in form[field]:
                                f[subfield].errors = clean_error_list(f[subfield])
                else:
                    # Simple field
                    form[field].errors = clean_error_list(form[field])
    return render_template(
        f"edit-{vocab}.html", form=form, doc_id=number)


@bp.route('/msc/<string(length=1):table><int:number>')
@bp.route('/msc/<string(length=1):table><int:number>/<field>')
def display(table, number, field=None, api=False):
    # Look up record to edit, or get new:
    record = Record.load(number, table)

    # Abort if series or number was wrong:
    if record is None or record.doc_id == 0:
        abort(404)

    # Form MSC ID
    mscid = record.mscid

    # Translate URI-based vocabularies:
    if 'keywords' in record:
        th = get_thesaurus()
        keywords = list()
        for keyword_uri in record['keywords']:
            keyword = th.get_label(keyword_uri)
            if keyword:
                keywords.append(keyword)
            else:
                print(f"DEBUG display: No keyword for {keyword_uri}.")
        record['keywords'] = keywords

    # If the record has version information, interpret the associated dates.
    versions = None
    if 'versions' in record:
        versions = list()
        # Give each version an index of where it comes in the database
        for index in range(len(record['versions'])):
            record['versions'][index]['index'] = index
        for v in record['versions']:
            if 'number' not in v:
                continue
            this_version = v
            this_version['status'] = ''
            if 'issued' in v:
                this_version['date'] = v['issued']
                if 'valid' in v:
                    valid_end = v['valid'].get('end')
                    if valid_end:
                        this_version['status'] = (
                            'deprecated on {}'.format(valid_end))
                    else:
                        this_version['status'] = 'current'
            elif 'valid' in v:
                valid_start = v['valid'].get('start')
                valid_end = v['valid'].get('end')
                if valid_start:
                    this_version['date'] = valid_start
                if valid_end:
                    this_version['status'] = (
                        'deprecated on {}'.format(valid_end))
                else:
                    this_version['status'] = 'current'
            elif 'available' in v:
                this_version['date'] = v['available']
                this_version['status'] = 'proposed'
            versions.append(this_version)
        try:
            versions.sort(key=lambda k: k['date'], reverse=True)
        except KeyError:
            print('WARNING: Record {}{} has missing version date.'
                  .format(mscid))
            try:
                versions.sort(key=lambda k: k['number'], reverse=True)
            except KeyError:
                # Leave in order of entry
                pass
        for version in versions:
            if version['status'] == 'current':
                break
            if version['status'] == 'proposed':
                continue
            if version['status'] == '':
                version['status'] = 'current'
                break

    # If the record has related entities, include the corresponding entries in
    # a 'relations' dictionary. The keys are consistent with form controls, so
    # we defer to that for lookups.
    rel = Relation()
    relations = dict()
    scheme_scheme_fields = list()
    for field in record.form():
        if field.type != 'SelectRelatedField':
            continue
        if (field.description in [
                'parent scheme', 'input scheme', 'output scheme']):
            scheme_scheme_fields.append(field.name)
        if field.flags.inverse:
            others = rel.subject_records(
                predicate=field.description, object=record.mscid)
        else:
            others = rel.object_records(
                subject=record.mscid, predicate=field.description)
        if others:
            relations[field.name] = others

    # This is only relevant in Scheme views, since relations to other schemes
    # are grouped under a single heading.
    hasRelatedSchemes = False
    if table == 'm':
        for field in scheme_scheme_fields:
            if field in relations:
                hasRelatedSchemes = True
                break

    # We are ready to display the information.
    return render_template(
        f"display-{record.series}.html", record=record, versions=versions,
        relations=relations, hasRelatedSchemes=hasRelatedSchemes)


def clean_error_list(field):
    seen_errors = set()
    for error in field.errors:
        if isinstance(error, list):
            for sub_error in error:
                seen_errors.add(sub_error)
        else:
            seen_errors.add(error)
    return list(seen_errors)
