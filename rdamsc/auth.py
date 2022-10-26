# Dependencies
# ============
# Standard
# --------
from datetime import datetime, timezone
from email.utils import parsedate_tz, mktime_tz

# Non-standard
# ------------
# See https://flask.palletsprojects.com/en/2.0.x/
from flask import (
    abort, Blueprint, current_app, flash, g, redirect, render_template,
    request, session, url_for
)
# See https://flask-login.readthedocs.io/
from flask_login import (
    LoginManager, login_user, logout_user, current_user, login_required
)
# See https://pythonhosted.org/Flask-OpenID/
# Following two statements remove a DeprecationWarning
import openid.oidutil
openid.oidutil.xxe_safe_elementtree_modules = ['defusedxml.ElementTree']
from flask_openid import OpenID
# See https://flask-wtf.readthedocs.io/
from flask_wtf import FlaskForm
# See https://developers.google.com/api-client-library/python/guide/aaa_oauth
from oauth2client import client, crypt
# See https://rauth.readthedocs.io/
from rauth import OAuth1Service, OAuth2Service
import requests
# See http://tinydb.readthedocs.io/
from tinydb import TinyDB, Query
# See https://wtforms.readthedocs.io/
from wtforms import validators, StringField

# Local
# -----
from .users import User, get_user_db
from .utils import Pluralizer

bp = Blueprint('auth', __name__)
oid = OpenID()
lm = LoginManager()
lm.login_view = 'auth.login'
lm.login_message = 'Please sign in to access this page.'
lm.login_message_category = "error"


class OAuthSignIn(object):
    '''Abstraction layer for RAuth. Source:
    https://blog.miguelgrinberg.com/post/oauth-authentication-with-flask
    '''
    providers = None

    def __init__(self, provider_name):
        self.provider_name = provider_name
        if 'OAUTH_CREDENTIALS' not in current_app.config:
            print('WARNING: OAuth authentication will not work without secret'
                  ' application keys. Please run your tests with a different'
                  ' authentication method.')
            self.consumer_id = None
            self.consumer_secret = None
        elif provider_name not in current_app.config['OAUTH_CREDENTIALS']:
            self.consumer_id = None
            self.consumer_secret = None
        else:
            credentials = current_app.config['OAUTH_CREDENTIALS'][provider_name]
            self.consumer_id = credentials['id']
            self.consumer_secret = credentials['secret']

    def authorize(self):
        raise NotImplementedError  # pragma: no cover

    def callback(self):
        raise NotImplementedError  # pragma: no cover

    def get_callback_url(self):
        return url_for('auth.oauth_callback', provider=self.provider_name,
                       _external=True)

    @classmethod
    def get_provider(cls, provider_name):
        if cls.providers is None:
            cls.providers = {}
            for provider_class in cls.__subclasses__():
                provider = provider_class()
                cls.providers[provider.provider_name] = provider
        return cls.providers.get(provider_name)


class TestSignIn(OAuthSignIn):
    '''For testing authorization flow, and authorized-only content. Disabled
    unless TESTING is True.'''
    def __init__(self):
        super(TestSignIn, self).__init__('test')
        self.formatted_name = 'Test'
        self.icon = 'fas fa-key'
        self.service = OAuth2Service(
            name=self.provider_name,
            client_id=self.consumer_id,
            client_secret=self.consumer_secret,
            authorize_url='https://localhost/login/oauth/authorize',
            access_token_url='https://localhost/login/oauth/access_token',
            base_url='https://localhost/')

    def authorize(self):
        if current_app.config['TESTING']:
            return redirect(self.service.get_authorize_url(
                scope='read:user',
                redirect_uri=self.get_callback_url()))
        abort(404)

    def callback(self):
        if current_app.config['TESTING']:
            return (
                self.provider_name + '$testuser',
                "Test User",
                "test@localhost.test")
        return (None, None, None)


