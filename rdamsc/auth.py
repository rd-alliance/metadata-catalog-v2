# Dependencies
# ============
# Standard
# --------
import logging
import sys
import time  # for Authlib patch
from typing import NamedTuple

if sys.version_info < (3, 11):
    from typing_extensions import TypedDict
else:
    from typing import TypedDict

# Non-standard
# ------------
from flask import (
    abort,
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    current_user,
    login_required,
)
from flask_wtf import FlaskForm
from authlib.integrations.flask_client.apps import FlaskOAuth1App, FlaskOAuth2App
from authlib.integrations.flask_client.integration import FlaskIntegration
from authlib.integrations.base_client import (
    errors as authlib_errors,
    sync_app,
    sync_openid,
)
import requests
from tinydb import Query
from tinydb.table import Document
from werkzeug import Response
from wtforms import validators, StringField

# Local
# -----
from .users import User, get_user_db
from .utils import Pluralizer

bp = Blueprint("auth", __name__)
lm = LoginManager()
lm.login_view = "auth.login"  # type: ignore
lm.login_message = "Please sign in to access this page."
lm.login_message_category = "error"


# Patch for Authlib issue 704
# ===========================
# See https://github.com/authlib/authlib/issues/704


def load_server_metadata(self):  # pragma: no cover
    if self._server_metadata_url and "_loaded_at" not in self.server_metadata:
        with self.client_cls(**self.client_kwargs) as session:
            session.headers["User-Agent"] = self._user_agent  # LINE ADDED
            resp = session.request(
                "GET", self._server_metadata_url, withhold_token=True
            )
            resp.raise_for_status()
            metadata = resp.json()

        metadata["_loaded_at"] = time.time()
        self.server_metadata.update(metadata)
    return self.server_metadata


sync_app.OAuth2Mixin.load_server_metadata = load_server_metadata


def fetch_jwk_set(self, force=False):  # pragma: no cover
    metadata = self.load_server_metadata()
    jwk_set = metadata.get("jwks")
    if jwk_set and not force:
        return jwk_set

    uri = metadata.get("jwks_uri")
    if not uri:
        raise RuntimeError('Missing "jwks_uri" in metadata')

    with self.client_cls(**self.client_kwargs) as session:
        session.headers["User-Agent"] = self._user_agent  # LINE ADDED
        resp = session.request("GET", uri, withhold_token=True)
        resp.raise_for_status()
        jwk_set = resp.json()

    self.server_metadata["jwks"] = jwk_set
    return jwk_set


sync_openid.OpenIDMixin.fetch_jwk_set = fetch_jwk_set


# Auth provider classes
# =====================
class OACAppKwargs(
    TypedDict,
    total=False,
):
    access_token_url: str
    api_base_url: str
    authorize_url: str
    client_kwargs: dict[str, str]
    request_token_url: str
    server_metadata_url: str


class ProfileData(NamedTuple):
    userid: str | None = None
    username: str | None = None
    email: str | None = None


