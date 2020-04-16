#!/usr/bin/env python3

# Dependencies
# ============
# Standard
# --------
import os

# Non-standard
# ------------
from flask import Flask


def create_app(test_config=None):
    # Create the app:
    app = Flask(__name__, instance_relative_config=True)

    # Set default configuration:
    app.config.from_mapping(
        SECRET_KEY='Do not use this in production.',
        WEBHOOK_SECRET='Do not use this in production either.',
        MAIN_DATABASE_PATH=os.path.join(
            app.instance_path, 'data', 'db.json'),
        USER_DATABASE_PATH=os.path.join(
            app.instance_path, 'data', 'users.json'),
        OAUTH_DATABASE_PATH=os.path.join(
            app.instance_path, 'oauth-urls.json'),
        OPENID_PATH=os.path.join(
            app.instance_path, 'open-id'),
        DEBUG=False,
        TESTING=False,
        JSON_AS_ASCII=False,
    )

    # Override these settings as appropriate:
    if test_config is None:
        # Load the instance config, if it exists:
        app.config.from_pyfile('config.py', silent=True)
    else:
        # Load the test configuration that was passed in:
        app.config.from_mapping(test_config)

    # Override with environment variable if set:
    app.config.from_envvar('MSC_SETTINGS', silent=True)

    # Make sure all these directories exist:
    for path in [app.instance_path,
                 os.path.dirname(app.config['MAIN_DATABASE_PATH']),
                 os.path.dirname(app.config['USER_DATABASE_PATH']),
                 os.path.dirname(app.config['OAUTH_DATABASE_PATH']),
                 app.config['OPENID_PATH']]:
        if not os.path.isdir(path):
            try:
                os.makedirs(path)
            except OSError:
                pass

    # Template option settings
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    # a simple page that says hello
    @app.route('/hello')
    def hello():
        return 'Hello, World!'

    return app
