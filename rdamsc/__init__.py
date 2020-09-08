#!/usr/bin/env python3

# Dependencies
# ============
# Standard
# --------
import os
import subprocess

# Non-standard
# ------------
# See https://flask.palletsprojects.com/en/1.1.x/
from flask import Flask, render_template, redirect, url_for
# See https://flask-login.readthedocs.io/
from flask_login import current_user
# See https://bloomberg.github.io/python-github-webhook/
from github_webhook import Webhook

# Local
# -----
from .utils import *
from .records import VocabTerm


def create_app(test_config=None):
    '''Factory for initialising the Flask application.'''

    # Create the app:
    app = Flask(__name__, instance_relative_config=True)

    # Set default configuration:
    app.config.from_mapping(
        SECRET_KEY='Do not use this in production.',
        WEBHOOK_SECRET='Do not use this in production either.',
        MAIN_DATABASE_PATH=os.path.join(
            app.instance_path, 'data', 'db.json'),
        VOCAB_DATABASE_PATH=os.path.join(
            app.instance_path, 'data', 'vocab.json'),
        TERM_DATABASE_PATH=os.path.join(
            app.instance_path, 'data', 'terms.json'),
        USER_DATABASE_PATH=os.path.join(
            app.instance_path, 'users', 'db.json'),
        OAUTH_DATABASE_PATH=os.path.join(
            app.instance_path, 'oauth', 'db.json'),
        OPENID_FS_STORE_PATH=os.path.join(
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
    for path in [os.path.dirname(app.config['MAIN_DATABASE_PATH']),
                 os.path.dirname(app.config['VOCAB_DATABASE_PATH']),
                 os.path.dirname(app.config['TERM_DATABASE_PATH']),
                 os.path.dirname(app.config['USER_DATABASE_PATH']),
                 os.path.dirname(app.config['OAUTH_DATABASE_PATH']),
                 app.config['OPENID_FS_STORE_PATH']]:
        if not os.path.isdir(path):
            try:
                os.makedirs(path)
            except OSError:
                pass

    # Template option settings:
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    # Initialise controlled terms:
    with app.app_context():
        VocabTerm.populate()

    # PAGES
    # =====

    # Front page:
    @app.route('/')
    def hello():
        return render_template('home.html')

    # Terms of use:
    @app.route('/terms-of-use')
    def terms_of_use():
        return render_template('terms-of-use.html')

    # Terms of use:
    @app.route('/accessibility')
    def accessibility():
        return render_template('accessibility.html')

    # Dynamic pages:
    from . import auth
    auth.oid.init_app(app)
    auth.lm.init_app(app)
    app.register_blueprint(auth.bp)

    from . import records
    app.register_blueprint(records.bp)

    from . import lists
    app.register_blueprint(lists.bp)

    from . import search
    app.register_blueprint(search.bp)

    from . import api1
    app.register_blueprint(api1.bp, url_prefix='/api')

    from . import api2
    app.register_blueprint(api2.bp, url_prefix='/api2')

    @app.route('/thesaurus')
    def redirect_thesaurus_scheme():
        return redirect(url_for('api2.get_thesaurus_scheme'))

    @app.route('/thesaurus/<any(domain, subdomain, concept):level><int:number>')
    def redirect_thesaurus_concept(level, number):
        return redirect(
            url_for('api2.get_thesaurus_concept', level=level, number=number))

    # Webhook:
    webhook = Webhook(app, secret=app.config['WEBHOOK_SECRET'])
    script_dir = os.path.dirname(__file__)

    @webhook.hook()
    def on_push(data):
        print("INFO: Upstream code repository has been updated.")
        print("INFO: Initiating git pull to update codebase.")
        call = subprocess.run(['git', '-C', script_dir, 'pull', '--rebase'],
                              stderr=subprocess.STDOUT)
        print("INFO: Git pull completed with exit code {}.".format(call.returncode))
        wsgi_path = app.config.get('WSGI_PATH')
        if wsgi_path:  # pragma: no cover
            if os.path.isfile(wsgi_path):
                os.utime(wsgi_path, None)
                print("INFO: Application reloaded.")
            else:
                print("WARNING: Value of WSGI_PATH ({}) is not a valid file."
                      .format(wsgi_path))

    # Utility functions used in templates
    @app.context_processor
    def utility_processor():
        return {
            'toURLSlug': to_url_slug,
            'fromURLSlug': from_url_slug,
            'hasDay': has_day,
            'isList': is_list}

    return app