class OAuthClient:
    """Wrapper around authlib's FlaskOAuth1App and FlaskOAuth2App.
    Supports OAuth 1.0, OAuth 2.0 and OpenID Connect.
    """

    framework_integration_cls = FlaskIntegration
    app_cls = FlaskOAuth2App
    slug = ""
    name = ""
    icon = "fa-solid fa-key"
    main = False
    app_kwargs: OACAppKwargs = {}

    def __init__(self, client_id: str, client_secret: str):
        self.app = self.app_cls(
            framework=self.framework_integration_cls(self.slug),
            name=self.slug,
            client_id=client_id,
            client_secret=client_secret,
            **self.app_kwargs,
        )

    def authorize_redirect(self) -> Response:
        """Returns Flask redirect to the provider login."""
        if current_app.logger.level < logging.INFO:
            # When debugging, it's useful to see where the error occurred.
            return self.app.authorize_redirect(redirect_uri=self.callback_url)
        else:
            try:
                return self.app.authorize_redirect(redirect_uri=self.callback_url)
            except requests.HTTPError as e:
                flash(f"Could not connect to provider: {e}.", "error")
                return redirect(url_for("auth.login"))

    def get_access_token(self) -> dict | None:
        """Returns token (parsed JSON from response, with additional
        "userinfo" key if OpenID Connect) if successful, None otherwise.
        """
        try:
            return self.app.authorize_access_token()
        except authlib_errors.MismatchingStateError:
            flash(
                "Token exchange failed: State not equal in request and response.",
                "error",
            )
            return None
        except authlib_errors.OAuthError as e:
            flash(f"Token exchange failed: {e.description}.", "error")
            return None
        except requests.HTTPError as e:
            flash(f"Token exchange failed: {e}.", "error")
            return None
        except RuntimeError as e:
            flash(f"Token exchange failed: {e}.", "error")
            return None

    def get_profile_data(self) -> ProfileData:
        """Returns a user ID (based off the provider name and the user
        ID held by the provider), name, and email address for the user.

        If the user did not authenticate or is otherwise unauthorized,
        will return None for all three values
        """
        raise NotImplementedError  # pragma: no cover

    @property
    def callback_url(self) -> str:
        return url_for("auth.oauth_callback", provider=self.slug, _external=True)


class DummyAuthClient(OAuthClient):
    """Dummy OAuth 2.0 implementation for testing authorization flow
    and authorized-only content. Disabled unless TESTING is True,
    to avoid accidental activation in config."""

    slug = "test"
    name = "Test"
    app_kwargs = {
        "authorize_url": "http://example.org/login/oauth/authorize",
        "access_token_url": "http://example.org/login/oauth/access_token",
        "api_base_url": "http://example.org/",
        "client_kwargs": dict(scope="user"),
    }

    def authorize_redirect(self) -> Response:
        if current_app.config["TESTING"] is not True:
            abort(404)
        return self.app.authorize_redirect(redirect_uri=self.callback_url)

    def get_profile_data(self) -> ProfileData:
        if current_app.config["TESTING"] is not True:
            return ProfileData()
        current_app.logger.debug(f"Login with {self.name}.")
        token = self.get_access_token()
        if token is None:
            return ProfileData()
        try:
            r: requests.Response = self.app.get("user")
            r.raise_for_status()
            id_info: dict = r.json()
            current_app.logger.debug(f"id_info = {id_info}")
            id = id_info["id"]
        except (requests.HTTPError, ValueError) as e:
            current_app.logger.debug(f"{e}")
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=id_info.get("name"),
            email=id_info.get("email"),
        )
        current_app.logger.debug(f"parsed as {profile_data}")
        return profile_data


class GitHubClient(OAuthClient):  # pragma: no cover
    """GitHub using OAuth 2.0."""

    slug = "github"
    name = "GitHub"
    icon = "fa-brands fa-github"
    app_kwargs = {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "access_token_url": "https://github.com/login/oauth/access_token",
        "api_base_url": "https://api.github.com/",
        "client_kwargs": dict(scope="read:user user:email"),
    }

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        token = self.get_access_token()
        if token is None:
            return ProfileData()
        try:
            r: requests.Response = self.app.get("user")
            r.raise_for_status()
            id_info: dict = r.json()
            current_app.logger.debug(f"id_info = {id_info}")
            id = id_info["login"]
        except (requests.HTTPError, ValueError) as e:
            current_app.logger.debug(f"{e}")
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=id_info.get("name"),
            email=id_info.get("email"),
        )
        if profile_data.email is None:
            email = ""
            try:
                r: requests.Response = self.app.get("user/emails")
                r.raise_for_status()
                contacts: list[dict] = r.json()
                current_app.logger.debug(f"contacts = {contacts}")
                for contact in contacts:
                    email = contact.get("email")
                    if contact.get("primary", False):
                        break
            except requests.HTTPError or ValueError:
                pass
            if email:
                profile_data = profile_data._replace(email=email)
        current_app.logger.debug(f"parsed as {profile_data}")
        return profile_data


