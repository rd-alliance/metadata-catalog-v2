import re
from urllib.parse import urlencode
import json
import pytest
from flask import g, session


def test_create_view_records(client, auth, app, page, data_db):
    auth.login()

    # Prepare term database:
    data_db.write_terms()

    # Get metadata creation form
    response = client.get('/edit/m0')
    html = response.get_data(as_text=True)
    csrf = page.get_csrf(html)

    # Test metadata scheme validators
    m1 = data_db.get_formdata('m1')
    m1["keywords-0"] = "Not a term"
    m1["csrf_token"] = csrf
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("there was an error", html)
    msg = "Value must be drawn from the UNESCO Thesaurus."
    page.assert_contains(msg, html)
    csrf = page.get_csrf(html)

    m1 = data_db.get_formdata('m1')
    m1["dataTypes"] = "msc:datatype1"
    m1.add("dataTypes", "Not a datatype")
    m1["csrf_token"] = csrf
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    msg = "not a valid choice for this field"
    page.assert_contains(msg, html)
    csrf = page.get_csrf(html)

    m1 = data_db.get_formdata('m1')
    m1["locations-0-type"] = "Not a valid type"
    m1["locations-0-url"] = "http://Not a valid URL"
    m1["csrf_token"] = csrf
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("there was an error", html)
    msg = "Not a valid choice"
    page.assert_contains(msg, html)
    msg = "That URL does not look quite right."
    page.assert_contains(msg, html)
    csrf = page.get_csrf(html)

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        assert db.get('m', dict()).get('1', dict()).get(
            'dataTypes') == data_db.m1['dataTypes']
