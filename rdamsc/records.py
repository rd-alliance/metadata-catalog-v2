# Dependencies
# ============
# Standard
# --------
import json
import os
import re
from typing import (
    List,
    Mapping,
    Tuple,
    Type,
)
from urllib.parse import urlparse

# Non-standard
# ------------
# See https://github.com/eugene-eeo/tinyrecord
from tinyrecord import transaction
# See https://flask.palletsprojects.com/en/2.0.x/
from flask import (
    Blueprint, abort, current_app, flash, g, redirect, render_template,
    request, url_for
)
# See https://flask-login.readthedocs.io/
from flask_login import login_required
# See https://flask-wtf.readthedocs.io/
from flask_wtf import FlaskForm
from markupsafe import escape, Markup
# See http://tinydb.readthedocs.io/
from tinydb import TinyDB, Query
from tinydb.database import Document
from tinydb.operations import delete
# See https://wtforms.readthedocs.io/
from wtforms import (
    FieldList, Form, FormField, HiddenField, SelectField, SelectMultipleField,
    StringField, TextAreaField, ValidationError, validators, widgets
)
from wtforms.utils import unset_value

# Local
# -----
from .db_utils import JSONStorageWithGit
from .utils import Pluralizer, clean_error_list, to_file_slug
from .vocab import get_thesaurus

bp = Blueprint('main', __name__)
mscid_prefix = 'msc:'
mp_len = len(mscid_prefix)
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
disallowed_tagblocks = [
    'script',
    'style',
]


# Database wrapper classes
# ========================
class Relation(object):
    '''Utility class for handling common operations on the relations table.
    Relations are stored using MSCIDs to identify records.'''

    _inversions = {
        'parent schemes': 'child schemes',
        'supported schemes': 'tools',
        'input schemes': 'input to mappings',
        'output schemes': 'output from mappings',
        'endorsed schemes': 'endorsements',
        'maintainers': 'maintained {}s',
        'funders': 'funded {}s',
        'users': 'used schemes',
        'originators': 'endorsements',
    }
    FORWARD = 'forward'
    INVERSE = 'inverse'

    @property
    def inversion_map(self):
        invrelmap = dict()
        for fw, iv in self.inversions.items():
            if fw in ['maintainers', 'funders']:
                for series in ['scheme', 'tool', 'mapping']:
                    invrelmap[iv.format(series)] = fw
            else:
                invrelmap[iv] = fw

        return invrelmap

    @property
    def inversions(self):
        return type(self)._inversions

    def __init__(self):
        db = get_data_db()
        self.tb = db.table('rel')
        self.series_map = dict()
        for subcls in Record.__subclasses__():
            self.series_map[subcls.table] = subcls.series

    def add(self, relations: Mapping[str, Mapping[str, List[str]]]):
        '''Adds relations to the table.'''
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
                            rel_record[p].sort(key=sortval)
                t.update(rel_record, doc_ids=[rel_record.doc_id])

    def remove(self, relations: Mapping[str, Mapping[str, List[str]]]):
        '''Removes relations from table, and returns those successfully
        removed for comparison.'''
        removed_relations = dict()
        with transaction(self.tb) as t:
            for s, properties in relations.items():
                relation = self.tb.get(Query()['@id'] == s)
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
                        del relation[p]
                        t.update(delete(p), doc_ids=[relation.doc_id])
                t.update(relation, doc_ids=[relation.doc_id])
        return removed_relations

    def subjects(self, predicate=None, object=None,
                 filter: Type[Document] = None):
        '''Returns list of MSCIDs for all records that are subjects in the
        relations database, optionally filtered by predicate, object and
        record class.'''
        mscids = set()
        prefix = f"{mscid_prefix}{filter.table}" if filter else None
        Q = Query()
        if object is None:
            if predicate is None:
                relations = self.tb.all()
            else:
                relations = self.tb.search(Q[predicate].exists())
            for relation in relations:
                if len(relation.keys()) == 1:
                    continue
                mscid = relation.get('@id')
                if prefix is None or mscid.startswith(prefix):
                    mscids.add(mscid)
        else:
            if predicate is None:
                relations = self.tb.all()
                for relation in relations:
                    for objects in relation.values():
                        if isinstance(objects, list) and object in objects:
                            mscid = relation.get('@id')
                            if prefix is None or mscid.startswith(prefix):
                                mscids.add(mscid)
            else:
                relations = self.tb.search(Q[predicate].any([object]))
                all_mscids = [relation.get('@id') for relation in relations]
                if prefix:
                    mscids = [m for m in all_mscids if m.startswith(prefix)]
                else:
                    mscids = all_mscids
        return sorted(mscids, key=sortval)

    def subject_records(self, predicate=None, object=None,
                        filter: Type[Document] = None):
        '''Returns list of Records that are subjects in the relations database,
        optionally filtered by predicate, object and record class.'''
        mscids = self.subjects(predicate, object, filter)
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
        return sorted(mscids, key=sortval)

    def object_records(self, subject=None, predicate=None):
        '''Returns list of Records that are objects in the relations database,
        optionally filtered by subject and predicate.'''
        mscids = self.objects(subject, predicate)
        return [Record.load_by_mscid(mscid) for mscid in mscids]

    def related(self, mscid: str, direction=None) -> Mapping[str, List[str]]:
        '''Returns dictionary where the keys are predicates (relationships)
        and the values are lists of MSCIDs of records related to the identified
        record by that predicate. The types of predicate can optionally be
        filtered by direction: "forward" indicates native predicates used in
        the database, "inverse" indicates their inverses, None indicates no
        filtering.
        '''
        Q = Query()
        results = dict()

        if direction is None or direction == Relation.FORWARD:
            relations = self.tb.search(Q['@id'] == mscid)
            for relation in relations:
                for predicate, objects in relation.items():
                    if predicate == '@id':
                        continue
                    results[predicate] = objects

        if direction is None or direction == Relation.INVERSE:
            relations = self.tb.all()
            for relation in relations:
                for predicate, objects in relation.items():
                    if isinstance(objects, list) and mscid in objects:
                        rel_mscid = relation.get('@id')
                        inv_predicate = self.inversions.get(predicate)
                        if inv_predicate is None:
                            continue
                        if predicate in ['maintainers', 'funders']:
                            series = self.series_map.get(
                                rel_mscid[mp_len:mp_len + 1])
                            inv_predicate = inv_predicate.format(series)
                        if inv_predicate not in results.keys():
                            results[inv_predicate] = list()
                        results[inv_predicate].append(rel_mscid)

        if results:
            for predicate in results.keys():
                results[predicate].sort(key=sortval)

        return results

    def related_records(self, mscid: str, direction=None) -> Mapping[
            str, List[Mapping]]:
        '''Returns dictionary where the keys are predicates (relationships)
        and the values are lists of records related to the identified
        record by that predicate. The types of predicate can optionally be
        filtered by direction: "forward" indicates native predicates used in
        the database, "inverse" indicates their inverses, None indicates no
        filtering.
        '''
        id_results = self.related(mscid, direction)
        results = dict()
        for predicate, mscids in id_results.items():
            results[predicate] = [
                Record.load_by_mscid(mscid) for mscid in mscids]
        return results