class GitLabClient(OAuthClient):  # pragma: no cover
    """GitLab using OpenID Connect."""

    slug = "gitlab"
    name = "GitLab"
    icon = "fa-brands fa-gitlab"
    app_kwargs = {
        "client_kwargs": dict(scope="openid email"),
        "server_metadata_url": "https://gitlab.com/.well-known/openid-configuration",
    }

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        token = self.get_access_token()
        if token is None:
            return ProfileData()
        try:
            user_info = token.get("userinfo") or self.app.userinfo()
            current_app.logger.debug(f"user_info = {user_info}")
            id = user_info["sub"]
            name = str(s) if (s := user_info.get("name")) else ""
            email = str(s) if (s := user_info.get("email")) else ""
        except (requests.HTTPError, ValueError) as e:
            current_app.logger.debug(f"{e}")
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=name,
            email=email,
        )
        current_app.logger.debug(f"parsed as {profile_data}")
        return profile_data


class GoogleClient(OAuthClient):  # pragma: no cover
    """Google using OpenID Connect.

    Not actively supported.
    """

    slug = "google"
    name = "Google"
    icon = "fa-brands fa-google"
    app_kwargs = {
        "client_kwargs": dict(scope="openid name email"),
        "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
    }

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        token = self.get_access_token()
        if token is None:
            return ProfileData()
        try:
            user_info = token.get("userinfo") or self.app.userinfo()
            current_app.logger.debug(f"user_info = {user_info}")
            id = user_info["sub"]
            name = str(s) if (s := user_info.get("name")) else ""
            email = str(s) if (s := user_info.get("email")) else ""
        except (requests.HTTPError, ValueError) as e:
            current_app.logger.debug(f"{e}")
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=name,
            email=email,
        )
        current_app.logger.debug(f"parsed as {profile_data}")
        return profile_data


class LinkedInClient(OAuthClient):  # pragma: no cover
    """LinkedIn using OAuth 2.0.

    Not actively supported.
    """

    slug = "linkedin"
    name = "LinkedIn"
    icon = "fa-brands fa-linkedin"
    app_kwargs = {
        "authorize_url": "https://www.linkedin.com/oauth/v2/authorization",
        "access_token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "api_base_url": "https://api.linkedin.com/v1/people/",
        "client_kwargs": {"scope": "r_basicprofile r_emailaddress"},
    }

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        token = self.get_access_token()
        if token is None:
            return ProfileData()
        try:
            r: requests.Response = self.app.get(
                "~:(id,formatted-name,email-address)?format=json"
            )
            r.raise_for_status()
            id_info: dict = r.json()
            current_app.logger.debug(f"id_info = {id_info}")
            id = id_info["id"]
        except (requests.HTTPError, ValueError) as e:
            current_app.logger.debug(f"{e}")
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=id_info.get("formattedName"),
            email=id_info.get("emailAddress"),
        )
        current_app.logger.debug(f"parsed as {profile_data}")
        return profile_data


class OrcidClient(OAuthClient):  # pragma: no cover
    """ORCID using OpenID Connect."""

    slug = "orcid"
    name = "ORCID"
    icon = "fa-brands fa-orcid"
    app_kwargs = {
        "api_base_url": "https://pub.orcid.org/v2.0/",
        "client_kwargs": dict(scope="openid"),
        "server_metadata_url": "https://orcid.org/.well-known/openid-configuration",
    }

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        token = self.get_access_token()
        if token is None:
            return ProfileData()
        try:
            user_info = token.get("userinfo") or self.app.userinfo()
            current_app.logger.debug(f"user_info = {user_info}")
            id = user_info["sub"]
            name = str(s) if (s := user_info.get("name")) else ""
            email = str(s) if (s := user_info.get("email")) else ""
        except requests.HTTPError or ValueError:
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=name,
            email=email,
        )
        if profile_data.email is None:
            email = ""
            try:
                r: requests.Response = self.app.get(
                    f"{id}/record",
                    headers={"Content-type": "application/vnd.orcid+json"},
                )
                r.raise_for_status()
                id_info: dict = r.json()
                current_app.logger.debug(f"id_info = {id_info}")
                contacts = (
                    id_info.get("person", dict())
                    .get("emails", dict())
                    .get("email", list())
                )
                for contact in contacts:
                    email = contact.get("email") or email
                    if contact.get("primary", False):
                        break
            except (requests.HTTPError, ValueError) as e:
                current_app.logger.debug(f"{e}")
                pass
            if email:
                profile_data = profile_data._replace(email=email)
        current_app.logger.debug(f"parsed as {profile_data}")
        return profile_data


