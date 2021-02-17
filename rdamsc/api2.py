# Dependencies
# ============
# Standard
# --------
import json
import re
import os
import math
from typing import (
    List,
    Mapping,
    Tuple,
    Type,
)

# Non-standard
# ------------
from tinydb.database import Document
from flask import (
    abort,
    Blueprint,
    g,
    jsonify,
    make_response,
    request,
    url_for,
)
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth, MultiAuth

# Local
# -----
from .records import (
    Relation,
    Record,
    Scheme,
    mscid_prefix,
)
from .vocab import Thesaurus
from .users import ApiUser, get_user_db

bp = Blueprint('api2', __name__)
basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth('Bearer')
multi_auth = MultiAuth(basic_auth, token_auth)
api_version = "2.0.0"


# Handy functions
# ===============
def embellish_record(record: Document, with_embedded=False):
    '''Add convenience fields and related entities to a record.'''

    # Form MSC ID
    mscid = record.mscid

    # Add convenience fields
    record['mscid'] = mscid
    record['uri'] = url_for(
        '.get_record', table=record.table, number=record.doc_id,
        _external=True)

    # Is this a controlled term?
    if len(record.table) > 1:
        return record

    # Add related entities
    related_entities = list()
    seen_mscids = dict()
    rel = Relation()
    relations = rel.related_records(mscid=mscid)
    for role in sorted(relations.keys()):
        for entity in relations[role]:
            related_entity = {
                'id': entity.mscid,
                'role': role[:-1],  # convert to singular
            }
            if with_embedded:
                related_entity['data'] = seen_mscids.get(entity.mscid)
                if related_entity['data'] is None:
                    full_entity = embellish_record(entity)
                    related_entity['data'] = full_entity
                    seen_mscids[entity.mscid] = full_entity
            related_entities.append(related_entity)
    if related_entities:
        record['relatedEntities'] = related_entities

    return record


def embellish_record_fully(record: Document):
    '''Convenience wrapper around embellish_record ensuring related entities
    are embedded.
    '''
    return embellish_record(record, with_embedded=True)


def embellish_relation(record: Mapping, route='.get_relation'):
    '''Embellishes a relationship or inverse relationship record.'''
    mscid = record['@id']
    n = len(mscid_prefix)
    table = mscid[n:n+1]
    number = mscid[n+1:]
    record['uri'] = url_for(
        route, table=table, number=number, _external=True)
    return record


def embellish_inv_relation(record: Mapping):
    '''Embellishes a relationship or inverse relationship record.'''
    return embellish_relation(record, route='.get_inv_relation')


def convert_thesaurus(record: Mapping):
    '''Converts an internal thesaurus entry into a SKOS Concept.'''
    th = Thesaurus()
    return th.get_concept(record.get('uri').split('/')[-1])


def do_not_embellish(record: Mapping):
    '''Dummy function, no-op.'''
    return record


def as_response_item(record: Mapping, callback=embellish_record):
    '''Embellishes a record using the callback function, then wraps it in a
    response object.
    '''

    # Embellish record
    data = callback(record)

    response = {
        'apiVersion': api_version,
        'data': data,
    }
    return response


def as_response_page(records: List[Mapping], link: str,
                     page_size=10, start: int=None, page: int=None,
                     callback=embellish_record):
    '''Wraps list of records in a response object representing a page of
    `page_size` items, starting with item number `start` or page number `page`
    (both counting from 1) The base URL for adjacent requests should be given
    as `link`. Individual records are embellished with the callback function
    before being added to the list of returned records; this should take the
    record as its positional argument.
    '''
    total_pages = math.ceil(len(records) / page_size)
    if start is not None:
        start_index = start
        if start_index > len(records) or start_index < 1:
            abort(404)
        page_index = math.floor(start_index / page_size) + 1
    elif page is not None:
        page_index = page
        if page_index > total_pages or page_index < 1:
            abort(404)
        start_index = ((page_index - 1) * page_size) + 1
    else:
        start_index = 1
        page_index = 1

    items = list()
    for record in records[start_index-1:start_index+page_size-1]:
        items.append(callback(record))

    response = {
        'apiVersion': api_version,
        'data': {
            'itemsPerPage': page_size,
            'currentItemCount': len(items),
            'startIndex': start_index,
            'totalItems': len(records),
            'pageIndex': page_index,
            'totalPages': total_pages,
        }
    }

    if (start_index - 1) % page_size > 0:
        response['data']['totalPages'] += 1

    if page and not start:
        if page_index < response['data']['totalPages']:
            response['data']['nextLink'] = (
                f"{link}?page={page + 1}&pageSize={page_size}")
        if page_index > 1:
            response['data']['previousLink'] = (
                f"{link}?page={page - 1}&pageSize={page_size}")
    else:
        if start_index + page_size <= len(records):
            response['data']['nextLink'] = (
                f"{link}?start={start_index + page_size}&pageSize={page_size}")
        if start_index > 1:
            prev_start = start_index - page_size
            if prev_start < 1:
                response['data']['previousLink'] = (
                    f"{link}?start=1&pageSize={start_index - 1}")
            else:
                response['data']['previousLink'] = (
                    f"{link}?start={prev_start}&pageSize={page_size}")

    response['data']['items'] = items
    return response


