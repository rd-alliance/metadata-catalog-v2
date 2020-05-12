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
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    # Test keyword validator
    m1 = data_db.get_formdata('m1')
    m1.update(page.get_all_hidden(html))
    m1["keywords-0"] = "Not a term"
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("there was an error", html)
    msg = "Value must be drawn from the UNESCO Thesaurus."
    page.assert_contains(msg, html)

    # Test built-in SelectMultipleField validator
    m1 = data_db.get_formdata('m1')
    m1.update(page.get_all_hidden(html))
    m1["dataTypes"] = "msc:datatype1"
    m1.add("dataTypes", "Not a datatype")
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    msg = "not a valid choice for this field"
    page.assert_contains(msg, html)

    # Test EmailOrURL (URL) validator
    m1 = data_db.get_formdata('m1')
    m1.update(page.get_all_hidden(html))
    m1["locations-0-type"] = "Not a valid type"
    m1["locations-1-url"] = "Not a valid URL"
    m1["locations-0-url"] = "http://Not a valid URL"
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("there was an error", html)
    msg = "Not a valid choice"
    page.assert_contains(msg, html)
    msg = "Please provide the protocol"
    page.assert_contains(msg, html)
    msg = "That URL does not look quite right."
    page.assert_contains(msg, html)

    # Test RequiredIf validator
    m1 = data_db.get_formdata('m1')
    m1.update(page.get_all_hidden(html))
    del m1["locations-0-type"]
    del m1["locations-1-url"]
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("there was an error", html)
    msg = "This field is required."
    page.assert_contains(msg, html)

    # Test built-in SelectField validator
    m1 = data_db.get_formdata('m1')
    m1.update(page.get_all_hidden(html))
    m1["identifiers-0-scheme"] = "Not a valid scheme"
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("there was an error", html)
    msg = "Not a valid choice"
    page.assert_contains(msg, html)

    # Test success of metadata editing form
    m1 = data_db.get_formdata('m1')
    m1.update(page.get_all_hidden(html))
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    msg = "Successfully added record."
    page.assert_contains(msg, html)

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        entry = db.get('m', dict()).get('1', dict())
        orig = json.loads(json.dumps(data_db.m1))
        orig['slug'] = 'test-scheme-1'
        assert orig == entry

    # Test redirection for bad numbers
    response = client.get('/edit/m12', follow_redirects=True)
    html = response.get_data(as_text=True)
    msg = "You are trying to update a record that doesn't exist."
    page.assert_contains(msg, html)
    msg = "Add new metadata scheme"
    page.assert_contains(msg, html)

    # Test stripping out bad tags
    m2 = data_db.get_formdata('m2')
    m2.update(page.get_all_hidden(html))
    m2['description'] = m2['description'].replace(
        '1.</p>',
        '<span class="mso-nasty">1</span><script>do_evil();</script>.</p>')
    response = client.post('/edit/m0', data=m2, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    msg = "Successfully added record."
    page.assert_contains(msg, html)

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        entry = db.get('m', dict()).get('2', dict())
        orig = json.loads(json.dumps(data_db.m2))
        del orig['versions']
        orig['slug'] = 'test-scheme-2'
        assert orig == entry

    # Test W3CDate validator
    response = client.get('/edit/m2/add')
    html = response.get_data(as_text=True)
    m2v1 = data_db.get_formdata('m2', version=0)
    m2v1.update(page.get_all_hidden(html))
    m2v1['issued'] = '01/01/2020'
    response = client.post('/edit/m2/add', data=m2v1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("there was an error", html)
    msg = "Please provide the date in yyyy-mm-dd format."
    page.assert_contains(msg, html)

    # Test adding version
    m2v1 = data_db.get_formdata('m2', version=0)
    m2v1.update(page.get_all_hidden(html))
    response = client.post('/edit/m2/add', data=m2v1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    msg = "Successfully added version."
    page.assert_contains(msg, html)

    # Test redirection for bad version numbers
    response = client.get('/edit/m2/12', follow_redirects=True)
    html = response.get_data(as_text=True)
    msg = "You are trying to update a version that doesn't exist."
    page.assert_contains(msg, html)
    msg = "Add new version"
    page.assert_contains(msg, html)

    # Test adding second version
    m2v2 = data_db.get_formdata('m2', version=1)
    m2v2.update(page.get_all_hidden(html))
    del m2v2["identifiers-0-id"]
    del m2v2["identifiers-0-scheme"]
    response = client.post('/edit/m2/add', data=m2v2, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    msg = "Successfully added version."
    page.assert_contains(msg, html)

    # Test editing second version
    response = client.get('/edit/m2/1')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    msg = "Edit version 2"
    page.assert_contains(msg, html)
    m2v2 = data_db.get_formdata('m2', version=1)
    m2v2.update(page.get_all_hidden(html))
    response = client.post('/edit/m2/1', data=m2v2, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    msg = "Successfully updated version."
    page.assert_contains(msg, html)

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        entry = db.get('m', dict()).get('2', dict())
        orig = json.loads(json.dumps(data_db.m2))
        orig['slug'] = 'test-scheme-2'
        assert orig == entry

    # Test redirection for version route for unversioned series
    response = client.get('/edit/g12/1', follow_redirects=True)
    html = response.get_data(as_text=True)
    assert response.status_code == 404

    response = client.get('/edit/g0')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    msg = "Add new organization"
    page.assert_contains(msg, html)

    # Test EmailOrURL (email) validator
    g1 = data_db.get_formdata('g1')
    g1.update(page.get_all_hidden(html))
    response = client.post('/edit/g0', data=g1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