class TwitterClient(OAuthClient):  # pragma: no cover
    """X (formerly Twitter) using OAuth 1.0a.

    Not actively supported. Do not configure alongside XClient.
    """

    app_cls = FlaskOAuth1App
    slug = "twitter"
    name = "X"
    icon = "fa-brands fa-twitter"
    app_kwargs = {
        "request_token_url": "https://api.x.com/oauth/request_token",
        "authorize_url": "https://api.x.com/oauth/authorize",
        "access_token_url": "https://api.x.com/oauth/access_token",
        "api_base_url": "https://api.x.com/1.1/",
    }

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        token = self.get_access_token()
        if token is None:
            return ProfileData()
        try:
            r: requests.Response = self.app.get("account/verify_credentials.json")
            r.raise_for_status()
            id_info: dict = r.json()
            current_app.logger.debug(f"id_info = {id_info}")
            id = id_info["id"]
        except (requests.HTTPError, ValueError) as e:
            current_app.logger.debug(f"{e}")
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=id_info.get("name"),
            # Need to write policy pages before retrieving email addresses
            email=None,
        )
        current_app.logger.debug(f"parsed as {profile_data}")
        return profile_data


class RDAClient(OAuthClient):  # pragma: no cover
    """RDA (WordPress miniOrange OAuth server) using OAuth 2.0."""

    slug = "rda"
    name = "RDA"
    main = True
    app_kwargs = {
        "api_base_url": "https://www.rd-alliance.org/wp-json/moserver",
        "client_kwargs": dict(scope="openid profile email"),
    }

    def __init__(self, client_id: str, client_secret: str):
        self.app_kwargs["server_metadata_url"] = (
            f"https://www.rd-alliance.org/wp-json/moserver/{client_id}"
            "/.well-known/openid-configuration"
        )
        super().__init__(client_id, client_secret)

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        token = self.get_access_token()
        if token is None:
            return ProfileData()
        try:
            user_info = token.get("userinfo") or self.app.userinfo()
            current_app.logger.debug(f"user_info = {user_info}")
            id = user_info["username"]
            name = str(s) if (s := user_info.get("display_name")) else ""
            if not name:
                name_parts = list()
                for part in ["first_name", "last_name"]:
                    if name_part := user_info.get(part):
                        name_parts.append(name_part)
                name = " ".join(name_parts) if name_parts else None
            email = str(s) if (s := user_info.get("email")) else ""
        except (requests.HTTPError, ValueError) as e:
            current_app.logger.debug(f"{e}")
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=name,
            email=email,
        )
        current_app.logger.debug(f"parsed as {profile_data}")
        return profile_data


