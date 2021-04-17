# Contributing code

## Data model

The data model for the Catalog is (unfortunately but unavoidably) expressed in
various different places. If the data model needs to be updated, it is
recommended you make the changes in the following order.

 1. Document what you think the data model should look like in `openapi.yaml`
    under `components["schemas"]`.

 2. Update the `schema` and `rolemap` properties of the respective entity
    classes in `rdamsc/records.py`. You should see a close correspondence with
    the schemas in `openapi.yaml`. You may also have to add a custom validator,
    which should normally be added as a method of the `Record` class with a name
    starting `_do_`; it should return a dictionary with keys `errors` (a list of
    dictionaries with key `message`) and `value` (a cleaned version of the
    input).

 3. Update the internal implementation of the data model for receiving form data
    in `rdamsc/records.py`. There are sections for defining validators, form
    components and the main forms. You will see the forms and form components
    closely mirror the schemas contained in `openapi.yaml`.

 4. It is possible that you might need to update the `get_form()` or
    `get_vform()` methods of the record classes in `rdamsc/records.py` if the
    changed fields need special handling.


## Testing

You should have your Python virtual environment set up as described in
INSTALLATION.md.

Having activated the virtual environment, use the following command to run all
the functional tests:

```bash
coverage run -m pytest
```

To generate the coverage report, run the following command:

```bash
coverage html -d "test_coverage_report"
```
