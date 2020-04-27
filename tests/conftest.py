import os
import re
import tempfile

import pytest
from rdamsc import create_app


class AuthActions(object):
    def __init__(self, client, page):
        self._client = client
        self._page = page

    def login(self):
        r = self._client.get('/callback/test', follow_redirects=True)
        html = r.get_data(as_text=True)
        if "<h1>Create Profile</h1>" in html:
            csrf = self._page.get_csrf(html)
            m = re.search(
                r'<input [^>]+ name="name" [^>]+ value="([^"]+)">', html)
            username = m.group(1)
            m = re.search(
                r'<input [^>]+ name="email" [^>]+ value="([^"]+)">', html)
            useremail = m.group(1)
            return self._client.post(
                '/create-profile',
                data={'csrf_token': csrf,
                      'name': username,
                      'email': useremail},
                follow_redirects=True)
        return r

    def logout(self):
        return self._client.get('/logout')


class PageActions(object):
    def __init__(self):
        self.html = ''

    def read(self, html):
        '''Loads HTML ready to be tested or processed further. Could include
        additional prep, currently doesn't.'''
        self.html = html

    def get_csrf(self, html=None):
        '''Extracts CSRF token from page's form controls.'''
        if html is not None:
            self.read(html)
        m = re.search(
            r'<input id="csrf_token" name="csrf_token"'' type="hidden"'
            r' value="([^"]+)">', self.html)
        if not m:
            return None
        return m.group(1)

    def assert_contains(self, substring, html=None):
        '''Asserts page source includes substring.'''
        __tracebackhide__ = True
        if html is not None:
            self.read(html)
        if substring not in self.html:
            pytest.fail(f"‘{substring}’ not in page. Full page:\n{self.html}")

    def assert_lacks(self, substring, html=None):
        '''Asserts page source does not include substring.'''
        __tracebackhide__ = True
        if html is not None:
            self.read(html)
        if substring in self.html:
            pytest.fail(f"‘{substring}’ is in page. Full page:\n{self.html}")


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
def auth(client, page):
    return AuthActions(client, page)


@pytest.fixture
def page():
    return PageActions()
