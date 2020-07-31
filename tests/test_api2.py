import json
import pytest
from flask import g, session


def test_m_get(client, app, data_db):

    # Prepare term database:
    data_db.write_db()
    data_db.write_terms()

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

    response = client.get('/api2/datatype1', follow_redirects=True)
    assert response.status_code == 200
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'data': data_db.get_apidata('datatype1')
    }, sort_keys=True)
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert ideal == actual

    response = client.get('/api2/location1', follow_redirects=True)
    assert response.status_code == 200
    ideal = json.dumps({
        'apiVersion': '2.0.0',
        'data': data_db.get_apiterm('location', 1)
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
