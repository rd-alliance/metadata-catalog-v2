import os
import pytest
from rdamsc import create_app


def test_config():
    assert not create_app().testing
    assert create_app({'TESTING': True}).testing


def test_bad_config():
    inst_path = '/'

    with pytest.raises(OSError):
        app = create_app({
            'TESTING': True,
            'MAIN_DATABASE_PATH': os.path.join(inst_path, 'data', 'db.json'),
            'VOCAB_DATABASE_PATH': os.path.join(inst_path, 'data', 'vocab.json'),
            'TERM_DATABASE_PATH': os.path.join(inst_path, 'data', 'terms.json'),
            'USER_DATABASE_PATH': os.path.join(inst_path, 'users', 'db.json'),
            'OAUTH_DATABASE_PATH': os.path.join(inst_path, 'oauth', 'db.json'),
            'OPENID_FS_STORE_PATH': os.path.join(inst_path, 'open-id'),
            'OAUTH_CREDENTIALS': {
                'test': {
                    'id': 'test-oauth-app-id',
                    'secret': 'test-oauth-app-secret'}}
        })


def test_hello(client, page):
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("<h1>Metadata Standards Catalog</h1>")
    page.assert_lacks("<h2>Make changes</h2>")


def test_terms_of_use(client, page):
    response = client.get('/terms-of-use')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("<h1>Terms of use</h1>", html)
