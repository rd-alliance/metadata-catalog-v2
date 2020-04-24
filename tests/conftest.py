import os
import re
import tempfile

import pytest
from rdamsc import create_app


class AuthActions(object):
    def __init__(self, client):
        self._client = client

    def login(self):
        r = self._client.get('/callback/test', follow_redirects=True)
        html = r.get_data(as_text=True)
        m = re.search(
            r'<input id="csrf_token" name="csrf_token"'' type="hidden"'
            r' value="([^"]+)">', html)
        if not m:
            return r
        csrf = m.group(1)
        m = re.search(r'<input [^>]+ name="name" [^>]+ value="([^"]+)">', html)
        username = m.group(1)
        m = re.search(r'<input [^>]+ name="email" [^>]+ value="([^"]+)">', html)
        useremail = m.group(1)
        return self._client.post(
            '/create-profile',
            data={'csrf_token': csrf, 'name': username, 'email': useremail},
            follow_redirects=True)

    def logout(self):
        return self._client.get('/logout')


@pytest.fixture
def app():
    inst_path = tempfile.mkdtemp()

    app = create_app({
        'TESTING': True,
        'MAIN_DATABASE_PATH': os.path.join(inst_path, 'data', 'db.json'),
        'USER_DATABASE_PATH': os.path.join(inst_path, 'users', 'db.json'),
        'OAUTH_DATABASE_PATH': os.path.join(inst_path, 'oauth', 'db.json'),
        'OPENID_FS_STORE_PATH': os.path.join(inst_path, 'open-id'),
        'OAUTH_CREDENTIALS': {
            'test': {
                'id': 'test-oauth-app-id',
                'secret': 'test-oauth-app-secret'}}
    })

    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


@pytest.fixture
def auth(client):
    return AuthActions(client)
