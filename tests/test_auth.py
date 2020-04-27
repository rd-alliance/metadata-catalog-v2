import re
from urllib.parse import urlencode
import json
import pytest
from flask import g, session


def test_oauth_login(client, auth, app, page):
    base = 'http://localhost'
    scope = 'read:user'
    callback = f'{base}/callback/test'
    appid = app.config['OAUTH_CREDENTIALS']['test']['id']
    userid = "test$testuser"
    username = "Test User"
    useremail = "test@localhost.local"

    # The following only appears on the home page when the user is logged in:
    auth_only = "<h2>Make changes</h2>"

    # Test profile creation via new OAuth login

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
    csrf = page.get_csrf(html)
    assert csrf

    response = client.post(
        '/create-profile',
        data={'csrf_token': csrf, 'name': username, 'email': useremail},
        follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    msg = "Profile successfully created."
    page.assert_contains(msg, html)
    page.assert_contains(auth_only)

    with open(app.config['USER_DATABASE_PATH']) as f:
        users = json.load(f)
        assert users.get('_default', dict()).get('1', dict()).get(
            'userid') == userid
        assert users.get('_default', dict()).get('1', dict()).get(
            'name') == username
        assert users.get('_default', dict()).get('1', dict()).get(
            'email') == useremail

    newemail = "test@example.com"

    response = client.get('/edit-profile')
    html = response.get_data(as_text=True)
    csrf = page.get_csrf(html)
    assert csrf

    # Test profile editing

    response = client.post(
        '/edit-profile',
        data={'csrf_token': csrf, 'name': username, 'email': newemail},
        follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    msg = "Profile successfully updated."
    page.assert_contains(msg, html)

    with open(app.config['USER_DATABASE_PATH']) as f:
        users = json.load(f)
        assert users.get('_default', dict()).get('1', dict()).get(
            'email') == newemail

    # Test regular logout

    response = client.get('/logout', follow_redirects=True)
    html = response.get_data(as_text=True)
    msg = "You were signed out."
    page.assert_contains(msg, html)
    page.assert_lacks(auth_only)

    # Test regular login via OAuth

    response = auth.login()
    html = response.get_data(as_text=True)
    msg = "Successfully signed in."
    page.assert_contains(msg, html)
    page.assert_contains(auth_only)

    # Test logout via profile deletion

    response = client.get('/remove-profile', follow_redirects=True)
    html = response.get_data(as_text=True)
    msg = "Your profile was successfully deleted."
    page.assert_contains(msg, html)
    page.assert_lacks(auth_only)

    with open(app.config['USER_DATABASE_PATH']) as f:
        users = json.load(f)
        assert users.get('_default', dict()).get('1', dict()).get(
            'userid') is None
