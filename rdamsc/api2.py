# Dependencies
# ============
# Standard
# --------
from collections import deque, defaultdict
import math
import re
from typing import (
    List,
    Mapping,
    Tuple,
    Union,
)

# Non-standard
# ------------
from flask import (
    abort,
    Blueprint,
    jsonify,
    make_response,
    redirect,
    request,
    url_for,
)
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth, MultiAuth
from tinydb.database import Document

# Local
# -----
from .records import (
    Relation,
    Record,
    Scheme,
    mscid_prefix,
    sortval,
)
from .users import ApiUser
from .vocab import Thesaurus

bp = Blueprint('api2', __name__)
basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth('Bearer')
multi_auth = MultiAuth(basic_auth, token_auth)
api_version = "2.1.0"


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
    related_entities = record.get_related_entities()
    if related_entities:
        seen_mscids = dict()
        record['relatedEntities'] = list()
        for related_entity in related_entities:
            if with_embedded:
                related_entity['data'] = seen_mscids.get(related_entity['id'])
                if related_entity['data'] is None:
                    entity = Record.load_by_mscid(related_entity['id'])
                    full_entity = embellish_record(entity)
                    related_entity['data'] = full_entity
                    seen_mscids[entity.mscid] = full_entity
            record['relatedEntities'].append(related_entity)

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
    table = mscid[n:n + 1]
    number = mscid[n + 1:]
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
                     page_size=10, start: int = None, page: int = None,
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
    for record in records[start_index - 1:start_index + page_size - 1]:
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


