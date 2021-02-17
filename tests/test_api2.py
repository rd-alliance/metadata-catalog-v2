import json
import pytest
from flask import g, session
from requests.auth import _basic_auth_str


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

    # Install API user account
    user_db.write_db()

    # Reject call with no credentials
    response = client.get(
        '/api2/user/token',
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
