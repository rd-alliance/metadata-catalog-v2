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
    request,
    url_for,
)


# Local
# -----
from .records import (
    Relation,
    Record,
    Scheme,
    mscid_prefix,
)
from .vocab import Thesaurus

bp = Blueprint('api', __name__)
api_version = "1.0.0"


# Handy functions
# ===============
def as_response_item(record: Mapping, route: str):
    '''Wraps item data in a response object, tailored for `route`.'''
    # Embellish record
    data = embellish_record(record, route=route)

    return data


def as_response_page(records: List[Mapping], link: str, route: str):
    '''Wraps list of MSCIDs in a response object.'''

    items = list()
    for record in records:
        if record:
            items.append({
                'id': int(record.doc_id),
                'slug': record.slug,
            })

    key_map = {
        'api/m': 'metadata-schemes',
        'api/g': 'organizations',
        'api/t': 'tools',
        'api/c': 'mappings',
        'api/e': 'endorsements',
    }

    key = None
    for endpoint in key_map.keys():
        if link.endswith(endpoint):
            key = key_map[endpoint]
            break
    else:
        abort(404)

    response = {
        key: items
    }

    return response


def embellish_record(record: Document, route='.get_record'):
    '''Add convenience fields and related entities to a record.'''

    # Form MSC ID
    mscid = record.mscid

    # Add convenience fields
    if 'identifiers' not in record:
        record['identifiers'] = list()
    record['identifiers'].insert(0, {
        'id': mscid,
        'scheme': 'RDA-MSCWG'})

    # Is this a controlled term?
    if len(record.table) > 1:
        return record

    # Add related entities
    related_entities = list()
    seen_mscids = dict()
    rel = Relation()
    relations = rel.related_records(mscid=mscid, direction=rel.FORWARD)
    for role in sorted(relations.keys()):
        for entity in relations[role]:
            related_entity = {
                'id': entity.mscid,
                'role': role[:-1],  # convert to singular
            }
            related_entities.append(related_entity)
    if related_entities:
        n = len(mscid_prefix)
        record['relatedEntities'] = sorted(
            related_entities, key=lambda k: k['id'][:n] + k['id'][n:].zfill(5))

    # Translate keywords
    if 'keywords' in record:
        thes = Thesaurus()
        old_keywords = record['keywords'][:]
        record['keywords'] = list()
        for kw_url in old_keywords:
            kw_label = thes.get_label(kw_url)
            if kw_label:
                record['keywords'].append(kw_label)
        record['keywords'].sort()

    # Translate dataTypes
    if 'dataTypes' in record:
        old_datatypes = record['dataTypes'][:]
        record['dataTypes'] = list()
        for dt_id in old_datatypes:
            dt = Record.load_by_mscid(dt_id)
            dt_summary = dict()
            label = dt.get('label')
            if label:
                dt_summary['label'] = label
            url = dt.get('id')
            if url:
                dt_summary['url'] = url
            record['dataTypes'].append(dt_summary)

    # Translate valid date
    if 'versions' in record:
        old_versions = record['versions'][:]
        record['versions'] = list()
        for vn in old_versions:
            if 'valid' in vn:
                old_valid = vn['valid'].copy()
                vn['valid'] = old_valid.get('start', '')
                if 'end' in old_valid:
                    vn['valid'] += f"/{old_valid['end']}"
            record['versions'].append(vn)

    return record


# Routes
# ======
@bp.route(
    '/<any(m, g, t, c, e):table>',
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
        '.get_record'))


@bp.route(
    '/<any(m, g, t, c, e):table>'
    '<int:number>',
    methods=['GET'])
def get_record(table, number):
    '''Return given record.'''
    record = Record.load(number, table)

    # Abort if series or number was wrong:
    if record is None or record.doc_id == 0:
        abort(404)

    # Return result
    return jsonify(as_response_item(record, '.get_record'))