def parse_query(filter: str):
    '''Normalises query string into a form suitable for passing to the
    `passes_filter()` function. Raises ValueError if parsing fails.

    INPUT SYNTAX

    Literal search through all fields:

    - Noun
    - "Noun"
    - "Noun phrase"

    Literal search in one field:

    - title:Noun
    - title:"Noun"
    - title:"Noun phrase"

    Boolean (all caps)

    - OR (default for adjacent terms)
    - AND
    - NOT

    Grouping

    - (Noun Verb), (Noun OR Verb)
    - title:(Noun Verb) = (title:Noun OR title:Verb)

    Wildcard searching

    - * (for 0-n characters)
    - ? (for 0-1 characters)

    Inclusive date ranges:

    - date:[2002-01-01 TO 2003-01-01]

    Above special characters can be escaped with backslash.

    OUTPUT

    Query structure is recursive. Innermost value is of the form

    - (field, VALUE)
    - (field, (MIN, MAX))

    where VALUE can be str, int, re.Pattern, and MIN and MAX can be str
    or int (representing inclusive limits). The field can be None to
    match across all available fields. These innermost values can
    be embedded in lists providing Boolean operations:

    - ["NOT", CONDITION]
    - ["OR", CONDITION, CONDITION, ...]
    - ["AND", CONDITION, CONDITION, ...]
    '''
    # Sanity check
    if len(filter) > 256:
        raise ValueError("Too long.")

    # State constants
    WORD = 1
    NOTWORD = 2
    ANDWORD = 3
    RANGE = 4
    TORANGE = 5
    QUOTE = 6
    RQUOTE = 7
    ESC = 8

    # Where tokens get put after processing:
    working = defaultdict(list)
    working[0] = list()

    # Field to which matching will be restricted:
    field = None
    field_level = 1

    # Level of Boolean complexity:
    level = 1

    # Repeated code
    def push_item(item):
        if state[-1] == WORD and len(working[level - 1]) == 1:
            working[level - 1].insert(0, "OR")
        elif state[-1] in [ANDWORD, NOTWORD]:
            state.pop()
            state.append(WORD)
        elif len(working[level - 1]) > 1:
            if working[level - 1][0] != "OR":
                raise ValueError(
                    "Boolean expression missing parentheses."
                )
        working[level - 1].append(item)

    def check_type(word: str) -> Union[re.Pattern, str]:
        '''If wildcards are present, converts to a regex. Otherwise
        returns the string unaltered. Database currently contains
        only strings, otherwise coercion to int (say) would happen
        here.'''
        if ("\x91" not in word and "\x92" not in word):
            return word
        safe_word = re.escape(word)
        safe_word = safe_word.replace("\x91", ".*")
        safe_word = safe_word.replace("\x92", ".?")
        return re.compile(safe_word)

    def unwild(word: str) -> str:
        return word.replace("\x91", "*").replace("\x92", "?")

    # Level of processing:
    state = [WORD]
    tokens = list(filter)
    for token in tokens:
        if state[-1] == ESC:
            state.pop()
            working[level].append(token)
            continue
        if token == "\\":
            state.append(ESC)
            continue

        if token == '"':
            if state[-1] in [WORD, ANDWORD, NOTWORD]:
                state.append(QUOTE)
                continue
            elif state[-1] in [RANGE, TORANGE]:
                state.append(RQUOTE)
                continue
            elif state[-1] in [QUOTE, RQUOTE]:
                state.pop()
                continue

        if token == "[" and state[-1] in [WORD, ANDWORD, NOTWORD]:
            level += 1
            state.append(RANGE)
            continue
        if token == "]":
            if state[-1] == TORANGE:
                # if level < 2:
                #     raise ValueError("Unmatched square brackets.")
                if working[level]:
                    word = "".join(working[level])
                    working[level] = list()
                    working[level - 1].append(word)
                level -= 1
                state.pop()
                if len(working[level]) != 2:
                    raise ValueError("Invalid range specification.")
                item = tuple(working[level])
                working[level] = list()
                push_item((field, item))
                if field_level == level:
                    field = None
                continue
            elif state[-1] == RANGE:
                raise ValueError("Invalid range specification.")
            elif state[-1] in [WORD, ANDWORD, NOTWORD]:
                raise ValueError("Unmatched square brackets.")

        if token == "(" and state[-1] in [WORD, ANDWORD, NOTWORD]:
            level += 1
            state.append(WORD)
            continue
        if token == ")" and state[-1] in [WORD, ANDWORD, NOTWORD]:
            if level < 2:
                raise ValueError("Unmatched parentheses.")
            if working[level]:
                word = check_type("".join(working[level]))
                working[level] = list()
                push_item((field, word))
            level -= 1
            state.pop()
            item = working[level]
            working[level] = list()
            push_item(item)
            if field_level == level:
                field = None
            continue

        if (
            token == ":"
            and state[-1] in [WORD, ANDWORD, NOTWORD]
            and working[level]
        ):
            word = unwild("".join(working[level]))
            working[level] = list()
            field = word
            field_level = level
            continue

        if token == " ":
            if state[-1] in [WORD, ANDWORD, NOTWORD]:
                if working[level]:
                    word = "".join(working[level])
                    working[level] = list()
                    if word in ["OR", "AND"]:
                        if word == "AND":
                            state.pop()
                            state.append(ANDWORD)
                        if len(working[level - 1]) == 0:
                            raise ValueError(
                                "Boolean expression missing first value."
                            )
                        elif len(working[level - 1]) == 1:
                            working[level - 1].insert(0, word)
                        else:
                            if working[level - 1][0] != word:
                                raise ValueError(
                                    "Boolean expression missing parentheses."
                                )
                        continue
                    elif word == "NOT":
                        state.pop()
                        state.append(NOTWORD)
                        if len(working[level - 1]):
                            raise ValueError(
                                "Boolean expression missing parentheses."
                            )
                        working[level - 1].append(word)
                        continue

                    word = check_type(word)
                    push_item((field, word))
                    if field_level == level:
                        field = None
                continue
            elif state[-1] == RANGE:
                if working[level]:
                    word = "".join(working[level])
                    working[level] = list()
                    if len(working[level - 1]) == 1:
                        if word == "TO":
                            state.pop()
                            state.append(TORANGE)
                            continue
                        raise ValueError("Invalid range specification.")
                    working[level - 1].append(word)
                continue
            elif state[-1] == TORANGE:
                if working[level]:
                    word = "".join(working[level])
                    working[level] = list()
                    if len(working[level - 1]) != 1:
                        raise ValueError("Invalid range specification.")
                    working[level - 1].append(word)
                continue

        if state[-1] not in [RANGE, TORANGE]:
            if token == "*":
                token = "\x91"
            elif token == "?":
                token = "\x92"

        working[level].append(token)

    if level > 1:
        if state[-1] in [RANGE, TORANGE]:
            raise ValueError("Unmatched square brackets.")
        else:
            raise ValueError("Unmatched parentheses.")
    if state[-1] in [WORD, ANDWORD, NOTWORD] and working[level]:
        word = check_type("".join(working[level]))
        if word in ["OR", "AND", "NOT"]:
            raise ValueError("Incomplete Boolean expression.")
        working[level] = list()
        push_item((field, word))
    elif state[-1] == QUOTE:
        raise ValueError("Unmatched quote marks.")
    elif state[-1] == ESC:
        raise ValueError("Dangling escape character.")

    if len(working[0]) == 1:
        return working[0][0]

    return working[0]


