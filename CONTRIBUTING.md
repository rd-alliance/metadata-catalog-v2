# Contributing code

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
