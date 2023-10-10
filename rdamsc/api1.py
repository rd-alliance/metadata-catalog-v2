# Dependencies
# ============
# Standard
# --------
import typing as t

# Non-standard
# ------------
from flask import (
    abort,
    Blueprint,
    jsonify,
    url_for,
)
from flask_cors import cross_origin

# Local
# -----
from .records import (
    MainTableID,
    Relation,
    Record,
    Scheme,
    mscid_prefix,
)
from .vocab import get_thesaurus

bp = Blueprint("api", __name__)
api_version = "1.0.0"


# Handy functions
# ===============
def as_response_item(record: Record, route: str):
    """Wraps item data in a response object, tailored for `route`."""
    # Embellish record
    data = embellish_record(record, route=route)

    return data


def as_response_page(records: t.List[Record], link: str, route: str):
    """Wraps list of MSCIDs in a response object."""

    items = list()
    for record in records:
        if record:
            items.append(
                {
                    "id": int(record.doc_id),
                    "slug": record.slug,
                }
            )

    key_map = {
        "api/m": "metadata-schemes",
        "api/g": "organizations",
        "api/t": "tools",
        "api/c": "mappings",
        "api/e": "endorsements",
    }

    key = None
    for endpoint in key_map.keys():
        if link.endswith(endpoint):
            key = key_map[endpoint]
            break
    else:
        abort(404)

    response = {key: items}

    return response


def embellish_record(record: Record, route: str = ".get_record"):
    """Adds convenience fields and related entities to a record."""

    # Form MSC ID
    mscid = record.mscid

    # Add convenience fields
    if "identifiers" not in record:
        record["identifiers"] = list()
    record["identifiers"].insert(0, {"id": mscid, "scheme": "RDA-MSCWG"})

    # Add related entities
    related_entities = list()
    rel = Relation()
    relations = rel.related_records(mscid=mscid, direction=rel.FORWARD)
    for role in sorted(relations.keys()):
        for entity in relations[role]:
            related_entity = {
                "id": entity.mscid,
                "role": role[:-1],  # convert to singular
            }
            related_entities.append(related_entity)
    if related_entities:
        n = len(mscid_prefix)
        record["relatedEntities"] = sorted(
            related_entities, key=lambda k: k["id"][:n] + k["id"][n:].zfill(5)
        )

    # Translate keywords
    if "keywords" in record:
        thes = get_thesaurus()
        old_keywords = record["keywords"][:]
        record["keywords"] = list()
        for kw_url in old_keywords:
            kw_label = thes.get_label(kw_url)
            if kw_label:
                record["keywords"].append(kw_label)
        record["keywords"].sort()

    # Translate dataTypes
    if "dataTypes" in record:
        old_datatypes = record["dataTypes"][:]
        record["dataTypes"] = list()
        for dt_id in old_datatypes:
            dt = Record.load_by_mscid(dt_id)
            dt_summary = dict()
            label = dt.get("label")
            if label:
                dt_summary["label"] = label
            url = dt.get("id")
            if url:
                dt_summary["url"] = url
            record["dataTypes"].append(dt_summary)

    # Translate valid date
    if "versions" in record:
        old_versions = record["versions"][:]
        record["versions"] = list()
        for vn in old_versions:
            if "valid" in vn:
                old_valid = vn["valid"].copy()
                vn["valid"] = old_valid.get("start", "")
                if "end" in old_valid:
                    vn["valid"] += f"/{old_valid['end']}"
            record["versions"].append(vn)

    return record


# Routes
# ======
@bp.route("/<any(m, g, t, c, e):table>", methods=["GET"])
def get_records(table: MainTableID):
    """Returns all records from the given table in abbreviated form:
    ```
    {table: [{id: int, slug: str}]}
    ```
    """
    record_cls = Record.get_class_by_table(table)
    if record_cls is None:  # pragma: no cover
        abort(404)
    records = [k for k in record_cls.all() if k]

    # Return result
    return jsonify(
        as_response_page(
            records, url_for(".get_records", table=table, _external=True), ".get_record"
        )
    )


@bp.route("/<any(m, g, t, c, e):table>" "<int:number>", methods=["GET"])
def get_record(table: MainTableID, number: int):
    """Returns given record."""
    record = Record.load(number, table)

    # Abort if series or number was wrong:
    if (not record) or record.doc_id == 0:
        abort(404)

    # Return result
    return jsonify(as_response_item(record, ".get_record"))


@bp.route("/subject-index", methods=["GET"])
@cross_origin()
def get_subject_tree():
    """Returns tree of used keywords."""
    th = get_thesaurus()
    keywords_used = Scheme.get_used_keywords()
    tree = th.get_tree(keywords_used)

    # Return result
    return jsonify(tree)