def extract_values(record: Mapping, fieldpath: deque) -> List:
    '''Gets all values within a record at the given fieldpath address.
    For example, for a fieldpath of ['genus', 'species'], gets the
    value at record['genus']['species'] or [v['species'] for v in
    record['genus']]. If the fieldpath is empty, gets all ‘leaf’
    values in the record.

    If the record does not have a value at the fieldpath address,
    raises KeyError. This allows passes_filter() to return immediately.
    '''
    values = list()
    if fieldpath:
        field = fieldpath.popleft()
        value = record[field]
        if isinstance(value, dict):
            return extract_values(value, fieldpath)
        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                key_error = True
                for v in value:
                    try:
                        values.extend(extract_values(v, fieldpath.copy()))
                        key_error = False
                    except KeyError:
                        pass
                if key_error:
                    raise KeyError(fieldpath[0])
                return values
            return value

        # Literal value
        if fieldpath:
            raise KeyError("Literal value has no further keys.")
        return [value]

    for field, value in record.items():
        if isinstance(value, dict):
            values.extend(extract_values(value, fieldpath))
        elif isinstance(value, list):
            if value and isinstance(value[0], dict):
                for v in value:
                    values.extend(extract_values(v, fieldpath))
            else:
                values.extend(value)
        else:
            # Literal value
            values.append(value)

    return values


def passes_filter(
    record: Record,
    filter: Union[List, Tuple],
    exact: bool = False,
) -> bool:
    '''Determines whether the record passes the filter (True) or
    is filtered out (False).

    - str: match means filter value equals or occurs in field value
    - re.Pattern: match means pattern occurs somewhere in field value
    - int, float, etc.: match means filter value == field value
    - int range: match means min <= field value <= max
    - str range: match means min <= field value for as many characters
      as they both possess, and field value <= max for as many characters
      as they both possess. This is optimised for ISO date strings, so
      2000-01-01 <= 2000 <= 2000-12 works as intended.
    '''
    if isinstance(filter, list):
        if filter[0] == "NOT":
            return not passes_filter(record, filter[1])
        if filter[0] == "AND":
            for f in filter[1:]:
                if not passes_filter(record, f):
                    return False
            return True
        if filter[0] == "OR":
            for f in filter[1:]:
                if passes_filter(record, f):
                    return True
            return False
        raise ValueError("Unknown Boolean operation.")  # pragma: no cover

    if not isinstance(filter, tuple):  # pragma: no cover
        raise ValueError("Filter must be List or Tuple.")

    # We get a list of values to test, such that if any one of them
    # matches filter[1], the record passes the given filter.
    fieldpath = deque(filter[0].split(".")) if filter[0] else deque()
    try:
        values_to_test = extract_values(record, fieldpath)
    except KeyError:
        return False

    test_cls = type(filter[1])

    if test_cls == str:
        for v in [d for d in values_to_test if isinstance(d, str)]:
            if exact:
                if filter[1].casefold() == v.casefold():
                    return True
            else:
                if filter[1].casefold() in v.casefold():
                    return True
        return False

    if test_cls == re.Pattern:
        for v in [d for d in values_to_test if isinstance(d, str)]:
            if exact:
                if filter[1].match(v):
                    return True
            else:
                if filter[1].search(v):
                    return True
        return False

    if test_cls == tuple:
        if isinstance(filter[1][0], int):
            for v in [d for d in values_to_test if isinstance(d, int)]:
                if filter[1][0] <= v <= filter[1][1]:
                    return True
            return False

        if isinstance(filter[1][0], str):
            len_start = len(filter[1][0])
            len_end = len(filter[1][1])
            for v in [d for d in values_to_test if isinstance(d, str)]:
                len_test = len(v)
                cmp_start = min(len_start, len_test)
                cmp_end = min(len_end, len_test)
                if (
                    filter[1][0][0:cmp_start] <= v[0:cmp_start]
                    and v[0:cmp_end] <= filter[1][1][0:cmp_end]
                ):
                    return True
            return False

        return False

    for v in values_to_test:
        if isinstance(v, test_cls):
            if v == filter[1]:
                return True
    return False


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
    record_cls = Record.get_class_by_table(table)
    if record_cls is None:  # pragma: no cover
        abort(404)
    records = [k for k in record_cls.all() if k]

    # Get filter parameter
    filter = request.values.get('q')
    if filter:
        try:
            parsed_filter = parse_query(filter)
        except ValueError as e:
            response = {
                'apiVersion': api_version,
                'error': {
                    'message': f"Bad q parameter: {e}",
                }
            }
            return jsonify(response), 400

        filtered = [k for k in records if passes_filter(k, parsed_filter)]
        records = filtered

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
    if (not record) or record.doc_id == 0:
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
    rel_records.sort(key=lambda k: sortval(k.get('@id')))

    # Get filter parameter
    filter = request.values.get('q')
    if filter:
        try:
            parsed_filter = parse_query(filter)
        except ValueError as e:
            response = {
                'apiVersion': api_version,
                'error': {
                    'message': f"Bad q parameter: {e}",
                }
            }
            return jsonify(response), 400

        filtered = [
            k for k in rel_records
            if passes_filter(k, parsed_filter, exact=True)
        ]
        rel_records = filtered

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
    if (not base_record) or base_record.doc_id == 0:
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

    # Get filter parameter
    filter = request.values.get('q')
    if filter:
        try:
            parsed_filter = parse_query(filter)
        except ValueError as e:
            response = {
                'apiVersion': api_version,
                'error': {
                    'message': f"Bad q parameter: {e}",
                }
            }
            return jsonify(response), 400

        filtered = [
            k for k in rel_records
            if passes_filter(k, parsed_filter, exact=True)
        ]
        rel_records = filtered

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
    if (not base_record) or base_record.doc_id == 0:
        abort(404)

    rel = Relation()
    mscid = f"{mscid_prefix}{table}{number}"
    rel_record = {'@id': mscid}
    rel_record.update(rel.related(mscid, direction=rel.INVERSE))

    # Return result
    return jsonify(as_response_item(
        rel_record, callback=embellish_inv_relation))


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


