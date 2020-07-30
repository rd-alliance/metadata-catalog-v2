import json
import pytest
from flask import g, session


def test_m_get(client, app, data_db):

    # Prepare term database:
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
            'items': data_db.get_apidataset('m')
        },
    }
    if total > 10:
        ideal['data']['nextLink'] = (
            'http://localhost/api2/m?start=11&pagesize=10')
    actual = json.dumps(response.get_json(), sort_keys=True)
    assert json.dumps(ideal, sort_keys=True) == actual
