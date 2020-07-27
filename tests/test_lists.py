def test_record_index(client, page, data_db):
    data_db.write_db()

    response = client.get('/scheme-index')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        '  ' * 3 +
        '<p><a href="/msc/m1">Test scheme 1</a></p>')
    page.assert_contains(
        '  ' * 5 +
        '<p><a href="/msc/m2">Test scheme 2</a></p>')

    response = client.get('/scheme-index/endorsed schemes')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        '  ' * 3 +
        '<p><a href="/msc/m1">Test scheme 1</a></p>')

    response = client.get('/tool-index')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        '  ' * 3 +
        '<p><a href="/msc/t1">Test tool 1</a></p>')

    response = client.get('/organization-index/funders')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        '  ' * 3 +
        '<p><a href="/msc/g1">Organization 1</a></p>')

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


def test_subject_index(client, page, data_db):
    data_db.write_db()

    response = client.get('/subject-index')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        '<p><a href="/subject/Science">Science</a></p>')
    page.assert_contains(
        '<p><a href="/subject/Earth%20sciences">Earth sciences</a></p>')
    page.assert_contains(
        '<p><a href="/subject/Environmental%20sciences%20and%20engineering">'
        'Environmental sciences and engineering</a></p>')
    page.assert_contains(
        '<p><a href="/subject/Ecosystems">Ecosystems</a></p>')
    page.assert_contains(
        '<p><a href="/subject/Ecological%20balance">'
        'Ecological balance</a></p>')
    page.assert_contains(
        '<p><a href="/subject/Biological%20diversity">'
        'Biological diversity</a></p>')
    page.assert_lacks("Arts and humanities")
    page.assert_lacks("Geography and oceanography")
    page.assert_lacks("Energy policy")
    page.assert_lacks("Biosphere")
    page.assert_lacks("Ecological crisis")
