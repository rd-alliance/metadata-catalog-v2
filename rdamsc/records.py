# Dependencies
# ============
# Standard
# --------
import re
from typing import (
    Mapping,
)
from urllib.parse import urlparse

# Non-standard
# ------------
# See http://tinydb.readthedocs.io/
from tinydb import TinyDB, Query, where
from tinydb.database import Document
from tinydb.operations import delete
# See https://github.com/eugene-eeo/tinyrecord
from tinyrecord import transaction
# See https://flask.palletsprojects.com/en/1.1.x/
from flask import (
    abort, Blueprint, current_app, flash, g, redirect, render_template, request,
    session, url_for
)
# See https://flask-login.readthedocs.io/
from flask_login import login_required
# See https://flask-wtf.readthedocs.io/ and https://wtforms.readthedocs.io/
from flask_wtf import FlaskForm
from wtforms import (
    FieldList, Form, FormField, HiddenField, SelectField, SelectMultipleField,
    StringField, TextAreaField, ValidationError, validators, widgets
)
from wtforms.compat import string_types


# Local
# -----
from .db_utils import JSONStorageWithGit
from .utils import Pluralizer

bp = Blueprint('main', __name__)


# Form components
# ===============
# Custom validators
# -----------------
def EmailOrURL(form, field):
    """Raise error if URL/email address is not well-formed."""
    result = urlparse(field.data)
    if result.scheme == 'mailto':
        if not re.match(r'[^@\s]+@[^@\s\.]+\.[^@\s]+', result.path):
            raise ValidationError(
                'That email address does not look quite right.')
    else:
        if not result.scheme:
            raise ValidationError(
                'Please provide the protocol (e.g. "http://", "mailto:").')
        if not result.netloc:
            return ValidationError('That URL does not look quite right.')


class RequiredIf(object):
    """A validator which makes a field required if another field is set and has
    a truthy value, and optional otherwise.
    """
    field_flags = ('optional', )

    def __init__(self, other_field_list, message=None, strip_whitespace=True):
        self.other_field_list = other_field_list
        self.message = message
        if strip_whitespace:
            self.string_check = lambda s: s.strip()
        else:
            self.string_check = lambda s: s

    def __call__(self, form, field):
        other_fields_empty = True
        for other_field_name in self.other_field_list:
            other_field = form._fields.get(other_field_name)
            if other_field is None:
                raise Exception(
                    'No field named "{}" in form'.format(other_field_name))
            if bool(other_field.data):
                if not field.raw_data or not field.raw_data[0]:
                    if self.message is None:
                        message = field.gettext('This field is required.')
                    else:
                        message = self.message
                    field.errors[:] = []
                    other_fields_empty = False
                    raise validators.StopValidation(message)
            elif (not field.raw_data) or (
                    isinstance(field.raw_data[0], string_types) and
                    not self.string_check(field.raw_data[0])):
                field.errors[:] = []
        if other_fields_empty:
            raise validators.StopValidation()


def W3CDate(form, field):
    """Raise error if a string is not a valid W3C-formatted date."""
    if re.search(r'^\d{4}(-\d{2}){0,2}$', field.data) is None:
        raise ValidationError('Please provide the date in yyyy-mm-dd format.')


# Reusable subforms
# -----------------
class NativeDateField(StringField):
    widget = widgets.Input(input_type='date')
    validators = [validators.Optional(), W3CDate]


class DataTypeForm(Form):
    label = StringField('Data type', default='')
    url = StringField('URL of definition', validators=[
        validators.Optional(), EmailOrURL])


class LocationForm(Form):
    url = StringField('URL', validators=[RequiredIf(['type']), EmailOrURL])
    type = SelectField('Type', validators=[RequiredIf(['url'])], default='')


class FreeLocationForm(Form):
    url = StringField('URL', validators=[RequiredIf(['type']), EmailOrURL])
    type = StringField('Type', validators=[RequiredIf(['url'])], default='')


class SampleForm(Form):
    title = StringField('Title', validators=[RequiredIf(['url'])])
    url = StringField('URL', validators=[RequiredIf(['title']), EmailOrURL])


class IdentifierForm(Form):
    id = StringField('ID')
    scheme = StringField('ID scheme')