class GoogleSignIn(OAuthSignIn):  # pragma: no cover
    def __init__(self):
        super(GoogleSignIn, self).__init__('google')
        self.formatted_name = 'Google'
        self.icon = 'fab fa-google'
        oauth_db = get_oauth_db()
        discovery = oauth_db.get(Query().provider == self.provider_name)
        discovery_url = ('https://accounts.google.com/.well-known/'
                         'openid-configuration')
        if not discovery:
            try:
                r = requests.get(discovery_url)
                discovery = r.json()
                discovery['provider'] = self.provider_name
                expiry_timestamp = mktime_tz(
                    parsedate_tz(r.headers['expires']))
                discovery['timestamp'] = expiry_timestamp
                oauth_db.insert(discovery)
            except Exception as e:
                print('WARNING: could not retrieve URLs for {}.'
                      .format(self.provider_name))
                print(e)
                discovery = dict()
        elif (datetime.now(timezone.utc).timestamp() > discovery['timestamp']):
            try:
                last_expiry_date = datetime.fromtimestamp(
                    discovery['timestamp'], timezone.utc)
                headers = {
                    'If-Modified-Since': last_expiry_date
                    .strftime('%a, %d %b %Y %H:%M:%S %Z')}
                r = requests.get(discovery_url, headers=headers)
                if r.status_code != requests.codes.not_modified:
                    discovery.update(r.json())
                expiry_timestamp = mktime_tz(
                    parsedate_tz(r.headers['expires']))
                discovery['timestamp'] = expiry_timestamp
                oauth_db.update(discovery, doc_ids=[discovery.doc_id])
            except Exception as e:
                print('WARNING: could not update URLs for {}.'
                      .format(self.provider_name))
                print(e)

        self.service = OAuth2Service(
            name=self.provider_name,
            client_id=self.consumer_id,
            client_secret=self.consumer_secret,
            authorize_url=discovery.get(
                'authorization_endpoint',
                'https://accounts.google.com/o/oauth2/v2/auth'),
            access_token_url=discovery.get(
                'token_endpoint',
                'https://www.googleapis.com/oauth2/v4/token'),
            base_url=discovery.get(
                'issuer',
                'https://accounts.google.com'))

    def authorize(self):
        return redirect(self.service.get_authorize_url(
            scope='profile email',
            response_type='code',
            redirect_uri=self.get_callback_url()))

    def callback(self):
        if 'code' not in request.args:
            return (None, None, None)
        r = self.service.get_raw_access_token(
            method='POST',
            data={'code': request.args['code'],
                  'grant_type': 'authorization_code',
                  'redirect_uri': self.get_callback_url()})
        oauth_info = r.json()
        access_token = oauth_info['access_token']
        id_token = oauth_info['id_token']
        oauth_session = self.service.get_session(access_token)
        try:
            idinfo = client.verify_id_token(id_token, self.consumer_id)
            if idinfo['iss'] not in ['accounts.google.com',
                                     'https://accounts.google.com']:
                raise crypt.AppIdentityError("Wrong issuer.")
        except crypt.AppIdentityError as e:
            print(e)
            return (None, None, None)
        return (
            self.provider_name + '$' + idinfo['sub'],
            idinfo.get('name'),
            idinfo.get('email'))


class LinkedinSignIn(OAuthSignIn):  # pragma: no cover
    def __init__(self):
        super(LinkedinSignIn, self).__init__('linkedin')
        self.formatted_name = 'LinkedIn'
        self.icon = 'fab fa-linkedin'
        self.service = OAuth2Service(
            name=self.provider_name,
            client_id=self.consumer_id,
            client_secret=self.consumer_secret,
            authorize_url='https://www.linkedin.com/oauth/v2/authorization',
            access_token_url='https://www.linkedin.com/oauth/v2/accessToken',
            base_url='https://api.linkedin.com/v1/people/')

    def authorize(self):
        return redirect(self.service.get_authorize_url(
            scope='r_basicprofile r_emailaddress',
            response_type='code',
            redirect_uri=self.get_callback_url()))

    def callback(self):
        if 'code' not in request.args:
            return (None, None, None)
        r = self.service.get_raw_access_token(
            method='POST',
            data={'code': request.args['code'],
                  'grant_type': 'authorization_code',
                  'redirect_uri': self.get_callback_url()})
        oauth_info = r.json()
        access_token = oauth_info['access_token']
        oauth_session = self.service.get_session(access_token)
        idinfo = oauth_session.get(
            '~:(id,formatted-name,email-address)?format=json').json()
        return (
            self.provider_name + '$' + idinfo['id'],
            idinfo.get('formattedName'),
            idinfo.get('emailAddress'))