class Record(Document):
    '''Abstract class with common methods for the helper classes
    for different types of record.'''

    @staticmethod
    def cleanup(data):
        """Takes dictionary and recursively removes entries where the value is
        (a) an empty string, (b) an empty list, (c) a dictionary wherein all the
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
    def get_class_by_table(cls, table: str):
        '''Returns subclass of Record with the corresponding table identifier,
        or None if identifier is invalid. Should not be called on subclasses.
        '''
        for subcls in cls.__subclasses__():
            if subcls.table == table:
                return subcls
        return None

    @classmethod
    def get_db(cls):
        return get_data_db()

    @classmethod
    def get_vocabs(cls):
        '''Gets controlled vocabularies for use as hints in unconstrained
        StringFields. Most of these have been removed since MSC v.1.'''
        return dict()

    @classmethod
    def load(cls, doc_id: int, table: str = None):
        '''Returns an instance of the Record subclass that corresponds to the
        given table, either blank or the existing record with the given doc_id.
        '''

        # We need to get the table to look up and the class to return the
        # record as. If called on Record with a table string, we use that table
        # and its corresponding subclass. If called from a subclass without a
        # table string, we use that subclass and its corresponding table.
        # Otherwise, it is an error and we return None.
        subclass = cls
        if table is None:
            if not hasattr(cls, 'table'):  # pragma: no cover
                return None
            table = cls.table
        else:
            subclass = cls.get_class_by_table(table)
            if subclass is None:  # pragma: no cover
                return None

        db = subclass.get_db()
        tb = db.table(table)
        doc = tb.get(doc_id=doc_id)

        if doc is not None:
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
            if hasattr(cls, 'table'):
                return cls.load(int(m.group('doc_id')))
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
    def conformance(self):
        '''Tests the conformity level of the record as it appears in the
        database. It does not test for invalid syntax or empty values, since
        these problems should have been eliminated when the record was saved.

        Special schema keys: `optional` items are not needed for a record to
        be considered complete; `or use` and `or use role` indicate that a field
        is ignored for conformance level calculations if the indicated field
        or a related record with the given role is present, respectively. A
        field is automatically ignored if each version has the information in
        question.
        '''
        if not hasattr(self, 'schema'):  # pragma: no cover
            raise NotImplementedError

        # Create portable version of record:
        port = dict(self)
        related_entities = self.get_related_entities()
        rel_roles = list()
        if related_entities:
            port['relatedEntities'] = related_entities
            rel_roles = [r['role'] for r in related_entities]

        versions = port.get('versions') if 'versions' in self.schema else None

        is_complete = True
        is_useful = True
        for k, d in self.schema.items():
            co_field = d.get('or use')
            if co_field and co_field in port:
                continue

            co_role = d.get('or use role')
            if co_role and co_role in rel_roles:
                continue

            if versions:
                is_in_all_versions = True
                for v in versions:
                    if k not in v:
                        is_in_all_versions = False
                if is_in_all_versions:
                    continue

            utility = d.get('useful')
            if utility is True:
                if k not in port:
                    is_complete = False
                    is_useful = False
                    break
            elif isinstance(utility, list):
                # roles for related entities
                for r in utility:
                    if r not in rel_roles:
                        is_complete = False
                        is_useful = False
                        break
            else:
                if k not in port and not d.get('optional', False):
                    is_complete = False

        if is_complete:
            return 'complete'
        if is_useful:
            return 'useful'
        if port.keys():
            return 'valid'
        return 'empty'

    @property
    def form(self):  # pragma: no cover
        raise NotImplementedError

    @property
    def has_versions(self):
        return False

    @property
    def mscid(self):
        return f"{mscid_prefix}{self.table}{self.doc_id}"

    @property
    def name(self):  # pragma: no cover
        return "Generic record"

    @property
    def slug(self):
        return self.get_slug()

    def _do_datatypes(self, value: List[str]):
        '''API validator for data types.'''
        result = {'errors': list(), 'value': list()}
        valid_types = [v[0] for v in Datatype.get_choices()
                       if v[0]]
        for i, v in enumerate(value):
            if v not in valid_types:
                result['errors'].append({
                    'message': f"No such datatype record: {v}.",
                    'location': f"[{i}]"})
            elif v not in result['value']:
                result['value'].append(v)
        return result

    def _do_date(self, value: str):
        '''API validator for a date.'''
        result = {'errors': list(), 'value': ''}
        wv = W3CDate()
        if wv.regex.match(value):
            result['value'] = value
        else:
            result['errors'].append({
                'message': "Date must be in yyyy or yyyy-mm or yyyy-mm-dd "
                           "format."})
        return result

    def _do_html(self, value: str):
        '''API validator for HTML text.'''
        result = {'errors': list(), 'value': ''}
        value = re.sub(r'\s+', r' ', value).strip()

        # This limit should only be hit by malicious requests:
        result['value'] = strip_tags(value)[:131072]
        return result

    def _do_id_doi(self, value: str):
        '''API validator for DOI ID scheme. Does not check if DOI is registered.
        '''
        result = {'errors': list(), 'value': ''}
        m = re.match(r'^(?:https?://(?:dx\.)?doi\.org/)?'
                     r'(?P<doi>10\.\d+/.+)$', value)
        if m:
            result['value'] = m.group('doi')
        else:
            result['errors'].append({'message': "Malformed DOI."})
        return result

    def _do_id_handle(self, value: str):
        '''API validator for Handle System ID scheme. Does not check if Handle
        is registered.
        '''
        result = {'errors': list(), 'value': ''}
        m = re.match(r'^(?:https?://hdl.handle.net/)?'
                     r'(?P<hdl>\d+\.\d+/.+)$', value)
        if m:
            result['value'] = m.group('hdl')
        else:
            result['errors'].append({'message': "Malformed Handle."})
        return result

    def _do_id_ror(self, value: str):
        '''API validator for ROR ID scheme. Does not verify the check digits.'''
        result = {'errors': list(), 'value': ''}
        m = re.match(r'^(?:https?://ror.org/)'
                     r'(?P<ror>0[0-9a-hjkmnp-z]{6}\d\d)$', value)
        if m:
            result['value'] = 'https://ror.org/' + m.group('ror')
        else:
            result['errors'].append({'message': "Malformed ROR."})
        return result

    def _do_identifiers(self, value: List[Mapping[str, str]]):
        '''API validator for identifiers.'''
        result = {'errors': list(), 'value': list()}
        valid_schemes = [v[0] for v in IDScheme.get_choices(self.__class__)
                         if v[0]]
        for i, v in enumerate(value):
            clean_value = dict()

            # Process ID string:
            id = v.get('id')
            if id is None:
                result['errors'].append({
                    'message': "Missing field: id.",
                    'location': f"[{i}]"})
            else:
                # Replace this if _do_text starts returning errors:
                clean_value['id'] = self._do_text(id).get('value', '')

            # Validate scheme:
            scheme = v.get('scheme')
            if scheme is None:
                result['errors'].append({
                    'message': "Missing field: scheme.",
                    'location': f"[{i}]"})
            elif scheme not in valid_schemes:
                result['errors'].append({
                    'message': f"Invalid scheme: {scheme}."
                    f" Valid schemes: {', '.join(valid_schemes)}.",
                    'location': f"[{i}].scheme"})
            else:
                clean_value['scheme'] = scheme

                # Scheme-based validation:
                subvalidator = f"_do_id_{scheme.lower()}"
                if clean_value.get('id') and hasattr(self, subvalidator):
                    validated = getattr(self, subvalidator)(clean_value['id'])
                    clean_value['id'] = validated.get('value')
                    for error in validated['errors']:
                        result['errors'].append({
                            'message': error.get('message', ''),
                            'location': f"[{i}].id"})

            result['value'].append(clean_value)
        return result

    def _do_vocabid(self, value: str):
        '''API validator for vocabulary term ID.'''
        return self._do_short_text(value, 64)

    def _do_locations(self, value: List[Mapping[str, str]]):
        '''API validator for locations.'''
        result = {'errors': list(), 'value': list()}
        valid_types = [v[0] for v in Location.get_choices(self.__class__)
                       if v[0]]
        for i, v in enumerate(value):
            clean_value = dict()

            # Validate URL
            url = v.get('url')
            if url is None:
                result['errors'].append({
                    'message': "Missing field: url.",
                    'location': f"[{i}]"})
            else:
                validated = self._do_url(url)
                for error in validated.get('errors'):
                    result['errors'].append({
                        'message': error.get('message', ''),
                        'location': f"[{i}].url"})
                clean_value['url'] = validated.get('value')

            # Validate type
            loc_type = v.get('type')
            if loc_type is None:
                result['errors'].append({
                    'message': "Missing field: type.",
                    'location': f"[{i}]"})
            elif loc_type not in valid_types:
                result['errors'].append({
                    'message': f"Invalid type: {loc_type}."
                    f" Valid types: {', '.join(valid_types)}.",
                    'location': f"[{i}].type"})
            else:
                clean_value['type'] = loc_type

            result['value'].append(clean_value)
        return result

    def _do_namespaces(self, value: List[Mapping[str, str]]):
        '''API validator for namespaces.'''
        result = {'errors': list(), 'value': list()}
        for i, v in enumerate(value):
            clean_value = dict()

            # Validate prefix
            prefix = v.get('prefix')
            if prefix is None:
                result['errors'].append({
                    'message': "Missing field: prefix.",
                    'location': f"[{i}]"})
            else:
                validated = self._do_short_text(prefix, 32)
                for error in validated.get('errors'):
                    result['errors'].append({
                        'message': error.get('message', ''),
                        'location': f"[{i}].prefix"})
                clean_value['prefix'] = validated.get('value')

            # Validate URI
            uri = v.get('uri')
            if uri is None:
                result['errors'].append({
                    'message': "Missing field: uri.",
                    'location': f"[{i}]"})
            else:
                validated = self._do_uri(uri)
                for error in validated.get('errors'):
                    result['errors'].append({
                        'message': error.get('message', ''),
                        'location': f"[{i}].uri"})
                clean_value['uri'] = validated.get('value')

            result['value'].append(clean_value)
        return result

    def _do_period(self, value: Mapping[str, str]):
        '''API validator for time periods (start/end dates).'''
        result = {'errors': list(), 'value': dict()}
        for key in ['start', 'end']:
            if key in value:
                validated = self._do_date(value[key])
                for error in validated.get('errors'):
                    result['errors'].append({
                        'message': error.get('message', ''),
                        'location': f".{key}{error.get('location', '')}"})
                result['value'][key] = validated.get('value')
        if not result['errors'] and (value.get('end', '9999-99-99')
                                     < value.get('start', '0000-00-00')):
            result['errors'].append({
                'message': "End date is before start date."})
        return result

    def _do_relations(self, value: List[Mapping[str, str]]):
        '''Validates that the ID exists and the role is recognised. Removes
        details beyond this and translates the role into temporary helper fields
        `predicate` and `direction`.
        '''
        if not hasattr(self, 'rolemap'):  # pragma: no cover
            raise NotImplementedError
        result = {'errors': list(), 'value': list()}
        cache = dict()
        for i, v in enumerate(value):
            clean_relation = dict()
            has_error = False
            accepts = None

            # Validate role
            role = v.get('role')
            if role is None:
                result['errors'].append({
                    'message': "Missing field: role.",
                    'location': f"[{i}]"})
                has_error = True
            elif role not in self.rolemap.keys():
                result['errors'].append({
                    'message': f"Invalid role: {role}."
                    f" Valid roles: {', '.join(self.rolemap.keys())}.",
                    'location': f"[{i}].role"})
                has_error = True
            else:
                accepts = self.rolemap[role]['accepts']

            # Validate MSCID
            mscid = v.get('id')
            if mscid is None:
                result['errors'].append({
                    'message': "Missing field: id.",
                    'location': f"[{i}]"})
                has_error = True
            else:
                rel_record = cache.get(mscid)
                if rel_record is None:
                    rel_record = Record.load_by_mscid(mscid)
                    cache[mscid] = rel_record
                if rel_record is None:
                    result['errors'].append({
                        'message': f"Not a valid MSC ID: {mscid}.",
                        'location': f"[{i}].id"})
                    has_error = True
                elif rel_record.doc_id == 0:
                    result['errors'].append({
                        'message': f"No such record: {mscid}.",
                        'location': f"[{i}].id"})
                    has_error = True
                elif accepts and rel_record.table != accepts:
                    result['errors'].append({
                        'message': f"The record {mscid} cannot take the role of"
                        f" {role}.",
                        'location': f"[{i}]"})
                    has_error = True

            if has_error:
                continue
            clean_relation = {
                'id': mscid,
                'role': role,
                'predicate': self.rolemap[role]['predicate'],
                'direction': self.rolemap[role]['direction'],
            }
            result['value'].append(clean_relation)
        return result

    def _do_series(self, value: List[str]):
        '''API validator limiting values to main record series.'''
        result = {'errors': list(), 'value': list()}
        valid_series = [
            Scheme.series, Tool.series, Crosswalk.series, Group.series,
            Endorsement.series]
        if not isinstance(value, list):
            result['errors'].append({
                'message': "Value must be a list (one or more of "
                           f"{', '.join(valid_series)}).",
                'location': ''})
            return result
        for i, v in enumerate(value):
            if v not in valid_series:
                result['errors'].append({
                    'message': f"Invalid series: {v}. "
                               f"Valid series: {', '.join(valid_series)}.",
                    'location': f"[{i}]"})
            else:
                result['value'].append(v)
        return result

    def _do_short_text(self, value: str, maxlength: int):
        '''API validator for short passages of plain text.'''
        result = self._do_text(value)
        length = len(result['value'])
        if length > maxlength:
            result['errors'].append({
                'message': f"Value must be {maxlength} characters or fewer "
                           f"(actual length: {length})."})
        return result

    def _do_text(self, value: str):
        '''API validator for plain text.'''
        result = {'errors': list(), 'value': ''}
        value = re.sub(r'\s+', r' ', value).strip()

        # This limit should only be hit by malicious requests:
        result['value'] = value[:65536]
        return result

    def _do_types(self, value: List[str]):
        '''API validator for entity types.'''
        result = {'errors': list(), 'value': list()}
        valid_types = [v[0] for v in EntityType.get_choices(self.__class__)
                       if v[0]]
        for i, v in enumerate(value):
            if v not in valid_types:
                result['errors'].append({
                    'message': f"Invalid type: {v}. "
                               f"Valid types: {', '.join(valid_types)}.",
                    'location': f"[{i}]"})
            else:
                result['value'].append(v)
        return result

    def _do_thesaurus(self, value: List[str]):
        '''API validator for subject thesaurus terms.'''
        result = {'errors': list(), 'value': list()}
        thes = get_thesaurus()
        valid_terms = thes.get_uris()
        for i, v in enumerate(value):
            if v not in valid_terms:
                result['errors'].append({
                    'message': f"Invalid term URI: {v}.",
                    'location': f"[{i}]"})
            elif v not in result['value']:
                result['value'].append(v)
        return result

    def _do_uri(self, value: str):
        '''API validator for namespace URIs.'''
        result = {'errors': list(), 'value': ''}
        if not value:
            return result

        uv = NamespaceURI()
        if not uv.gen_regex.match(value):
            result['errors'].append({
                'message': "Value must include protocol:"
                           " http, https."})
        elif not value.endswith(('/', '#')):
            result['errors'].append({
                'message': "Value must end with / or #."})
        else:
            match = uv.url_regex.match(value)
            if not (match and uv.validate_hostname(match.group('host'))):
                result['errors'].append({
                    'message': f"Invalid URI: {value}."})

        result['value'] = value
        return result

    def _do_url(self, value: str):
        '''API validator for URLs and mailto: email addresses.'''
        result = {'errors': list(), 'value': ''}
        if not value:
            return result

        uv = EmailOrURL()
        if not uv.gen_regex.match(value):
            result['errors'].append({
                'message': "Value must include protocol:"
                           " http, https, mailto."})
        elif value.startswith('mailto:'):
            if not uv.email_regex.match(value):
                result['errors'].append({
                    'message': "Invalid email address."})
            else:
                length = len(value)
                if length > 254:
                    result['errors'].append({
                        'message': "Value must be 254 characters or fewer"
                                   f" (actual length: {length})."})
        else:
            match = uv.url_regex.match(value)
            if not (match and uv.validate_hostname(match.group('host'))):
                result['errors'].append({
                    'message': f"Invalid URL: {value}."})

        result['value'] = value
        return result

    def _do_versionid(self, value: str):
        '''API validator for version numbers/identifiers.'''
        return self._do_short_text(value, 32)

    def _save(self, value: Mapping) -> str:
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
                    t.update(delete(key), doc_ids=[self.doc_id])
                t.update(value, doc_ids=[self.doc_id])
        else:
            self.doc_id = tb.insert(value)

        return ''

    def _save_relations(self, forward: List[Tuple[bool, str, List[str]]],
                        inverted: List[Tuple[str, str, bool]]) -> str:
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

    def annul(self) -> List[Mapping[str, str]]:
        '''Removes content of record. Returns a list of error messages if any
        problems arise.
        '''

        # Get current list of relations for this record so we can delete them:
        rel = Relation()
        # Forward relationships: List[Tuple[False, predicate, List[object]]]
        fwd_rel = rel.related(self.mscid, direction=rel.FORWARD)
        forward = [(False, k, v) for k, v in fwd_rel.items()]
        # Inverse relationships: List[Tuple[subject, predicate, False]]
        invrelmap = rel.inversion_map
        inv_rel = rel.related(self.mscid, direction=rel.INVERSE)
        inverted = list()
        for relation, mscids in inv_rel.items():
            predicate = invrelmap.get(relation)
            if predicate is None:  # pragma: no cover
                return [{'message': 'Database error: unrecognised predicate'}]
            for mscid in mscids:
                inverted.append((mscid, predicate, False))

        # Save the main record:
        error = self._save(dict())
        if error:
            return [{'message': error}]

        # Update relations
        if forward or inverted:
            error = self._save_relations(forward, inverted)
            if error:
                return [{'message': error}]

        return list()

    def get_form(self):  # pragma: no cover
        raise NotImplementedError

    def get_related_entities(self) -> List[Mapping[str, str]]:
        '''Returns a list of dictionaries where each gives the MSC ID of another
        record, and the role that record plays with respect to the current one.
        '''
        if len(self.table) > 1:
            return None

        related_entities = list()
        rel = Relation()
        relations = rel.related(mscid=self.mscid)
        for role in sorted(relations.keys()):
            for mscid in relations[role]:
                related_entity = {
                    'id': mscid,
                    'role': role[:-1],  # convert to singular
                }
                related_entities.append(related_entity)
        return related_entities

    def get_slug(self, *, apidata: Mapping = None, formdata: Mapping = None):
        return self.get('slug')

    def get_vform(self):  # pragma: no cover
        raise NotImplementedError

    def insert_relations(self, data: Mapping):
        '''Adds the relations of the current record to the input form data and
        return the result.'''
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
                    predicate=predicate, object=object,
                    filter=field.flags.cls))
            else:
                subject = self.mscid
                mscids.extend(rel.objects(
                    subject=subject, predicate=predicate))
            rel_summary[field.name] = mscids

        for key, value in rel_summary.items():
            if value:
                data[key] = value

        data['old_relations'] = json.dumps(rel_summary)

        return data

    def populate_form(self, data: Mapping, is_version=False):
        form = self.vform(data=data) if is_version else self.form(data=data)
        for field in form:
            if field.type == 'FieldList' and field.name in data:
                last_entry = field.data[-1]
                if not last_entry:
                    continue
                if isinstance(last_entry, dict):
                    for value in last_entry.values():
                        if value:
                            break
                    else:
                        continue
                field.append_entry()

        # Assign validators to current choices (these are in all the forms):
        for f in form.locations:
            f['type'].choices = Location.get_choices(self.__class__)
        for f in form.identifiers:
            f.scheme.choices = IDScheme.get_choices(self.__class__)

        return form

    def reload(self):
        db = self.get_db()
        tb = db.table(self.table)
        doc = tb.get(doc_id=self.doc_id)
        for key in [k for k in self.keys() if k not in doc]:
            del self[key]
        self.update(doc)

    def save_api_input(self, input_data: Mapping) -> List[Mapping[str, str]]:
        '''Processes form input and saves it. Returns a list of error messages
        if any problems arise.'''

        # Validate and clean:
        errors, input_data = self.validate(input_data)
        if errors:
            return errors

        # Insert slug:
        input_data['slug'] = self.get_slug(apidata=input_data)

        # Move relatedEntities information into new lists: we can add new ones
        # but not remove old ones.

        # Forward relationships: List[Tuple[True, predicate, List[object]]]
        # Inverse relationships: List[Tuple[subject, predicate, True]]
        forward_map = dict()
        inverted = list()

        related_entities = input_data.get('relatedEntities', list())
        if related_entities:
            rel = Relation()
            for relation in related_entities:
                predicate = relation.get('predicate')

                # What do we need to do?
                if relation.get('direction') == rel.INVERSE:
                    inverted.append((relation.get('id'), predicate, True))
                else:
                    if predicate not in forward_map:
                        forward_map[predicate] = list()
                    forward_map[predicate].append(relation.get('id'))

            del input_data['relatedEntities']

        forward = [(True, k, v) for k, v in forward_map.items()]

        # Save the main record:
        error = self._save(input_data)
        if error:
            return [{'message': error}]

        # Update relations
        if related_entities:
            error = self._save_relations(forward, inverted)
            if error:
                return [{'message': error}]

        return list()

    def save_gui_input(self, formdata: Mapping):
        '''Processes form input and saves it. Returns error message if a
        problem arises.'''

        # Insert slug:
        formdata['slug'] = self.get_slug(formdata=formdata)

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
            html_safe = strip_tags(html_in)
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

        # We will assemble lists of changes to make.
        # Forward relationships are List[Tuple[Bool, predicate, List[object]]].
        # Inverse relationships are List[Tuple[subject, predicate, Bool]].
        # Bool=True indicates an addition, Bool=False indicates a deletion.
        forward = list()
        inverted = list()

        # Previously stored relationships (falling back to databases if not
        # available from form data):
        rel = Relation()
        old_relations = dict()
        old_relation_json = formdata.get('old_relations')
        if old_relation_json:
            try:
                old_relations = json.loads(old_relation_json)
            except json.JSONDecodeError:
                print("WARNING Record.save_gui_input: ignoring bad JSON in"
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
                        # Add this relationship:
                        inverted.append((s, predicate, True))
                for s in old_subjects:
                    if s not in formdata[field.name]:
                        # Remove this relationship:
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

    def save_gui_vinput(self, formdata: Mapping, index: int = None):
        '''Processes form input and saves it. Returns error message if a
        problem arises.'''

        # Get list of fields we can iterate over:
        fields = self.vform()

        # Sanitize HTML input:
        for field in fields:
            if field.type != 'TextHTMLField':
                continue
            html_in = formdata.get(field.name)
            if not html_in:
                continue
            html_safe = strip_tags(html_in)
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

    def save_invrel_patch(self, input_data: Mapping) -> \
            Tuple[List[Mapping[str, str]], Mapping]:
        '''Validates a set of patches and applies them to the database if they
        pass validation. Returns error list and resulting record.
        '''
        if not hasattr(self, 'rolemap'):  # pragma: no cover
            raise NotImplementedError

        rel = Relation()

        acceptable = dict()
        for role, info in self.rolemap.items():
            if info['direction'] == Relation.FORWARD:
                continue
            if info['predicate'] in ['maintainers', 'funders']:
                series = rel.series_map.get(info['accepts'])
                acceptable[rel.inversions.get(
                    info['predicate']).format(series)] = info['accepts']
            else:
                acceptable[rel.inversions.get(
                    info['predicate'])] = info['accepts']

        result = {'@id': self.mscid}
        result.update(rel.related(self.mscid, direction=rel.INVERSE))

        self.cache = dict()
        errors = list()
        if not isinstance(input_data, list):
            errors.append({
                'message': "Input must be in JSON Patch format (an array of "
                           "objects).",
                'location': '$'})
            return (errors, result)

        for i, patch in enumerate(input_data):
            if not isinstance(patch, dict):
                errors.append({
                    'message': "Not a JSON object.",
                    'location': f'$[{i}]'})
                continue
            err, result = self.validate_rel_patch(result, patch, acceptable)
            for e in err:
                errors.append({
                    'message': e.get('message'),
                    'location': f"$[{i}]{e.get('location')}"})

        if errors:
            return (errors, result)

        # Save changes:
        invrelmap = rel.inversion_map
        current = rel.related(self.mscid, direction=rel.INVERSE)
        changes = list()
        for inverted, mscids in result.items():
            predicate = invrelmap.get(inverted)
            if inverted in current:
                for mscid in mscids:
                    if mscid not in current[inverted]:
                        changes.append((mscid, predicate, True))
            else:
                for mscid in mscids:
                    changes.append((mscid, predicate, True))
        for inverted, mscids in current.items():
            predicate = invrelmap.get(inverted)
            if inverted in result:
                for mscid in mscids:
                    if mscid not in result[inverted]:
                        changes.append((mscid, predicate, False))
            else:
                for mscid in mscids:
                    changes.append((mscid, predicate, False))

        self._save_relations(list(), changes)

        final = {'@id': self.mscid}
        final.update(rel.related(self.mscid, direction=rel.INVERSE))
        return (errors, final)

    def save_rel_patch(self, input_data: Mapping) -> \
            Tuple[List[Mapping[str, str]], Mapping]:
        '''Validates a set of patches and applies them to the database if they
        pass validation. Returns error list and resulting record.
        '''
        if not hasattr(self, 'rolemap'):  # pragma: no cover
            raise NotImplementedError

        acceptable = dict()
        for role, info in self.rolemap.items():
            if info['direction'] == Relation.INVERSE:
                continue
            acceptable[info['predicate']] = info['accepts']

        rel = Relation()
        rel_record = rel.tb.get(Query()['@id'] == self.mscid)
        if rel_record is None:
            result = {'@id': self.mscid}
            rel_id = None
        else:
            result = dict(rel_record)
            rel_id = rel_record.doc_id

        self.cache = dict()
        errors = list()
        if not isinstance(input_data, list):
            errors.append({
                'message': "Input must be in JSON Patch format (an array of "
                           "objects).",
                'location': '$'})
            return (errors, result)

        for i, patch in enumerate(input_data):
            if not isinstance(patch, dict):
                errors.append({
                    'message': "Not a JSON object.",
                    'location': f'$[{i}]'})
                continue
            err, result = self.validate_rel_patch(result, patch, acceptable)
            for e in err:
                errors.append({
                    'message': e.get('message'),
                    'location': f"$[{i}]{e.get('location')}"})

        if errors:
            return (errors, result)

        if rel_id is None:
            rel_id = rel.tb.insert(result)
        else:
            with transaction(rel.tb) as t:
                for key in (k for k in rel_record if k not in result):
                    t.update(delete(key), doc_ids=[rel_id])
                t.update(result, doc_ids=[rel_id])

        return (errors, rel.tb.get(doc_id=rel_id))

    def save_rel_record(self, input_data: Mapping) -> \
            Tuple[List[Mapping[str, str]], Mapping]:
        '''Validates a complete relations table record and saves it to the
        database if it passes validation. Returns error list and clean record.
        '''
        errors, result = self.validate_rel_record(input_data)
        if errors:
            return (errors, result)

        rel = Relation()
        rel_record = rel.tb.get(Query()['@id'] == self.mscid)

        if rel_record is not None:
            with transaction(rel.tb) as t:
                for key in (k for k in rel_record if k not in result):
                    t.update(delete(key), doc_ids=[rel_record.doc_id])
                t.update(result, doc_ids=[rel_record.doc_id])
        else:
            rel_id = rel.tb.insert(result)

        return (errors, result)

    def validate(self, input_data: Mapping) -> Tuple[
            List[Mapping[str, str]], Mapping]:
        '''Checks input for valid keys and values. Invalid keys are removed.
        Invalid values raise an error. Valid values are cleaned. Returns a
        tuple consisting of a list of errors and the clean record.'''
        if not hasattr(self, 'schema'):  # pragma: no cover
            raise NotImplementedError

        result = self.validate_against(input_data, self.schema)
        errors = list()
        for error in result['errors']:
            errors.append({
                'message': error.get('message', ''),
                'location': f"${error.get('location', '')}",
            })

        return (errors, result['value'])

    def validate_against(self, input_data: Mapping, schema: Mapping)\
            -> Mapping[str, str]:
        '''Recursive function for performing validation against a given schema.
        '''
        errors = list()
        clean_data = dict()
        for k, d in schema.items():
            if k not in input_data:
                if d.get('required'):
                    errors.append({
                        'message': f"Missing field: {k}.",
                        'location': '',
                    })
                continue

            if 'schema' in d:
                clean_data[k] = list()

                for i, instance in enumerate(input_data[k]):
                    result = self.validate_against(instance, d['schema'])
                    for error in result['errors']:
                        errors.append({
                            'message': error.get('message', ''),
                            'location':
                                f".{k}[{i}]{error.get('location', '')}",
                        })
                    clean_data[k].append(result['value'])

                if not clean_data[k]:
                    del clean_data[k]

                continue

            validator_name = f"_do_{d.get('type', 'MISSING')}"
            validator = getattr(self, validator_name)
            validated = validator(input_data[k])
            for error in validated['errors']:
                errors.append({
                    'message': error.get('message', ''),
                    'location': f".{k}{error.get('location', '')}",
                })
            clean_data[k] = validated['value']

        return {'errors': errors, 'value': clean_data}

    def validate_rel_list(self, mscids: List[str], predicate: str, table: str)\
            -> Tuple[List[Mapping[str, str]], Mapping]:
        '''Reports errors if any mscids in the list are invalid or
        do not belong to the given table.
        '''
        errors = list()
        clean_list = list()
        for i, mscid in enumerate(mscids):
            if mscid in clean_list:
                continue
            if mscid == self.mscid:
                errors.append({
                    'message': "Cannot associate a record with itself.",
                    'location': f"[{i}]"})
                continue
            rel_record = self.cache.get(mscid, False)
            if rel_record is False:
                rel_record = Record.load_by_mscid(mscid)
                self.cache[mscid] = rel_record
            if rel_record is None:
                errors.append({
                    'message': f"Not a valid MSC ID: {mscid}.",
                    'location': f"[{i}]"})
                continue
            elif rel_record.doc_id == 0:
                errors.append({
                    'message': f"No such record: {mscid}.",
                    'location': f"[{i}]"})
                continue
            elif table and rel_record.table != table:
                errors.append({
                    'message': f"The record {mscid} cannot be used with the"
                    f" predicate {predicate}.",
                    'location': f"[{i}]"})
                continue
            clean_list.append(mscid)

        return (errors, clean_list)

    def validate_rel_patch(
        self, input_data: Mapping,
        patch: Mapping[str, str],
        acceptable: Mapping[str, str]
            ) -> Tuple[List[Mapping[str, str]], Mapping]:
        '''Parses a patch, and (if possible) applies it to the input data.
        Returns a tuple consisting of a list of errors and the resulting
        record.
        '''
        errors = list()
        output = input_data

        op = patch.get('op')
        known_ops = ['add', 'remove', 'replace', 'test']
        if op is None:
            errors.append({
                'message': "JSON object must have an ‘op’ member.",
                'location': ''})
        elif op not in known_ops:
            errors.append({
                'message': f"Supported operations are {', '.join(known_ops)}.",
                'location': '.op'})

        # Supported paths are `/predicate` (when operating on the whole list
        # of related records) or `/predicate/-` or `/predicate/<int>` (when
        # operating on a single record in the list).
        path = patch.get('path')
        if path is None:
            errors.append({
                'message': "JSON object must have a ‘path’ member.",
                'location': ''})
        else:
            m = re.match(r'/(?P<predicate>[^/]+)(?:/(?P<index>-|\d+))?', path)
            if m is None:
                errors.append({
                    'message': "The supplied path could not be parsed.",
                    'location': '.path'})
            elif m.group('predicate') not in acceptable:
                errors.append({
                    'message': f"Invalid predicate: {m.group('predicate')}."
                    f" Valid predicates: {', '.join(acceptable.keys())}.",
                    'location': '.path'})
            elif op and m.group('index') is not None:
                curr_list = output.get(m.group('predicate'))
                if op == 'add':
                    if m.group('index') != '-':
                        if int(m.group('index')) > len(curr_list):
                            errors.append({
                                'message':
                                    "Cannot add a value at that position.",
                                'location': '.path'})
                else:
                    if not curr_list:
                        errors.append({
                            'message':
                                "No values exist at that position.",
                            'location': '.path'})
                    elif m.group('index') != '-':
                        if int(m.group('index')) >= len(curr_list):
                            errors.append({
                                'message':
                                    "No value exists at that position.",
                                'location': '.path'})

        if op and op != 'remove' and 'value' not in patch:
            errors.append({
                'message': "JSON object must have a ‘value’ member when ‘op’ is"
                           f" {op}.",
                'location': ''})

        # We can only proceed if there have been no errors:
        if errors:
            return (errors, output)

        # Attempt to apply the patch.
        index = m.group('index')
        if op == 'test':
            value = patch['value']
            if index is None:
                curr_value = output.get(m.group('predicate'))
            else:
                curr_list = output.get(m.group('predicate'))
                if index == '-':
                    curr_value = curr_list[-1]
                else:
                    curr_value = curr_list[int(index)]
            if value != curr_value:
                errors.append({
                    'message':
                        f"Test failed. Current value would be {curr_value}.",
                    'location': '.value'})
        elif op == 'remove':
            if index is None:
                if m.group('predicate') not in output:
                    errors.append({
                        'message':
                            "Predicate already missing.",
                        'location': '.path'})
                else:
                    del output[m.group('predicate')]
            else:
                i = -1 if index == '-' else int(index)
                output[m.group('predicate')].pop(i)
        elif op == 'add':
            value = patch['value']
            predicate = m.group('predicate')
            if index is None:
                if not isinstance(value, list):
                    errors.append({
                        'message':
                            "Value must be a list of MSC IDs.",
                        'location': '.value'})
                else:
                    list_errors, clean_list = self.validate_rel_list(
                        value, predicate, acceptable[predicate])
                    for error in list_errors:
                        errors.append({
                            'message': error['message'],
                            'location': f".value{error['location']}"})
                    if not list_errors:
                        output[predicate] = clean_list
            else:
                if not isinstance(value, str):
                    errors.append({
                        'message': "Value must be a single MSC ID.",
                        'location': '.value'})
                else:
                    list_errors, clean_list = self.validate_rel_list(
                        [value], predicate, acceptable[predicate])
                    for error in list_errors:
                        errors.append({
                            'message': error['message'],
                            'location': '.value'})
                    if not list_errors:
                        clean_value = clean_list[0]
                        if predicate not in output:
                            output[predicate] = list()
                        i = -1 if index == '-' else int(index)
                        if i < len(output[predicate]) and i > -1:
                            output[predicate].insert(i, clean_value)
                        else:
                            output[predicate].append(clean_value)
        elif op == 'replace':
            value = patch['value']
            predicate = m.group('predicate')
            if index is None:
                if predicate not in output:
                    errors.append({
                        'message': "Predicate needs to be added.",
                        'location': '.path'})
                elif not isinstance(value, list):
                    errors.append({
                        'message':
                            "Value must be a list of MSC IDs.",
                        'location': '.value'})
                else:
                    list_errors, clean_list = self.validate_rel_list(
                        value, predicate, acceptable[predicate])
                    for error in list_errors:
                        errors.append({
                            'message': error['message'],
                            'location': f".value{error['location']}"})
                    if not list_errors:
                        output[predicate] = clean_list
            else:
                if not isinstance(value, str):
                    errors.append({
                        'message': "Value must be a single MSC ID.",
                        'location': '.value'})
                else:
                    list_errors, clean_list = self.validate_rel_list(
                        [value], predicate, acceptable[predicate])
                    for error in list_errors:
                        errors.append({
                            'message': error['message'],
                            'location': '.value'})
                    if not list_errors:
                        clean_value = clean_list[0]
                        i = -1 if index == '-' else int(index)
                        output[predicate][i] = clean_value

        return (errors, output)

    def validate_rel_record(self, input_data: Mapping) -> \
            Tuple[List[Mapping[str, str]], Mapping]:
        '''Checks validity of a set of relations. Invalid keys are removed.
        Invalid values raise an error. Valid values are cleaned. Returns a
        tuple consisting of a list of errors and the clean record.'''
        if not hasattr(self, 'rolemap'):  # pragma: no cover
            raise NotImplementedError

        acceptable = dict()
        for role, info in self.rolemap.items():
            if info['direction'] == Relation.INVERSE:
                continue
            acceptable[info['predicate']] = info['accepts']

        result = {'errors': list(), 'value': {'@id': self.mscid}}
        self.cache = dict()
        for predicate, mscids in input_data.items():

            # Validate role
            accepts = list()
            if predicate not in acceptable:
                result['errors'].append({
                    'message': f"Invalid predicate: {predicate}."
                    f" Valid predicates: {', '.join(acceptable.keys())}.",
                    'location': f".{predicate}"})
            else:
                accepts = acceptable[predicate]

            # Validate MSCIDs
            if not isinstance(mscids, list):
                result['errors'].append({
                    'message': f"Value must be a list of MSC IDs.",
                    'location': f".{predicate}"})
                continue

            if not accepts:
                continue

            list_errors, clean_list = self.validate_rel_list(
                mscids, predicate, accepts)
            if list_errors:
                for error in list_errors:
                    result['errors'].append({
                        'message': error.get('message', ''),
                        'location': f".{predicate}{error.get('location', '')}",
                    })
                continue

            result['value'][predicate] = clean_list

        errors = list()
        for error in result['errors']:
            errors.append({
                'message': error.get('message', ''),
                'location': f"${error.get('location', '')}",
            })

        return (errors, result['value'])


class Scheme(Record):
    '''Object representing a metadata scheme.'''
    table = 'm'
    series = 'scheme'
    schema = {
        'title': {
            'type': 'text',
            'useful': True},
        'description': {
            'type': 'html',
            'useful': True },
        'citation_docs': {
            'type': 'html',
            'useful': True },
        'keywords': {
            'type': 'thesaurus',
            'useful': True},
        'dataTypes': {
            'type': 'datatypes'},
        'locations': {
            'type': 'locations',
            'useful': True},
        'namespaces': {
            'type': 'namespaces',
            'optional': True},
        'identifiers': {
            'type': 'identifiers',
            'useful': True},
        'relatedEntities': {
            'type': 'relations'},
        'versions': {
            'schema': {
                'number': {
                    'type': 'versionid'},
                'title': {
                    'type': 'text'},
                'note': {
                    'type': 'html'},
                'issued': {
                    'type': 'date'},
                'available': {
                    'type': 'date'},
                'valid': {
                    'type': 'period'},
                'locations': {
                    'type': 'locations'},
                'namespaces': {
                    'type': 'namespaces'},
                'identifiers': {
                    'type': 'identifiers'},
                'samples': {
                    'schema': {
                        'url': {
                            'type': 'url'},
                        'title': {
                            'type': 'text'}}}}}}
    rolemap = {
        'parent scheme': {
            'predicate': 'parent schemes',
            'direction': Relation.FORWARD,
            'accepts': 'm'},
        'child scheme': {
            'predicate': 'parent schemes',
            'direction': Relation.INVERSE,
            'accepts': 'm'},
        'input to mapping': {
            'predicate': 'input schemes',
            'direction': Relation.INVERSE,
            'accepts': 'c'},
        'output from mapping': {
            'predicate': 'output schemes',
            'direction': Relation.INVERSE,
            'accepts': 'c'},
        'maintainer': {
            'predicate': 'maintainers',
            'direction': Relation.FORWARD,
            'accepts': 'g'},
        'funder': {
            'predicate': 'funders',
            'direction': Relation.FORWARD,
            'accepts': 'g'},
        'user': {
            'predicate': 'users',
            'direction': Relation.FORWARD,
            'accepts': 'g'},
        'tool': {
            'predicate': 'supported schemes',
            'direction': Relation.INVERSE,
            'accepts': 't'},
        'endorsement': {
            'predicate': 'endorsed schemes',
            'direction': Relation.INVERSE,
            'accepts': 'e'},
    }

    @classmethod
    def get_vocabs(cls):
        '''Gets controlled vocabularies for use as hints in unconstrained
        StringFields.'''
        vocabs = dict()

        th = get_thesaurus()
        vocabs['subjects'] = th.get_long_labels()

        return vocabs

    @classmethod
    def get_used_keywords(cls) -> List[str]:
        '''Returns a deduplicated list of subject keywords (as URIs) in use in
        the database.
        '''
        # Get list of keywords in use
        schemes_with_kw = cls.search(Query().keywords.exists())
        keywords_used = set()
        for s in schemes_with_kw:
            for kw in s['keywords']:
                keywords_used.add(kw)

        return list(keywords_used)

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def form(self):
        return SchemeForm

    @property
    def has_versions(self):
        return True

    @property
    def name(self):
        return self.get('title', "Untitled")

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
        data = self.insert_relations(data)

        # Translate keywords from URI to string
        th = get_thesaurus()
        if 'keywords' in data:
            keywords = list()
            for keyword_uri in data['keywords']:
                keywords.append(th.get_long_label(keyword_uri))
            data['keywords'] = keywords

        # Populate form:
        form = self.populate_form(data)

        # Scheme-specific form settings:
        for field in form.keywords:
            if len(field.validators) == 1:
                field.validators.append(
                    validators.AnyOf(
                        th.get_valid(),
                        'Value must be drawn from the UNESCO Thesaurus.'))
        form.parent_schemes.omit_mscid(self.mscid)
        form.child_schemes.omit_mscid(self.mscid)
        form.dataTypes.choices = Datatype.get_choices()

        return form

    def get_slug(self, *, apidata: Mapping = None, formdata: Mapping = None):
        slug = self.get('slug')
        if slug:
            return slug
        for mapping in [formdata, apidata, self]:
            if mapping is not None:
                name = mapping.get('title')
                if name:
                    return to_file_slug(name, self.search)
        return None

    def get_vform(self, index: int = None):
        # Get data from database:
        main_data = json.loads(json.dumps(self))

        # Get version info:
        data = dict()
        if index is not None:
            try:
                data = main_data.get('versions', list())[index]
            except IndexError:
                index = None
                pass

        # Populate form:
        form = self.populate_form(data, is_version=True)

        return form


class Tool(Record):
    '''Object representing a tool.'''
    table = 't'
    series = 'tool'
    schema = {
        'title': {
            'type': 'text',
            'useful': True},
        'description': {
            'type': 'html',
            'useful': True},
        'types': {
            'type': 'types'},
        'locations': {
            'type': 'locations',
            'useful': True},
        'identifiers': {
            'type': 'identifiers',
            'useful': True},
        'creators': {
            'schema': {
                'fullName': {
                    'type': 'text'},
                'givenName': {
                    'type': 'text'},
                'familyName': {
                    'type': 'text'}}},
        'relatedEntities': {
            'type': 'relations'},
        'versions': {
            'schema': {
                'number': {
                    'type': 'versionid'},
                'title': {
                    'type': 'text'},
                'note': {
                    'type': 'html'},
                'issued': {
                    'type': 'date'},
                'locations': {
                    'type': 'locations'},
                'identifiers': {
                    'type': 'identifiers'}}}}
    rolemap = {
        'supported scheme': {
            'predicate': 'supported schemes',
            'direction': Relation.FORWARD,
            'accepts': 'm'},
        'maintainer': {
            'predicate': 'maintainers',
            'direction': Relation.FORWARD,
            'accepts': 'g'},
        'funder': {
            'predicate': 'funders',
            'direction': Relation.FORWARD,
            'accepts': 'g'}}

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def form(self):
        return ToolForm

    @property
    def has_versions(self):
        return True

    @property
    def name(self):
        return self.get('title', "Untitled")

    @property
    def vform(self):
        return ToolVersionForm

    def get_form(self):
        # Get data from database:
        data = json.loads(json.dumps(self))

        # Strip out version info, this is handled separately:
        if 'versions' in data:
            del data['versions']

        # Populate with relevant relations
        data = self.insert_relations(data)

        # Populate form:
        form = self.populate_form(data)

        # Tool-specific form settings:
        form.types.choices = EntityType.get_choices(self.__class__)

        return form

    def get_slug(self, *, apidata: Mapping = None, formdata: Mapping = None):
        slug = self.get('slug')
        if slug:
            return slug
        for mapping in [formdata, apidata, self]:
            if mapping is not None:
                name = mapping.get('title')
                if name:
                    return to_file_slug(name, self.search)
        return None

    def get_vform(self, index: int = None):
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
        form = self.populate_form(data, is_version=True)

        return form


class Crosswalk(Record):
    '''Object representing a mapping.'''
    table = 'c'
    series = 'mapping'
    schema = {
        'name': {
            'type': 'text'},
        'description': {
            'type': 'html'},
        'locations': {
            'type': 'locations',
            'useful': True},
        'identifiers': {
            'type': 'identifiers',
            'useful': True},
        'creators': {
            'schema': {
                'fullName': {
                    'type': 'text'},
                'givenName': {
                    'type': 'text'},
                'familyName': {
                    'type': 'text'}}},
        'relatedEntities': {
            'type': 'relations',
            'useful': ['input scheme', 'output scheme']},
        'versions': {
            'schema': {
                'number': {
                    'type': 'versionid'},
                'note': {
                    'type': 'html'},
                'issued': {
                    'type': 'date'},
                'locations': {
                    'type': 'locations'},
                'identifiers': {
                    'type': 'identifiers'}}}}
    rolemap = {
        'input scheme': {
            'predicate': 'input schemes',
            'direction': Relation.FORWARD,
            'accepts': 'm'},
        'output scheme': {
            'predicate': 'output schemes',
            'direction': Relation.FORWARD,
            'accepts': 'm'},
        'maintainer': {
            'predicate': 'maintainers',
            'direction': Relation.FORWARD,
            'accepts': 'g'},
        'funder': {
            'predicate': 'funders',
            'direction': Relation.FORWARD,
            'accepts': 'g'}}

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def form(self):
        return CrosswalkForm

    @property
    def has_versions(self):
        return True

    @property
    def name(self):
        name = self.get('name')
        if name:
            return name

        rel = Relation()
        inputs = rel.object_records(
            subject=self.mscid, predicate="input schemes")
        outputs = rel.object_records(
            subject=self.mscid, predicate="output schemes")

        if inputs and outputs:
            return f"{inputs[0].name} to {outputs[0].name}"

        return "Unnamed"

    @property
    def vform(self):
        return CrosswalkVersionForm

    def get_form(self):
        # Get data from database:
        data = json.loads(json.dumps(self))

        # Strip out version info, this is handled separately:
        if 'versions' in data:
            del data['versions']

        # Populate with relevant relations
        data = self.insert_relations(data)

        # Populate form:
        form = self.populate_form(data)

        return form

    def get_slug(self, *, apidata: Mapping = None, formdata: Mapping = None):
        slug = self.get('slug')
        if slug:
            return slug
        for mapping in [formdata, apidata, self]:
            if mapping is not None:
                name = mapping.get('name')
                if name:
                    return to_file_slug(name, self.search)

        inputs = list()
        outputs = list()
        if formdata:
            for mscid in formdata.get('input_schemes', list()):
                inputs.append(Record.load_by_mscid(mscid))
                break
            for mscid in formdata.get('output_schemes', list()):
                outputs.append(Record.load_by_mscid(mscid))
                break
        elif apidata:
            for entity in apidata.get('relatedEntities'):
                if entity.get('role') == 'input scheme':
                    record = Record.load_by_mscid(entity.get('id'))
                    if record:
                        inputs.append(record)
                        if outputs:
                            break
                elif entity.get('role') == 'output scheme':
                    record = Record.load_by_mscid(entity.get('id'))
                    if record:
                        outputs.append(record)
                        if inputs:
                            break
        else:
            rel = Relation()
            inputs.extend(rel.object_records(
                subject=self.mscid, predicate="input schemes"))
            outputs.extend(rel.object_records(
                subject=self.mscid, predicate="output schemes"))

        if inputs and outputs:
            slug = "{}_TO_{}".format(
                '-'.join(inputs[0].slug.split('-')[:3]),
                '-'.join(outputs[0].slug.split('-')[:3]))
            i = ''
            while self.search(Query().slug == (slug + str(i))):
                if i == '':
                    i = 1
                else:
                    i += 1
            else:
                return slug

        return None

    def get_vform(self, index: int = None):
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
        form = self.populate_form(data, is_version=True)

        return form


class Group(Record):
    '''Object representing an organization.'''
    table = 'g'
    series = 'organization'
    schema = {
        'name': {
            'type': 'text',
            'useful': True},
        'description': {
            'type': 'html'},
        'citation_docs': {
            'type': 'html',
            'useful': True },
        'types': {
            'type': 'types'},
        'locations': {
            'type': 'locations'},
        'identifiers': {
            'type': 'identifiers',
            'useful': True},
        'relatedEntities': {
            'type': 'relations'}}
    rolemap = {
        'maintained scheme': {
            'predicate': 'maintainers',
            'direction': Relation.INVERSE,
            'accepts': 'm'},
        'maintained tool': {
            'predicate': 'maintainers',
            'direction': Relation.INVERSE,
            'accepts': 't'},
        'maintained mapping': {
            'predicate': 'maintainers',
            'direction': Relation.INVERSE,
            'accepts': 'c'},
        'funded scheme': {
            'predicate': 'funders',
            'direction': Relation.INVERSE,
            'accepts': 'm'},
        'funded tool': {
            'predicate': 'funders',
            'direction': Relation.INVERSE,
            'accepts': 't'},
        'funded mapping': {
            'predicate': 'funders',
            'direction': Relation.INVERSE,
            'accepts': 'c'},
        'used scheme': {
            'predicate': 'users',
            'direction': Relation.INVERSE,
            'accepts': 'm'},
        'endorsement': {
            'predicate': 'originators',
            'direction': Relation.INVERSE,
            'accepts': 'e'}}

    @classmethod
    def get_choices(cls):
        choices = [('', '')]
        for scheme in cls.search(Query().slug.exists()):
            choices.append(
                (scheme.mscid, scheme.get('name', 'Unnamed')))

        choices.sort(key=lambda k: k[1].lower())
        return choices

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def form(self):
        return GroupForm

    @property
    def name(self):
        return self.get('name')

    def get_form(self):
        # Get data from database:
        data = json.loads(json.dumps(self))

        # Populate with relevant relations
        data = self.insert_relations(data)

        # Populate form:
        form = self.populate_form(data)

        # Group-specific form settings:
        form.types.choices = EntityType.get_choices(self.__class__)

        return form

    def get_slug(self, *, apidata: Mapping = None, formdata: Mapping = None):
        slug = self.get('slug')
        if slug:
            return slug
        for mapping in [formdata, apidata, self]:
            if mapping is not None:
                name = mapping.get('name')
                if name:
                    return to_file_slug(name, self.search)
        return None


class Endorsement(Record):
    '''Object representing an endorsement.'''
    table = 'e'
    series = 'endorsement'
    schema = {
        'title': {
            'type': 'text',
            'or use role': 'originator'},
        'description': {
            'type': 'html',
            'optional': True},
        'creators': {
            'schema': {
                'fullName': {
                    'type': 'text'},
                'givenName': {
                    'type': 'text'},
                'familyName': {
                    'type': 'text'}},
            'or use role': 'originator'},
        'publication': {
            'type': 'text',
            'or use role': 'originator'},
        'issued': {
            'type': 'date',
            'or use': 'valid'},
        'valid': {
            'type': 'period',
            'or use': 'issued'},
        'locations': {
            'type': 'locations',
            'useful': True},
        'identifiers': {
            'type': 'identifiers',
            'useful': True},
        'relatedEntities': {
            'type': 'relations',
            'useful': ['endorsed scheme']}}
    rolemap = {
        'endorsed scheme': {
            'predicate': 'endorsed schemes',
            'direction': Relation.FORWARD,
            'accepts': 'm'},
        'originator': {
            'predicate': 'originators',
            'direction': Relation.FORWARD,
            'accepts': 'g'}}

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def form(self):
        return EndorsementForm

    @property
    def name(self):
        return self.get('title')

    def get_form(self):
        # Get data from database:
        data = json.loads(json.dumps(self))

        # Populate with relevant relations
        data = self.insert_relations(data)

        # Populate form:
        form = self.populate_form(data)

        return form

    def get_slug(self, *, apidata: Mapping = None, formdata: Mapping = None):
        slug = self.get('slug')
        if slug:
            return slug
        for mapping in [formdata, apidata, self]:
            if mapping is not None:
                name = mapping.get('title')
                if name:
                    return to_file_slug(name, self.search)
        return None


class Datatype(Record):
    '''Wraps items in the dataType table.'''
    table = 'datatype'
    series = 'datatype'
    schema = {
        'id': {
            'type': 'url'},
        'label': {
            'type': 'text',
            'required': True}}

    @classmethod
    def get_db(cls):
        return get_term_db()

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

    @classmethod
    def load_by_label(cls, label: str):
        db = cls.get_db()
        tb = db.table(cls.table)
        doc = tb.get(Query().label == label)

        if doc:
            return cls(value=doc, doc_id=doc.doc_id)
        return cls(value=dict(), doc_id=0)

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def form(self):
        return DatatypeForm

    @property
    def name(self):
        return self.get('label', f'Type {self.doc_id}')

    def annul(self) -> List[Mapping[str, str]]:
        '''Removes content of record. Returns a list of error messages if any
        problems arise.
        '''

        # Save the main record:
        error = self._save(dict())
        if error:
            return [{'message': error}]

        return list()

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
        '''Processes form input and saves it. Returns error message if a
        problem arises.'''

        # Save the main record:
        error = self._save(formdata)
        if error:
            return error


class VocabTerm(Document):
    '''Abstract class with common methods for the helper classes
    for different types of vocabulary terms.'''
    schema = {
        'id': {
            'type': 'vocabid',
            'required': True},
        'label': {
            'type': 'text',
            'required': True},
        'applies': {
            'type': 'series'}}

    @classmethod
    def get_db(cls):
        return get_term_db()

    @classmethod
    def get_choices(cls, filter: Type[Record] = None):
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

    @property
    def form(self):
        return VocabForm

    def get_form(self):
        # Get data from database:
        data = json.loads(json.dumps(self))

        # Populate form:
        form = self.form(data=data)

        if self.doc_id == 0:
            form.id.validators = [validators.InputRequired()]
            form.id.render_kw = {'required': True}

        return form

    def annul(self) -> List[Mapping[str, str]]:
        '''Removes content of record. Returns a list of error messages if any
        problems arise.
        '''

        # Save the main record:
        error = self._save(dict())
        if error:
            return [{'message': error}]

        return list()

    def get_overlaps(self, id: str = None):
        '''Returns a list of record types for which a term with the same ID has
        already been coined.
        '''
        overlaps = list()

        # Optional argument is given when saving input; otherwise we are
        # rendering the editing form:
        is_save = True
        if id is None:
            is_save = False
            id = self.get("id", "")

        if not id:
            return overlaps

        Q = Query()
        for value, label, selected in self.get_form().applies.iter_choices():
            if is_save and not selected:
                continue
            records = self.search(
                (Q.id == id) & (Q.applies.any([value])))
            for record in records:
                if record.doc_id != self.doc_id:
                    overlaps.append(value)
                    break
        return overlaps

    def save_gui_input(self, formdata: Mapping):
        '''Processes form input and saves it. Returns error message if a
        problem arises.
        '''

        # Override id:
        old_id = self.get('id')
        if old_id:
            formdata['id'] = old_id

        # Check for overlaps:
        overlaps = self.get_overlaps(formdata['id'])
        if overlaps:
            error = (f"A term with ID ‘{formdata['id']}’ has already been"
                     f" coined for {' and '.join(overlaps)}.")
            return error

        # Save the main record:
        error = self._save(formdata)
        if error:
            return error


class Location(VocabTerm, Record):
    '''Wraps options for link types.'''
    table = 'location'
    series = 'location'

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


class EntityType(VocabTerm, Record):
    '''Wraps options for classifying entities.'''
    table = 'type'
    series = 'type'

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


class IDScheme(VocabTerm, Record):
    '''Wraps options for recognised ID schemes.'''
    table = 'id_scheme'
    series = 'id_scheme'

    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


# Form components
# ===============
# Custom validators
# -----------------
class EmailOrURL(object):
    """Adaptation of WTForms URL validator to test mailto: URLs as well.
    """
    def __init__(self, require_tld=True):
        self.gen_regex = re.compile(
            r"^(?P<protocol>[a-z]+):.+",
            re.IGNORECASE)
        self.url_regex = re.compile(
            r"^(?P<protocol>[a-z]+):"
            r"//(?P<host>[^\/\?:]+)"
            r"(?P<port>:[0-9]+)?"
            r"(?P<path>\/.*?)?"
            r"(?P<query>\?.*)?$",
            re.IGNORECASE)
        self.email_regex = re.compile(
            r"^(?P<protocol>mailto):"
            r"(?P<user>[A-Z0-9][A-Z0-9._%+-]{0,63})@"
            r"(?P<host>(?:[A-Z0-9-]{2,63}\.)+[A-Z]{2,63})$",
            re.IGNORECASE)
        self.validate_hostname = validators.HostnameValidation(
            require_tld=require_tld,
            allow_ip=True,
        )

    def __call__(self, form, field):
        datum = field.data if field.data else ''

        if not self.gen_regex.match(datum):
            raise ValidationError(field.gettext(
                'Please provide the protocol (e.g. "http://", "mailto:").'))

        if datum.startswith('mailto:'):
            if len(datum[7:]) > 254:
                raise ValidationError(
                    'That email address is too long.')

            match = self.email_regex.match(datum)
            if not match:
                raise ValidationError(field.gettext(
                    'That email address does not look quite right.'))

        else:
            match = self.url_regex.match(datum)
            message = field.gettext(
                'That URL does not look quite right.')
            if not match:
                raise ValidationError(message)
            if not self.validate_hostname(match.group('host')):
                raise ValidationError(message)


class NamespaceURI(object):
    """Adaptation of WTForms URL validator to test for the right ending.
    """
    def __init__(self, require_tld=True):
        self.gen_regex = re.compile(
            r"^(?P<protocol>[a-z]+):.+",
            re.IGNORECASE)
        self.url_regex = re.compile(
            r"^(?P<protocol>[a-z]+):"
            r"//(?P<host>[^\/\?:]+)"
            r"(?P<port>:[0-9]+)?"
            r"(?P<path>\/.*?)?"
            r"(?P<query>\?.*)?$",
            re.IGNORECASE)
        self.validate_hostname = validators.HostnameValidation(
            require_tld=require_tld,
            allow_ip=True,
        )

    def __call__(self, form, field):
        datum = field.data if field.data else ''

        if not self.gen_regex.match(datum):
            raise ValidationError(field.gettext(
                'Please provide the protocol (e.g. "http://", "mailto:").'))

        if not datum.endswith(('/', '#')):
            raise ValidationError(field.gettext(
                'The URI must end with "/" or "#".'
            ))

        match = self.url_regex.match(datum)
        message = field.gettext(
            'That URI does not look quite right.')
        if not match:
            raise ValidationError(message)
        if not self.validate_hostname(match.group('host')):
            raise ValidationError(message)


class Optional(object):
    """This is just like the normal WTForms version but with more explicit
    Boolean logic.

    If the input is empty or (unless called with strip_whitespace=False)
    consists solely of whitespace, it stops the validation chain and removes
    any previous errors (so it can be used anywhere in the chain).
    """
    def __init__(self, strip_whitespace=True):
        if strip_whitespace:
            self.string_check = lambda s: s.strip()
        else:
            self.string_check = lambda s: s

        self.field_flags = {"optional": True}

    def __call__(self, form, field):
        if (not field.raw_data) or (
                isinstance(field.raw_data[0], str) and
                not self.string_check(field.raw_data[0])):
            field.errors[:] = []
            raise validators.StopValidation()


class RequiredIf(object):
    """A validator which makes a field required if another field is set and has
    a truthy value, and optional otherwise.
    """
    def __init__(self, other_field_list, message=None, strip_whitespace=True):
        self.other_field_list = other_field_list
        self.message = message
        if strip_whitespace:
            self.string_check = lambda s: s.strip()
        else:
            self.string_check = lambda s: s

        self.field_flags = {"optional": True}

    def __call__(self, form, field):
        other_fields_empty = True
        for other_field_name in self.other_field_list:
            other_field = form._fields.get(other_field_name)
            if other_field is None:
                raise Exception(
                    'No field named "{}" in form'.format(other_field_name))
            if bool(other_field.data):
                other_fields_empty = False
        if other_fields_empty:
            # Optional
            if (not field.raw_data) or (
                    isinstance(field.raw_data[0], str) and
                    not self.string_check(field.raw_data[0])):
                field.errors[:] = []
                raise validators.StopValidation()
        else:
            # InputRequired
            if not field.raw_data or not field.raw_data[0]:
                if self.message is None:
                    message = field.gettext('This field is required.')
                else:
                    message = self.message
                field.errors[:] = []
                raise validators.StopValidation(message)


class W3CDate(validators.Regexp):
    """Validates a W3C-formatted year, month or date syntactically, but does
    not eliminate semantically invalid dates such as `0000-02-31`.
    """
    def __init__(self, message=None):
        pattern = (
            r'^(?P<year>\d{4})'
            r'(?P<month>-0[1-9]|-1[0-2])?'
            r'(?(month)(?P<day>-0[1-9]|-[1-2][0-9]|-3[0-1])?)$')
        super(W3CDate, self).__init__(pattern, message=message)

    def __call__(self, form, field):
        message = self.message
        if message is None:
            message = field.gettext(
                "Please provide the date in yyyy-mm-dd format.")

        super(W3CDate, self).__call__(form, field, message)


# Custom widgets
# --------------
class CheckboxSelect(widgets.Select):
    '''Renders as a series of radio buttons or checkboxes instead of
    a select element with option elements.
    '''
    def __call__(self, field, **kwargs):
        kwargs.setdefault('id', field.id)
        attrs = {'id': field.id}
        html = list()
        for value, label, selected in field.iter_choices():
            html.append(self.render_option(
                field, value, label, selected, **kwargs))
        return Markup('\n'.join(html))

    def render_option(self, field, value, label, selected, **kwargs):
        if value is True:
            # Handle the special case of a 'True' value.
            value = str(value)

        choice_id = f'{field.id}-{value}'
        div_attrs = dict()
        label_attrs = {'for': choice_id}
        if 'divclass' in kwargs:
            div_attrs['class'] = kwargs.pop('divclass')
        if 'labelclass' in kwargs:
            label_attrs['class'] = kwargs.pop('labelclass')
        attrs = dict()
        if self.multiple:
            attrs['type'] = 'checkbox'
        else:
            attrs['type'] = 'radio'
        disabling = kwargs.pop('disabling', list())
        indent_size = kwargs.pop('indent', 0)
        attrs.update(dict(kwargs, id=choice_id, name=field.name, value=value))

        # If a term is both disabled and checked, this means there is an error
        # in the database, so we force disabled options to be "off".
        if attrs['value'] in disabling:
            attrs['disabled'] = True
        elif selected:
            attrs['checked'] = True
        indent = " " * indent_size
        return Markup(
            f'{indent}<div {widgets.html_params(**div_attrs)}>\n'
            f'{indent}  <input {widgets.html_params(**attrs)}>\n'
            f'{indent}  <label {widgets.html_params(**label_attrs)}>'
            f'{escape(label)}</label>\n'
            f'{indent}</div>')


# Custom fields
# ---------------
class FormFieldFixed(FormField):
    '''This does not pass on a form field prefix (unused in this application
    anyway), so the Form can include a field named ‘prefix’.
    '''
    def process(self, formdata, data=unset_value):
        if data is unset_value:
            try:
                data = self.default()
            except TypeError:
                data = self.default
            self._obj = data

        self.object_data = data

        prefix = self.name + self.separator
        if isinstance(data, dict):
            self.form = self.form_class(
                formdata=formdata, prefix=prefix, data=data)
        else:
            self.form = self.form_class(
                formdata=formdata, obj=data, prefix=prefix)


class NativeDateField(StringField):
    validators = [Optional(), W3CDate()]


class SelectRelatedField(SelectMultipleField):
    def __init__(self, label='', record: Type[Record] = Scheme, inverse=False,
                 **kwargs):
        choices = record.get_choices()
        super(SelectMultipleField, self).__init__(
            label, choices=choices, **kwargs)
        setattr(self.flags, 'inverse', inverse)
        setattr(self.flags, 'cls', record)

    def omit_mscid(self, mscid: str):
        filtered_choices = [choice for choice in self.choices
                            if choice[0] != mscid]
        self.choices = filtered_choices


class TextHTMLField(TextAreaField):
    pass


# Reusable subforms
# -----------------
class CreatorForm(Form):
    fullName = StringField('Full name')
    givenName = StringField('Given name(s)')
    familyName = StringField('Family name')


class DateRangeForm(Form):
    start = NativeDateField('from')
    end = NativeDateField('until')


class EndorsementLocationForm(Form):
    url = StringField('URL', validators=[Optional(), EmailOrURL()])
    type = HiddenField('document')


class IdentifierForm(Form):
    id = StringField('ID')
    # Setting a default value works around the WTForms (< 2.3.0) bug where
    # SelectFields return the string 'None' if no selection is made.
    scheme = SelectField(
        'ID scheme', validators=[RequiredIf(['id'])], default='')


class LocationForm(Form):
    url = StringField('URL', validators=[RequiredIf(['type']), EmailOrURL()])
    # Setting a default value works around the WTForms (< 2.3.0) bug where
    # SelectFields return the string 'None' if no selection is made.
    type = SelectField('Type', validators=[RequiredIf(['url'])], default='')


class NamespaceForm(Form):
    prefix = StringField(
        'Prefix',
        validators=[RequiredIf(['uri']), validators.Length(max=32)])
    uri = StringField(
        'URL',
        validators=[RequiredIf(['prefix']), NamespaceURI()])


class SampleForm(Form):
    title = StringField('Title', validators=[RequiredIf(['url'])])
    url = StringField('URL', validators=[RequiredIf(['title']), EmailOrURL()])


# Top-level forms
# ---------------
class SchemeForm(FlaskForm):
    title = StringField('Name of metadata scheme')
    description = TextHTMLField('Description')
    citation_docs = TextHTMLField('Citation Documentation')
    keywords = FieldList(
        StringField('Subject area', validators=[Optional()]),
        'Subject areas', min_entries=1)
    dataTypes = SelectMultipleField(
        'Types of data described by this scheme')
    locations = FieldList(
        FormField(LocationForm), 'Relevant links', min_entries=1)
    namespaces = FieldList(
        FormFieldFixed(NamespaceForm),
        'Unversioned predicate namespaces for this scheme', min_entries=1)
    identifiers = FieldList(
        FormField(IdentifierForm), 'Identifiers for this scheme',
        min_entries=1)
    parent_schemes = SelectRelatedField(
        'Parent metadata schemes', Scheme,
        description='parent schemes')
    child_schemes = SelectRelatedField(
        'Profiles of this scheme', Scheme,
        description='parent schemes', inverse=True)
    input_to_mappings = SelectRelatedField(
        'Mappings that take this scheme as input', Crosswalk,
        description='input schemes', inverse=True)
    output_from_mappings = SelectRelatedField(
        'Mappings that give this scheme as output', Crosswalk,
        description='output schemes', inverse=True)
    maintainers = SelectRelatedField(
        'Organizations that maintain this scheme', Group,
        description='maintainers')
    funders = SelectRelatedField(
        'Organizations that funded this scheme', Group,
        description='funders')
    users = SelectRelatedField(
        'Organizations that use this scheme', Group,
        description='users')
    tools = SelectRelatedField(
        'Tools that support this scheme', Tool,
        description='supported schemes', inverse=True)
    endorsements = SelectRelatedField(
        'Endorsements of this scheme', Endorsement,
        description='endorsed schemes', inverse=True)
    old_relations = HiddenField()


class SchemeVersionForm(FlaskForm):
    number = StringField(
        'Version number',
        validators=[validators.Length(max=32)])
    title = StringField('Name of metadata scheme')
    note = TextHTMLField('Note')
    issued = NativeDateField('Date published')
    available = NativeDateField('Date released as draft/proposal')
    valid = FormField(DateRangeForm, 'Date considered current')
    locations = FieldList(
        FormField(LocationForm), 'Relevant links', min_entries=1)
    namespaces = FieldList(
        FormFieldFixed(NamespaceForm),
        'Predicate namespaces for this version of the scheme', min_entries=1)
    identifiers = FieldList(
        FormField(IdentifierForm), 'Identifiers for this version of the scheme',
        min_entries=1)
    samples = FieldList(
        FormField(SampleForm), 'Sample records conforming to this scheme',
        min_entries=1)


class ToolForm(FlaskForm):
    title = StringField('Name of tool')
    description = TextHTMLField('Description')
    types = SelectMultipleField(
        'Type of tool', render_kw={'size': 5})
    locations = FieldList(
        FormField(LocationForm), 'Links to this tool', min_entries=1)
    identifiers = FieldList(
        FormField(IdentifierForm), 'Identifiers for this tool', min_entries=1)
    creators = FieldList(
        FormField(CreatorForm), 'People responsible for this tool',
        min_entries=1)
    supported_schemes = SelectRelatedField(
        'Metadata scheme(s) supported by this tool', Scheme,
        description="supported schemes")
    maintainers = SelectRelatedField(
        'Organizations that maintain this tool', Group,
        description='maintainers')
    funders = SelectRelatedField(
        'Organizations that funded this tool', Group,
        description='funders')
    old_relations = HiddenField()


class ToolVersionForm(FlaskForm):
    number = StringField(
        'Version number',
        validators=[validators.Length(max=32)])
    title = StringField('Name of tool')
    note = TextHTMLField('Note')
    issued = NativeDateField('Date published')
    locations = FieldList(
        FormField(LocationForm), 'Relevant links', min_entries=1)
    identifiers = FieldList(
        FormField(IdentifierForm), 'Identifiers for this tool',
        min_entries=1)


class CrosswalkForm(FlaskForm):
    name = StringField('Name or descriptor for mapping')
    description = TextHTMLField('Description')
    locations = FieldList(
        FormField(LocationForm), 'Links to this mapping', min_entries=1)
    identifiers = FieldList(
        FormField(IdentifierForm), 'Identifiers for this mapping',
        min_entries=1)
    creators = FieldList(
        FormField(CreatorForm), 'People responsible for this mapping',
        min_entries=1)
    input_schemes = SelectRelatedField(
        'Input metadata scheme(s)', Scheme,
        description='input schemes')
    output_schemes = SelectRelatedField(
        'Output metadata scheme(s)', Scheme,
        description='output schemes')
    maintainers = SelectRelatedField(
        'Organizations that maintain this mapping', Group,
        description='maintainers')
    funders = SelectRelatedField(
        'Organizations that funded this mapping', Group,
        description='funders')
    old_relations = HiddenField()


class CrosswalkVersionForm(FlaskForm):
    number = StringField(
        'Version number',
        validators=[validators.Length(max=32)])
    note = TextHTMLField('Note')
    issued = NativeDateField('Date published')
    locations = FieldList(
        FormField(LocationForm), 'Relevant links', min_entries=1)
    identifiers = FieldList(
        FormField(IdentifierForm), 'Identifiers for this mapping',
        min_entries=1)


class GroupForm(FlaskForm):
    name = StringField('Name of organization')
    description = TextHTMLField('Description')
    citation_docs = TextHTMLField('Citation Documentation')
    types = SelectMultipleField(
        'Type of organization')
    locations = FieldList(
        FormField(LocationForm), 'Relevant links', min_entries=1)
    identifiers = FieldList(
        FormField(IdentifierForm), 'Identifiers for this organization',
        min_entries=1)
    maintained_schemes = SelectRelatedField(
        'Schemes maintained by this organization', Scheme,
        description='maintainers', inverse=True)
    maintained_tools = SelectRelatedField(
        'Tools maintained by this organization', Tool,
        description='maintainers', inverse=True)
    maintained_mappings = SelectRelatedField(
        'Mappings maintained by this organization', Crosswalk,
        description='maintainers', inverse=True)
    funded_schemes = SelectRelatedField(
        'Schemes funded by this organization', Scheme,
        description='funders', inverse=True)
    funded_tools = SelectRelatedField(
        'Tools funded by this organization', Tool,
        description='funders', inverse=True)
    funded_mappings = SelectRelatedField(
        'Mappings funded by this organization', Crosswalk,
        description='funders', inverse=True)
    used_schemes = SelectRelatedField(
        'Schemes used by this organization', Scheme,
        description='users', inverse=True)
    endorsements = SelectRelatedField(
        'Endorsements made by this organization', Endorsement,
        description='originators', inverse=True)
    old_relations = HiddenField()


class EndorsementForm(FlaskForm):
    title = StringField('Title of the endorsement document')
    description = TextHTMLField('Description of the endorsement document')
    creators = FieldList(
        FormField(CreatorForm), 'Authors of the endorsement document',
        min_entries=1)
    publication = StringField(
        'Other bibliographic information (excluding date)')
    issued = NativeDateField('Endorsement date')
    valid = FormField(DateRangeForm, 'Date considered current')
    locations = FieldList(
        FormField(EndorsementLocationForm), 'Links to this endorsement',
        min_entries=1)
    identifiers = FieldList(
        FormField(IdentifierForm), 'Identifiers for this endorsement',
        min_entries=1)
    endorsed_schemes = SelectRelatedField(
        'Endorsed schemes', Scheme,
        description='endorsed schemes')
    originators = SelectRelatedField(
        'Endorsing organizations', Group,
        description='originators')
    old_relations = HiddenField()


class DatatypeForm(FlaskForm):
    id = StringField(
        'URL identifying this type of data',
        validators=[Optional(), EmailOrURL()])
    label = StringField(
        'Descriptor for this type of data',
        validators=[validators.InputRequired()])


class VocabForm(FlaskForm):
    id = StringField(
        'Database value',
        validators=[validators.Length(max=64)])
    label = StringField(
        'Displayed value',
        validators=[validators.InputRequired()])
    applies = SelectMultipleField(
        'Applies to',
        choices=[
            (Scheme.series, Scheme.series),
            (Tool.series, Tool.series),
            (Crosswalk.series, Crosswalk.series),
            (Endorsement.series, Endorsement.series),
            (Group.series, Group.series)],
        widget=CheckboxSelect(multiple=True))


# Utility functions
# =================
def get_data_db():
    if 'data_db' not in g:
        g.data_db = TinyDB(
            current_app.config['MAIN_DATABASE_PATH'],
            storage=JSONStorageWithGit,
            indent=1,
            ensure_ascii=False)

    return g.data_db


def get_term_db():
    if 'term_db' not in g:
        g.term_db = TinyDB(
            current_app.config['TERM_DATABASE_PATH'],
            storage=JSONStorageWithGit,
            indent=1,
            ensure_ascii=False)

    return g.term_db


def get_table_order():
    '''Provides a mapping between table names and the order in which they are
    defined in this file, for the purposes of consistent sorting.'''
    if 'table_order' not in g:
        g.table_order = dict()
        for i, subcls in enumerate(Record.__subclasses__()):
            g.table_order[subcls.table] = i

    return g.table_order


def get_safe_pad():
    if 'safe_pad' not in g:
        safe_pad = 100
        data_db = get_data_db()
        for t in data_db.tables():
            tbl = data_db.table(t)
            while len(tbl) > safe_pad:
                safe_pad *= 10
        g.safe_pad = 10 * safe_pad

    return g.safe_pad


def sortval(mscid: str) -> int:
    '''Converts an MSCID into a numeric value to aid sorting.'''
    table = mscid[mp_len:mp_len + 1]
    number = mscid[mp_len + 1:]
    table_order = get_table_order()
    safe_pad = get_safe_pad()

    sort_value = (safe_pad * table_order.get(table, 99)) + int(number)
    return sort_value


def strip_tags(string: str) -> str:
    '''Ensure only safe tags are included in string.'''

    # Check for tags that must have their contents removed:
    for tag in disallowed_tagblocks:
        matches = re.finditer(
            r'<' + tag + r'( [^>])?>.*?</' + tag + r'\s*>',
            string,
            re.DOTALL)
        for m in matches:
            string = string.replace(m.group(0), '')

    # Check matched tags:
    matches = re.finditer(
        r'<(?P<close>/)?(?P<tag>\w+)(?P<attrib> [^>]*)?>',
        string,
        re.DOTALL)
    seen = list()
    for m in matches:
        if m.group(0) in seen:
            continue
        repl = ''
        if m.group('tag') in allowed_tags:
            repl += '<'
            if m.group('close'):
                repl += '/'
            repl += m.group("tag")
            attribs = m.group('attrib')
            while attribs:
                a = re.search(
                    r''' (?P<attr>[-\w]+)='''
                    r'''(?:(?P<v1>\w+)|"(?P<v2>[^"]*)"|'(?P<v3>[^']*)')''',
                    attribs)
                if not a:
                    attribs = ''
                    continue
                if a.group('attr') in allowed_tags[m.group('tag')]:
                    val = (a.group("v1") if a.group("v1") else (
                        a.group("v2") if a.group("v2") is not None else
                        a.group("v3")))
                    repl += f' {a.group("attr")}="{val}"'
                attribs = attribs.replace(a.group(0), '')
            repl += '>'
        string = string.replace(m.group(0), repl)
        seen.append(m.group(0))
    return string


# Routes
# ======
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
        return redirect(url_for('main.edit_record', table=table, number=0))

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
        if error:
            flash(error, 'error')
            return redirect(
                url_for('main.edit_record', table=table, number=number))
        else:
            if number:
                # Editing an existing record
                flash('Successfully updated record.', 'success')
            else:
                # Adding a new record
                flash('Successfully added record.', 'success')
            return redirect(
                url_for('main.display', table=table, number=record.doc_id))
    elif record.has_versions:
        flash("Fill out information here that applies to all versions."
              " You can add/edit information about specific versions after"
              " saving your changes.", 'info')
    if form.errors:
        if 'csrf_token' in form.errors.keys():
            msg = ('Could not save changes as your form session has expired.'
                   ' Please try again.')
        else:
            msg = ('Could not save changes as there {:/was an error/were N'
                   ' errors}. See below for details.'
                   .format(Pluralizer(len(form.errors))))
        flash(msg, 'error')
        for field, errors in form.errors.items():
            if len(errors) > 0:
                if isinstance(errors[0], dict):
                    # Subform
                    for subform in errors:
                        for subfield, suberrors in subform.items():
                            for f in form[field]:
                                f[subfield].errors = clean_error_list(
                                    f[subfield])
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
        return redirect(url_for('main.edit_record', table=table, number=0))

    if index is not None and index >= len(record.get('versions', list())):
        flash("You are trying to update a version that doesn't exist."
              "Try adding this new one instead.", 'error')
        return redirect(url_for(
            'main.edit_version', table=table, number=number))

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

        # Save form data to database
        error = record.save_gui_vinput(form_data, index=index)
        if index is None:
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
                    url_for('main.display', table=table, number=number))
        else:
            # Editing an existing record
            if error:
                flash(error, 'error')
                return redirect(
                    url_for('main.edit_version', series=table, number=number,
                            index=index))
            else:
                flash('Successfully updated version.', 'success')
                return redirect(
                    url_for('main.display', table=table, number=number))
    if form.errors:
        if 'csrf_token' in form.errors.keys():
            msg = ('Could not save changes as your form session has expired.'
                   ' Please try again.')
        else:
            msg = ('Could not save changes as there {:/was an error/were N'
                   ' errors}. See below for details.'
                   .format(Pluralizer(len(form.errors))))
        flash(msg, 'error')
        for field, errors in form.errors.items():
            if len(errors) > 0:
                if isinstance(errors[0], dict):
                    # Subform
                    for subform in errors:
                        for subfield, suberrors in subform.items():
                            for f in form[field]:
                                f[subfield].errors = clean_error_list(
                                    f[subfield])
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

    if number == 0:
        form['id'].validators = [validators.InputRequired()]

    # Processing the request
    if request.method == 'POST' and form.validate():
        form_data = form.data
        # Save form data to database
        error = record.save_gui_input(form_data)
        if number:
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
        if 'csrf_token' in form.errors.keys():
            msg = ('Could not save changes as your form session has expired.'
                   ' Please try again.')
        else:
            msg = ('Could not save changes as there {:/was an error/were N'
                   ' errors}. See below for details.'
                   .format(Pluralizer(len(form.errors))))
        flash(msg, 'error')
        for field, errors in form.errors.items():
            if len(errors) > 0:
                if isinstance(errors[0], dict):
                    # Subform
                    for subform in errors:
                        for subfield, suberrors in subform.items():
                            for f in form[field]:
                                f[subfield].errors = clean_error_list(
                                    f[subfield])
                else:
                    # Simple field
                    form[field].errors = clean_error_list(form[field])

    overlaps = list() if vocab == 'datatype' else record.get_overlaps()
    return render_template(
        f"edit-{vocab}.html", form=form, doc_id=number, overlaps=overlaps)


@bp.route('/msc/<string(length=1):table><int:number>')
@bp.route('/msc/<string(length=1):table><int:number>/<field>')
def display(table, number, field=None, api=False):
    # Look up record to edit, or get new:
    record = Record.load(number, table)

    # Abort if series or number was wrong:
    if (not record) or record.doc_id == 0:
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
                print(f"WARNING display: No keyword for {keyword_uri}.")
        record['keywords'] = keywords

    # Objectify data types:
    if 'dataTypes' in record:
        datatypes = list()
        for dt_mscid in record['dataTypes']:
            datatype = Datatype.load_by_mscid(dt_mscid)
            if datatype:
                datatypes.append(datatype)
        record['dataTypes'] = datatypes

    # If the record has version information, interpret the associated dates.
    versions = None
    if 'versions' in record:
        versions = list()
        # Give each version an index of where it comes in the database
        for index in range(len(record['versions'])):
            record['versions'][index]['index'] = index
        for v in record['versions']:
            this_version = v.copy()
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
            print(f'WARNING: Record {mscid} is missing a version date.')
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
                'parent schemes', 'input schemes', 'output schemes']):
            scheme_scheme_fields.append(field.name)
        if field.flags.inverse:
            others = rel.subject_records(
                predicate=field.description, object=record.mscid,
                filter=field.flags.cls)
        else:
            others = rel.object_records(
                subject=record.mscid, predicate=field.description)
        if others:
            # In some cases we need information about further relationships:
            if field.name == 'input_to_mappings':
                for crosswalk in others:
                    crosswalk['output_schemes'] = rel.object_records(
                        subject=crosswalk.mscid, predicate='output schemes')
            elif field.name == 'output_from_mappings':
                for crosswalk in others:
                    crosswalk['input_schemes'] = rel.object_records(
                        subject=crosswalk.mscid, predicate='input schemes')
            elif field.name == 'endorsements':
                if field.description == 'originators':
                    for endorsement in others:
                        endorsement['endorsed_schemes'] = rel.object_records(
                            subject=endorsement.mscid,
                            predicate='endorsed schemes')
                elif field.description == 'endorsed schemes':
                    for endorsement in others:
                        endorsement['originators'] = rel.object_records(
                            subject=endorsement.mscid, predicate='originators')
            relations[field.name] = others

    # We add some helper logic where relations to other schemes are grouped
    # under a single heading.
    params = dict()
    if table == 'm':
        for field in scheme_scheme_fields:
            if field in relations:
                params['hasRelatedSchemes'] = True
                break
        else:
            params['hasRelatedSchemes'] = False
    elif table == 'c':
        params['hasRelatedGroups'] = (
            'maintainers' in relations or 'funders' in relations or
            'creators' in record)
    elif table == 'g':
        records_seen = {
            'schemes': dict(), 'tools': dict(), 'mappings': dict()}
        relrec = dict()
        relids = dict()
        for ser in records_seen.keys():
            for relation, records in relations.items():
                if relation.endswith(ser):
                    for r in records:
                        records_seen[ser][r.mscid] = r
                relids[relation] = [k.mscid for k in records]
            relrec[ser] = dict()
            for id, r in records_seen[ser].items():
                key = None
                if id in relids.get(f'funded_{ser}', list()):
                    if id in relids.get(f'maintained_{ser}', list()):
                        if id in relids.get(f'used_{ser}', list()):
                            key = 'funds, maintains, and uses'
                        else:
                            key = 'funds and maintains'
                    elif id in relids.get(f'used_{ser}', list()):
                        key = 'funds and uses'
                    else:
                        key = 'funds'
                else:
                    if id in relids.get(f'maintained_{ser}', list()):
                        if id in relids.get(f'used_{ser}', list()):
                            key = 'maintains and uses'
                        else:
                            key = 'maintains'
                    elif id in relids.get(f'used_{ser}', list()):
                        key = 'uses'
                if key:
                    if key not in relrec[ser]:
                        relrec[ser][key] = list()
                    relrec[ser][key].append(r)
        for ser in relrec.keys():
            for key in relrec[ser].keys():
                relrec[ser][key].sort(key=lambda k: k.name)
            params[f'related_{ser}'] = relrec[ser]

    # We are ready to display the information.
    return render_template(
        f"display-{record.series}.html", record=record, versions=versions,
        relations=relations, **params)
