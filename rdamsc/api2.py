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

# Non-standard
# ------------
from flask import (
    abort,
    Blueprint,
    g,
    jsonify,
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
def as_response_item(data: Mapping):
    '''Wraps item data in a response object.'''
    response = {
        'apiVersion': api_version,
        'data': data,
    }
    return response


def embellish_record(record: Record, with_embedded=False):
    '''Add convenience fields and related entities to a record.'''
    # Form MSC ID
    mscid = record.mscid

    # Add convenience fields
    record['mscid'] = mscid
    record['uri'] = url_for(
        'api2.get_record', table=record.table, number=record.doc_id,
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
    for record_cls in table.__subclasses__():
        if table != record_cls.table:
            continue
        records = record_cls.all()

    else:
        abort(404)


@bp.route('/api2/<string(length=1):table><int:number>', methods=['GET'])
def get_record(table, number):
    # Look up record to edit, or get new:
    record = Record.load(number, table)

    # Abort if series or number was wrong:
    if record is None or record.doc_id == 0:
        abort(404)

    # Embellish record
    data = embellish_record(record, with_embedded=True)

    # Return result
    return jsonify(as_response_item(data))
