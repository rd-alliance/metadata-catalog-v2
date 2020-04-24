# Dependencies
# ============
# Standard
# --------
import json
import re
from typing import (
    List,
    Mapping,
    Type,
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
from .utils import Pluralizer, to_file_slug

bp = Blueprint('main', __name__)
mscid_prefix = 'msc:'
allowed_tags = {
    'p': [],
    'blockquote': [],
    'ol': [],
    'ul': [],
    'li': [],
    'dl': [],
    'dt': [],
    'dd': [],
    'a': ['href'],
    'em': [],
    'strong': [],
    'q': [],
    'abbr': ['title'],
    'code': [],
    'i': [],
    'sup': [],
    'sub': [],
    'bdi': [],
    'bdo': ['dir'],
    'br': [],
    'wbr': [],
    }



# Database wrapper classes
# ========================
class Relation:
    '''Utility class for handling common operations on the relations table.
    Relations are stored using MSCIDs to identify records.'''
    def __init__(self):
        db = get_data_db()
        self.tb = db.table('rel')

    def add(self, relations: Mapping[str, Mapping[str, List[str]]]):
        '''Adds relations to the table.'''
        with transaction(self.tb) as t:
            for s, properties in relations.items():
                relation = t.get(Query()['@id'] == s)
                if relation is None:
                    properties['@id'] = s
                    t.insert(properties)
                    continue
                for p, objects in properties.items():
                    if p not in relation:
                        relation[p] = objects
                        continue
                    for o in objects:
                        if o not in relation[p]:
                            relation[p].append(o)
                t.update(relation, doc_ids=[relation.doc_id])

    def remove(self, relations: Mapping[str, Mapping[str, List[str]]]):
        '''Removes relations from table, and returns those successfully
        removed for comparison.'''
        removed_relations = dict()
        with transaction(self.tb) as t:
            for s, properties in relations.items():
                relation = t.get(Query()['@id'] == s)
                if relation is None:
                    continue
                for p, objects in properties.items():
                    if p not in relation:
                        continue
                    for o in objects:
                        if o not in relation[p]:
                            continue
                        if s not in removed_relations:
                            removed_relations[s] = dict()
                        if p not in removed_relations:
                            removed_relations[s][p] = list()
                        relation[p].remove(o)
                        removed_relations[s][p].append(o)
                    if not relation[p]:
                        del relation[p]
                t.update(relation, doc_ids=[relation.doc_id])
        return removed_relations

    def subjects(self, predicate=None, object=None):
        '''Returns list of MSCIDs for all records that are subjects in the
        relations database, optionally filtered by predicate and object.'''
        mscids = set()
        Q = Query()
        if object is None:
            if predicate is None:
                relations = self.tb.all()
            else:
                relations = self.tb.search(Q[predicate].exists())
            for relation in relations:
                if len(relation.keys() == 1):
                    continue
                mscids.add(relation.get('@id'))
        else:
            if predicate is None:
                relations = self.tb.all()
                for relation in relations:
                    for objects in relation.values():
                        if isinstance(objects, list) and object in objects:
                            mscids.add(relation.get('@id'))
            else:
                relations = self.tb.search(Q[predicate].any(object))
                mscids = [relation.get('@id') for relation in relations]
        n = len(mscid_prefix) + 1
        return sorted(mscids, key=lambda k: k[:n] + k[n:].zfill(5))

    def subject_records(self, predicate=None, object=None):
        '''Returns list of Records that are subjects in the relations database,
        optionally filtered by predicate and object.'''
        mscids = self.subjects(predicate, object)
        return [Record.load_by_mscid(mscid) for mscid in mscids]

    def objects(self, subject=None, predicate=None):
        '''Returns list of MSCIDs for all records that are objects in the
        relations database, optionally filtered by subject and predicate.'''
        mscids = set()
        Q = Query()
        if predicate is None:
            if subject is None:
                relations = self.tb.all()
            else:
                relations = self.tb.search(Q['@id'] == subject)
            for relation in relations:
                for key, objects in relation.items():
                    if key == '@id':
                        continue
                    for object in objects:
                        mscids.add(object)
        else:
            if subject is None:
                relations = self.tb.search(Q[predicate].exists())
            else:
                relations = self.tb.search(Q['@id'] == subject)
            for relation in relations:
                for object in relation.get(predicate, list()):
                    mscids.add(object)
        n = len(mscid_prefix) + 1
        return sorted(mscids, key=lambda k: k[:n] + k[n:].zfill(5))

    def object_records(self, subject=None, predicate=None):
        '''Returns list of Records that are objects in the relations database,
        optionally filtered by subject and predicate.'''
        mscids = self.objects(subject, predicate)
        return [Record.load_by_mscid(mscid) for mscid in mscids]


class Record(Document):
    '''Abstract class with common methods for the helper classes
    for different types of record.'''

    @staticmethod
    def cleanup(data):
        """Takes dictionary and recursively removes entries where the value is (a)
        an empty string, (b) an empty list, (c) a dictionary wherein all the
        values are empty, (d) null. Values of 0 are not removed. Also strips
        out csrf_token.
        """
        for key, value in data.copy().items():
            if isinstance(value, dict):
                new_value = Record.cleanup(value)
                if not new_value:
                    del data[key]
                else:
                    data[key] = new_value
            elif isinstance(value, list):
                if not value:
                    del data[key]
                else:
                    clean_list = list()
                    for item in value:
                        if isinstance(item, dict):
                            new_item = Record.cleanup(item)
                            if new_item:
                                clean_list.append(new_item)
                        elif item:
                            clean_list.append(item)
                    if clean_list:
                        data[key] = clean_list
                    else:
                        del data[key]
            elif value == '':
                del data[key]
            elif value is None:
                del data[key]
            elif key is 'csrf_token':
                del data[key]
        return data

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
            return subclass(value=doc, doc_id=doc.doc_id)
        return subclass(value=dict(), doc_id=0)

    @classmethod
    def load_by_mscid(cls, mscid: str):
        '''Returns an instance of the Record subclass that corresponds to the
        given MSCID, or None if the MSCID was not syntactically correct.
        '''
        mscid_format = re.compile(
            mscid_prefix
            + r'(?P<table>c|e|g|m|t)'
            + r'(?P<doc_id>\d+)'
            + r'(#v(?P<version>.*))?$')
        m = mscid_format.match(mscid)
        if m:
            return cls.load(int(m.group('doc_id')), m.group('table'))
        return None

    @classmethod
    def all(cls):
        '''Should only be called on subclasses of Record. Returns a list of all
        instances of that subclass from the database.'''
        db = get_data_db()
        tb = db.table(cls.table)
        docs = tb.all()
        return [cls(value=doc, doc_id=doc.doc_id) for doc in docs]

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
        return f"{mscid_prefix}{self.table}{self.doc_id}"

    @property
    def slug(self):
        return self.get('slug')

    def _save(self, value: Mapping):
        '''Saves record to database. Returns error message if a problem
        arises.'''

        # Remove empty and noisy fields
        value = self.cleanup(value)

        # Update or insert record as appropriate
        db = get_data_db()
        tb = db.table(self.table)
        if self.doc_id:
            with transaction(tb) as t:
                for key in (k for k in self if k not in value):
                    t.update_callable(delete(key), doc_ids=[self.doc_id])
                t.update(value, doc_ids=[self.doc_id])
        else:
            self.doc_id = tb.insert(value)

        return ''

    def _save_relations(self, statements: List[Mapping],
                        missing_statements: List[Mapping]):
        '''Saves relation edits to the Relations table.'''
        rel = Relation()

        if statements:
            relations = self._triples_to_dict(statements)
            rel.add(relations)

        if missing_statements:
            relations_to_delete = self._triples_to_dict(missing_statements)
            rel.remove(relations_to_delete)

        return ''

    def _triples_to_dict(self, statements: List[Mapping]):
        '''Assembles dictionary of relations. Replaces 'SELF' with actual mscid.'''
        relations = dict()
        for statement in statements:
            s = statement['subject']
            p = statement['predicate']
            o = statement['object']
            if s == o:
                continue
            if s == 'SELF':
                s = self.mscid
            if o == 'SELF':
                o = self.mscid
            if s not in relations:
                relations[s] = dict()
            if p not in relations[s]:
                relations[s][p] = list()
            relations[s][p].append()
        return relations

    def save_gui_input(self, value: Mapping):
        '''Processes form input and saves it. Returns error message if a problem
        arises.'''

        # Insert slug:
        value['slug'] = self.slug

        # Restore version information:
        value['versions'] = self.get('versions', list())

        # Get list of fields we can iterate over:
        fields = self.form()

        # Sanitize HTML input:
        for field in fields:
            if field.type != 'TextHTMLField':
                continue
            html_in = value.get(field.short_name)
            if not html_in:
                continue
            # TODO: apply filtering
            html_safe = html_in
            value[field.short_name] = html_safe

        # Check to see if any relatedEntities information has been removed:
        missing_statements = list()
        rel = Relation()
        if self.doc_id != 0:
            for field in fields:
                if field.type != 'SelectRelatedField':
                    continue
                predicate = field.description
                if field.flags.inverse:
                    object = self.mscid
                    mscids = rel.subjects(
                        predicate=predicate, object=object)
                    if mscids:
                        for subject in mscids:
                            if subject not in value.get(field.name, list()):
                                missing_statements.append({
                                    'subject': subject,
                                    'predicate': predicate,
                                    'object': object})
                else:
                    subject = self.mscid
                    mscids = rel.objects(
                        subject=subject, predicate=predicate)
                    if mscids:
                        for object in mscids:
                            if object not in value.get(field.name, list()):
                                missing_statements.append({
                                    'subject': subject,
                                    'predicate': predicate,
                                    'object': object})

        # Remove form inputs containing relatedEntities information, and save
        # them separately. NB. We may not have mscid yet, so use 'SELF' for
        # current record:
        statements = list()
        for field in fields:
            if field.type != 'SelectRelatedField':
                continue
            if field.name not in value:
                continue
            # Save in our list, the right way around:
            predicate = field.description
            for entity in value[field.name]:
                if field.flags.inverse:
                    subject = entity
                    object = 'SELF'
                else:
                    subject = 'SELF'
                    object = entity
                statements.append({
                    'subject': subject,
                    'predicate': predicate,
                    'object': object})
            del value[field.name]

        # Save the main record:
        error = self._save(value)
        if error:
            return error

        # Update relations
        return self._save_relations(statements, missing_statements)


class Scheme(Record):
    table = 'm'
    series = 'scheme'

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

    @property
    def form(self):
        return SchemeForm

    @property
    def name(self):
        return self.get('title')

    @property
    def slug(self):
        slug = self.get('slug')
        if slug:
            return slug
        if self.name:
            return to_file_slug(self.name)
        return None

    def get_form(self):
        # Get data from database:
        data = json.loads(json.dumps(self))

        # Strip out version info, this is handled separately:
        if 'versions' in data:
            del data['versions']

        # Populate with relevant relations
        rel = Relation()
        for field in self.form():
            if field.type != 'SelectRelatedField':
                continue
            predicate = field.description
            mscids = list()
            if field.flags.inverse:
                object = self.mscid
                mscids.extend(rel.subjects(
                    predicate=predicate, object=object))
            else:
                subject = self.mscid
                mscids.extend(rel.objects(
                    subject=subject, predicate=predicate))
            if mscids:
                data[field.short_name] = mscids

        # Populate form:
        form = self.form(data=data)

        # Assign validators to current choices:
        scheme_locations = [
            ('', ''), ('document', 'document'), ('website', 'website'),
            ('RDA-MIG', 'RDA MIG Schema'), ('DTD', 'XML/SGML DTD'),
            ('XSD', 'XML Schema'), ('RDFS', 'RDF Schema')]
        for f in form.locations:
            f['type'].choices = scheme_locations

        return form


class Tool(Record):
    table = 't'
    series = 'tool'

    '''Object representing a tool.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def name(self):
        return self.get('title')

    @property
    def slug(self):
        slug = self.get('slug')
        if slug:
            return slug
        if self.name:
            return to_file_slug(self.name)
        return None


class Crosswalk(Record):
    table = 'c'
    series = 'mapping'

    '''Object representing a mapping.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def name(self):
        return self.get('name')

    @property
    def slug(self):
        slug = self.get('slug')
        if slug:
            return slug
        if self.name:
            return to_file_slug(self.name)
        return None


class Group(Record):
    table = 'g'
    series = 'organization'

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

    @property
    def name(self):
        return self.get('name')

    @property
    def slug(self):
        slug = self.get('slug')
        if slug:
            return slug
        if self.name:
            return to_file_slug(self.name)
        return None


class Endorsement(Record):
    table = 'e'
    series = 'endorsement'

    '''Object representing an endorsement.'''
    def __init__(self, value: Mapping, doc_id: int):
        super().__init__(value, doc_id, self.table)

    @property
    def name(self):
        return self.get('title')

    @property
    def slug(self):
        slug = self.get('slug')
        if slug:
            return slug
        if self.name:
            return to_file_slug(self.name)
        return None


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


# Custom elements
# ---------------
class SelectRelatedField(SelectMultipleField):
    def __init__(self, label='', record: Type[Record]=Scheme, inverse=False,
                 **kwargs):
        choices = record.get_choices()
        super(SelectMultipleField, self).__init__(
            label, choices=choices, **kwargs)
        setattr(self.flags, 'inverse', inverse)


class TextHTMLField(TextAreaField):
    pass


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
    description = TextHTMLField('Description')
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
    parent_schemes = SelectRelatedField(
        'Parent metadata scheme(s)', Scheme,
        description='parent scheme')
    child_schemes = SelectRelatedField(
        'Parent metadata scheme(s)', Scheme,
        description='parent scheme', inverse=True)
    maintainers = SelectRelatedField(
        'Organizations that maintain this scheme', Group,
        description='maintainer')
    funders = SelectRelatedField(
        'Organizations that funded this scheme', Group,
        description='funder')
    users = SelectRelatedField(
        'Organizations that use this scheme', Group,
        description='user')
    locations = FieldList(
        FormField(LocationForm), 'Relevant links', min_entries=1)
    samples = FieldList(
        FormField(SampleForm), 'Sample records conforming to this scheme',
        min_entries=1)
    identifiers = FieldList(
        FormField(IdentifierForm), 'Identifiers for this scheme',
        min_entries=1)


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
        # Save form data to database
        error = record.save_gui_input(form_data)
        if record.doc_id:
            # Editing an existing record
            if error:
                flash(error, 'error')
                return redirect(
                    url_for('main.edit_record', series=series, number=number))
            else:
                flash('Successfully updated record.', 'success')
                return redirect(
                    url_for('main.display', series=series, number=number))
        else:
            # Adding a new record
            if error:
                flash(error, 'error')
                return redirect(
                    url_for('main.edit_record', series=series, number=number))
            else:
                number = record.doc_id
                flash('Successfully added record.', 'success')
                return redirect(
                    url_for('main.display', series=series, number=number))
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
        f"edit-{record.series}.html", form=form, doc_id=number, version=None,
        idSchemes=list(), safe_tags=allowed_tags **params)


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
        f"display-{record.series}.html", record=record, versions=versions,
        relations=relations, hasRelatedSchemes=hasRelatedSchemes)


def clean_error_list(field):
    seen_errors = set()
    for error in field.errors:
        seen_errors.add(error)
    return list(seen_errors)