@basic_auth.verify_password
def verify_password(username, password):
    user = ApiUser.load_by_userid(username)
    if user.is_active and user.verify_password(password):
        return user
    return None


@token_auth.verify_token
def verify_token(token):
    user = ApiUser.load_by_token(token)
    if user.doc_id:
        return user
    return None


# Routes
# ======
@bp.route(
    '/<any(m, g, t, c, e, datatype, location, type, id_scheme):table>',
    methods=['GET'])
def get_records(table):
    '''Return a page of records from the given table.'''
    # TODO: Note we currently do a new search each time and discard items
    # outside the page's item range. It would be better to implement a cache
    # token so the search results could be saved for, say, an hour and
    # traversed robustly using the token.
    for record_cls in Record.__subclasses__():
        if table != record_cls.table:
            continue
        records = record_cls.all()
        break
    else:  # pragma: no cover
        abort(404)

    # Get paging parameters
    start_raw = request.values.get('start')
    start = int(start_raw) if start_raw else None

    page_raw = request.values.get('page')
    page = int(page_raw) if page_raw else None

    page_size = int(request.values.get('pageSize', 10))

    # Return result
    return jsonify(as_response_page(
        records, url_for('.get_records', table=table, _external=True),
        page_size=page_size, start=start, page=page))


@bp.route(
    '/<any(m, g, t, c, e, datatype, location, type, id_scheme):table>'
    '<int:number>',
    methods=['GET'])
def get_record(table, number):
    '''Return given record.'''
    record = Record.load(number, table)

    # Abort if series or number was wrong:
    if record is None or record.doc_id == 0:
        abort(404)

    # Return result
    return jsonify(as_response_item(record, callback=embellish_record_fully))


@bp.route('/rel', methods=['GET'])
def get_relations():
    '''Return a page of records from the relations table.'''
    # TODO: Note we currently do a new search each time and discard items
    # outside the page's item range. It would be better to implement a cache
    # token so the search results could be saved for, say, an hour and
    # traversed robustly using the token.
    rel = Relation()
    rel_records = rel.tb.all()

    # Get paging parameters:
    start_raw = request.values.get('start')
    start = int(start_raw) if start_raw else None

    page_raw = request.values.get('page')
    page = int(page_raw) if page_raw else None

    page_size = int(request.values.get('pageSize', 10))

    # Return result
    return jsonify(as_response_page(
        rel_records, url_for('.get_relations'), page_size=page_size,
        start=start, page=page, callback=embellish_relation))


@bp.route('/rel/<string(length=1):table><int:number>', methods=['GET'])
def get_relation(table, number):
    '''Return forward relations for the given record.'''
    # Abort if series or number was wrong:
    base_record = Record.load(number, table)
    if base_record is None or base_record.doc_id == 0:
        abort(404)

    rel = Relation()
    mscid = f"{mscid_prefix}{table}{number}"
    rel_record = {'@id': mscid}
    rel_record.update(rel.related(mscid, direction=rel.FORWARD))

    # Return result
    return jsonify(as_response_item(rel_record, callback=embellish_relation))


