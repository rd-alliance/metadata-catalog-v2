import json
from urllib.parse import urlencode


def test_bad_provider(client):
    # Unsupported provider:
    response = client.get('/authorize/null')
    assert response.status_code == 404

    response = client.get('/callback/null')
    assert response.status_code == 404

    # Supported provider with missing key
    response = client.get('/authorize/linkedin')
    assert response.status_code == 404

    response = client.get('/callback/linkedin')
    assert response.status_code == 404


def test_oauth_login(client, auth, app, page):
    base = 'http://localhost'
    scope = 'read:user'
    callback = f'{base}/callback/test'
    appid = app.config['OAUTH_CREDENTIALS']['test']['id']
    assert appid == 'test-oauth-app-id'
    userid = "test$testuser"
    username = "Test User"
    useremail = "test@localhost.test"

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

    # Missing username
    response = client.post(
        '/create-profile',
        data={'csrf_token': csrf, 'email': useremail},
        follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error.")
    page.assert_contains("You must provide a user name.")
    csrf = page.get_csrf()

    # Missing email
    response = client.post(
        '/create-profile',
        data={'csrf_token': csrf, 'name': username},
        follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error.")
    page.assert_contains("You must enter an email address.")
    csrf = page.get_csrf()

    # Bad email
    response = client.post(
        '/create-profile',
        data={'csrf_token': csrf, 'name': username, 'email': 'bad_address'},
        follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error.")
    page.assert_contains("You must enter a valid email address.")

    # Missing CSRF
    response = client.post(
        '/create-profile',
        data={'name': username, 'email': useremail},
        follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "Could not save changes as your form session has expired.")
    csrf = page.get_csrf()

    # All good
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

    # Missing username
    response = client.post(
        '/edit-profile',
        data={'csrf_token': csrf, 'email': newemail},
        follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error.")
    page.assert_contains("You must provide a user name.")

    # Missing CSRF
    response = client.post(
        '/edit-profile',
        data={'name': username, 'email': newemail},
        follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains(
        "Could not save changes as your form session has expired.")
    csrf = page.get_csrf()

    # All good
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

    # Test redirection when logged in user visits login page:

    response = client.get('/login', follow_redirects=True)
    html = response.get_data(as_text=True)
    page.assert_contains(auth_only, html)

    response = client.get('/authorize/test', follow_redirects=True)
    html = response.get_data(as_text=True)
    page.assert_contains(auth_only, html)

    response = client.get('/callback/test', follow_redirects=True)
    html = response.get_data(as_text=True)
    page.assert_contains(auth_only, html)

    response = client.get('/create-profile', follow_redirects=True)
    html = response.get_data(as_text=True)
    page.assert_contains(auth_only, html)

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
