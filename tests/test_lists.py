def test_record_index(client, page, data_db):
    data_db.write_db()

    response = client.get('/scheme-index')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains('Index of metadata standards')
    page.assert_contains(
        '  ' * 3 +
        '<a class="nav-link" href="/msc/m1">Test scheme 1</a>')
    page.assert_contains(
        '  ' * 5 +
        '<a class="nav-link" href="/msc/m2">Test scheme 2</a>')

    response = client.get('/scheme-index/endorsed schemes')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        '  ' * 3 +
        '<a class="nav-link" href="/msc/m1">Test scheme 1</a>')

    response = client.get('/tool-index')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains('Index of tools')
    page.assert_contains(
        '  ' * 3 +
        '<a class="nav-link" href="/msc/t1">Test tool 1</a>')

    response = client.get('/organization-index')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains('Index of organizations', html=html)

    response = client.get('/organization-index/funders')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        '  ' * 3 +
        '<a class="nav-link" href="/msc/g1">Organization 1</a>')

    response = client.get('/mapping-index')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains('Index of mappings', html=html)

    response = client.get('/endorsement-index')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains('Index of endorsements', html=html)

    response = client.get('/-index/')
    assert response.status_code == 404

    response = client.get('/badseries-index')
    assert response.status_code == 404

    response = client.get('/datatype-index')
    assert response.status_code == 404

    response = client.get('/location-index')
    assert response.status_code == 404

    response = client.get('/mapping-index/badrole')
    assert response.status_code == 404

    response = client.get('/organization-index/endorsed schemes')
    assert response.status_code == 404

    response = client.get('/endorsement-index/funders')
    assert response.status_code == 404


def test_bad_record_index(client, page, data_db):
    data_db.write_bad_db()  # This has an infinite loop in it

    response = client.get('/scheme-index')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        '  ' * 5 +
        '<a class="nav-link" href="/msc/m2">Test scheme 2</a>')
    page.assert_contains(
        '  ' * 7 +
        '<a class="nav-link" href="/msc/m3">Test scheme 3</a>')


def test_subject_index(client, page, data_db):
    data_db.write_db()

    response = client.get('/subject-index')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        '<a class="nav-link" href="/subject/Science">Science</a>')
    page.assert_contains(
        '<a class="nav-link" href="/subject/Earth%20sciences">Earth sciences</a>')
    page.assert_contains(
        '<a class="nav-link" href="/subject/Environmental%20sciences%20and%20engineering">'
        'Environmental sciences and engineering</a>')
    page.assert_contains(
        '<a class="nav-link" href="/subject/Ecosystems">Ecosystems</a>')
    page.assert_contains(
        '<a class="nav-link" href="/subject/Ecological%20balance">'
        'Ecological balance</a>')
    page.assert_contains(
        '<a class="nav-link" href="/subject/Biological%20diversity">'
        'Biological diversity</a>')
    page.assert_lacks("Arts and humanities")
    page.assert_lacks("Geography and oceanography")
    page.assert_lacks("Energy policy")
    page.assert_lacks("Biosphere")
    page.assert_lacks("Ecological crisis")