class TwitterSignIn(OAuthSignIn):  # pragma: no cover
    def __init__(self):
        super(TwitterSignIn, self).__init__('twitter')
        self.formatted_name = 'Twitter'
        self.icon = 'fab fa-twitter'
        self.service = OAuth1Service(
            name=self.provider_name,
            consumer_key=self.consumer_id,
            consumer_secret=self.consumer_secret,
            request_token_url='https://api.twitter.com/oauth/request_token',
            authorize_url='https://api.twitter.com/oauth/authorize',
            access_token_url='https://api.twitter.com/oauth/access_token',
            base_url='https://api.twitter.com/1.1/')

    def authorize(self):
        request_token = self.service.get_request_token(
            params={'oauth_callback': self.get_callback_url()})
        session['request_token'] = request_token
        return redirect(self.service.get_authorize_url(request_token[0]))

    def callback(self):
        request_token = session.pop('request_token')
        if 'oauth_verifier' not in request.args:
            return (None, None, None)
        oauth_session = self.service.get_auth_session(
            request_token[0],
            request_token[1],
            data={'oauth_verifier': request.args['oauth_verifier']}
        )
        idinfo = oauth_session.get('account/verify_credentials.json').json()
        return (
            self.provider_name + '$' + str(idinfo.get('id')),
            idinfo.get('name'),
            # Need to write policy pages before retrieving email addresses
            None)


class GithubSignIn(OAuthSignIn):  # pragma: no cover
    def __init__(self):
        super(GithubSignIn, self).__init__('github')
        self.formatted_name = 'GitHub'
        self.icon = 'fab fa-github'
        self.service = OAuth2Service(
            name=self.provider_name,
            client_id=self.consumer_id,
            client_secret=self.consumer_secret,
            authorize_url='https://github.com/login/oauth/authorize',
            access_token_url='https://github.com/login/oauth/access_token',
            base_url='https://api.github.com/')

    def authorize(self):
        return redirect(self.service.get_authorize_url(
            scope='read:user user:email',
            redirect_uri=self.get_callback_url()))

    def callback(self):
        if 'code' not in request.args:
            return (None, None, None)
        access_token = self.service.get_access_token(
            method='POST',
            data={'code': request.args['code'],
                  'redirect_uri': self.get_callback_url()})
        oauth_session = self.service.get_session(access_token)
        idinfo = oauth_session.get('user').json()
        if not idinfo.get('email'):
            email_address = ''
            emailinfo = oauth_session.get('user/emails').json()
            for email_object in emailinfo:
                email_address = email_object.get('email')
                if email_object.get('primary', False):
                    break
            if email_address:
                idinfo['email'] = email_address
        return (
            self.provider_name + '$' + idinfo['login'],
            idinfo.get('name'),
            idinfo.get('email'))