class VersionForm(Form):
    number = StringField('Version number', validators=[
        RequiredIf(['issued', 'available', 'valid_from']), validators.Length(max=20)])
    number_old = HiddenField(validators=[validators.Length(max=20)])
    issued = NativeDateField('Date published')
    available = NativeDateField('Date released as draft/proposal')
    valid_from = NativeDateField('Date considered current')
    valid_to = NativeDateField('until')


#class SchemeVersionForm(Form):
    #scheme_choices = Scheme.get_choices()

    #id = SelectField('Metadata scheme', choices=scheme_choices)
    #version = StringField('Version')


class CreatorForm(Form):
    fullName = StringField('Full name')
    givenName = StringField('Given name(s)')
    familyName = StringField('Family name')


# Top-level forms
# ---------------
class SchemeForm(FlaskForm):
    title = StringField('Name of metadata scheme')
    description = TextAreaField('Description')
    keywords = FieldList(
        StringField('Subject area', validators=[
            validators.Optional(),
            #validators.AnyOf(
                #get_subject_terms(complete=True),
                #'Value must match an English preferred label in the {}.'
                #.format(thesaurus_link))
            ]),
        'Subject areas', min_entries=1)
    dataTypes = FieldList(
        FormField(DataTypeForm), 'Data types', min_entries=1)
    parent_schemes = SelectMultipleField('Parent metadata scheme(s)')
    maintainers = SelectMultipleField(
        'Organizations that maintain this scheme')
    funders = SelectMultipleField('Organizations that funded this scheme')
    users = SelectMultipleField('Organizations that use this scheme')
    locations = FieldList(
        FormField(LocationForm), 'Relevant links', min_entries=1)
    samples = FieldList(
        FormField(SampleForm), 'Sample records conforming to this scheme',
        min_entries=1)
    identifiers = FieldList(
        FormField(IdentifierForm), 'Identifiers for this scheme',
        min_entries=1)


# Database wrapper classes
# ========================
class Record(Document):
    '''Abstract class with common methods for the helper classes
    for different types of record.'''

    @classmethod
    def load(cls, doc_id: int, table: str=None):
        '''Returns an instance of the Record subclass that corresponds to the
        given table, either blank or the existing record with the given doc_id.
        '''
        if table is None:
            table = cls.table

        # This bit allows the function to be called on Record and
        # return a Scheme (say):
        subclass = cls
        valid_tables = list()
        for subcls in cls.__subclasses__():
            valid_tables.append(subcls.table)
            if subcls.table == table:
                subclass = subcls

        db = get_data_db()
        if table not in valid_tables:
            print(f"DEBUG: {table} not a valid table.")
            return None
        tb = db.table(table)
        doc = tb.get(doc_id=doc_id)

        if doc:
            print(f"DEBUG: Returning existing record.")
            return subclass(value=doc, doc_id=doc.doc_id)
        print(f"DEBUG: Returning new record.")
        return subclass(value=dict(), doc_id=0)

    @classmethod
    def search(cls, cond: Query):
        '''Should only be called on subclasses of Record. Performs a TinyDB
        search on the corresponding table, converts the results into
        instances of the given subclass.'''
        db = get_data_db()
        tb = db.table(cls.table)
        docs = tb.search(cond)
        return [cls(value=doc, doc_id=doc.doc_id) for doc in docs]

    def __init__(self, value: Mapping, doc_id: int, table: str):
        super().__init__(value, doc_id)
        self.table = table

    @property
    def mscid(self):
        return f"msc:{self.table}{self.doc_id}"

    def create(self, value: Mapping):
        if self.doc_id:
            # Should be zero
            return 0

        db = get_data_db()
        tb = db.table(self.table)
        return tb.insert(value)

    def modify(self, value: Mapping):
        if not self.doc_id:
            # Should not be zero
            return False

        db = get_data_db()
        tb = db.table(self.table)
        with transaction(self.table) as t:
            for key in (k for k in self if k not in value):
                t.update_callable(delete(key), eids=[self.doc_id])
            t.update(value, eids=[self.doc_id])

        return True