@bp.route('/invrel', methods=['GET'])
def get_inv_relations():
    '''Return a page of records generated from inverting the relations table.
    '''
    # TODO: Note we currently do a new search each time and discard items
    # outside the page's item range. It would be better to implement a cache
    # token so the search results could be saved for, say, an hour and
    # traversed robustly using the token.

    rel = Relation()
    mscids = rel.objects()
    rel_records = list()

    for mscid in mscids:
        rel_record = {'@id': mscid}
        rel_record.update(rel.related(mscid, direction=rel.INVERSE))
        rel_records.append(rel_record)

    # Get paging parameters:
    start_raw = request.values.get('start')
    start = int(start_raw) if start_raw else None

    page_raw = request.values.get('page')
    page = int(page_raw) if page_raw else None

    page_size = int(request.values.get('pageSize', 10))

    # Return result
    return jsonify(as_response_page(
        rel_records, url_for('.get_inv_relations'), page_size=page_size,
        start=start, page=page, callback=embellish_inv_relation))


@bp.route('/invrel/<string(length=1):table><int:number>', methods=['GET'])
def get_inv_relation(table, number):
    '''Return inverse relations for the given record.'''
    # Abort if series or number was wrong:
    base_record = Record.load(number, table)
    if base_record is None or base_record.doc_id == 0:
        abort(404)

    rel = Relation()
    mscid = f"{mscid_prefix}{table}{number}"
    rel_record = {'@id': mscid}
    rel_record.update(rel.related(mscid, direction=rel.INVERSE))

    # Return result
    return jsonify(as_response_item(rel_record, callback=embellish_inv_relation))


@bp.route('/thesaurus')
def get_thesaurus_scheme():
    '''Return SKOS record for MSC Thesaurus Scheme.'''
    th = Thesaurus()

    return jsonify(as_response_item(th.as_jsonld, callback=do_not_embellish))


@bp.route('/thesaurus/<any(domain, subdomain, concept):level><int:number>')
def get_thesaurus_concept(level, number):
    '''Return SKOS record for MSC Thesaurus Concept.'''
    th = Thesaurus()

    # Get requested level of detail:
    form = request.values.get('form', 'concept')

    # Generate record
    concept = th.get_concept(
        f"{level}{number}", recursive=(form == 'tree'))

    if concept is None:
        abort(404)

    return jsonify(as_response_item(concept, callback=do_not_embellish))


@bp.route('/thesaurus/concepts')
def get_thesaurus_concepts():
    '''Get list of concepts from the MSC Thesaurus.'''
    th = Thesaurus()

    # Get paging parameters
    start_raw = request.values.get('start')
    start = int(start_raw) if start_raw else None

    page_raw = request.values.get('page')
    page = int(page_raw) if page_raw else None

    page_size = int(request.values.get('pageSize', 10))

    # Return result
    return jsonify(as_response_page(
        th.entries, url_for('.get_thesaurus_concepts'), page_size=page_size,
        start=start, page=page, callback=convert_thesaurus))


@bp.route('/thesaurus/concepts/used')
def get_thesaurus_concepts_used():
    '''Get list of concepts from the MSC Thesaurus that are in use.'''
    th = Thesaurus()
    used = Scheme.get_used_keywords()

    entries = [entry for entry in th.entries if entry.get('uri') in used]

    # Get paging parameters
    start_raw = request.values.get('start')
    start = int(start_raw) if start_raw else None

    page_raw = request.values.get('page')
    page = int(page_raw) if page_raw else None

    page_size = int(request.values.get('pageSize', 10))

    # Return result
    return jsonify(as_response_page(
        entries, url_for('.get_thesaurus_concepts_used'),
        page_size=page_size, start=start, page=page,
        callback=convert_thesaurus))


@bp.route('/user/token', methods=['GET'])
@basic_auth.login_required
def get_auth_token():
    user = basic_auth.current_user()
    token = user.generate_auth_token()
    return jsonify({
        'apiVersion': api_version,
        'token': token.decode('ascii')})


@bp.route('/user/reset-password', methods=['POST'])
@multi_auth.login_required
def reset_password():
    user = multi_auth.current_user()
    response = {
        'apiVersion': api_version,
        'username': user.get('userid'),
        'password_reset': False
    }
    if request.json is None:
        abort(make_response((response, 400)))
    new_password = request.json.get('new_password', '')
    if len(new_password) < 8:
        abort(make_response((response, 400)))
    response['password_reset'] = user.hash_password(new_password)
    if response['password_reset']:
        return jsonify(response)
    else:
        abort(make_response((response, 400)))