class GitlabSignIn(OAuthSignIn):  # pragma: no cover
    def __init__(self):
        super(GitlabSignIn, self).__init__('gitlab')
        self.formatted_name = 'GitLab'
        self.icon = 'fab fa-gitlab'
        oauth_db = get_oauth_db()
        discovery = oauth_db.get(Query().provider == self.provider_name)
        discovery_url = ('https://gitlab.com/.well-known/'
                         'openid-configuration')
        if not discovery:
            try:
                r = requests.get(discovery_url)
                discovery = r.json()
                discovery['provider'] = self.provider_name
                expiry_timestamp = mktime_tz(
                    parsedate_tz(r.headers['date'])) + 3600
                discovery['timestamp'] = expiry_timestamp
                oauth_db.insert(discovery)
            except Exception as e:
                print('WARNING: could not retrieve URLs for {}.'
                      .format(self.provider_name))
                print(e)
                discovery = dict()
        elif (datetime.now(timezone.utc).timestamp() > discovery['timestamp']):
            try:
                last_expiry_date = datetime.fromtimestamp(
                    discovery['timestamp'], timezone.utc)
                headers = {
                    'If-Modified-Since': last_expiry_date
                    .strftime('%a, %d %b %Y %H:%M:%S %Z')}
                r = requests.get(discovery_url, headers=headers)
                if r.status_code != requests.codes.not_modified:
                    discovery.update(r.json())
                expiry_timestamp = mktime_tz(
                    parsedate_tz(r.headers['date'])) + 3600
                discovery['timestamp'] = expiry_timestamp
                oauth_db.update(discovery, doc_ids=[discovery.doc_id])
            except Exception as e:
                print('WARNING: could not update URLs for {}.'
                      .format(self.provider_name))
                print(e)

        self.userinfo = discovery.get(
            'userinfo_endpoint',
            'https://gitlab.com/oauth/userinfo')
        self.service = OAuth2Service(
            name=self.provider_name,
            client_id=self.consumer_id,
            client_secret=self.consumer_secret,
            authorize_url=discovery.get(
                'authorization_endpoint',
                'https://gitlab.com/oauth/authorize'),
            access_token_url=discovery.get(
                'token_endpoint',
                'https://gitlab.com/oauth/token'),
            base_url=discovery.get(
                'issuer',
                'https://gitlab.com'))

    def authorize(self):
        return redirect(self.service.get_authorize_url(
            scope='openid email',
            response_type='code',
            redirect_uri=self.get_callback_url()))

    def callback(self):
        if 'code' not in request.args:
            return (None, None, None)
        r = self.service.get_raw_access_token(
            method='POST',
            data={'code': request.args['code'],
                  'grant_type': 'authorization_code',
                  'redirect_uri': self.get_callback_url()})
        oauth_info = r.json()
        access_token = oauth_info['access_token']
        id_token = oauth_info['id_token']
        oauth_session = self.service.get_session(access_token)
        idinfo = oauth_session.get(self.userinfo).json()
        return (
            self.provider_name + '$' + idinfo['sub'],
            idinfo.get('name'),
            idinfo.get('email'))


class OrcidSignIn(OAuthSignIn):  # pragma: no cover
    def __init__(self):
        super(OrcidSignIn, self).__init__('orcid')
        self.formatted_name = 'ORCID'
        self.icon = 'fab fa-orcid'
        self.service = OAuth2Service(
            name=self.provider_name,
            client_id=self.consumer_id,
            client_secret=self.consumer_secret,
            authorize_url='https://orcid.org/oauth/authorize',
            access_token_url='https://orcid.org/oauth/token',
            base_url='https://pub.orcid.org/v2.0/')

    def authorize(self):
        return redirect(self.service.get_authorize_url(
            scope='/authenticate',
            response_type='code',
            redirect_uri=self.get_callback_url()))

    def callback(self):
        if 'code' not in request.args:
            return (None, None, None)
        r = self.service.get_raw_access_token(
            method='POST',
            data={'code': request.args['code'],
                  'grant_type': 'authorization_code',
                  'redirect_uri': self.get_callback_url()})
        oauth_info = r.json()
        access_token = oauth_info['access_token']
        orcid = oauth_info['orcid']
        oauth_session = self.service.get_session(access_token)
        idinfo = oauth_session.get(
            '{}/record'.format(orcid),
            headers={'Content-type': 'application/vnd.orcid+json'}).json()
        email = None
        emails = idinfo.get('person', dict()).get('emails', dict()).get(
            'email', list())
        for email_obj in emails:
            this_email = email_obj.get('email')
            if this_email and email_obj.get('primary'):
                email = this_email
                break
            elif email:
                continue
            email = this_email
        return (
            self.provider_name + '$' + orcid,
            oauth_info.get('name'),
            email)


