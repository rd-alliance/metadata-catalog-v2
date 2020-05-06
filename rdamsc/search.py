# Dependencies
# ============
# Non-standard
# ------------
# See https://flask.palletsprojects.com/en/1.1.x/
from flask import (
    abort, Blueprint, current_app, flash, g, redirect, render_template,
    request, session, url_for
)
# See http://tinydb.readthedocs.io/
from tinydb import Query

# Local
# -----
from .records import Datatype, Group, Relation, Scheme
from .utils import Pluralizer
from .vocab import get_thesaurus

bp = Blueprint('search', __name__)

@bp.route('/search', methods=['GET', 'POST'])
def scheme_search(isGui=None):
    return render_template(
        'search-form.html', form=None, titles=list(),
        subjects=list(), ids=list(), funders=list(),
        dataTypes=list())

@bp.route('/subject/<subject>')
def subject(subject):
    '''Show search results for a given subject. Implicitly searches for
    ancestor and descendent terms as well.'''

    # Get search terms to use
    th = get_thesaurus()
    uris = th.get_branch(subject)
    if not uris:
        flash(f'The subject "{subject}" was not found in the thesaurus.', 'error')
        return render_template('search-results.html', title=subject)

    # Search for schemes
    results = Scheme.search(Query().keywords.any(uris))
    no_of_hits = len(results)
    if no_of_hits:
        flash('Found {:N scheme/s}.'.format(Pluralizer(no_of_hits)))
        results.sort(key=lambda k: k.name.lower())
    else:
        flash('No schemes have been associated with this subject area.'
              ' Would you like to see some <a href="{}">generic schemes</a>?'
              .format(url_for('subject', subject='Multidisciplinary')),
              'error')
    return render_template(
        'search-results.html', title=subject, results=results)


@bp.route('/datatype/datatype<int:number>')
def dataType(number):
    datatype = Datatype.load(number)
    if not datatype:
        abort(404)

    results = Scheme.search(Query().dataTypes.any(datatype.mscid))
    no_of_hits = len(results)
    if no_of_hits:
        flash('Found {:N scheme/s} used for this type of data.'
              .format(Pluralizer(no_of_hits)))
        results.sort(key=lambda k: k.name.lower())
    else:
        flash('No schemes have been reported to be used for this type of'
              ' data.', 'error')
    return render_template(
        'search-results.html', title=datatype.get('label', f'type {number}'),
        results=results)


@bp.route('/<any(funder, maintainer, user):role>/g<int:number>')
def group(role, number):
    rel = Relation()
    group = Group.load(number)
    verb = role[0:-1] + 'd'
    results = rel.subject_records(predicate=role, object=group.mscid, filter=Scheme)
    no_of_hits = len(results)
    if no_of_hits:
        flash('Found {:N scheme/s} {} by this organization.'
              .format(Pluralizer(no_of_hits), verb))
        results.sort(key=lambda k: k.name.lower())
    else:
        flash('No schemes found that are {} by this organization.'.format(verb),
              'error')
    return render_template(
        'search-results.html', title=group.name, results=results)
