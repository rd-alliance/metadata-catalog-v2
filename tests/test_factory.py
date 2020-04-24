from rdamsc import create_app


def test_config():
    assert not create_app().testing
    assert create_app({'TESTING': True}).testing


def test_hello(client):
    response = client.get('/')
    assert response.status_code == 200
    title = "<h1>Metadata Standards Catalog</h1>"
    assert title in response.get_data(as_text=True)
    auth_only = "<h2>Make changes</h2>"
    assert auth_only not in response.get_data(as_text=True)