def get_oauth_db():
    if 'oauth_db' not in g:
        g.oauth_db = TinyDB(current_app.config['OAUTH_DATABASE_PATH'])

    return g.oauth_db


@lm.user_loader
def load_user(id):
    '''Utility for loading users.'''
    user_db = get_user_db()
    document = user_db.get(doc_id=int(id))
    if document:
        return User(value=document, doc_id=document.doc_id)
    return None  # pragma: no cover


class LoginForm(FlaskForm):
    openid = StringField('OpenID URL', validators=[validators.URL()])


@bp.route('/login', methods=['GET', 'POST'])
@oid.loginhandler
def login():
    '''This login view can handle both OpenID v2 and OpenID Connect
    authentication. The POST method begins the OpenID v2 process. The
    OpenID Connect links route to oauth_authorize() instead.
    '''
    if current_user.is_authenticated:
        return redirect(oid.get_next_url())
    form = LoginForm(request.form)
    if request.method == 'POST' and form.validate():  # pragma: no cover
        openid = form.openid.data
        if openid:
            return oid.try_login(
                openid, ask_for=['email', 'nickname'],
                ask_for_optional=['fullname'])
    error = oid.fetch_error()
    if error:  # pragma: no cover
        flash(error, 'error')
    providers = list()
    if 'OAUTH_CREDENTIALS' in current_app.config:
        for provider_class in OAuthSignIn.__subclasses__():
            provider = provider_class()
            if provider.provider_name not in current_app.config.get(
                    'OAUTH_CREDENTIALS'):
                continue
            provider_details = {
                'name': provider.formatted_name,
                'slug': provider.provider_name}
            if hasattr(provider, 'icon'):
                provider_details['icon'] = provider.icon
            providers.append(provider_details)
        providers.sort(key=lambda k: k['slug'])
    return render_template(
        'login.html', form=form, providers=providers, next=oid.get_next_url())


@oid.after_login
def create_or_login(resp):  # pragma: no cover
    '''This function handles the response from an OpenID v2 provider.
    '''
    session['openid'] = resp.identity_url
    user_db = get_user_db()
    User = Query()
    profile = user_db.get(User.userid == resp.identity_url)
    if profile:
        flash('Successfully signed in.')
        user = load_user(profile.doc_id)
        login_user(user)
        return redirect(oid.get_next_url())
    return redirect(url_for(
        'auth.create_profile', next=oid.get_next_url(),
        name=resp.fullname or resp.nickname, email=resp.email))


@bp.route('/authorize/<provider>')
def oauth_authorize(provider):
    '''This function calls out to the OpenID Connect provider.
    '''
    if not current_user.is_anonymous:
        return redirect(url_for('hello'))
    oauth = OAuthSignIn.get_provider(provider)
    if oauth is None or oauth.consumer_id is None:
        abort(404)
    return oauth.authorize()


@bp.route('/callback/<provider>')
def oauth_callback(provider):
    '''The OpenID Connect provider sends information back to this URL,
    where we use it to extract a unique ID, user name and email address.
    '''
    user_db = get_user_db()
    if not current_user.is_anonymous:
        return redirect(url_for('hello'))
    oauth = OAuthSignIn.get_provider(provider)
    if oauth is None or oauth.consumer_id is None:
        abort(404)
    openid, username, email = oauth.callback()
    session['openid'] = openid
    if openid is None:
        flash('Authentication failed.')
        return redirect(url_for('hello'))
    User = Query()
    profile = user_db.get(User.userid == openid)
    if profile:
        flash('Successfully signed in.')
        user = load_user(profile.doc_id)
        login_user(user)
        return redirect(url_for('hello'))
    return redirect(url_for(
        'auth.create_profile', next=url_for('hello'),
        name=username, email=email))


