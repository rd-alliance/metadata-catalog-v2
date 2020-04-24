import re
from urllib.parse import urlencode
import pytest
from flask import g, session


def is_in_html(sub, page):
    __tracebackhide__ = True
    if sub not in page:
        pytest.fail(f"‘{sub}’ not in page. Full page:\n{page}")


def not_in_html(sub, page):
    __tracebackhide__ = True
    if sub not in page:
        pytest.fail(f"‘{sub}’ is in page. Full page:\n{page}")


def test_oauth_login(client, app):
    base = 'http://localhost'
    scope = 'read:user'
    callback = f'{base}/callback/test'
    appid = app.config['OAUTH_CREDENTIALS']['test']['id']
    userid = "test$testuser"
    username = "Test User"
    useremail = "test@localhost.local"

    response = client.get('/authorize/test')
    assert response.status_code == 302
    url = ('https://localhost/login/oauth/authorize?' + urlencode({
        'scope': scope, 'redirect_uri': callback, 'client_id': appid}))
    assert response.headers['Location'] == url

    response = client.get('/callback/test')
    assert response.status_code == 302
    url = ('/create-profile?' + urlencode({
        'next': '/', 'name': username, 'email': useremail}))
    redirection = response.headers['Location']
    assert redirection.endswith(url)

    response = client.get(url)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    m = re.search(
        r'<input id="csrf_token" name="csrf_token"'' type="hidden"'
        r' value="([^"]+)">', html)
    assert m
    csrf = m.group(1)

    response = client.post(
        '/create-profile',
        data={'csrf_token': csrf, 'name': username, 'email': useremail},
        follow_redirects=True)
    assert response.status_code == 200
    msg = "Profile successfully created."
    html = response.get_data(as_text=True)
    is_in_html(msg, html)
    auth_only = "<h2>Make changes</h2>"
    is_in_html(auth_only, html)
