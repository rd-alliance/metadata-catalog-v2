# Dependencies
# ============
# Standard
# --------
from collections.abc import Iterable
from typing import Literal

# Non-standard
# ------------
from flask import Blueprint, abort, current_app, render_template, url_for

# Local
# -----
from .records import Record, Relation, Scheme, VocabTerm
from .vocab import TreeNode, get_thesaurus

bp = Blueprint("list", __name__)
RoleLabel = Literal[
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


class IDAdder:
    """Optimization to avoid repeatedly testing if we're collecting IDs."""

    def __init__(self, ids: set[str] | None = None):
        if ids is None:
            self.add = self.discard_value
        else:
            self.add = self.add_value
            self.set = ids

    def discard_value(self, records: Iterable[Record]):
        pass

    def add_value(self, records: Iterable[Record]):
        for record in records:
            self.set.add(record.mscid)


def get_scheme_tree(
    records: list[Record],
    id_adder: IDAdder,
    seen_so_far: set[str] | None = None,
) -> list[TreeNode]:
    """Takes list of parent schemes and returns tree suitable for use with the
    contents template.

    If provided, populates `id_adder` with the MSCIDs of all records
    descending from the given list of parent schemes.
    """
    if seen_so_far is None:
        seen_so_far = set()

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
        id_adder.add(children)
        seen_so_far.add(record.mscid)
        node = TreeNode(
            uri=url_for("main.display", table=record.table, number=record.doc_id),
            label=record.name,
            children=get_scheme_tree(
                children,
                id_adder,
                seen_so_far=seen_so_far,
            ),
        )
        tree.append(node)
    return tree


# List of main records
# ====================
@bp.route(
    '/<string:series>-index/<any("parent schemes", "supported schemes",'
    ' "input schemes", "output schemes", "endorsed schemes", maintainers,'
    " funders, users, originators):role>"
)
@bp.route("/<string:series>-index")
def record_index(series: str, role: RoleLabel | None = None):
    """Renders index pages for the main records.

    The contents template takes a 'tree' variable, which is a list of
    dictionaries, each with keys 'label' (human-readable name) and 'uri'
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

        # Get blocklist of child schemes
        children = rel.subjects(predicate="parent schemes")
        children_seen = set()

        # Assemble tree of records that are not on blocklist:
        tree = get_scheme_tree(
            [record for record in records if record and record.mscid not in children],
            IDAdder(children_seen),
        )

        # Check for records excluded because of parent/child looping:
        children_unseen = [v for v in children if v not in children_seen]
        if children_unseen:
            tree.extend(
                get_scheme_tree(
                    [r for v in children_unseen if (r := Scheme.load_by_mscid(v))],
                    IDAdder(),
                )
            )
            tree.sort(key=lambda d: d["label"].lower())

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
                TreeNode(
                    uri=url_for(
                        "main.display", table=record.table, number=record.doc_id
                    ),
                    label=record.name,
                )
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
    """Renders index page for subject search pages.

    The contents template takes a 'tree' variable, which is a list of
    dictionaries, each with keys 'label' (human-readable name) and 'uri'
    (Catalog page URL). The dictionary represents a node and if the node has
    children, the dictionary has a 'children' key, the value of which is
    another tree.
    """
    current_app.logger.debug("Getting thesaurus...")
    th = get_thesaurus()
    current_app.logger.debug("Getting used keywords...")
    keywords_used = Scheme.get_used_keywords()
    current_app.logger.debug("Transforming to tree...")
    tree = th.get_tree(keywords_used)
    current_app.logger.debug("Rendering page...")
    return render_template("contents.html", title="Index of subjects", tree=tree)
