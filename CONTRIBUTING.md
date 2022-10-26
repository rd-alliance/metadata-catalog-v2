# Contributing code

## Data model

The data model for the Catalog is (unfortunately but unavoidably) expressed in
various different places. If the data model needs to be updated, it is
recommended you make the changes in the following order.

 1. Document what you think the data model should look like in `openapi.yaml`
    under `components["schemas"]`.

 2. Make the corresponding changes to the entity classes in `rdamsc/records.py`.

    If you are adding a new relationship between entities, update the `rolemap`
    properties of each affected entity and `Relation._inversions`. If there is
    a name collision between several pairwise relationships (as with
    `maintainers`), update `Relation.inversion_map()`. If an entity would not be
    considered useful without having that relationship, add the relationship
    role name to a list at `schema['relatedEntities']['useful']` for the entity.

    If you are adding a new property to an entity, update the `schema` property
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

You should have your Python virtual environment set up as described in
INSTALLATION.md.

Having activated the virtual environment, use the following command to run all
the functional tests:

```bash
venv/bin/coverage run -m pytest
```

To generate the coverage report, run the following command:

```bash
venv/bin/coverage html -d "test_coverage_report"
```

## Upgrading dependencies

In the virtual environment, you can upgrade the requirements file as follows.

```bash
sed -i 's/[~=]=/>=/' requirements.txt
pip install -U -r requirements.txt
pip freeze | sed 's/==/~=/' | grep -vEe "^(-e|pkg_resources)" > requirements.txt
```

Remove any lines that are unique to your virtual environment, such as linters
or code formatters, for example by replacing the `grep` argument:

```bash
grep -vEe "^(-e|pkg_resources|pycodestyle)"
```

Run unit tests and ensure that all tests pass by doing one of the following:

- updating the code;
- reverting individual requirements;
- reverting the whole requirements file.

Once all tests pass successfully, commit any changes to the requirements file.
If you needed to update code, the live server must be put into maintenance mode
before the change is pushed to the live branch so that the installed
requirements can be updated immediately afterwards.
