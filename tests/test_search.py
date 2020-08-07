def test_scheme_search(client, page, data_db):
    data_db.write_db()
    data_db.write_terms()

    # Test CSRF
    query = {"title": "Test"}
    response = client.post('/search', data=query, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "Could not perform search as your form session has expired.")

    # Test one query, four results
    hidden = page.get_all_hidden()
    query.update(hidden)
    response = client.post('/search', data=query, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        f"Found 4 schemes with title matching \"{query['title']}\".")
    page.assert_lacks(
        "Found 4 schemes in total.")

    # Test finding version by title
    response = client.get('/search')
    html = response.get_data(as_text=True)
    hidden = page.get_all_hidden(html)
    query = {"title": "Scheme version"}
    query.update(hidden)
    response = client.post('/search', data=query, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        f"Found 1 scheme with title matching \"{query['title']}\".")
    page.assert_lacks(
        "Found 1 scheme in total.")
    page.assert_contains("<h1>Test scheme 2</h1>")

    # Test one query, one result
    query = {"identifier": "10.1234/m1"}
    query.update(hidden)
    response = client.post('/search', data=query, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        f"Found 1 scheme with identifier \"{query['identifier']}\".")
    page.assert_lacks(
        "Found 1 scheme in total.")
    page.assert_contains("<h1>Test scheme 1</h1>")

    # Test finding version by ID
    query = {"identifier": "10.1234/m2v1"}
    query.update(hidden)
    response = client.post('/search', data=query, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        f"Found 1 scheme with identifier \"{query['identifier']}\".")
    page.assert_lacks(
        "Found 1 scheme in total.")
    page.assert_contains("<h1>Test scheme 2</h1>")

    # Test multiple keywords, spot on
    query = hidden.copy()
    kws = ["Earth sciences", "Biological diversity"]
    for i, kw in enumerate(kws):
        query.update({f"keywords-{i}": kw})
    response = client.post('/search', data=query, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        f"Found 2 schemes related to {' and '.join(kws)}.")

    # Test keyword ancestor
    query = hidden.copy()
    kws = ["Science"]
    for i, kw in enumerate(kws):
        query.update({f"keywords-{i}": kw})
    response = client.post('/search', data=query, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        f"Found 2 schemes related to {' and '.join(kws)}.")

    # Test keyword descendent
    query = hidden.copy()
    kws = ["Geodynamics"]
    for i, kw in enumerate(kws):
        query.update({f"keywords-{i}": kw})
    response = client.post('/search', data=query, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        f"Found 2 schemes related to {' and '.join(kws)}.")

    # Test unrepresented keyword
    query = hidden.copy()
    kws = ["Ecological crisis"]
    for i, kw in enumerate(kws):
        query.update({f"keywords-{i}": kw})
    response = client.post('/search', data=query, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        f"No schemes found related to {' and '.join(kws)}.")

    # Test bad keyword
    query = hidden.copy()
    kws = ["Wurzels"]
    for i, kw in enumerate(kws):
        query.update({f"keywords-{i}": kw})
    response = client.post('/search', data=query, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "Could not perform search as there was an error.")
    page.assert_contains(
        "Value must be drawn from the UNESCO Thesaurus.")

    # Test multiple criteria, regex
    query = {"funder": "Org*", "dataType": "Dataset"}
    query.update(hidden)
    response = client.post('/search', data=query, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        f"Found 2 schemes with funder matching \"{query['funder']}\".")
    page.assert_contains(
        f"Found 2 schemes used with data of type \"{query['dataType']}\".")
    page.assert_contains(
        "Found 3 schemes in total.")

    # Test unknown funder
    query = {"funder": "EPSRC"}
    query.update(hidden)
    response = client.post('/search', data=query, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        f"No funders found matching \"{query['funder']}\".")

    # Test unknown datatype
    query = {"dataType": "Shopping list"}
    query.update(hidden)
    response = client.post('/search', data=query, follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        f"No schemes found used with data of type \"{query['dataType']}\".")


def test_subject_search(client, page, data_db):
    data_db.write_db()
    data_db.write_terms()

    # Test exact matching subject
    response = client.get('/subject/Biological diversity')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "<h1>Biological diversity</h1>")
    page.assert_contains("Found 2 schemes.")

    # Test keyword ancestor
    response = client.get('/subject/Science')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "<h1>Science</h1>")
    page.assert_contains("Found 2 schemes.")

    # Test keyword descendent
    response = client.get('/subject/Geodynamics')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "<h1>Geodynamics</h1>")
    page.assert_contains("Found 2 schemes.")

    # Test unrepresented keyword
    response = client.get('/subject/Ecological crisis')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "<h1>Ecological crisis</h1>")
    page.assert_contains(
        "No schemes have been associated with this subject area.")

    # Test bad keyword
    response = client.get('/subject/Wurzels')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "<h1>Wurzels</h1>")
    page.assert_contains(
        'The subject "Wurzels" was not found in the thesaurus.')


def test_datatype_search(client, page, data_db):
    data_db.write_db()
    data_db.write_terms()

    # Test results for existing datatype
    response = client.get('/datatype/datatype1')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "<h1>Dataset</h1>")
    page.assert_contains("Found 2 schemes used for this type of data.")

    # Test no results for existing datatype
    response = client.get('/datatype/datatype2')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "<h1>Catalog</h1>")
    page.assert_contains(
        "No schemes have been reported to be used for this type of data.")

    # Test results for non-existent datatype
    response = client.get('/datatype/datatype0')
    assert response.status_code == 404


def test_group_search(client, page, data_db):
    data_db.write_db()

    # Test results for role
    response = client.get('/funder/g1')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "<h1>Organization 1</h1>")
    page.assert_contains("Found 2 schemes funded by this organization.")

    # Test no results for role
    response = client.get('/maintainer/g1')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "<h1>Organization 1</h1>")
    page.assert_contains(
        "No schemes found that are maintained by this organization.")

    # Test results for bad role
    response = client.get('/usurper/g1')
    assert response.status_code == 404

    # Test results for bad group
    response = client.get('/user/g2')
    assert response.status_code == 404