@bp.route(
    '/<any(m, g, t, c, e, datatype, location, type, id_scheme):table>',
    methods=['POST'])
@bp.route(
    '/<any(m, g, t, c, e, datatype, location, type, id_scheme):table>'
    '<int:number>',
    methods=['PUT'])
@multi_auth.login_required
def set_record(table, number=0):
    '''Adds a record to the database and returns it.'''
    # Look up record to edit, or get new:
    record = Record.load(number, table)
    print(f"Looking up record {table}{number}...")

    # If number is wrong, we reinforce the point by redirecting:
    if record.doc_id != number:
        print(f"Expecting {number}, got {record.doc_id}.")
        return redirect(url_for('api2.set_record', table=table, number=None))

    # Get input:
    data = request.get_json(force=True)

    # Handle any errors:
    errors = record.save_api_input(data)
    if errors:
        response = {
            'apiVersion': api_version,
            'error': {
                'message': errors[0]['message'],
                'errors': errors
            }
        }
        return jsonify(response), 400

    # Return report:
    record.reload()
    response = as_response_item(record, callback=embellish_record_fully)
    response['meta'] = {
        'conformance': record.conformance,
    }

    return jsonify(response)


@bp.route(
    '/<any(m, g, t, c, e, datatype, location, type, id_scheme):table>'
    '<int:number>',
    methods=['DELETE'])
@multi_auth.login_required
def annul_record(table, number=0):
    '''Adds a record to the database and returns it.'''
    # Look up record to edit, or get new:
    record = Record.load(number, table)

    # Abort if table or number was wrong:
    if record is None or record.doc_id != number:
        abort(404)

    # Handle any errors:
    errors = record.annul()
    if errors:
        response = {
            'apiVersion': api_version,
            'error': {
                'message': errors[0]['message'],
                'errors': errors
            }
        }
        return jsonify(response), 400

    # Otherwise return an empty success message:
    return '', (204)


@bp.route(
    '/rel/<any(m, t, c, e):table><int:number>', methods=['POST', 'PUT'])
@multi_auth.login_required
def set_relation(table, number):
    '''Add or replace entire forward relation table for a main entity.'''
    record = Record.load(number, table)

    # Abort if table or number was wrong:
    if record is None or record.doc_id != number:
        abort(404)

    # Get input:
    data = request.get_json(force=True)

    # Handle any errors:
    errors, result = record.save_rel_record(data)
    if errors:
        response = {
            'apiVersion': api_version,
            'error': {
                'message': errors[0]['message'],
                'errors': errors
            }
        }
        return jsonify(response), 400

    # Return report:
    response = as_response_item(result, callback=do_not_embellish)
    return jsonify(response)


@bp.route(
    '/rel/<any(m, t, c, e):table><int:number>', methods=['PATCH'])
@multi_auth.login_required
def patch_relation(table, number):
    record = Record.load(number, table)

    # Abort if table or number was wrong:
    if record is None or record.doc_id != number:
        abort(404)

    # Get input:
    data = request.get_json(force=True)

    # Handle any errors:
    errors, result = record.save_rel_patch(data)
    if errors:
        response = {
            'apiVersion': api_version,
            'error': {
                'message': errors[0]['message'],
                'errors': errors
            }
        }
        return jsonify(response), 400

    # Return report:
    response = as_response_item(result, callback=do_not_embellish)
    return jsonify(response)


@bp.route(
    '/invrel/<any(m, g):table><int:number>', methods=['PATCH'])
@multi_auth.login_required
def patch_inv_relation(table, number):
    record = Record.load(number, table)

    # Abort if table or number was wrong:
    if record is None or record.doc_id != number:
        abort(404)

    # Get input:
    data = request.get_json(force=True)

    # Handle any errors:
    errors, result = record.save_invrel_patch(data)
    if errors:
        response = {
            'apiVersion': api_version,
            'error': {
                'message': errors[0]['message'],
                'errors': errors
            }
        }
        return jsonify(response), 400

    # Return report:
    response = as_response_item(result, callback=do_not_embellish)
    return jsonify(response)
