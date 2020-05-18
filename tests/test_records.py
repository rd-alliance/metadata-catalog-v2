import re
from urllib.parse import urlencode
import json
import pytest
from flask import g, session


def test_create_view_records(client, auth, app, page, data_db):
    auth.login()

    # Prepare term database:
    data_db.write_terms()

    # Test CSRF error message:
    m1 = data_db.get_formdata('m1')
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Add new metadata scheme")
    page.assert_contains(
        "Could not save changes as your form session has expired.")

    # Test keyword validator:
    m1 = data_db.get_formdata('m1')
    m1.update(page.get_all_hidden())
    m1["keywords-0"] = "Not a term"
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error")
    page.assert_contains("Value must be drawn from the UNESCO Thesaurus.")

    # Test built-in SelectMultipleField validator:
    m1 = data_db.get_formdata('m1')
    m1.update(page.get_all_hidden())
    m1["dataTypes"] = "msc:datatype1"
    m1.add("dataTypes", "Not a datatype")
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error")
    page.assert_contains("not a valid choice for this field")

    # Test EmailOrURL (URL) validator:
    m1 = data_db.get_formdata('m1')
    m1.update(page.get_all_hidden())
    m1["locations-0-type"] = "Not a valid type"
    m1["locations-1-url"] = "Not a valid URL"
    m1["locations-0-url"] = "http://Not a valid URL"
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error")
    page.assert_contains("Not a valid choice")
    page.assert_contains("Please provide the protocol")
    page.assert_contains("That URL does not look quite right.")

    # Test RequiredIf validator:
    m1 = data_db.get_formdata('m1')
    m1.update(page.get_all_hidden())
    del m1["locations-0-type"]
    del m1["locations-1-url"]
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error")
    page.assert_contains("This field is required.")

    # Test built-in SelectField validator:
    m1 = data_db.get_formdata('m1')
    m1.update(page.get_all_hidden())
    m1["identifiers-0-scheme"] = "Not a valid scheme"
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error")
    page.assert_contains("Not a valid choice")

    # Test success of metadata editing form:
    m1 = data_db.get_formdata('m1')
    m1.update(page.get_all_hidden())
    response = client.post('/edit/m0', data=m1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("Successfully added record.", html)

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        entry = db.get('m', dict()).get('1', dict())
        orig = json.loads(json.dumps(data_db.m1))
        orig['slug'] = 'test-scheme-1'
        assert orig == entry

    # Test redirection for bad numbers:
    response = client.get('/edit/m12', follow_redirects=True)
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "You are trying to update a record that doesn't exist.")
    page.assert_contains("Add new metadata scheme")

    # Test stripping out bad tags:
    m2 = data_db.get_formdata('m2')
    m2.update(page.get_all_hidden())
    m2['description'] = m2['description'].replace(
        '1.</p>',
        '<span class="mso-nasty">1</span><script>do_evil();</script>.</p>')
    response = client.post('/edit/m0', data=m2, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Successfully added record.")
    page.assert_contains(
        '<p>Paragraph 1.</p><p><a href="https://m.us/">Paragraph</a> 2.</p>')

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        entry = db.get('m', dict()).get('2', dict())
        orig = json.loads(json.dumps(data_db.m2))
        del orig['versions']
        orig['slug'] = 'test-scheme-2'
        assert orig == entry

    # Test normal version addition screen:
    response = client.get('/edit/m2/add')
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Add new version")

    # Test W3CDate validator:
    m2v1 = data_db.get_formdata('m2', version=0)
    m2v1.update(page.get_all_hidden())
    m2v1['issued'] = '01/01/2020'
    response = client.post('/edit/m2/add', data=m2v1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error")
    page.assert_contains("Please provide the date in yyyy-mm-dd format.")

    # Test adding version:
    m2v1 = data_db.get_formdata('m2', version=0)
    m2v1.update(page.get_all_hidden())
    response = client.post('/edit/m2/add', data=m2v1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("Successfully added version.", html)

    # Test redirection for bad version numbers:
    response = client.get('/edit/m2/12', follow_redirects=True)
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("You are trying to update a version that doesn't exist.")
    page.assert_contains("Add new version")

    # Test adding second version:
    m2v2 = data_db.get_formdata('m2', version=1)
    m2v2.update(page.get_all_hidden())
    del m2v2["identifiers-0-id"]
    del m2v2["identifiers-0-scheme"]
    response = client.post('/edit/m2/add', data=m2v2, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("Successfully added version.", html)

    # Test editing second version:
    response = client.get('/edit/m2/1')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Edit version 2")
    m2v2 = data_db.get_formdata('m2', version=1)
    m2v2.update(page.get_all_hidden())
    response = client.post('/edit/m2/1', data=m2v2, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("Successfully updated version.", html)

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        entry = db.get('m', dict()).get('2', dict())
        orig = json.loads(json.dumps(data_db.m2))
        orig['slug'] = 'test-scheme-2'
        assert orig == entry

    # Test presentation of name, no fullName:
    response = client.get('/edit/t0')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Add new tool")
    t1 = data_db.get_formdata('t1')
    t1.update(page.get_all_hidden())
    response = client.post('/edit/t0', data=t1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Successfully added record.")
    page.assert_contains("Forename Surname")

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        entry = db.get('t', dict()).get('1', dict())
        orig = json.loads(json.dumps(data_db.t1))
        orig['slug'] = 'test-tool-1'
        assert orig == entry

    # Test redirection for bad number and non-existent version:
    response = client.get('/edit/t12/3', follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "You are trying to update a record that doesn't exist.")
    page.assert_contains("Add new tool")

    t2 = data_db.get_formdata('t2')
    t2.update(page.get_all_hidden())
    response = client.post('/edit/t0', data=t2, follow_redirects=True)

    response = client.get('/edit/t2/add')
    html = response.get_data(as_text=True)
    t2v1 = data_db.get_formdata('t2', version=0)
    t2v1.update(page.get_all_hidden(html))
    response = client.post('/edit/t2/add', data=t2v1, follow_redirects=True)

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        entry = db.get('t', dict()).get('2', dict())
        orig = json.loads(json.dumps(data_db.t2))
        orig['slug'] = 'test-tool-2'
        assert orig == entry

    # Test presentation of fullName, familyName, givenName:
    response = client.get('/edit/c0')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Add new mapping")
    c1 = data_db.get_formdata('c1')
    c1.update(page.get_all_hidden())
    response = client.post('/edit/c0', data=c1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Successfully added record.")
    page.assert_contains("Given Family")
    page.assert_lacks("Forename Surname")

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        entry = db.get('c', dict()).get('1', dict())
        orig = json.loads(json.dumps(data_db.c1))
        orig['slug'] = 'test-crosswalk-1'
        assert orig == entry

    # Test redirection for version route for unversioned series:
    response = client.get('/edit/g12/1', follow_redirects=True)
    assert response.status_code == 404

    response = client.get('/edit/g0')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Add new organization")

    # Test EmailOrURL (email) validator:
    g1 = data_db.get_formdata('g1')
    g1.update(page.get_all_hidden())
    g1['locations-1-url'] = 'mailto:not-@-valid-address'
    response = client.post('/edit/g0', data=g1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("That email address does not look quite right.", html)
    g1['locations-1-url'] = 'mailto:' + 255*'@'
    response = client.post('/edit/g0', data=g1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("That email address is too long.")

    g1 = data_db.get_formdata('g1')
    g1.update(page.get_all_hidden())
    response = client.post('/edit/g0', data=g1, follow_redirects=True)

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        entry = db.get('g', dict()).get('1', dict())
        orig = json.loads(json.dumps(data_db.g1))
        orig['slug'] = 'organization-1'
        assert orig == entry

    # Test adding record with relations:
    response = client.get('/edit/e0')
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Add new endorsement")
    e1 = data_db.get_formdata('e1', with_relations=True)
    e1.update(page.get_all_hidden())
    e1['issued'] = "2017-12"
    e1.pop('valid-start')
    e1.pop('valid-end')
    endorsed_schemes = e1.poplist('endorsed_schemes')
    endorsed_schemes.pop()
    for s in endorsed_schemes:
        e1.add('endorsed_schemes', s)
    response = client.post('/edit/e0', data=e1, follow_redirects=True)
    html = response.get_data(as_text=True)
    page.assert_contains("Successfully added record.", html)

    # Test display of date without day:
    response = client.get(s.replace('msc:', '/msc/'))
    html = response.get_data(as_text=True)
    page.assert_contains("Endorsed in 2017-12", html)

    # Test adding record more relations of the same type:
    response = client.get('/edit/e1')
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Edit endorsement msc:e1")
    e1 = data_db.get_formdata('e1', with_relations=True)
    e1.update(page.get_all_hidden())
    e1.pop('valid-start')
    e1.pop('valid-end')
    response = client.post('/edit/e1', data=e1, follow_redirects=True)
    html = response.get_data(as_text=True)
    page.assert_contains("Successfully updated record.", html)

    # Test display of date with day:
    response = client.get(s.replace('msc:', '/msc/'))
    html = response.get_data(as_text=True)
    page.assert_contains("Endorsed on 2017-12-31", html)

    # Test display of date range:
    response = client.get('/edit/e1')
    html = response.get_data(as_text=True)
    e1 = data_db.get_formdata('e1', with_relations=True)
    e1.update(page.get_all_hidden(html))
    client.post('/edit/e1', data=e1, follow_redirects=True)
    response = client.get(s.replace('msc:', '/msc/'))
    html = response.get_data(as_text=True)
    page.assert_contains("Endorsed between 2018-01-01 and 2019-12-31", html)

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        entry = db.get('e', dict()).get('1', dict())
        orig = json.loads(json.dumps(data_db.e1))
        orig['slug'] = 'test-endorsement-1'
        assert orig == entry
        rel_entry = db.get('rel', dict()).get('1', dict())
        rel_orig = json.loads(json.dumps(data_db.rel1))
        assert rel_orig == rel_entry

    # Test generation of name/slug for mappings:
    response = client.get('/edit/c0')
    html = response.get_data(as_text=True)
    c2 = data_db.get_formdata('c2', with_relations=True)
    c2.update(page.get_all_hidden(html))
    response = client.post('/edit/c0', data=c2, follow_redirects=True)
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Successfully added record.")
    page.assert_contains("<h1>Test scheme 1 to Test scheme 2</h1>")
    response = client.get('/edit/c2/add')
    html = response.get_data(as_text=True)
    c2v1 = data_db.get_formdata('c2', version=0)
    c2v1.update(page.get_all_hidden(html))
    response = client.post('/edit/c2/add', data=c2v1, follow_redirects=True)

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        entry = db.get('c', dict()).get('2', dict())
        orig = json.loads(json.dumps(data_db.c2))
        orig['slug'] = 'test-scheme-1_TO_test-scheme-2'
        assert orig == entry
        rel_entry = db.get('rel', dict()).get('2', dict())
        rel_orig = json.loads(json.dumps(data_db.rel2))
        assert rel_orig == rel_entry

    # Get group update form:
    response = client.get('/edit/g1')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Edit organization msc:g1")

    # Test removing inverse relationships:
    g1 = data_db.get_formdata('g1')
    g1.update(page.get_all_hidden())
    response = client.post('/edit/g1', data=g1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("Successfully updated record.", html)

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        assert orig == entry
        rel_entry = db.get('rel', dict()).get('1', dict())
        rel_orig = json.loads(json.dumps(data_db.rel1))
        del rel_orig['originator']
        assert rel_orig == rel_entry
        rel_entry = db.get('rel', dict()).get('2', dict())
        rel_orig = json.loads(json.dumps(data_db.rel2))
        del rel_orig['funder']
        assert rel_orig == rel_entry

    # Test adding inverse relationships:
    response = client.get('/edit/g1')
    html = response.get_data(as_text=True)
    g1 = data_db.get_formdata('g1', with_relations=True)
    g1.update(page.get_all_hidden(html))
    response = client.post('/edit/g1', data=g1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("Successfully updated record.", html)

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        rel_entry = db.get('rel', dict()).get('1', dict())
        rel_orig = json.loads(json.dumps(data_db.rel1))
        assert rel_orig == rel_entry
        rel_entry = db.get('rel', dict()).get('2', dict())
        rel_orig = json.loads(json.dumps(data_db.rel2))
        assert rel_orig == rel_entry
        rel_entry = db.get('rel', dict()).get('3', dict())
        rel_orig = json.loads(json.dumps(data_db.rel3))
        assert rel_orig == rel_entry

    # Test removing forward relationships:
    response = client.get('/edit/e1')
    html = response.get_data(as_text=True)
    e1 = data_db.get_formdata('e1')
    e1.update(page.get_all_hidden(html))
    response = client.post('/edit/e1', data=e1, follow_redirects=True)

    with open(app.config['MAIN_DATABASE_PATH']) as f:
        db = json.load(f)
        rel_entry = db.get('rel', dict()).get('1', dict())
        assert {"@id": "msc:e1"} == rel_entry


def test_create_terms(client, auth, app, page, data_db):
    auth.login()

    # Create Datatype
    response = client.get('/edit/datatype100', follow_redirects=True)
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("<h1>Add new datatype</h1>")
    page.assert_contains(
        "You are trying to update a record that doesn't exist.")
    datatype1 = data_db.get_formdata('datatype1')
    datatype1.update(page.get_all_hidden())
    response = client.post(
        '/edit/datatype0', data=datatype1, follow_redirects=True)
    html = response.get_data(as_text=True)
    page.assert_contains("Successfully added record.", html)

    with open(app.config['TERM_DATABASE_PATH']) as f:
        db = json.load(f)
        rel_entry = db.get('datatype', dict()).get('1', dict())
        assert data_db.datatype1 == rel_entry

    # Test CSRF error message:
    loc1json = (
        '{ "id": "website", "label": "website",'
        '"applies": ["scheme", "organization", "tool"]}')
    loc1 = json.loads(loc1json)
    response = client.post('/edit/location1', data=loc1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Edit link type")
    page.assert_contains(
        "Could not save changes as your form session has expired.")

    # Test missing label
    del loc1['label']
    loc1.update(page.get_all_hidden())
    response = client.post('/edit/location1', data=loc1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error")
    page.assert_contains("This field is required.")

    # Test missing ID on new label
    response = client.get('/edit/type0', follow_redirects=True)
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("<h1>Add new entity type</h1>")
    type0 = {"label": "Test type", "applies": ["tool"]}
    type0.update(page.get_all_hidden())
    response = client.post('/edit/type0', data=loc1, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error")
    page.assert_contains("This field is required.")


def test_auth_protection(client, auth, app, page, data_db):
    data_db.write_db()
    data_db.write_terms()

    response = client.get('/edit/m1', follow_redirects=True)
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Please sign in to access this page.")
    page.assert_contains("<h1>Sign in</h1>")

    response = client.get('/edit/m2/0', follow_redirects=True)
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Please sign in to access this page.")
    page.assert_contains("<h1>Sign in</h1>")

    response = client.get('/edit/datatype1', follow_redirects=True)
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Please sign in to access this page.")
    page.assert_contains("<h1>Sign in</h1>")