class Scheme(Record):
    table = 'm'
    template = 'metadata-scheme.html'

    @classmethod
    def get_choices(cls):
        choices = [('', '')]
        for scheme in cls.search(Query().slug.exists()):
            choices.append(
                (scheme.mscid, scheme.get('title', 'Untitled')))

        choices.sort(key=lambda k: k[1].lower())
        return choices

    @classmethod
    def get_vocabs(cls):
        '''Gets controlled vocabularies for use in form autocompletion.'''
        vocabs = dict()

        vocabs['subjects'] = list()
        vocabs['dataTypeURLs'] = list()
        vocabs['dataTypeLabels'] = list()

        return vocabs

    '''Object representing a metadata scheme.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    def get_form(self):
        # Populate form with current data:
        form = SchemeForm(data=self)

        # Assign validators to current choices:
        form.parent_schemes.choices = self.get_choices()
        organization_choices = Group.get_choices()
        form.maintainers.choices = organization_choices
        form.funders.choices = organization_choices
        form.users.choices = organization_choices
        scheme_locations = [
            ('', ''), ('document', 'document'), ('website', 'website'),
            ('RDA-MIG', 'RDA MIG Schema'), ('DTD', 'XML/SGML DTD'),
            ('XSD', 'XML Schema'), ('RDFS', 'RDF Schema')]
        for f in form.locations:
            f['type'].choices = scheme_locations

        return form


class Tool(Record):
    table = 't'
    template = 'tool.html'

    '''Object representing a tool.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


class Crosswalk(Record):
    table = 'c'
    template = 'mapping.html'

    '''Object representing a mapping.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


class Group(Record):
    table = 'g'
    template = 'organization.html'

    @classmethod
    def get_choices(cls):
        choices = [('', '')]
        for scheme in cls.search(Query().slug.exists()):
            choices.append(
                (scheme.mscid, scheme.get('name', 'Unnamed')))

        choices.sort(key=lambda k: k[1].lower())
        return choices

    '''Object representing an organization.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