class XClient(OAuthClient):  # pragma: no cover
    """X (formerly Twitter) using OAuth 2.0.

    Not actively supported. Do not configure alongside TwitterClient.
    """

    slug = "x"
    name = "X"
    icon = "fa-brands fa-x-twitter"
    app_kwargs = {
        "authorize_url": "https://x.com/i/oauth2/authorize",
        "access_token_url": "https://api.x.com/2/oauth2/token",
        "api_base_url": "https://api.x.com/2/",
        "client_kwargs": dict(scope="users.read"),
    }

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        token = self.get_access_token()
        if token is None:
            return ProfileData()
        try:
            r: requests.Response = self.app.get("account/verify_credentials.json")
            r.raise_for_status()
            id_info: dict = r.json()
            current_app.logger.debug(f"id_info = {id_info}")
            id = id_info["id"]  # not tested
        except requests.HTTPError or ValueError:
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=id_info.get("name"),  # not tested
            email=id_info.get("email"),  # not tested
        )
        if profile_data.username is None:
            # Email not available by this method
            name = ""
            try:
                r: requests.Response = self.app.get(
                    "users/me", params={"user.fields": "name"}
                )
                r.raise_for_status()
                user_info: dict = r.json()
                current_app.logger.debug(f"user_info = {user_info}")
                name = id_info.get("data", dict()).get("name")
            except (requests.HTTPError, ValueError) as e:
                current_app.logger.debug(f"{e}")
                pass
            if name:
                profile_data = profile_data._replace(username=name)
        current_app.logger.debug(f"parsed as {profile_data}")
        return profile_data


# Form components
# ===============
class LoginForm(FlaskForm):
    openid = StringField("OpenID v2 URL", validators=[validators.URL()])


class ProfileForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[validators.InputRequired(message="You must provide a user name.")],
    )
    email = StringField(
        "Email",
        validators=[
            validators.InputRequired(message="You must enter an email address."),
            validators.Email(message="You must enter a valid email address."),
        ],
    )


# Utility functions
# =================
def get_oauth_clients() -> dict[str, OAuthClient]:
    """Returns cached mapping to OAuthClient instances from their
    identifying slugs.
    """
    if "oauth_clients" not in g:
        g.oauth_clients = dict()
        cls_lookup = {cls.slug: cls for cls in OAuthClient.__subclasses__()}
        credential_store = current_app.config.get("OAUTH_CREDENTIALS")
        if not isinstance(credential_store, dict):
            return g.oauth_clients
        for slug, credentials in credential_store.items():
            cls = cls_lookup.get(slug)
            if not cls:
                current_app.logger.error(f"Unhandled OAuth provider '{slug}'.")
                continue
            client_id = credentials.get("id")
            if not client_id:
                current_app.logger.error(f"No client ID for OAuth provider '{slug}'.")
                continue
            client_secret = credentials.get("secret")
            if not client_secret:
                current_app.logger.error(
                    f"No client secret for OAuth provider '{slug}'."
                )
                continue
            g.oauth_clients[slug] = cls(
                client_id=client_id, client_secret=client_secret
            )
    return g.oauth_clients


@lm.user_loader
def load_user(id: str | int) -> User | None:
    """Utility for loading users."""
    user_db = get_user_db()
    document = user_db.get(doc_id=int(id))
    if isinstance(document, Document):
        return User(value=document, doc_id=document.doc_id)
    return None  # pragma: no cover


# Routes
# ======
@bp.route("/login", methods=["GET"])
def login():
    """This login view formerly handled both OpenID v2 and OAuth 2.0
    (OpenID Connect) authentication: the POST method was used to begin
    the OpenID v2 process.

    Now this page simply provides a series of OAuth 2.0 links that route
    to oauth_authorize().
    """
    if current_user.is_authenticated:
        return redirect(url_for("hello"))
    main_providers = list()
    providers = list()
    clients = get_oauth_clients()
    for client in sorted(clients.values(), key=lambda v: v.slug):
        if client.main:
            main_providers.append(client)
        else:
            providers.append(client)
    flash(
        "Logging in with RDA credentials is currently unavailable. "
        "We are working with the RDA website developers to fix this.",
        "warning",
    )
    return render_template(
        "login.html",
        main_providers=main_providers,
        providers=providers,
    )


@bp.route("/authorize/<provider>")
def oauth_authorize(provider: str):
    """This function calls out to the OAuth provider."""
    if not current_user.is_anonymous:
        return redirect(url_for("hello"))
    clients = get_oauth_clients()
    client = clients.get(provider)
    if client is None:
        abort(404)
    return client.authorize_redirect()


