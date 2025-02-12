import json
import logging
from urllib.parse import urlencode

from flask import Flask, request
from flask.testing import FlaskClient

from .conftest import AuthActions, PageActions


def test_bad_provider(client: FlaskClient):
    # Unsupported provider:
    r = client.get("/authorize/null")
    assert r.status_code == 404

    r = client.get("/callback/null")
    assert r.status_code == 404

    # Supported provider with missing key
    r = client.get("/authorize/linkedin")
    assert r.status_code == 404

    r = client.get("/callback/linkedin")
    assert r.status_code == 404


def test_oauth_login(
    client: FlaskClient,
    auth: AuthActions,
    app: Flask,
    page: PageActions,
    caplog,
):
    caplog.set_level(logging.DEBUG)

    appid = app.config["OAUTH_CREDENTIALS"]["test"]["id"]
    assert appid == "test-oauth-app-id"

    full_auth_url = f"{auth.authorize_url}?" + urlencode(
        {
            "response_type": "code",
            "client_id": appid,
            "redirect_uri": f"{auth._app_host}callback/{auth.provider}",
            "scope": auth.scope,
        }
    )

    # 1. "Sign in with" should point to a local authorize URL, which redirects:

    r = client.get(f"/authorize/{auth.provider}")
    assert r.status_code == 302
    assert r.headers["Location"].startswith(full_auth_url)
    state = r.headers["Location"].replace(f"{full_auth_url}&state=", "")
    code = "test-code-value"

    # 2. On success, provider would ping the callback. The app then gets a token
    #    and uses it to obtain profile data.

    # safe characters should match werkzeug.urls.iri_to_uri()
    create_profile_url = "/create-profile?" + urlencode(
        {"next": "/", "name": auth.username, "email": auth.useremail},
        safe="%!$&'()*+,/:;=?@",
    )

    r = client.get(f"/callback/test?state={state}&code={code}")
    assert r.status_code == 302
    redirection = r.headers["Location"]
    assert redirection.endswith(create_profile_url)

    # Test profile creation via new OAuth login
    r = client.get(create_profile_url)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    csrf = page.get_csrf(html)
    assert csrf

    # Missing username
    r = client.post(
        "/create-profile",
        data={"csrf_token": csrf, "email": auth.useremail},
        follow_redirects=True,
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error.")
    page.assert_contains("You must provide a user name.")
    csrf = page.get_csrf()

    # Missing email
    r = client.post(
        "/create-profile",
        data={"csrf_token": csrf, "name": auth.username},
        follow_redirects=True,
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error.")
    page.assert_contains("You must enter an email address.")
    csrf = page.get_csrf()

    # Bad email
    r = client.post(
        "/create-profile",
        data={"csrf_token": csrf, "name": auth.username, "email": "bad_address"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error.")
    page.assert_contains("You must enter a valid email address.")

    # Missing CSRF
    r = client.post(
        "/create-profile",
        data={"name": auth.username, "email": auth.useremail},
        follow_redirects=True,
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Could not save changes as your form session has expired.")
    csrf = page.get_csrf()

    # All good
    r = client.post(
        "/create-profile",
        data={"csrf_token": csrf, "name": auth.username, "email": auth.useremail},
        follow_redirects=True,
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    msg = "Profile successfully created."
    page.assert_contains(msg, html)

    # The following only appears on the home page when the user is logged in:
    auth_only = "<h2>Make changes</h2>"
    page.assert_contains(auth_only)

    with open(app.config["USER_DATABASE_PATH"]) as f:
        users = json.load(f)
        assert (
            users.get("_default", dict()).get("1", dict()).get("userid") == auth.userid
        )
        assert (
            users.get("_default", dict()).get("1", dict()).get("name") == auth.username
        )
        assert (
            users.get("_default", dict()).get("1", dict()).get("email")
            == auth.useremail
        )

    newemail = "test@example.com"

    r = client.get("/edit-profile")
    html = r.get_data(as_text=True)
    csrf = page.get_csrf(html)
    assert csrf

    # Test profile editing

    # Missing username
    r = client.post(
        "/edit-profile",
        data={"csrf_token": csrf, "email": newemail},
        follow_redirects=True,
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    page.read(html)
    page.assert_contains("there was an error.")
    page.assert_contains("You must provide a user name.")

    # Missing CSRF
    r = client.post(
        "/edit-profile",
        data={"name": auth.username, "email": newemail},
        follow_redirects=True,
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    page.read(html)
    page.assert_contains("Could not save changes as your form session has expired.")
    csrf = page.get_csrf()

    # All good
    r = client.post(
        "/edit-profile",
        data={"csrf_token": csrf, "name": auth.username, "email": newemail},
        follow_redirects=True,
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    msg = "Profile successfully updated."
    page.assert_contains(msg, html)

    with open(app.config["USER_DATABASE_PATH"]) as f:
        users = json.load(f)
        assert users.get("_default", dict()).get("1", dict()).get("email") == newemail

    # Test redirection when logged in user visits login page:

    r = client.get("/login", follow_redirects=True)
    html = r.get_data(as_text=True)
    page.assert_contains(auth_only, html)

    r = client.get("/authorize/test", follow_redirects=True)
    html = r.get_data(as_text=True)
    page.assert_contains(auth_only, html)

    r = client.get("/callback/test", follow_redirects=True)
    html = r.get_data(as_text=True)
    page.assert_contains(auth_only, html)

    r = client.get("/create-profile", follow_redirects=True)
    html = r.get_data(as_text=True)
    page.assert_contains(auth_only, html)

    # Test regular logout

    r = client.get("/logout", follow_redirects=True)
    html = r.get_data(as_text=True)
    msg = "You were signed out."
    page.assert_contains(msg, html)
    page.assert_lacks(auth_only)

    # Test regular login via OAuth

    r = auth.login()
    html = r.get_data(as_text=True)
    msg = "Successfully signed in."
    page.assert_contains(msg, html)
    page.assert_contains(auth_only)

    # Test logout via profile deletion

    r = client.get("/remove-profile", follow_redirects=True)
    html = r.get_data(as_text=True)
    msg = "Your profile was successfully deleted."
    page.assert_contains(msg, html)
    page.assert_lacks(auth_only)

    with open(app.config["USER_DATABASE_PATH"]) as f:
        users = json.load(f)
        assert users.get("_default", dict()).get("1", dict()).get("userid") is None
