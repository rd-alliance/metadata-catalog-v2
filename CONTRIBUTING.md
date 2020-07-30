# Contributing code

## Data model

The data model for the Catalog is (unfortunately but unavoidably) expressed in
various different places. If the data model needs to be updated, it is
recommended you make the changes in the following order.

 1. Document what you think the data model should look like in `openapi.yaml`
    under `components["schemas"]`.

 2. Update the internal implementation of the data model for receiving form data
    in `rdamsc/records.py`. There are sections for defining validators, form
    components and the main forms. You will see the forms and form components
    closely mirror the schemas contained in `openapi.yaml`.

 3. It is possible that you might need to update the `get_form()` or
    `get_vform()` methods of the record classes in `rdamsc/records.py` if the
    changed fields need special handling.

 4. Update the implementation of the data model for receiving and rendering data
    in JSON format via the API in `rdamsc/api2.py`.

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
