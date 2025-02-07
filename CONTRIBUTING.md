# Contributing code

## Navigating the source code

The following table should help locate which bits of code do what, and where to
write the corresponding tests.

| `rdamsc/` | `tests/` | Contents |
| --- | --- | --- |
| `__init__.py` | `test_factory.py`, `test_webhook.py` | Main app routing, webhook |
| `api1.py` | `test_api1.py` | Version 1 API emulation |
| `api2.py` | `test_api2.py` | Version 2 API |
| `auth.py` | `test.auth.py`, `test_z_auth.py` | OAuth 2.0 authentication and user profile pages |
| `db_utils.py` | `test_records.py` | Version-controlled JSON database |
| `lists.py` | `test-lists.py` | Index pages for main record types |
| `records.py` | `test_records.py` | Display and editing pages for main record types and folksonomies |
| `search.py` | `test_search.py` | Search form and results pages |
| `users.py` | `test_auth.py` | Website and API user classes and functions |
| `vocab.py` | `test_api2.py` | Subject thesaurus class and functions |

## Data model

The data model for the Catalog is (unfortunately but unavoidably) expressed in
various different places. If the data model needs to be updated, it is
recommended you make the changes in the following order.

 1. Document what you think the data model should look like in `openapi.yaml`
    under `components["schemas"]`.

 2. Make the corresponding changes to the entity classes in `rdamsc/records.py`.

    If you are adding a **new relationship** between entities, update the
    `rolemap` properties of each affected entity. A `rolemap` entry maps from a
    role (singular) to a dictionary with the following keys:

    - `predicate`: the forward version of the role; it should be plural if
      multiple objects can play this role for the subject of the predicate
      (which is usually the case).
    - `direction`: either `Relation.FORWARD` or `Relation.INVERSE`. For example,
      the role ‘child scheme’ is the predicate ‘parent schemes’ in the inverse
      direction.
    - `accepts`: the table name for the (object) record playing this role for the
      current (subject) record; for example `m` or `g`.
    - `one_way`: if the role is between two records of the same type (with the
      same table name), and cannot be mutual, include this key with the value
      `True`; otherwise omit it. For example, *A* cannot be both a parent and
      child scheme of *B*.

    You should also update `Relation._inversions` to give the proper inversion
    of the predicate name (probably the plural of the inverted role).

    - If there is a name collision between several pairwise relationships (as
      with `maintainers`), update `Relation.inversion_map()`. Note the technique
      for replacing `{}` in the `Relation._inversions` value with the right
      string.

    If an entity would not be considered useful without having that
    relationship, add the relationship role name to a list at
    `schema['relatedEntities']['useful']` for the entity (see the example for
    `Crosswalk.schema`).

    If you are adding a **new property** to an entity, update the `schema` property
    of the entity class. You should see a close correspondence with the schemas
    in `openapi.yaml`. There are some special keys in the `schema` relating to
    validation and conformance level calculation:

    - `type` refers to the validator for the API to use;
    - `useful` (Boolean) refers to whether the property must be present for the
      record to be considered useful.
    - `optional` (Boolean) refers to whether the record can be considered
      complete without including this property.
    - `or use` (property) means this property can be ignored for conformance level
      calculations if the other property has a value.
    - `or use role` (role) means this property can be ignored for conformance
      level calculations if the entity has the given relationship with another
      entity.

    If you use a new value for `type`, then you will also
    need to add a custom validator as a method of the `Record` class named
    `_do_` plus the type; it should return a dictionary with keys `errors` (a
    list of dictionaries with key `message`) and `value` (a cleaned version of
    the input). Note that the `type` is plural if the value is a list.

 3. Update the internal implementation of the data model for receiving form data
    in `rdamsc/records.py`. There are sections for defining validators, form
    components and the main forms. You will see the forms and form components
    closely mirror the schemas contained in `openapi.yaml`.

 4. It is possible that you might need to update the `get_form()` or
    `get_vform()` methods of the record classes, or `Record.populate_form()`, in
    `rdamsc/records.py` if the changed fields need special handling (e.g.
    a dynamic controlled vocabulary).

 5. Update the HTML templates in `rdamsc/templates` to accommodate the new
    information. For example, if you have changed the data model for Schemes,
    you may need to edit `display-scheme.html`, `edit-scheme.html` and
    `edit-scheme-version.html`.

 6. Write and run unit tests to ensure the above code works as intended.

    In `tests/conftest.py`, update the test records in
    `DataDBActions.__init__()`, adding examples of new fields and so on.

    In `tests/test_records.py` and `tests/test_api2.py`, write new tests for any
    new validators, and adjust the existing tests as necessary (e.g. to take
    account of new fields on conformance evaluations)

