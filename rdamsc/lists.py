# Dependencies
# ============
# Standard
# --------
import typing as t

# Non-standard
# ------------
from flask import Blueprint, abort, current_app, render_template, url_for

# Local
# -----
from .records import Record, Relation, Scheme, VocabTerm
from .vocab import get_thesaurus

bp = Blueprint("list", __name__)
RoleLabel = t.Literal[
    "parent schemes",
    "supported schemes",
    "input schemes",
    "output schemes",
    "endorsed schemes",
    "maintainers",
    "funders",
    "users",
    "originators",
]


def noop(*args) -> None:
    """Null operation."""
    pass


def add_mscids(collection: t.Set[str], records: t.Iterable[Record]) -> None:
    """Adds MSCIDs of records to the given set."""
    for record in records:
        collection.add(record.mscid)


def get_scheme_tree(
    records: list[Scheme],
    descendent_ids: t.Optional[t.Set[str]] = None,
    seen_so_far: t.Optional[list[str]] = None,
) -> list[dict[str, str | list]]:
    """Takes list of parent schemes and returns tree suitable for use with the
    contents template.

    If provided, populates `descendent_ids` with the MSCIDs of all records
    descending from the given list of parent schemes.
    """
    add_children = noop if descendent_ids is None else add_mscids
    if seen_so_far is None:
        seen_so_far = list()

    tree = list()
    rel = Relation()
    records.sort(key=lambda k: k.name.lower())
    for record in records:
        if record.mscid in seen_so_far:
            current_app.logger.warning(
                f"parent/child recursion error detected for {record.mscid}."
            )
            return tree
        children = rel.subject_records("parent schemes", record.mscid)
        add_children(descendent_ids, children)
        node = {
            "name": record.name,
            "url": url_for("main.display", table=record.table, number=record.doc_id),
            "children": get_scheme_tree(
                children,
                descendent_ids=descendent_ids,
                seen_so_far=seen_so_far + [record.mscid],
            ),
        }
        tree.append(node)
    return tree


# List of standards
# =================
@bp.route(
    '/<string:series>-index/<any("parent schemes", "supported schemes",'
    ' "input schemes", "output schemes", "endorsed schemes", maintainers,'
    " funders, users, originators):role>"
)
@bp.route("/<string:series>-index")
def record_index(series: str, role: RoleLabel = None):
    """The contents template takes a 'tree' variable, which is a list of
    dictionaries, each with keys 'name' (human-readable name) and 'url'
    (Catalog page URL). The dictionary represents a node and if the node has
    children, the dictionary has a 'children' key, the value of which is
    another tree.
    """
    # Happily, this works for the English labels in use:
    heading = f"{series}s"
    if series == "scheme" and role is None:
        # Listing metadata schemes.
        rel = Relation()

        heading = "metadata standards"
        records = Scheme.all()

        # Get blacklist of child schemes
        children = rel.subjects(predicate="parent schemes")
        children_seen = set()

        # Assemble tree of records that are not on blacklist:
        tree = get_scheme_tree(
            [record for record in records if record and record.mscid not in children],
            descendent_ids=children_seen,
        )

        # Check for records excluded because of parent/child looping:
        children_unseen = [v for v in children if v not in children_seen]
        if children_unseen:
            tree.extend(
                get_scheme_tree([Scheme.load_by_mscid(v) for v in children_unseen])
            )
            tree.sort(key=lambda d: d["name"].lower())

        return render_template("contents.html", title=f"Index of {heading}", tree=tree)

    # Abort if series is a vocabulary item:
    elif series == "datatype" or series in [
        c.series for c in VocabTerm.__subclasses__()
    ]:
        abort(404)

    # Listing another type of record.
    for record_cls in Record.__subclasses__():
        if series == record_cls.series:
            # Get all of them in alphabetical order:
            if role:
                if role.endswith("schemes"):
                    if series != "scheme":
                        abort(404)
                elif series != "organization":
                    abort(404)
                heading = role
                if role == "originators":
                    heading = "endorsing organizations"
                rel = Relation()
                records = rel.object_records(predicate=role)
            else:
                records = [k for k in record_cls.all() if k]
            records.sort(key=lambda k: k.name)
            tree = [
                {
                    "name": record.name,
                    "url": url_for(
                        "main.display", table=record.table, number=record.doc_id
                    ),
                }
                for record in records
                if record
            ]
            return render_template(
                "contents.html", title=f"Index of {heading}", tree=tree
            )
    else:
        abort(404)


# Subject index
# =============
@bp.route("/subject-index")
def subject_index():
    th = get_thesaurus()
    keywords_used = Scheme.get_used_keywords()
    tree = th.get_tree(keywords_used)
    return render_template("contents.html", title="Index of subjects", tree=tree)