class ProfileForm(FlaskForm):
    name = StringField('Name', validators=[validators.InputRequired(
        message='You must provide a user name.')])
    email = StringField('Email', validators=[validators.InputRequired(
        message='You must enter an email address.'), validators.Email(
        message='You must enter a valid email address.')])


@bp.route('/create-profile', methods=['GET', 'POST'])
def create_profile():
    '''If the user authenticated successfully by either means, but does
    not exist in the user database, this view creates and saves their profile.
    '''
    user_db = get_user_db()
    if current_user.is_authenticated:
        return redirect(url_for('hello'))
    if 'openid' not in session or session['openid'] is None:
        flash('OpenID sign-in failed, sorry.', 'error')
        return redirect(url_for('hello'))
    form = ProfileForm(request.values)
    if request.method == 'POST' and form.validate():
        name = request.form['name']
        email = request.form['email']
        data = {
            'name': form.name.data,
            'email': form.email.data,
            'userid': session['openid']}
        user_doc_id = user_db.insert(data)
        flash('Profile successfully created.')
        user = User(value=data, doc_id=user_doc_id)
        login_user(user)
        return redirect(oid.get_next_url() or url_for('hello'))
    if form.errors:
        if 'csrf_token' in form.errors:
            msg = ('Could not save changes as your form session has expired.'
                   ' Please try again.')
        else:
            msg = ('Could not create profile as there {:/was an error/were N'
                   ' errors}. See below for details.'
                   .format(Pluralizer(len(form.errors))))
        flash(msg, 'error')
    return render_template(
        'create-profile.html', form=form,
        next=oid.get_next_url() or url_for('hello'))


@bp.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    '''Allows users to change their displayed username and email address.
    '''
    user_db = get_user_db()
    openid_formatted = 'unknown profile'
    openid_tuple = current_user['userid'].partition('$')
    if openid_tuple[2]:
        # OpenID Connect profile
        openid_format = '{} profile for '
        for provider_class in OAuthSignIn.__subclasses__():
            provider = provider_class()
            if openid_tuple[0] == provider.provider_name:
                openid_formatted = (openid_format
                                    .format(provider.formatted_name))
                break
        else:  # pragma: no cover
            openid_formatted = (openid_format
                                .format(openid_tuple[0]))
        openid_formatted += current_user['name']
    else:  # pragma: no cover
        # OpenID v2 profile
        openid_formatted = current_user['userid']
    form = ProfileForm(request.values, data=current_user)
    if request.method == 'POST' and form.validate():
        name = request.form['name']
        email = request.form['email']
        data = {
            'name': form.name.data,
            'email': form.email.data,
            'userid': current_user['userid']}
        if user_db.update(data, doc_ids=[current_user.doc_id]):
            flash('Profile successfully updated.')
        else:  # pragma: no cover
            flash('Profile could not be updated, sorry.')
        return redirect(url_for('hello'))
    if form.errors:
        if 'csrf_token' in form.errors:
            msg = ('Could not save changes as your form session has expired.'
                   ' Please try again.')
        else:
            msg = ('Could not update profile as there {:/was an error/were N'
                   ' errors}. See below for details.'
                   .format(Pluralizer(len(form.errors))))
        flash(msg, 'error')
    return render_template(
        'edit-profile.html', form=form, openid_formatted=openid_formatted)


@bp.route('/remove-profile')
@login_required
def remove_profile():
    '''Allows users to remove their profile from the system.
    '''
    user_db = get_user_db()
    if user_db.remove(doc_ids=[current_user.doc_id]):
        flash('Your profile was successfully deleted.')
        logout_user()
        session.pop('openid', None)
        flash('You were signed out.')
    else:  # pragma: no cover
        flash('Your profile could not be deleted.')
    return redirect(url_for('hello'))


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('openid', None)
    flash('You were signed out.')
    return redirect(url_for('hello'))
