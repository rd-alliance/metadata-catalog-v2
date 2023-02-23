import os
from datetime import datetime, timedelta, timezone
from time import sleep

from flask import Flask
from flask.testing import FlaskClient
import pytest

from rdamsc import create_app
from tests.conftest import PageActions


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


def test_hello(app: Flask, client: FlaskClient, page: PageActions):
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_contains("<h1>Metadata Standards Catalog</h1>")
    page.assert_lacks("<h2>Make changes</h2>")

    now = datetime.now(timezone.utc)
    nextyear = now.year + 1

    # No start, no end
    page.assert_lacks("The Metadata Standards Catalog will be unavailable")

    # No start, future end
    app.config["MAINTENANCE_END"] = f"{nextyear}-04-01 12:00"
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_lacks("The Metadata Standards Catalog will be unavailable", html)

    # No start, past end
    app.config["MAINTENANCE_END"] = now.isoformat()
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_lacks("The Metadata Standards Catalog will be unavailable", html)

    # Future start, no end
    app.config["MAINTENANCE_START"] = f"{nextyear}-04-01 09:00"
    del app.config["MAINTENANCE_END"]
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains(
        "The Metadata Standards Catalog will be unavailable on 1 April "
        f"{nextyear} from 09:00 UTC",
        html
    )

    # Future start, future end
    app.config["MAINTENANCE_END"] = f"{nextyear}-04-01 12:00"
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains(
        "The Metadata Standards Catalog will be unavailable on 1 April "
        f"{nextyear} from 09:00 to 12:00 UTC",
        html
    )

    # Future start, past end
    app.config["MAINTENANCE_END"] = now.isoformat()
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains(
        "The Metadata Standards Catalog will be unavailable on 1 April "
        f"{nextyear} from 09:00 UTC",
        html
    )

    # Past start, no end
    app.config["MAINTENANCE_START"] = now.isoformat()
    del app.config["MAINTENANCE_END"]
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains(
        "The Metadata Standards Catalog is currently undergoing scheduled maintenance.",
        html
    )

    # Past start, future end
    app.config["MAINTENANCE_END"] = f"{nextyear}-04-01 12:00"
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains(
        "The Metadata Standards Catalog is undergoing scheduled maintenance until "
        f"1 April {nextyear} at 12:00 UTC",
        html
    )

    while True:
        now2 = datetime.now(timezone.utc)
        soon = now2 + timedelta(seconds=60)
        if soon.day == now2.day:
            break
        sleep(60)
    app.config["MAINTENANCE_END"] = soon.isoformat()
    soon_hr = (f"{soon.strftime('%H:%M')} UTC")
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains(
        "The Metadata Standards Catalog is undergoing scheduled maintenance until "
        + soon_hr,
        html
    )

    # Past start, past end
    app.config["MAINTENANCE_END"] = now2.isoformat()
    response = client.get('/')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.read(html)
    page.assert_lacks("The Metadata Standards Catalog will be unavailable")
    page.assert_lacks(
        "The Metadata Standards Catalog is currently undergoing scheduled maintenance"
    )
    page.assert_lacks(
        "The Metadata Standards Catalog is undergoing scheduled maintenance"
    )


def test_terms_of_use(client: FlaskClient, page: PageActions):
    response = client.get('/terms-of-use')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page.assert_contains("<h1>Terms of use</h1>", html)
