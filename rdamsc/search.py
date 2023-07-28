# Dependencies
# ============
# Non-standard
# ------------
# See https://flask.palletsprojects.com/en/2.0.x/
from flask import (
    Blueprint, abort, flash, redirect, render_template, request, url_for
)
# See https://flask-wtf.readthedocs.io/
from flask_wtf import FlaskForm
# See http://tinydb.readthedocs.io/
from tinydb import Query
# See https://wtforms.readthedocs.io/
from wtforms import (
    FieldList, StringField, validators
)

# Local
# -----
from .records import Datatype, Group, Relation, Scheme, mscid_prefix
from .utils import Pluralizer, clean_error_list, url_for_subject, wild_to_regex
from .vocab import get_thesaurus

bp = Blueprint('search', __name__)


class SchemeSearchForm(FlaskForm):
    title = StringField('Name of scheme')
    keywords = FieldList(
        StringField('Subject area', validators=[validators.Optional()]),
        'Subject area', min_entries=1)
    identifier = StringField('External identifier')
    funder = StringField('Funder')
    dataType = StringField('Data type')


def flash_result(no_of_hits: int, type: str):
    """Flashes user with informative message about a search result, based on
    thing they are supposed to have in common.

    Arguments:
        no_of_hits (int): Number of results
        type (str): Basis of matching, e.g. 'with title X'
    """
    if no_of_hits:
        flash('Found {:N scheme/s} {}.'.format(Pluralizer(no_of_hits), type))
    else:
        flash('No schemes found {}. '.format(type), 'error')
    return None


