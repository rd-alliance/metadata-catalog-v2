#!/usr/bin/env python3

# Dependencies
# ============
# Standard
# --------
import os

import urllib.parse

# Non-standard
# ------------
from flask import Flask, render_template

from flask_login import current_user


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
    for path in [app.instance_path,
                 os.path.dirname(app.config['MAIN_DATABASE_PATH']),
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

    # Placeholders
    @app.route('/search', methods=['GET', 'POST'])
    def scheme_search(isGui=None):
        return render_template(
            'search-form.html', form=None, titles=list(),
            subjects=list(), ids=list(), funders=list(),
            dataTypes=list())

    @app.route('/subject/<subject>')
    def subject(subject):
        pass

    @app.route('/datatype/<path:dataType>')
    def dataType(dataType):
        pass


    from . import auth
    auth.oid.init_app(app)
    auth.lm.init_app(app)
    app.register_blueprint(auth.bp)

    from . import records
    app.register_blueprint(records.bp)

    @app.context_processor
    def utility_processor():
        return {
            'toURLSlug': to_url_slug,
            'fromURLSlug': from_url_slug,
            'abbrevURL': abbrev_url,
            'parseDateRange': parse_date_range}

    return app


def to_url_slug(string):
    """Transforms string into URL-safe slug."""
    slug = urllib.parse.quote_plus(string)
    return slug


def from_url_slug(slug):
    """Transforms URL-safe slug back into regular string."""
    string = urllib.parse.unquote_plus(slug)
    return string


def abbrev_url(url):
    """Extracts last component of URL path. Useful for datatype URLs."""
    url_tuple = urllib.parse.urlparse(url)
    path = url_tuple.path
    if not path:
        return url
    path_fragments = path.split("/")
    if not path_fragments[-1] and len(path_fragments) > 1:
        return path_fragments[-2]
    return path_fragments[-1]


def parse_date_range(string):
    date_split = string.partition('/')
    if date_split[2]:
        return (date_split[0], date_split[2])
    return (string, None)

