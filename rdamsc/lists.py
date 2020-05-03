# Dependencies
# ============
# Standard
# --------
from typing import List, Mapping

# Non-standard
# ------------
import requests
# See https://flask.palletsprojects.com/en/1.1.x/
from flask import (
    abort, Blueprint, render_template, url_for
)

# Local
# -----
from .records import Record, Relation, Scheme

bp = Blueprint('list', __name__)


def get_scheme_tree(records: List[Scheme]) -> Mapping[str, str]:
    '''Takes list of parent schemes and returns tree suitable for use with the
    contents template.'''
    records.sort(key=lambda k: k.name)
    tree = list()
    rel = Relation()
    for record in records:
        children = rel.subject_records("parent scheme", record.mscid)
        node = {
            'name': record.name,
            'url': url_for(
                'main.display', table=record.table, number=record.doc_id),
            'children': get_scheme_tree(children)
            }
        tree.append(node)
    return tree


# List of standards
# =================
@bp.route('/<string:series>-index')
def record_index(series=None):
    '''The contents template takes a 'tree' variable, which is a list of
    dictionaries, each with keys 'name' (human-readable name) and 'url'
    (Catalog page URL). The dictionary represents a node and if the node has
    children, the dictionary has a 'children' key, the value of which is
    another tree.
    '''
    if series is None:
        abort(404)
    elif series == "scheme":
        # Listing metadata schemes.
        # Get all of them:
        records = Scheme.all()

        # Get blacklist of child schemes
        rel = Relation()
        children = rel.subjects(predicate="parent scheme")

        # Assemble tree of records that are not on blacklist:
        tree = get_scheme_tree([
            record for record in records if record.mscid not in children])
        return render_template(
            'contents.html', title='Index of metadata standards', tree=tree)

    # Listing another type of record.
    for record_cls in Record.__subclasses__():
        if series == record_cls.series:
            # Get all of them in alphabetical order:
            records = record_cls.all()
            records.sort(key=lambda k: k.name)
            tree = [{
                'name': record.name,
                'url': url_for(
                    'main.display', table=record.table, number=record.doc_id)
                } for record in records]
            return render_template(
                'contents.html', title=f'Index of {series}s', tree=tree)
            break
    else:
        abort(404)
