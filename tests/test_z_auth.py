import os
import tempfile

from rdamsc import create_app
from rdamsc.auth import OAuthSignIn


def test_back_door(page):
    '''This test must be run last as it disables the test login credentials.'''
    with tempfile.TemporaryDirectory() as inst_path:
        live_app = create_app({
            'TESTING': False,
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

        with live_app.test_client() as live_client:

            response = live_client.get('/authorize/test')
            assert response.status_code == 404

            response = live_client.get('/callback/test', follow_redirects=True)
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            page.assert_contains('Authentication failed.', html)

            response = live_client.get('/create-profile', follow_redirects=True)
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            page.assert_contains('OpenID sign-in failed, sorry.', html)

    with tempfile.TemporaryDirectory() as inst_path:
        live_app = create_app({
            'TESTING': False,
            'MAIN_DATABASE_PATH': os.path.join(inst_path, 'data', 'db.json'),
            'VOCAB_DATABASE_PATH': os.path.join(inst_path, 'data', 'vocab.json'),
            'TERM_DATABASE_PATH': os.path.join(inst_path, 'data', 'terms.json'),
            'USER_DATABASE_PATH': os.path.join(inst_path, 'users', 'db.json'),
            'OAUTH_DATABASE_PATH': os.path.join(inst_path, 'oauth', 'db.json'),
            'OPENID_FS_STORE_PATH': os.path.join(inst_path, 'open-id'),
        })

        with live_app.test_client() as live_client:

            # Reset class property
            OAuthSignIn.providers = None

            response = live_client.get('/login')
            assert response.status_code == 200

            response = live_client.get('/authorize/test')
            assert response.status_code == 404

            response = live_client.get('/callback/test')
            assert response.status_code == 404