@bp.route("/callback/<provider>")
def oauth_callback(provider: str):
    """The OAuth provider sends information back to this URL,
    where we use it to extract a unique ID, user name and email address.
    """
    user_db = get_user_db()
    if not current_user.is_anonymous:
        return redirect(url_for("hello"))
    clients = get_oauth_clients()
    client = clients.get(provider)
    if client is None:
        abort(404)
    userid, username, email = client.get_profile_data()
    session["openid"] = userid
    if userid is None:
        flash("Authentication failed.", "error")
        return redirect(url_for("hello"))
    User = Query()
    profile = user_db.get(User.userid == userid)
    if isinstance(profile, Document):
        flash("Successfully signed in.")
        user = load_user(profile.doc_id)
        login_user(user)
        return redirect(url_for("hello"))
    return redirect(
        url_for(
            "auth.create_profile", next=url_for("hello"), name=username, email=email
        )
    )


@bp.route("/create-profile", methods=["GET", "POST"])
def create_profile():
    """If the user authenticated successfully by either means, but does
    not exist in the user database, this view creates and saves their profile.
    """
    user_db = get_user_db()
    if current_user.is_authenticated:
        return redirect(url_for("hello"))
    if "openid" not in session or session["openid"] is None:
        flash("OAuth sign-in failed, sorry.", "error")
        return redirect(url_for("hello"))
    form = ProfileForm(request.values)
    if request.method == "POST" and form.validate():
        data = {
            "name": form.name.data,
            "email": form.email.data,
            "userid": session["openid"],
        }
        user_doc_id = user_db.insert(data)
        flash("Profile successfully created.")
        user = User(value=data, doc_id=user_doc_id)
        login_user(user)
        return redirect(url_for("hello"))
    if form.errors:
        if "csrf_token" in form.errors:
            msg = (
                "Could not save changes as your form session has expired."
                " Please try again."
            )
        else:
            msg = (
                "Could not create profile as there {:/was an error/were N"
                " errors}. See below for details.".format(Pluralizer(len(form.errors)))
            )
        flash(msg, "error")
    return render_template("create-profile.html", form=form, next=url_for("hello"))


@bp.route("/edit-profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    """Allows users to change their displayed username and email address."""
    user_db = get_user_db()
    userid_tuple = current_user["userid"].partition("$")
    clients = get_oauth_clients()
    client = clients.get(userid_tuple[0])
    client_name = client.name if client else userid_tuple[0]
    openid_formatted = f"{client_name} profile for {current_user['name']}"
    form = ProfileForm(request.values, data=current_user)
    if request.method == "POST" and form.validate():
        data = {
            "name": form.name.data,
            "email": form.email.data,
            "userid": current_user["userid"],
        }
        if user_db.update(data, doc_ids=[current_user.doc_id]):
            flash("Profile successfully updated.")
        else:  # pragma: no cover
            flash("Profile could not be updated, sorry.", "error")
        return redirect(url_for("hello"))
    if form.errors:
        if "csrf_token" in form.errors:
            msg = (
                "Could not save changes as your form session has expired."
                " Please try again."
            )
        else:
            msg = (
                "Could not update profile as there {:/was an error/were N"
                " errors}. See below for details.".format(Pluralizer(len(form.errors)))
            )
        flash(msg, "error")
    return render_template(
        "edit-profile.html", form=form, openid_formatted=openid_formatted
    )


@bp.route("/remove-profile")
@login_required
def remove_profile():
    """Allows users to remove their profile from the system."""
    user_db = get_user_db()
    if user_db.remove(doc_ids=[current_user.doc_id]):
        flash("Your profile was successfully deleted.")
        logout_user()
        session.pop("openid", None)
        flash("You were signed out.")
    else:  # pragma: no cover
        flash("Your profile could not be deleted.", "error")
    return redirect(url_for("hello"))


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("openid", None)
    flash("You were signed out.")
    return redirect(url_for("hello"))