## Testing

The recommended technique for running tests is with the `tox` tool:

```bash
tox
```

This should generate an HTML coverage report at `htmlcov/index.html` and will
also normalize the formatting of the source code and unit tests.

## Upgrading dependencies

In the virtual environment, you can upgrade the requirements file as follows.

```bash
sed -i 's/[~=]=/>=/' requirements.txt
pip install -U --upgrade-strategy eager -r requirements.txt
pip freeze | sed 's/==/~=/' | grep -vEe "^-e" > requirements.txt
```

The `requirements.txt` file should only contain the dependencies of a production
installation, so remove any lines that pertain to development or are otherwise
unique to your virtual environment, such as linters or code formatters. If you
have a good idea of what these are, you can strip them out by modifying the
argument to the `grep` command above, for example:

```bash
grep -vEe "^(-e|pkg_resources|pycodestyle)"
```

It is usually best, though, to delete and recreate the virtual environment,
then reinstall the application:

```bash
# Only if currently in the virtual environment:
deactivate
# In all cases:
rm -r venv
python3 -m venv venv
. venv/bin/activate
pip install -e .
pip freeze | sed 's/==/~=/' | grep -vEe "^-e" > requirements.txt
```

Once you have recreated the requirements file, reinstall any helper packages you
need, such as those needed for linting the unit tests:

```bash
pip install -e ".[dev]"
```

Run the unit tests as described above. If you encounter any errors or warnings
triggered by the updated requirements, fix them in one of these ways:

- updating the code;
- suppressing temporary or superfluous warnings in `pyproject.toml`;
- reverting individual requirements;
- reverting the whole requirements file.

Once all tests pass successfully, commit any changes to the requirements file.
If you needed to update code, the live server should be put into maintenance mode
before the change is pushed to the live branch so any problems can be addressed.

### Dependency notes

Here are the direct dependencies of the main code, with links to the
corresponding documentation for each of them:

  - [Flask], [WTForms] (with help from [Flask-WTF]), and [MarkupSafe] are needed
    for the actual rendering of the pages, with [Werkzeug] doing the routing.
  - [Flask-Login] is used for user authorization and session management.
  - [Flask-CORS] is used to allow requests from JavaScript.
  - [Flask-HTTPAuth] and [PassLib] are used for API authentication.
  - [Authlib], [RAuth] (which depends on [Requests]), and [Google-Auth] are used
    for OAuth 2.0 (and OpenID Connect) support.
  - The database is implemented using [TinyDB] v4+ and [TinyRecord].
  - The subject thesaurus is converted from RDF to JSON via [RDFLib].
  - [Dulwich] is used to apply version control to the database.
  - [GitHub-Webhook] allows the Catalog to update itself.

[Authlib]: https://docs.authlib.org/en/stable/
[Dulwich]: https://www.dulwich.io/
[Flask]: http://flask.pocoo.org/
[Flask-CORS]: http://flask-cors.readthedocs.io/
[Flask-HTTPAuth]: https://flask-httpauth.readthedocs.io/
[Flask-Login]: https://flask-login.readthedocs.io/
[Flask-WTF]: https://flask-wtf.readthedocs.io/
[GitHub-Webhook]: https://bloomberg.github.io/python-github-webhook/
[Google-Auth]: https://github.com/googleapis/google-auth-library-python
[MarkupSafe]: https://markupsafe.palletsprojects.com/
[PassLib]: https://passlib.readthedocs.io/
[RAuth]: https://rauth.readthedocs.io/
[RDFLib]: http://rdflib.readthedocs.io/
[Requests]: http://docs.python-requests.org/
[TinyDB]: http://tinydb.readthedocs.io/
[TinyRecord]: https://pypi.org/project/tinyrecord/
[Werkzeug]: https://werkzeug.palletsprojects.com/
[WTForms]: https://wtforms.readthedocs.io/
