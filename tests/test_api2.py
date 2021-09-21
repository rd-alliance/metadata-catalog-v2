import json
import pytest
import time
from flask import g, session
from requests.auth import _basic_auth_str
from itsdangerous import TimedJSONWebSignatureSerializer as JWS


def test_main_get(client, app, data_db):

    # Prepare database:
    data_db.write_db()

    # Test getting one record:
    response = client.get('/api2/m1', follow_redirects=True)
    assert response.status_code == 200
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'data': data_db.get_apidata('m1')
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    response = client.get('/api2/m3', follow_redirects=True)
    assert response.status_code == 200
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'data': data_db.get_apidata('m3')
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    response = client.get('/api2/q1', follow_redirects=True)
    assert response.status_code == 404

    response = client.get('/api2/m0', follow_redirects=True)
    assert response.status_code == 404

    # Test getting pages of records
    response = client.get('/api2/m', follow_redirects=True)
    assert response.status_code == 200
    total = data_db.count('m')
    current = total if total < 10 else 10
    page_total = ((total - 1) // 10) + 1
    ideal = {
        'apiVersion': '2.0.0',
        'data': {
            'itemsPerPage': 10,
            'currentItemCount': current,
            'startIndex': 1,
            'totalItems': total,
            'pageIndex': 1,
            'totalPages': page_total,
            'items': data_db.get_apidataset('m')[:10]
        },
    }
    if total > 10:
        ideal['data']['nextLink'] = (
            'http://localhost/api2/m?start=11&pageSize=10')
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual

    response = client.get('/api2/m?start=3&pageSize=2', follow_redirects=True)
    assert response.status_code == 200
    actual = response.get_json()
    assert actual['data']['totalPages'] == ((total - 1) // 2) + 1
    assert actual['data']['previousLink'] == (
        'http://localhost/api2/m?start=1&pageSize=2')

    response = client.get(
        '/api2/m?start=2&page=10&pageSize=2', follow_redirects=True)
    assert response.status_code == 200
    actual = response.get_json()
    assert actual['data']['totalPages'] == ((total - 1) // 2) + 2
    assert actual['data']['nextLink'].endswith('start=4&pageSize=2')
    assert actual['data']['previousLink'].endswith('start=1&pageSize=1')

    response = client.get('/api2/m?page=1&pageSize=2', follow_redirects=True)
    assert response.status_code == 200
    actual = response.get_json()
    assert actual['data']['nextLink'].endswith('page=2&pageSize=2')

    response = client.get('/api2/m?page=2&pageSize=2', follow_redirects=True)
    assert response.status_code == 200
    actual = response.get_json()
    assert actual['data']['previousLink'].endswith('page=1&pageSize=2')

    response = client.get('/api2/m?page=2&pageSize=2', follow_redirects=True)
    assert response.status_code == 200
    actual = response.get_json()
    assert actual['data']['previousLink'].endswith('page=1&pageSize=2')

    response = client.get('/api2/q', follow_redirects=True)
    assert response.status_code == 404
    response = client.get('/api2/m?start=0&pageSize=10', follow_redirects=True)
    assert response.status_code == 404
    response = client.get('/api2/m?start=99&pageSize=10', follow_redirects=True)
    assert response.status_code == 404
    response = client.get('/api2/m?page=0&pageSize=10', follow_redirects=True)
    assert response.status_code == 404
    response = client.get('/api2/m?page=9&pageSize=10', follow_redirects=True)
    assert response.status_code == 404

    # Test getting one relation
    response = client.get('/api2/rel/m1', follow_redirects=True)
    assert response.status_code == 200
    ideal = {
        'apiVersion': '2.0.0',
        'data': data_db.rel3
    }
    ideal['data']['uri'] = "http://localhost/api2/rel/m1"
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual

    response = client.get('/api2/rel/m10', follow_redirects=True)
    assert response.status_code == 404

    # Test getting page of relations
    response = client.get('/api2/rel', follow_redirects=True)
    assert response.status_code == 200
    results = data_db.get_apirelset()
    total = len(results)
    current = total if total < 10 else 10
    page_total = ((total - 1) // 10) + 1
    ideal = {
        'apiVersion': '2.0.0',
        'data': {
            'itemsPerPage': 10,
            'currentItemCount': current,
            'startIndex': 1,
            'totalItems': total,
            'pageIndex': 1,
            'totalPages': page_total,
            'items': results[:10]
        },
    }
    if total > 10:
        ideal['data']['nextLink'] = (
            'http://localhost/api2/rel?start=11&pageSize=10')
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual

    # Test getting one inverse relation
    response = client.get('/api2/invrel/g1', follow_redirects=True)
    assert response.status_code == 200
    results = data_db.get_apirelset(inverse=True)
    for result in results:
        if result['@id'] == 'msc:g1':
            g1rel = result
            break
    else:
        g1rel = None
    ideal = {
        'apiVersion': '2.0.0',
        'data': g1rel}
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual

    response = client.get('/api2/invrel/g10', follow_redirects=True)
    assert response.status_code == 404

    # Test getting page of inverse relations
    response = client.get('/api2/invrel', follow_redirects=True)
    assert response.status_code == 200
    total = len(results)
    current = total if total < 10 else 10
    page_total = ((total - 1) // 10) + 1
    ideal = {
        'apiVersion': '2.0.0',
        'data': {
            'itemsPerPage': 10,
            'currentItemCount': current,
            'startIndex': 1,
            'totalItems': total,
            'pageIndex': 1,
            'totalPages': page_total,
            'items': results[:10]
        },
    }
    if total > 10:
        ideal['data']['nextLink'] = (
            'http://localhost/api2/rel?start=11&pageSize=10')
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual


def test_term_get(client, app, data_db):

    # Prepare term database:
    data_db.write_terms()

    # Test getting one datatype
    response = client.get('/api2/datatype1', follow_redirects=True)
    assert response.status_code == 200
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'data': data_db.get_apidata('datatype1')
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test getting page of datatypes
    response = client.get('/api2/datatype', follow_redirects=True)
    assert response.status_code == 200
    total = data_db.count('datatype')
    current = total if total < 10 else 10
    page_total = ((total - 1) // 10) + 1
    ideal = {
        'apiVersion': '2.0.0',
        'data': {
            'itemsPerPage': 10,
            'currentItemCount': current,
            'startIndex': 1,
            'totalItems': total,
            'pageIndex': 1,
            'totalPages': page_total,
            'items': data_db.get_apidataset('datatype')[:10]
        },
    }
    if total > 10:
        ideal['data']['nextLink'] = (
            'http://localhost/api2/datatype?start=11&pageSize=10')
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual

    # Test getting one vocab term
    response = client.get('/api2/location1', follow_redirects=True)
    assert response.status_code == 200
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'data': data_db.get_apiterm('location', 1)
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test getting page of vocab terms
    response = client.get('/api2/location', follow_redirects=True)
    assert response.status_code == 200
    all_records = data_db.get_apitermset('location')
    total = len(all_records)
    current = total if total < 10 else 10
    page_total = ((total - 1) // 10) + 1
    ideal = {
        'apiVersion': '2.0.0',
        'data': {
            'itemsPerPage': 10,
            'currentItemCount': current,
            'startIndex': 1,
            'totalItems': total,
            'pageIndex': 1,
            'totalPages': page_total,
            'items': all_records[:10]
        },
    }
    if total > 10:
        ideal['data']['nextLink'] = (
            'http://localhost/api2/location?start=11&pageSize=10')
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual


def test_thesaurus(client, app, data_db):

    # Test getting full scheme record
    ideal = {
        "apiVersion": "2.0.0",
        "data": {
            "@context": {
                "skos": "http://www.w3.org/2004/02/skos/core#"},
            "@id": "http://rdamsc.bath.ac.uk/thesaurus",
            "@type": "skos:ConceptScheme",
            "skos:hasTopConcept": [{
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/domain0"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/domain1"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/domain2"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/domain3"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/domain4"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/domain5"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/domain6"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/domain7"}],
            "skos:prefLabel": [{
                "@language": "en",
                "@value": "RDA MSC Thesaurus"}]}}
    response = client.get('/api2/thesaurus', follow_redirects=True)
    assert response.status_code == 200
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual

    response = client.get('/thesaurus', follow_redirects=True)
    assert response.status_code == 200
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual

    # Test getting domain record
    response = client.get('/api2/thesaurus/domain0', follow_redirects=True)
    assert response.status_code == 200

    ideal = {
        "apiVersion": "2.0.0",
        "data": {
            "@context": {
                "skos": "http://www.w3.org/2004/02/skos/core#"},
            "@id": "http://rdamsc.bath.ac.uk/thesaurus/domain4",
            "@type": "skos:Concept",
            "skos:prefLabel": [{
                "@value": "Social and human sciences",
                "@language": "en"}],
            "skos:narrower": [{
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/subdomain405"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/subdomain410"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/subdomain415"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/subdomain420"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/subdomain425"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/subdomain430"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/subdomain435"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/subdomain440"
            }, {
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/subdomain445"}],
            "skos:topConceptOf": [{
                "@id": "http://rdamsc.bath.ac.uk/thesaurus"}]}}
    response = client.get('/api2/thesaurus/domain4', follow_redirects=True)
    assert response.status_code == 200
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual

    response = client.get('/api2/thesaurus/domain4?form=concept', follow_redirects=True)
    assert response.status_code == 200
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual

    response = client.get('/thesaurus/domain4', follow_redirects=True)
    assert response.status_code == 200
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual

    # Test getting subdomain record
    response = client.get('/api2/thesaurus/subdomain0', follow_redirects=True)
    assert response.status_code == 404

    ideal = {
        "apiVersion": "2.0.0",
        "data": {
            "@context": {
                "skos": "http://www.w3.org/2004/02/skos/core#"},
            "@id": "http://rdamsc.bath.ac.uk/thesaurus/subdomain655",
            "@type": "skos:Concept",
            "skos:broader": [{
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/domain6"}],
            "skos:narrower": [{
                "@id": "http://vocabularies.unesco.org/thesaurus/concept634"
            }, {
                "@id": "http://vocabularies.unesco.org/thesaurus/concept635"
            }, {
                "@id": "http://vocabularies.unesco.org/thesaurus/concept636"
            }, {
                "@id": "http://vocabularies.unesco.org/thesaurus/concept637"
            }, {
                "@id": "http://vocabularies.unesco.org/thesaurus/concept638"
            }, {
                "@id": "http://vocabularies.unesco.org/thesaurus/concept639"
            }, {
                "@id": "http://vocabularies.unesco.org/thesaurus/concept640"
            }, {
                "@id": "http://vocabularies.unesco.org/thesaurus/concept641"
            }, {
                "@id": "http://vocabularies.unesco.org/thesaurus/concept642"}],
            "skos:prefLabel": [{
                "@language": "en",
                "@value": "Materials and products"}]}}
    response = client.get('/api2/thesaurus/subdomain655', follow_redirects=True)
    assert response.status_code == 200
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual

    # Test getting concept record
    response = client.get('/api2/thesaurus/concept0', follow_redirects=True)
    assert response.status_code == 404

    ideal = {
        "apiVersion": "2.0.0",
        "data": {
            "@context": {
                "skos": "http://www.w3.org/2004/02/skos/core#"},
            "@id": "http://vocabularies.unesco.org/thesaurus/concept1811",
            "@type": "skos:Concept",
            "skos:broader": [{
                "@id": "http://vocabularies.unesco.org/thesaurus/concept634"}],
            "skos:narrower": [{
                "@id": "http://vocabularies.unesco.org/thesaurus/concept4918"}],
            "skos:prefLabel": [{
                "@language": "en",
                "@value": "Crops"}]}}
    response = client.get('/api2/thesaurus/concept1811', follow_redirects=True)
    assert response.status_code == 200
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual

    ideal['data']['skos:broader'] = [{
        "@id": "http://vocabularies.unesco.org/thesaurus/concept634",
        "@type": "skos:Concept",
        "skos:broader": [{
            "@id": "http://rdamsc.bath.ac.uk/thesaurus/subdomain655",
            "@type": "skos:Concept",
            "skos:broader": [{
                "@id": "http://rdamsc.bath.ac.uk/thesaurus/domain6",
                "@type": "skos:Concept",
                "skos:topConceptOf": [{
                    "@id": "http://rdamsc.bath.ac.uk/thesaurus"}]}]}]}]
    ideal['data']['skos:narrower'] = [{
        "@id": "http://vocabularies.unesco.org/thesaurus/concept4918",
        "@type": "skos:Concept",
        "skos:narrower": [{
            "@id": "http://vocabularies.unesco.org/thesaurus/concept2912"}]}]
    response = client.get('/api2/thesaurus/concept1811?form=tree', follow_redirects=True)
    assert response.status_code == 200
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual

    # Test getting page of complete list of concepts
    response = client.get('/api2/thesaurus/concepts')
    assert response.status_code == 200
    test_data = response.get_json()
    assert test_data.get("apiVersion") == "2.0.0"
    assert test_data.get("data").get("currentItemCount") == 10
    assert len(test_data.get("data").get("items")) == 10
    assert test_data.get("data").get("itemsPerPage") == 10
    assert test_data.get("data").get("nextLink") == "/api2/thesaurus/concepts?start=11&pageSize=10"
    assert test_data.get("data").get("pageIndex") == 1
    assert test_data.get("data").get("startIndex") == 1
    assert test_data.get("data").get("totalItems") == 4778
    assert test_data.get("data").get("totalPages") == 478
    assert test_data.get("data").get("items")[0] == {
        "@context": {
            "skos": "http://www.w3.org/2004/02/skos/core#",
        },
        "@id": "http://rdamsc.bath.ac.uk/thesaurus/domain0",
        "@type": "skos:Concept",
        "skos:prefLabel": [{
            "@language": "en",
            "@value": "Multidisciplinary",
        }],
        "skos:topConceptOf": [{
            "@id": "http://rdamsc.bath.ac.uk/thesaurus"
        }]}

    # Test getting page of list of concepts in use: none in use
    response = client.get('/api2/thesaurus/concepts/used')
    assert response.status_code == 200
    test_data = response.get_json()
    assert test_data.get("apiVersion") == "2.0.0"
    assert test_data.get("data").get("currentItemCount") == 0
    assert len(test_data.get("data").get("items")) == 0
    assert test_data.get("data").get("itemsPerPage") == 10
    assert test_data.get("data").get("pageIndex") == 1
    assert test_data.get("data").get("startIndex") == 1
    assert test_data.get("data").get("totalItems") == 0
    assert test_data.get("data").get("totalPages") == 0

    # Test getting page of list of concepts in use: some in use
    data_db.write_db()
    response = client.get('/api2/thesaurus/concepts/used')
    assert response.status_code == 200
    test_data = response.get_json()
    assert test_data.get("apiVersion") == "2.0.0"
    assert test_data.get("data").get("currentItemCount") == 2
    assert len(test_data.get("data").get("items")) == 2
    assert test_data.get("data").get("itemsPerPage") == 10
    assert test_data.get("data").get("pageIndex") == 1
    assert test_data.get("data").get("startIndex") == 1
    assert test_data.get("data").get("totalItems") == 2
    assert test_data.get("data").get("totalPages") == 1
    assert test_data.get("data").get("items")[0] == {
        "@context": {
            "skos": "http://www.w3.org/2004/02/skos/core#"
        },
        "@id": "http://rdamsc.bath.ac.uk/thesaurus/subdomain235",
        "@type": "skos:Concept",
        "skos:broader": [{
            "@id": "http://rdamsc.bath.ac.uk/thesaurus/domain2"
        }],
        "skos:narrower": [{
            "@id": "http://vocabularies.unesco.org/thesaurus/concept158"
        }, {
            "@id": "http://vocabularies.unesco.org/thesaurus/concept159"
        }, {
            "@id": "http://vocabularies.unesco.org/thesaurus/concept160"
        }, {
            "@id": "http://vocabularies.unesco.org/thesaurus/concept161"
        }, {
            "@id": "http://vocabularies.unesco.org/thesaurus/concept162"
        }, {
            "@id": "http://vocabularies.unesco.org/thesaurus/concept163"
        }, {
            "@id": "http://vocabularies.unesco.org/thesaurus/concept164"
        }, {
            "@id": "http://vocabularies.unesco.org/thesaurus/concept165"
        }],
        "skos:prefLabel": [{
            "@language": "en",
            "@value": "Earth sciences",
        }]}


def test_auth_api2(client, app, data_db, user_db):

    # Generate expired token:
    s = JWS(app.config['SECRET_KEY'], expires_in=1)
    old_token = s.dumps({'id': 1}).decode('ascii')
    expires = time.time() + 2

    # Install API user account
    user_db.write_db()

    # Reject calls with no credentials
    response = client.get(
        '/api2/user/token',
        follow_redirects=True)
    assert response.status_code == 401

    response = client.post(
        '/api2/user/reset-password',
        data={"new_password": "compromised"},
        follow_redirects=True)
    assert response.status_code == 401

    response = client.post(
        '/api2/m',
        json={"name": "Compromised"},
        follow_redirects=True)
    assert response.status_code == 401

    response = client.put(
        '/api2/g1',
        json={"name": "Compromised"},
        follow_redirects=True)
    assert response.status_code == 401

    response = client.delete(
        '/api2/t1',
        follow_redirects=True)
    assert response.status_code == 401

    response = client.put(
        '/api2/rel/c1',
        json={'input schemes': ['msc:m1']},
        follow_redirects=True)
    assert response.status_code == 401

    response = client.patch(
        '/api2/rel/e1',
        json=[{'op': 'add', 'path': '/endorsed schemes/-', 'value': 'msc:m3'}],
        follow_redirects=True)
    assert response.status_code == 401

    response = client.patch(
        '/api2/invrel/g1',
        json=[{'op': 'add', 'path': '/funded schemes/-', 'value': 'msc:m3'}],
        follow_redirects=True)
    assert response.status_code == 401

    # Reject call with bad credentials
    username = user_db.api_users1.get('userid')
    password = 'wrong'
    credentials = _basic_auth_str(username, password)
    response = client.get(
        '/api2/user/token',
        headers={"Authorization": credentials},
        follow_redirects=True)
    assert response.status_code == 401

    # Succeed with good credentials
    username = user_db.api_users1.get('userid')
    password = user_db.pwd1
    credentials = _basic_auth_str(username, password)
    response = client.get(
        '/api2/user/token',
        headers={"Authorization": credentials},
        follow_redirects=True)
    assert response.status_code == 200
    test_data = response.get_json()
    assert test_data.get("token")
    token = test_data.get("token")

    # Reset password: too short
    new_password = "short"
    credentials = f"Bearer {token}"
    response = client.post(
        '/api2/user/reset-password',
        headers={"Authorization": credentials},
        json={"new_password": new_password},
        follow_redirects=True)
    assert response.status_code == 400
    test_data = response.get_json()
    assert test_data.get('password_reset') is False

    # Reset password: not JSON
    new_password = "Replacement password"
    credentials = f"Bearer {token}"
    response = client.post(
        '/api2/user/reset-password',
        headers={"Authorization": credentials},
        data={"new_password": new_password},
        follow_redirects=True)
    assert response.status_code == 400
    test_data = response.get_json()
    assert test_data.get('password_reset') is False

    # Reset password: bad token
    credentials = f"Bearer GOBBLEDEGOOK"
    response = client.post(
        '/api2/user/reset-password',
        headers={"Authorization": credentials},
        data={"new_password": new_password},
        follow_redirects=True)
    assert response.status_code == 401

    # Reset password: expired token
    credentials = f"Bearer {old_token}"
    while expires > time.time():
        pass
    response = client.post(
        '/api2/user/reset-password',
        headers={"Authorization": credentials},
        json={"new_password": new_password},
        follow_redirects=True)
    assert response.status_code == 401

    # Reset password: okay
    credentials = f"Bearer {token}"
    response = client.post(
        '/api2/user/reset-password',
        headers={"Authorization": credentials},
        json={"new_password": new_password},
        follow_redirects=True)
    assert response.status_code == 200
    test_data = response.get_json()
    assert test_data.get('username') == username
    assert test_data.get('password_reset') is True

    # Test new password
    credentials = _basic_auth_str(username, new_password)
    response = client.get(
        '/api2/user/token',
        headers={"Authorization": credentials},
        follow_redirects=True)
    assert response.status_code == 200


def test_main_write(client, auth_api, app, data_db):

    available_records = set()

    def assert_okay(response):
        data = response.get_json()
        if response.status_code != 200:
            print(f"=====\nErrors:")
            print(data.get('error', dict()).get('errors'))
            print("=====")
        assert response.status_code == 200
        mscid = data.get('data', dict()).get('mscid')
        if mscid:
            available_records.add(mscid)

    # Install terms
    data_db.write_terms()

    # Test adding new scheme successfully
    record = data_db.get_apidata('m1')
    del record['relatedEntities']
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/m',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert_okay(response)
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'meta': {'conformance': 'useful'},
        'data': record
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test location/URL/email validator:
    record = data_db.get_apidata('g1')
    del record['relatedEntities']
    overlong_email = "mailto:" + ("x" * 63) + "@" + ("foobar." * 26) + "org"
    record['locations'].extend([
        # no url
        {"type": "website"},
        # bad url (no protocol)
        {"url": "not-a-url", "type": "website"},
        # bad url (other problem)
        {"url": "http://not-a-url", "type": "website"},
        # bad email (bad pattern)
        {"url": "mailto:not-@n-email", "type": "email"},
        # bad email (too long)
        {"url": overlong_email, "type": "email"},
        # no type
        {"url": "http://website.org/g1"},
        # bad type
        {"url": "http://website.org/g1", "type": "not-a-type"},
    ])
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/g',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'error': {
            'message': "Missing field: url.",
            'errors': [{
                'message': "Missing field: url.",
                'location': '$.locations[2]'
            }, {
                # Depends on starter pack of terms
                'message': "Value must include protocol: http, https, mailto.",
                'location': '$.locations[3].url'
            }, {
                'message': "Invalid URL: http://not-a-url.",
                'location': '$.locations[4].url'
            }, {
                'message': "Invalid email address.",
                'location': '$.locations[5].url'
            }, {
                'message': "Value must be 254 characters or fewer (actual "
                           f"length: {len(overlong_email)}).",
                'location': '$.locations[6].url'
            }, {
                'message': "Missing field: type.",
                'location': '$.locations[7]'
            }, {
                'message': "Invalid type: not-a-type."
                " Valid types: website, email.",
                'location': '$.locations[8].type'
            }]}
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test identifier validator:
    record = data_db.get_apidata('g1')
    del record['relatedEntities']
    record['identifiers'] = [
        # no id
        {'scheme': 'DOI'},
        # malformed DOI
        {'id': 'not-a-doi', 'scheme': 'DOI'},
        # malformed ROR
        {'id': 'not-a-ror', 'scheme': 'ROR'},
        # TODO: validation for other scheme types
        # no scheme
        {'id': '10.1234/g1'},
        # bad scheme
        {'id': '10.1234/g1', 'scheme': 'not-a-scheme'},
    ]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/g',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'error': {
            'message': "Missing field: id.",
            'errors': [{
                'message': "Missing field: id.",
                'location': '$.identifiers[0]'
            }, {
                'message': "Malformed DOI.",
                'location': '$.identifiers[1].id'
            }, {
                'message': "Malformed ROR.",
                'location': '$.identifiers[2].id'
            }, {
                'message': "Missing field: scheme.",
                'location': '$.identifiers[3]'
            }, {
                # Depends on starter pack of terms
                'message': "Invalid scheme: not-a-scheme. "
                           "Valid schemes: DOI, ROR.",
                'location': '$.identifiers[4].scheme'
            }]}
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test type validator:
    record = data_db.get_apidata('g1')
    del record['relatedEntities']
    record['types'] = ['not-a-type']
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/g',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    errmess = (
        "Invalid type: not-a-type. Valid types: standards body, archive, "
        "professional group, coordination group.")
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'error': {
            'message': errmess,
            'errors': [{
                'message': errmess,
                'location': '$.types[0]'
            }]}
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    record = data_db.get_apidata('c1')
    record['identifiers'] = [
        # malformed Handle
        {'id': 'not-a-handle', 'scheme': 'Handle'},
    ]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/c',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'error': {
            'message': "Malformed Handle.",
            'errors': [{
                'message': "Malformed Handle.",
                'location': '$.identifiers[0].id'
            }]}
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test adding new group successfully:
    record = data_db.get_apidata('g1')
    del record['relatedEntities']
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/g',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert_okay(response)
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'meta': {'conformance': 'useful'},
        'data': record
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test keywords validator:
    record = data_db.get_apidata('m2')
    del record['relatedEntities']
    bad_keyword = 'http://rdamsc.bath.ac.uk/thesaurus/not-a-term'
    record['keywords'] = [bad_keyword]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/m',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'error': {
            'message': f"Invalid term URI: {bad_keyword}.",
            'errors': [{
                'message': f"Invalid term URI: {bad_keyword}.",
                'location': '$.keywords[0]'
            }]}
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test datatype validator:
    record = data_db.get_apidata('m2')
    del record['relatedEntities']
    bad_keyword = 'msc:not-a-datatype1'
    record['dataTypes'] = [bad_keyword]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/m',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'error': {
            'message': f"No such datatype record: {bad_keyword}.",
            'errors': [{
                'message': f"No such datatype record: {bad_keyword}.",
                'location': '$.dataTypes[0]'
            }]}
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test other identifier scheme validators:
    record = data_db.get_apidata('m2')
    del record['relatedEntities']
    record['identifiers'] = [
        # malformed Handle
        {'id': 'not-a-handle', 'scheme': 'Handle'},
        # bad scheme
        {'id': '10.1234/m2', 'scheme': 'ROR'},
    ]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/m',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'error': {
            'message': "Malformed Handle.",
            'errors': [{
                'message': "Malformed Handle.",
                'location': '$.identifiers[0].id'
            }, {
                # Depends on starter pack of terms
                'message': "Invalid scheme: ROR. "
                           "Valid schemes: DOI, Handle.",
                'location': '$.identifiers[1].scheme'
            }]}
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test version ID validator:
    record = data_db.get_apidata('m2')
    del record['relatedEntities']
    record['versions'][0]['number'] = '1' * 33
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/m',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    ideal_error = "Value must be 32 characters or fewer (actual length: 33)."
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'error': {
            'message': ideal_error,
            'errors': [{
                'message': ideal_error,
                'location': '$.versions[0].number'
            }]}
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test period/date validators:
    record = data_db.get_apidata('m2')
    del record['relatedEntities']
    record['versions'][0]['valid']['start'] = '1 January 2020'
    record['versions'][0]['valid']['end'] = '1 January 2022'
    record['versions'][1]['valid']['start'] = '2022-01-01'
    record['versions'][1]['valid']['end'] = '2020-03-01'
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/m',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    ideal_error = "Date must be in yyyy or yyyy-mm or yyyy-mm-dd format."
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'error': {
            'message': ideal_error,
            'errors': [{
                'message': ideal_error,
                'location': '$.versions[0].valid.start'
            }, {
                'message': ideal_error,
                'location': '$.versions[0].valid.end'
            }, {
                'message': "End date is before start date.",
                'location': '$.versions[1].valid'
            }]}
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test namespace validators
    record = data_db.get_apidata('m2')
    del record['relatedEntities']
    record['versions'][0]['namespaces'] = [
        # no prefix
        {'uri': 'https://schemes.org/ns/bar/1.0/'},
        # overlong prefix
        {'prefix': 'bar1'*9, 'uri': 'https://schemes.org/ns/bar/1.0/'},
        # no uri
        {'prefix': 'bar1'},
        # bad uri (no protocol)
        {'prefix': 'bar1', "uri": "not-a-url"},
        # bad uri (no / or # at the end)
        {'prefix': 'bar1', "uri": "https://schemes.org/ns/bar/1.0"},
        # bad uri (other problem)
        {'prefix': 'bar1', "uri": "http://not-a-url/"},
    ]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/m',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    ideal_error = "Missing field: prefix."
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'error': {
            'message': ideal_error,
            'errors': [{
                'message': ideal_error,
                'location': '$.versions[0].namespaces[0]'
            }, {
                'message': "Value must be 32 characters or fewer "
                           "(actual length: 36).",
                'location': '$.versions[0].namespaces[1].prefix'
            }, {
                'message': "Missing field: uri.",
                'location': '$.versions[0].namespaces[2]'
            }, {
                'message': "Value must include protocol: http, https.",
                'location': '$.versions[0].namespaces[3].uri'
            }, {
                'message': "Value must end with / or #.",
                'location': '$.versions[0].namespaces[4].uri'
            }, {
                'message': "Invalid URI: http://not-a-url/.",
                'location': '$.versions[0].namespaces[5].uri'
            }]}
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test relation validator:
    record = data_db.get_apidata('m2')
    record['relatedEntities'] = [
        # Missing role
        {'id': 'msc:m1'},
        # Invalid role
        {'id': 'msc:m1', 'role': 'originator'},
        # Missing MSC ID
        {'role': 'parent scheme'},
        # Invalid MSC ID
        {'id': '10.1234/56', 'role': 'parent scheme'},
        # Non-existent MSC ID
        {'id': 'msc:m3', 'role': 'parent scheme'},
        # Existent but wrong type of MSC ID
        {'id': 'msc:g1', 'role': 'parent scheme'}]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/m',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'error': {
            'message': "Missing field: role.",
            'errors': [{
                'message': "Missing field: role.",
                'location': '$.relatedEntities[0]'
            }, {
                'message': "Invalid role: originator. "
                           "Valid roles: parent scheme, child scheme, "
                           "input to mapping, output from mapping, maintainer, "
                           "funder, user, tool, endorsement.",
                'location': '$.relatedEntities[1].role'
            }, {
                'message': "Missing field: id.",
                'location': '$.relatedEntities[2]'
            }, {
                'message': "Not a valid MSC ID: 10.1234/56.",
                'location': '$.relatedEntities[3].id'
            }, {
                'message': "No such record: msc:m3.",
                'location': '$.relatedEntities[4].id'
            }, {
                'message': "The record msc:g1 cannot take the role of parent "
                           "scheme.",
                'location': '$.relatedEntities[5]'
            }]}
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test adding relation when adding new record
    record = data_db.get_apidata('m2')
    # - Strip out all but the parent scheme relation
    orig_rels = record.get('relatedEntities')
    rels = list()
    while orig_rels:
        rel = orig_rels.pop(0)
        if rel.get('role') == 'parent scheme':
            # - Strip out all but the (reciprocal) child scheme relation
            rel_orig_rels = rel.get('data', dict()).get('relatedEntities')
            rel_rels = list()
            while rel_orig_rels:
                rel_rel = rel_orig_rels.pop(0)
                if rel_rel.get('role') == 'child scheme':
                    rel_rels.append(rel_rel)
            rel['data']['relatedEntities'] = rel_rels
            rels.append(rel)
    record['relatedEntities'] = rels
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/m',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert_okay(response)
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'meta': {'conformance': 'complete'},
        'data': record
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test update, not removing missing relation, HTML validator
    record_no_rel = record.copy()
    del record_no_rel['relatedEntities']
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.put(
        '/api2/m2',
        headers={"Authorization": credentials},
        json=record_no_rel,
        follow_redirects=True)
    assert_okay(response)
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'meta': {'conformance': 'complete'},
        'data': record
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test adding new tool successfully, filtering out unused keys
    record = data_db.get_apidata('t1')
    del record['relatedEntities']
    record['extra'] = 'Not included.'
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/t',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert_okay(response)
    del record['extra']
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'meta': {'conformance': 'useful'},
        'data': record
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test adding inverse relation when adding new record
    record = data_db.get_apidata('m3')
    # - Strip out all but the tools relation
    orig_rels = record.get('relatedEntities')
    rels = list()
    while orig_rels:
        rel = orig_rels.pop(0)
        if rel.get('role') == 'tool':
            # - Strip out all but the (reciprocal) child scheme relation
            rel_orig_rels = rel.get('data', dict()).get('relatedEntities')
            rel_rels = list()
            while rel_orig_rels:
                rel_rel = rel_orig_rels.pop(0)
                if rel_rel.get('role') == 'supported scheme':
                    rel_rels.append(rel_rel)
            rel['data']['relatedEntities'] = rel_rels
            rels.append(rel)
    record['relatedEntities'] = rels
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/m',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert_okay(response)
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'meta': {'conformance': 'valid'},
        'data': record
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual
    assert 'msc:m3' in available_records

    # Add remaining records:
    for table in ['m', 'g', 't', 'e', 'c']:
        i = 1
        while hasattr(data_db, f"{table}{i}"):
            if f"msc:{table}{i}" in available_records:
                i += 1
                continue

            record = data_db.get_apidata(f"{table}{i}")
            orig_rels = record.get('relatedEntities')
            rels = list()
            while orig_rels:
                rel = orig_rels.pop(0)
                del rel['data']
                if rel.get('id') in available_records:
                    rels.append(rel)
            record['relatedEntities'] = rels
            credentials = f"Bearer {auth_api.get_token()}"
            response = client.post(
                f'/api2/{table}',
                headers={"Authorization": credentials},
                json=record,
                follow_redirects=True)
            assert_okay(response)

            i += 1

    # Test validation errors for rel endpoint
    record = data_db.rel3.copy()
    del record['@id']
    record['funded schemes'] = 'msc:m2'
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/rel/m1',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()
    assert result['error']['errors'][0]['message'] == (
        "Invalid predicate: funded schemes. Valid predicates: "
        "parent schemes, maintainers, funders, users.")
    assert result['error']['errors'][0]['location'] == r'$.funded schemes'

    assert result['error']['errors'][1]['message'] == (
        "Value must be a list of MSC IDs.")
    assert result['error']['errors'][1]['location'] == r'$.funded schemes'

    del record['funded schemes']
    record['users'] = ['msc:g1', 'msc:g2']
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/rel/m1',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()
    assert result['error']['errors'][0]['message'] == (
        "No such record: msc:g2.")
    assert result['error']['errors'][0]['location'] == r'$.users[1]'

    # Apply forward relations for m1:
    del record['users']
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/rel/m1',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert_okay(response)

    patch = list()
    for key, value in data_db.rel4.items():
        if key == '@id':
            continue
        patch.append({
            'op': 'add',
            'path': f"/{key}",
            'value': value})
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/rel/m2',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert_okay(response)

    patch = [{
        'op': 'add',
        'path': '/funded schemes/0',
        'value': 'msc:m3'}]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/invrel/g1',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert_okay(response)

    # Have we successfully recreated the database?
    for table in ['m', 'g', 't', 'e', 'c']:
        i = 1
        while hasattr(data_db, f"{table}{i}"):
            response = client.get(f'/api2/{table}{i}', follow_redirects=True)
            assert_okay(response)
            ideal = json.dumps({
                'apiVersion': '2.0.0',
                'data': data_db.get_apidata(f"{table}{i}")
            }, sort_keys=True)
            actual = json.dumps(response.get_json(), sort_keys=True)
            assert ideal == actual

            i += 1

    # Test redirection for bad numbers:
    record = data_db.get_apidata('m1')
    del record['relatedEntities']
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.put(
        '/api2/m42',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=False)
    assert response.status_code == 302
    assert response.headers.get('Location').endswith('/api2/m')

    record = {'parent schemes': ['msc:m1']}
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.put(
        '/api2/rel/m42',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=False)
    assert response.status_code == 404

    # Test adding new relation record:
    record = {'parent schemes': ['msc:m1']}
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/rel/m4',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert_okay(response)

    # Test deletion (making sure we have an inverted relationship)
    record = {'parent schemes': ['msc:m4']}
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/rel/m3',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert_okay(response)

    credentials = f"Bearer {auth_api.get_token()}"
    response = client.delete(
        '/api2/m4',
        headers={"Authorization": credentials},
        follow_redirects=True)
    assert response.status_code == 204

    response = client.get(
        '/api2/m4',
        follow_redirects=True)
    assert response.status_code == 404

    response = client.get(
        '/api2/rel/m4',
        follow_redirects=True)
    assert response.status_code == 404

    response = client.get(
        '/api2/invrel/m4',
        follow_redirects=True)
    assert response.status_code == 404

    # But it should be possible to restore a deleted record via the API:
    record = data_db.get_apidata('m4')
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.put(
        '/api2/m4',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    print("Response for updating a deleted record:")
    print(json.dumps(response.get_json(), sort_keys=True))
    assert_okay(response)

    response = client.get(
        '/api2/m4',
        follow_redirects=True)
    assert response.status_code == 200


# Test suite for patch handling.
def test_rel_patch(client, auth_api, app, data_db):

    # Install terms
    data_db.write_terms()

    # Prepare database:
    data_db.write_db()

    # Test non-existent subject-record
    patch = [{
        'op': 'add',
        'path': '/parent schemes/-',
        'value': 'msc:m1'}]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/rel/m42',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 404

    patch = [{
        'op': 'add',
        'path': '/child schemes/-',
        'value': 'msc:m1'}]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/invrel/m42',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 404

    # Test syntactic validity of request
    patch = {
        'op': 'add',
        'path': '/maintainers/-',
        'value': 'msc:g1'}
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/rel/m1',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()
    assert result.get('error', dict()).get('message') == (
        "Input must be in JSON Patch format (an array of objects).")
    assert result['error']['errors'][0]['location'] == r'$'

    patch = ['op', 'add', 'path', '/maintainers/-', 'value', 'msc:g1']
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/rel/m1',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()
    assert len(result.get('error', dict()).get('errors', list())) > 0
    assert result['error']['errors'][0]['message'] == "Not a JSON object."
    assert result['error']['errors'][0]['location'] == r'$[0]'
    assert result['error']['errors'][5]['message'] == "Not a JSON object."
    assert result['error']['errors'][5]['location'] == r'$[5]'

    patch = ['op', 'add', 'path', '/maintained scheme/-', 'value', 'msc:m1']
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/invrel/g1',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()
    assert len(result.get('error', dict()).get('errors', list())) > 0
    assert result['error']['errors'][0]['message'] == "Not a JSON object."
    assert result['error']['errors'][0]['location'] == r'$[0]'
    assert result['error']['errors'][5]['message'] == "Not a JSON object."
    assert result['error']['errors'][5]['location'] == r'$[5]'

    patch = {
        'op': 'add',
        'path': '/child schemes/-',
        'value': 'msc:m2'}
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/invrel/m1',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()
    assert result.get('error', dict()).get('message') == (
        "Input must be in JSON Patch format (an array of objects).")
    assert result['error']['errors'][0]['location'] == r'$'

    patch = ['op', 'add', 'path', '/child schemes/-', 'value', 'msc:m2']
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/invrel/m1',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()
    assert len(result.get('error', dict()).get('errors', list())) > 0
    assert result['error']['errors'][0]['message'] == "Not a JSON object."
    assert result['error']['errors'][0]['location'] == r'$[0]'
    assert result['error']['errors'][5]['message'] == "Not a JSON object."
    assert result['error']['errors'][5]['location'] == r'$[5]'

    # Test that the patch can be parsed correctly
    patch = [{
        'path': '/funders/-',
        'value': 'msc:g1',
    }, {
        'op': 'bad op',
        'path': '/funders/-',
        'value': 'msc:g1',
    }, {
        'op': 'add',
        'value': 'msc:g1',
    }, {
        'op': 'add',
        'path': 'foobar',
        'value': 'msc:g1',
    }, {
        'op': 'add',
        'path': '/foobar',
        'value': 'msc:g1',
    }, {
        'op': 'add',
        'path': '/funders/10',
        'value': 'msc:g1',
    }, {
        'op': 'remove',
        'path': '/maintainers/-',
    }, {
        'op': 'remove',
        'path': '/funders/1',
    }, {
        'op': 'add',
        'path': '/funders/-',
    }]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/rel/m1',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()
    assert len(result.get('error', dict()).get('errors', list())) == len(patch)

    assert result['error']['errors'][0]['message'] == (
        "JSON object must have an ‘op’ member.")
    assert result['error']['errors'][0]['location'] == r'$[0]'

    assert result['error']['errors'][1]['message'] == (
        "Supported operations are add, remove, replace, test.")
    assert result['error']['errors'][1]['location'] == r'$[1].op'

    assert result['error']['errors'][2]['message'] == (
        "JSON object must have a ‘path’ member.")
    assert result['error']['errors'][2]['location'] == r'$[2]'

    assert result['error']['errors'][3]['message'] == (
        "The supplied path could not be parsed.")
    assert result['error']['errors'][3]['location'] == r'$[3].path'

    assert result['error']['errors'][4]['message'] == (
        "Invalid predicate: foobar. Valid predicates: "
        "parent schemes, maintainers, funders, users.")
    assert result['error']['errors'][4]['location'] == r'$[4].path'

    assert result['error']['errors'][5]['message'] == (
        "Cannot add a value at that position.")
    assert result['error']['errors'][5]['location'] == r'$[5].path'

    assert result['error']['errors'][6]['message'] == (
        "No values exist at that position.")
    assert result['error']['errors'][6]['location'] == r'$[6].path'

    assert result['error']['errors'][7]['message'] == (
        "No value exists at that position.")
    assert result['error']['errors'][7]['location'] == r'$[7].path'

    assert result['error']['errors'][8]['message'] == (
        "JSON object must have a ‘value’ member when ‘op’ is add.")
    assert result['error']['errors'][8]['location'] == r'$[8]'

    # Test for errors applying test patch
    patch = [{
        'op': 'test',
        'path': '/funders',
        'value': ['msc:c1'],
    }, {
        'op': 'test',
        'path': '/funders/-',
        'value': 'msc:c1',
    }]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/rel/m1',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()
    assert len(result.get('error', dict()).get('errors', list())) == len(patch)

    assert result['error']['errors'][0]['message'] == (
        "Test failed. Current value would be ['msc:g1'].")
    assert result['error']['errors'][0]['location'] == r'$[0].value'
    assert result['error']['errors'][1]['message'] == (
        "Test failed. Current value would be msc:g1.")
    assert result['error']['errors'][1]['location'] == r'$[1].value'

    # Test for errors applying remove patch
    patch = [{
        'op': 'remove',
        'path': '/endorsements',
    }]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/invrel/m4',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()
    assert len(result.get('error', dict()).get('errors', list())) == len(patch)

    assert result['error']['errors'][0]['message'] == (
        "Predicate already missing.")
    assert result['error']['errors'][0]['location'] == r'$[0].path'

    # Test for errors applying add/replace patch
    patch = [{
        'op': 'add',
        'path': '/funders',
        'value': 'msc:g1',
    }, {
        'op': 'add',
        'path': '/funders/-',
        'value': ['msc:g1'],
    }, {
        'op': 'replace',
        'path': '/funders',
        'value': 'msc:g1',
    }, {
        'op': 'replace',
        'path': '/funders/-',
        'value': ['msc:g1'],
    }, {
        'op': 'replace',
        'path': '/maintainers',
        'value': ['msc:g1'],
    }, {
        'op': 'replace',
        'path': '/maintainers/-',
        'value': 'msc:g1',
    }]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/rel/m1',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()
    assert len(result.get('error', dict()).get('errors', list())) == len(patch)

    assert result['error']['errors'][0]['message'] == (
        "Value must be a list of MSC IDs.")
    assert result['error']['errors'][0]['location'] == r'$[0].value'

    assert result['error']['errors'][1]['message'] == (
        "Value must be a single MSC ID.")
    assert result['error']['errors'][1]['location'] == r'$[1].value'

    assert result['error']['errors'][2]['message'] == (
        "Value must be a list of MSC IDs.")
    assert result['error']['errors'][2]['location'] == r'$[2].value'

    assert result['error']['errors'][3]['message'] == (
        "Value must be a single MSC ID.")
    assert result['error']['errors'][3]['location'] == r'$[3].value'

    assert result['error']['errors'][4]['message'] == (
        "Predicate needs to be added.")
    assert result['error']['errors'][4]['location'] == r'$[4].path'

    assert result['error']['errors'][5]['message'] == (
        "No values exist at that position.")
    assert result['error']['errors'][5]['location'] == r'$[5].path'

    # Test for errors in relation values
    patch = [{
        'op': 'add',
        'path': '/funders',
        'value': ['msc:m1'],
    }, {
        'op': 'add',
        'path': '/funders/-',
        'value': 'foobar',
    }, {
        'op': 'replace',
        'path': '/funders',
        'value': ['msc:g42'],
    }, {
        'op': 'replace',
        'path': '/funders/-',
        'value': 'msc:m2',
    }]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/rel/m1',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 400

    result = response.get_json()
    assert len(result.get('error', dict()).get('errors', list())) == len(patch)

    assert result['error']['errors'][0]['message'] == (
        "Cannot associate a record with itself.")
    assert result['error']['errors'][0]['location'] == r'$[0].value[0]'

    assert result['error']['errors'][1]['message'] == (
        "Not a valid MSC ID: foobar.")
    assert result['error']['errors'][1]['location'] == r'$[1].value'

    assert result['error']['errors'][2]['message'] == (
        "No such record: msc:g42.")
    assert result['error']['errors'][2]['location'] == r'$[2].value[0]'

    assert result['error']['errors'][3]['message'] == (
        "The record msc:m2 cannot be used with the predicate funders.")
    assert result['error']['errors'][3]['location'] == r'$[3].value'

    # Test adding first relation with a patch
    patch = [{
        'op': 'add',
        'path': '/supported schemes',
        'value': ['msc:m1']}]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/rel/t2',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 200
    result = response.get_json()
    assert result['data']['supported schemes'] == ['msc:m1']

    patch = [{
        'op': 'add',
        'path': '/maintainers/-',
        'value': 'msc:g1'}]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/rel/t2',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 200
    result = response.get_json()
    assert result['data']['maintainers'] == ['msc:g1']

    # Test successful test and replace
    patch = [{
        'op': 'replace',
        'path': '/supported schemes',
        'value': ['msc:m2']
    }, {
        'op': 'test',
        'path': '/supported schemes',
        'value': ['msc:m2']
    }, {
        'op': 'replace',
        'path': '/supported schemes/0',
        'value': 'msc:m3'
    }, {
        'op': 'test',
        'path': '/supported schemes/0',
        'value': 'msc:m3'
    }]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/rel/t2',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 200
    result = response.get_json()
    assert result['data']['supported schemes'] == ['msc:m3']

    # Test successful remove
    patch = [{
        'op': 'remove',
        'path': '/supported schemes/-'}]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/rel/t2',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 200
    result = response.get_json()
    assert len(result['data']['supported schemes']) == 0

    patch = [{
        'op': 'remove',
        'path': '/tools'}]
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.patch(
        '/api2/invrel/m3',
        headers={"Authorization": credentials},
        json=patch,
        follow_redirects=True)
    assert response.status_code == 200
    result = response.get_json()
    assert 'tools' not in result['data']


# Test suite for editing DataTypes and VocabTerms.
def test_term_write(client, auth_api, app, data_db):

    # Test error on missing required field:
    record = data_db.get_apidata('datatype1')
    del record['label']
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/datatype',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()

    assert result['error']['errors'][0]['message'] == (
        "Missing field: label.")
    assert result['error']['errors'][0]['location'] == '$'

    # Test adding new datatype successfully
    record = data_db.get_apidata('datatype1')
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/datatype',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 200
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'meta': {'conformance': 'complete'},
        'data': record
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    # Test overly long vocab term ID:
    record = {
        'id': "x"*65,
        'label': "Test"}
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/location',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()

    assert result['error']['errors'][0]['message'] == (
        "Value must be 64 characters or fewer (actual length: 65).")
    assert result['error']['errors'][0]['location'] == '$.id'

    # Test bad applies:
    record = {
        'id': "contact",
        'label': "contact form",
        'applies': ['datatype']}
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/location',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()

    assert result['error']['errors'][0]['message'] == (
        "Invalid series: datatype. Valid series: "
        "scheme, tool, mapping, organization, endorsement.")
    assert result['error']['errors'][0]['location'] == '$.applies[0]'

    record = {
        'id': "contact",
        'label': "contact form",
        'applies': 'datatype'}
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/location',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 400
    result = response.get_json()

    assert result['error']['errors'][0]['message'] == (
        "Value must be a list (one or more of "
        "scheme, tool, mapping, organization, endorsement).")
    assert result['error']['errors'][0]['location'] == '$.applies'

    record = {
        'mscid': 'msc:id_scheme4',
        'id': "ISNI",
        'label': "ISNI",
        'applies': ['organization']}
    credentials = f"Bearer {auth_api.get_token()}"
    response = client.post(
        '/api2/id_scheme',
        headers={"Authorization": credentials},
        json=record,
        follow_redirects=True)
    assert response.status_code == 200
    record['uri'] = "http://localhost/api2/id_scheme4"
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'meta': {'conformance': 'complete'},
        'data': record
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    credentials = f"Bearer {auth_api.get_token()}"
    response = client.delete(
        '/api2/datatype1',
        headers={"Authorization": credentials},
        follow_redirects=True)
    assert response.status_code == 204

    response = client.get(
        '/api2/datatype1',
        follow_redirects=True)
    assert response.status_code == 404

    credentials = f"Bearer {auth_api.get_token()}"
    response = client.delete(
        '/api2/id_scheme4',
        headers={"Authorization": credentials},
        follow_redirects=True)
    assert response.status_code == 204

    response = client.get(
        '/api2/id_scheme4',
        follow_redirects=True)
    assert response.status_code == 404
