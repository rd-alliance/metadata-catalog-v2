import json
import pytest
from flask import g, session


def test_main_get(client, app, data_db):

    # Prepare database:
    data_db.write_db()
    data_db.write_terms()

    # Test getting one record:
    response = client.get('/api/m2', follow_redirects=True)
    assert response.status_code == 200
    ideal_data = data_db.get_api1data('m2')
    ideal = json.dumps(ideal_data, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    response = client.get('/api/m3', follow_redirects=True)
    assert response.status_code == 200
    ideal_data = data_db.get_api1data('m3')
    ideal = json.dumps(ideal_data, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    response = client.get('/api/g1', follow_redirects=True)
    assert response.status_code == 200
    ideal_data = data_db.get_api1data('g1')
    ideal = json.dumps(ideal_data, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    response = client.get('/api/t1', follow_redirects=True)
    assert response.status_code == 200
    ideal_data = data_db.get_api1data('t1')
    ideal = json.dumps(ideal_data, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    response = client.get('/api/c1', follow_redirects=True)
    assert response.status_code == 200
    ideal_data = data_db.get_api1data('c1')
    ideal = json.dumps(ideal_data, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    response = client.get('/api/e1', follow_redirects=True)
    assert response.status_code == 200
    ideal_data = data_db.get_api1data('e1')
    ideal = json.dumps(ideal_data, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    response = client.get('/api/q1', follow_redirects=True)
    assert response.status_code == 404

    response = client.get('/api/m0', follow_redirects=True)
    assert response.status_code == 404

    # Test getting list of records:
    response = client.get('/api/m', follow_redirects=True)
    assert response.status_code == 200
    total = data_db.count('m')
    ideal_data = {'metadata-schemes': list()}
    i = 0
    while i < total:
        i += 1
        ideal_data['metadata-schemes'].append({
            "id": i,
            "slug": getattr(data_db, f"m{i}").get('slug')})
    ideal = json.dumps(ideal_data, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    response = client.get('/api/g', follow_redirects=True)
    assert response.status_code == 200
    total = data_db.count('g')
    ideal_data = {'organizations': list()}
    i = 0
    while i < total:
        i += 1
        ideal_data['organizations'].append({
            "id": i,
            "slug": getattr(data_db, f"g{i}").get('slug')})
    ideal = json.dumps(ideal_data, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual


def test_tree_get(client, app, data_db):
    # Prepare database:
    data_db.write_db()
    data_db.write_terms()

    response = client.get('/api/subject-index', follow_redirects=True)
    assert response.status_code == 200
    ideal_data = [{
        "name": "Science",
        "url": "/subject/Science",
        "children": [{
            "name": "Earth sciences",
            "url": "/subject/Earth%20sciences"
        }, {
            "name": "Environmental sciences and engineering",
            "url": "/subject/Environmental%20sciences%20and%20engineering",
            "children": [{
                "name": "Ecosystems",
                "url": "/subject/Ecosystems",
                "children": [{
                    "name": "Ecological balance",
                    "url": "/subject/Ecological%20balance",
                    "children": [{
                        "name": "Biological diversity",
                        "url": "/subject/Biological%20diversity"}]}]}]}]}]
    ideal = json.dumps(ideal_data, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual
