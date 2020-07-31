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
)

bp = Blueprint('api2', __name__)
api_version = "2.0.0"


# Handy functions
# ===============
def as_response_item(record: Mapping):
    '''Wraps item data in a response object.'''
    # Embellish record
    data = embellish_record(record, with_embedded=True)

    response = {
        'apiVersion': api_version,
        'data': data,
    }
    return response


def as_response_page(records: List[Mapping], link: str, page_size=10,
                     start: int=None, page: int=None):
    '''Wraps list of records in a response object representing a page of
    `page_size` items, starting with item number `start` or page number `page`
    (both counting from 1) The base URL for adjacent requests should be given
    as `link`.
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
        items.append(embellish_record(record))

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


def embellish_record(record: Record, with_embedded=False):
    '''Add convenience fields and related entities to a record.'''
    # Form MSC ID
    mscid = record.mscid

    # Add convenience fields
    record['mscid'] = mscid
    record['uri'] = url_for(
        '.get_record', table=record.table, number=record.doc_id,
        _external=True)

    # Add related entities
    related_entities = list()
    seen_mscids = dict()
    rel = Relation()
    relations = rel.related_records(mscid=mscid)
    for role in sorted(relations.keys()):
        for entity in relations[role]:
            related_entity = {
                'id': entity.mscid,
                'role': role,
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


# Routes
# ======
@bp.route('/api2/<string(length=1):table>', methods=['GET'])
def get_records(table):
    '''Return a page of records from the given table.'''
    # TODO: Note we currently do a new search each time and discard items
    # outside the page's item range. It would be better to implement a cache
    # token so the search results could be saved for, say, an hour and
    # traversed robustly while the token is used and valid.
    for record_cls in Record.__subclasses__():
        if table != record_cls.table:
            continue
        records = record_cls.all()
        break
    else:
        abort(404)

    # Get paging parameters
    start_raw = request.values.get('start')
    start = int(start_raw) if start_raw else None

    page_raw = request.values.get('page')
    page = int(page_raw) if page_raw else None

    page_size = int(request.values.get('pageSize', 10))

    # Return result
    return jsonify(as_response_page(
        records, url_for('.get_records', table=table),
        page_size=page_size, start=start, page=page))


@bp.route('/api2/<string(length=1):table><int:number>', methods=['GET'])
def get_record(table, number):
    '''Return given record.'''
    record = Record.load(number, table)

    # Abort if series or number was wrong:
    if record is None or record.doc_id == 0:
        abort(404)

    # Return result
    return jsonify(as_response_item(record))