class Endorsement(Record):
    table = 'e'
    template = 'endorsement.html'

    '''Object representing an endorsement.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)


def get_data_db():
    if 'data_db' not in g:
        g.data_db = TinyDB(
            current_app.config['MAIN_DATABASE_PATH'],
            storage=JSONStorageWithGit,
            indent=2,
            ensure_ascii=False)

    return g.data_db


@bp.route('/edit/<string(length=1):series><int:number>',
          methods=['GET', 'POST'])
@login_required
def edit_record(series, number):
    # Look up record to edit, or get new:
    record = Record.load(number, series)

    # Abort if series was wrong:
    if record is None:
        abort(404)

    # If number is wrong, we reinforce the point by redirecting to 0:
    if record.doc_id != number:
        flash("You are trying to update a record that doesn't exist."
              "Try filling out this new one instead.", 'error')
        return redirect(url_for('main.edit_record', series=series, number=0))

    # Instantiate edit form
    form = record.get_form()

    # Form-specific value lists
    params = record.get_vocabs()

    # Processing the request
    if request.method == 'POST' and form.validate():
        form_data = form.data
        if series == 'e':
            # Here is where we automatically insert the URL type
            filtered_locations = list()
            for f in form.locations:
                if f.url.data:
                    location = {'url': f.url.data, 'type': 'document'}
                    filtered_locations.append(location)
            form_data['locations'] = filtered_locations
        # Translate form data into internal data model
        if record.doc_id:
            # Editing an existing record
            if record.modify(form_data):
                flash('Successfully updated record.', 'success')
                return redirect(
                    url_for('main.display', series=series, number=number))
            else:
                flash('You tried to update a non-existent record.', 'error')
                return redirect(
                    url_for('main.edit_record', series=series, number=number))
        else:
            # Adding a new record
            number = record.create(form_data)
            if number:
                flash('Successfully added record.', 'success')
                return redirect(
                    url_for('main.display', series=series, number=number))
            else:
                flash('You tried to re-create an existing record.', 'error')
                return redirect(
                    url_for('main.edit_record', series=series, number=number))
    if form.errors:
        flash('Could not save changes as there {:/was an error/were N errors}.'
              ' See below for details.'.format(Pluralizer(len(form.errors))),
              'error')
        for field, errors in form.errors.items():
            if len(errors) > 0:
                if isinstance(errors[0], str):
                    # Simple field
                    form[field].errors = clean_error_list(form[field])
                else:
                    # Subform
                    for subform in errors:
                        for subfield, suberrors in subform.items():
                            for f in form[field]:
                                f[subfield].errors = clean_error_list(f[subfield])
    return render_template(
        'edit-' + record.template, form=form, doc_id=number, version=None,
        idSchemes=list(), **params)


@bp.route('/msc/<string(length=1):series><int:number>')
@bp.route('/msc/<string(length=1):series><int:number>/<field>')
def display(series, number, field=None, api=False):
    # Look up record to edit, or get new:
    record = Record.load(number, series)

    # Abort if series or number was wrong:
    if record is None or record.doc_id == 0:
        abort(404)

    # Form MSC ID
    mscid = record.mscid

    # If the record has version information, interpret the associated dates.
    versions = None
    if 'versions' in record:
        versions = list()
        for v in record['versions']:
            if 'number' not in v:
                continue
            this_version = v
            this_version['status'] = ''
            #if 'issued' in v:
                #this_version['date'] = v['issued']
                #if 'valid' in v:
                    #date_range = parse_date_range(v['valid'])
                    #if date_range[1]:
                        #this_version['status'] = (
                            #'deprecated on {}'.format(date_range[1]))
                    #else:
                        #this_version['status'] = 'current'
            #elif 'valid' in v:
                #date_range = parse_date_range(v['valid'])
                #this_version['date'] = date_range[0]
                #if date_range[1]:
                    #this_version['status'] = (
                        #'deprecated on {}'.format(date_range[1]))
                #else:
                    #this_version['status'] = 'current'
            #elif 'available' in v:
                #this_version['date'] = v['available']
                #this_version['status'] = 'proposed'
            versions.append(this_version)
        try:
            versions.sort(key=lambda k: k['date'], reverse=True)
        except KeyError:
            print('WARNING: Record {}{} has missing version date.'
                  .format(mscid))
            versions.sort(key=lambda k: k['number'], reverse=True)
        for version in versions:
            if version['status'] == 'current':
                break
            if version['status'] == 'proposed':
                continue
            if version['status'] == '':
                version['status'] = 'current'
                break

    # If the record has related entities, include the corresponding entries in
    # a 'relations' dictionary.
    relations = dict()
    hasRelatedSchemes = False
    #if 'relatedEntities' in record:
        #for entity in record['relatedEntities']:
            #role = entity['role']
            #if role not in relations_msc_form:
                #print('WARNING: Record {} has related entity with unrecognized'
                      #' role "{}".'.format(mscid, role))
                #continue
            #relation_list = relations_msc_form[role]
            #if relation_list not in relations:
                #relations[relation_list] = list()
            #entity_series, entity_number = parse_mscid(entity['id'])
            #document_record = tables[entity_series].get(doc_id=entity_number)
            #if document_record:
                #relations[relation_list].append(document_record)
                #if entity_series == 'm':
                    #hasRelatedSchemes = True

    # Now we gather information about inverse relationships and add them to the
    # 'relations' dictionary as well.
    # For speed, we only run this check for metadata schemes, since only that
    # template currently includes this information.
    #if series in ['m']:
        #for s, t in tables.items():
            ## The following query takes account of id#version syntax
            #matches = t.search(Query().relatedEntities.any(
                #Query()['id'].matches('{}(#v.*)?$'.format(mscid))))
            #for match in matches:
                #role_list, document_record = get_relation(mscid, match)
                #if role_list:
                    #if role_list in [
                            #'child schemes', 'mappings_to', 'mappings_from']:
                        #hasRelatedSchemes = True
                    #if role_list not in relations:
                        #relations[role_list] = list()
                    #relations[role_list].append(document_record)

    # We are ready to display the information.
    return render_template(
        'display-' + record.template, record=record, versions=versions,
        relations=relations, hasRelatedSchemes=hasRelatedSchemes)


def clean_error_list(field):
    seen_errors = set()
    for error in field.errors:
        seen_errors.add(error)
    return list(seen_errors)