@bp.route('/search', methods=['GET', 'POST'])
def scheme_search():
    # Get form:
    form = SchemeSearchForm()

    # Apply subject keyword validation:
    th = get_thesaurus()
    for field in form.keywords:
        if len(field.validators) == 1:
            field.validators.append(
                validators.AnyOf(
                    th.get_valid(),
                    'Value must be drawn from the UNESCO Thesaurus.'))

    # Load relation handling:
    rel = Relation()

    # Process form
    if request.method == 'POST' and form.validate():
        results_by_id = dict()
        Q = Query()
        title = 'Search results'
        no_of_queries = 0

        title_wild = form.data.get('title')
        if title_wild:
            no_of_queries += 1
            sub_results_by_id = dict()
            title_query = wild_to_regex(title_wild)
            for m in Scheme.search(Q.title.search(title_query)):
                sub_results_by_id[m.mscid] = m
            for m in Scheme.search(Q.versions.any(
                    Q.title.search(title_query))):
                sub_results_by_id[m.mscid] = m
            flash_result(len(sub_results_by_id),
                         f'with title matching "{title_wild}"')
            results_by_id.update(sub_results_by_id)

        term_list_raw = form.data.get('keywords')
        term_list = [v for v in term_list_raw if v]
        if term_list:
            no_of_queries += 1
            sub_results_by_id = dict()
            term_set = set()
            for term in term_list:
                if not term:  # pragma: no cover
                    continue
                term_set.update(th.get_branch(term))
            if term_set:
                # Search for matching schemes
                for m in Scheme.search(Q.keywords.any(term_set)):
                    sub_results_by_id[m.mscid] = m
            flash_result(len(sub_results_by_id),
                         f'related to {" and ".join(term_list)}')
            results_by_id.update(sub_results_by_id)

        id_query = form.data.get('identifier')
        if id_query:
            no_of_queries += 1
            sub_results_by_id = dict()
            for m in Scheme.search(Q.identifiers.any(
                    Q.id == id_query)):
                sub_results_by_id[m.mscid] = m
            for m in Scheme.search(Q.versions.any(
                    Q.identifiers.any(Q.id == id_query))):
                sub_results_by_id[m.mscid] = m
            flash_result(len(sub_results_by_id),
                         f'with identifier "{id_query}"')
            results_by_id.update(sub_results_by_id)

        funder_wild = form.data.get('funder')
        funder_mscids = list()
        if funder_wild:
            no_of_queries += 1
            # Interpret search
            funder_query = wild_to_regex(funder_wild)
            for m in Group.search(Q.name.search(
                    funder_query)):
                funder_mscids.append(m.mscid)
            if funder_mscids:
                sub_results_by_id = dict()
                for f in funder_mscids:
                    for m in rel.subject_records(
                            predicate='funders', object=f, filter=Scheme):
                        sub_results_by_id[m.mscid] = m
                flash_result(len(sub_results_by_id),
                             f'with funder matching "{funder_wild}"')
                results_by_id.update(sub_results_by_id)
            else:
                flash(f'No funders found matching "{funder_wild}".',
                      'error')

        dtype_raw = form.data.get('dataType')
        if dtype_raw:
            no_of_queries += 1
            sub_results_by_id = dict()
            dtype = Datatype.load_by_label(dtype_raw)
            for m in Scheme.search(Q.dataTypes.any(dtype.mscid)):
                sub_results_by_id[m.mscid] = m
            flash_result(len(sub_results_by_id),
                         f'used with data of type "{dtype_raw}"')
            results_by_id.update(sub_results_by_id)

        # Show results
        no_of_hits = len(results_by_id)
        if no_of_queries > 1:
            flash('Found {:N scheme/s} in total.'.format(
                Pluralizer(no_of_hits)))
        if no_of_hits == 1:
            # Go direct to that page
            for result in results_by_id.values():
                return redirect(
                    url_for('main.display', table='m', number=result.doc_id))
        # Otherwise return as a list
        document_list = sorted(results_by_id.values(),
                               key=lambda k: k.name.lower())
        # Show results list
        return render_template(
            'search-results.html', title=title, results=document_list)

    if form.errors:
        if 'csrf_token' in form.errors.keys():
            msg = ('Could not perform search as your form session has expired.'
                   ' Please try again.')
        else:
            msg = ('Could not perform search as there {:/was an error/were N'
                   ' errors}. See below for details.'
                   .format(Pluralizer(len(form.errors))))
        flash(msg, 'error')
        for field, errors in form.errors.items():
            if len(errors) > 0:
                if isinstance(errors[0], dict):
                    # Subform
                    for subform in errors:
                        for subfield, suberrors in subform.items():
                            for f in form[field]:
                                f[subfield].errors = clean_error_list(
                                    f[subfield])
                else:
                    # Simple field
                    form[field].errors = clean_error_list(form[field])

    # No results displayed, so render form instead.
    # Enable autocompletion for title, identifier, funder, dataType:
    all_schemes = Scheme.all()
    title_set = set()
    type_set = set()
    funder_set = set()
    id_set = set()
    for scheme in all_schemes:
        if not scheme:
            continue
        title_set.add(scheme.name)
        for type_id in scheme.get('dataTypes', list()):
            type = Datatype.load_by_mscid(type_id)
            type_set.add(type.get('label'))
        for group in rel.object_records(predicate='funders'):
            funder_set.add(group.name)
        for id in scheme.get('identifiers', list()):
            id_set.add(id.get('id'))
        for vn in scheme.get('versions', list()):
            vtitle = vn.get('title')
            if vtitle:
                title_set.add(vtitle)
            for id in vn.get('identifiers', list()):
                id_set.add(id.get('id'))
    # Enable autocompletion for subject_terms:
    subject_list = th.get_labels()
    # Sort suggestions:
    title_list = (
        sorted(title_set, key=lambda k: k.lower())
        if title_set else list())
    n = len(mscid_prefix) + 1
    id_list = (
        sorted(id_set, key=lambda k: k[:n] + k[n:].zfill(5))
        if id_set else list())
    funder_list = (
        sorted(funder_set, key=lambda k: k.lower())
        if funder_set else list())
    type_list = (
        sorted(type_set, key=lambda k: k.lower())
        if type_set else list())
    subject_list.sort()
    return render_template(
        'search-form.html', form=form, titles=title_list,
        subjects=subject_list, ids=id_list, funders=funder_list,
        dataTypes=type_list)


@bp.route('/subject/<path:subject>')
def subject(subject):
    '''Show search results for a given subject. Implicitly searches for
    ancestor and descendent terms as well.'''

    # In case this didn't get done by the server:
    subject = subject.replace("%2F", "/")

    # Get search terms to use
    th = get_thesaurus()
    uris = th.get_branch(subject)
    if not uris:
        flash(f'The subject "{subject}" was not found in the thesaurus.',
              'error')
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
              .format(url_for_subject('Multidisciplinary')),
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
        'search-results.html', title=datatype.name, results=results)


@bp.route('/<any(funder, maintainer, user):role>/g<int:number>')
def group(role, number):
    group = Group.load(number)
    if not group:
        abort(404)

    rel = Relation()
    verb = role[0:-1] + 'd'
    results = rel.subject_records(
        predicate=f"{role}s", object=group.mscid, filter=Scheme)
    no_of_hits = len(results)
    if no_of_hits:
        flash('Found {:N scheme/s} {} by this organization.'
              .format(Pluralizer(no_of_hits), verb))
        results.sort(key=lambda k: k.name.lower())
    else:
        flash(f"No schemes found that are {verb} by this organization.",
              'error')
    return render_template(
        'search-results.html', title=group.name, results=results)
