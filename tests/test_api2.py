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
    print("DEBUG: predicted")
    print(ideal)
    print("DEBUG: actual")
    print(actual)
    assert ideal == actual
