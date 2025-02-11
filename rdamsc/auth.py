# Dependencies
# ============
# Standard
# --------
from datetime import datetime, timezone
from email.utils import parsedate_tz, mktime_tz
from sys import api_version
import typing as t

# Non-standard
# ------------
from flask import (
    Response,
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
import google.auth.transport.requests as google_requests
import google.auth.exceptions as google_exceptions
from google.oauth2 import id_token as google_id_token
from authlib.oauth2.client import OAuth2Client
from authlib.integrations.flask_client.apps import FlaskOAuth1App, FlaskOAuth2App
from authlib.integrations.flask_client.integration import FlaskIntegration
import requests
from tinydb import TinyDB, Query
from wtforms import validators, StringField

# Local
# -----
from .users import User, get_user_db
from .utils import Pluralizer

bp = Blueprint("auth", __name__)
lm = LoginManager()
lm.login_view = "auth.login"
lm.login_message = "Please sign in to access this page."
lm.login_message_category = "error"


# Auth provider classes
# =====================
class ProfileData(t.NamedTuple):
    userid: t.Optional[str] = None
    username: t.Optional[str] = None
    email: t.Optional[str] = None

class OAuthClient:
    """Wrapper around authlib's FlaskOAuth1App and FlaskOAuth2App."""

    framework_integration_cls = FlaskIntegration
    app_cls = FlaskOAuth2App
    slug = ""
    name = ""
    icon = "fas fa-key"
    main = False
    app_kwargs = dict()

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
        raise NotImplementedError  # pragma: no cover

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

class GitHubClient(OAuthClient):
    slug = "github"
    name = "GitHub"
    icon = "fab fa-github"
    app_kwargs = dict(
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"},
    )

    def authorize_redirect(self) -> Response:
        return self.app.authorize_redirect(redirect_uri=self.callback_url)

    def get_profile_data(self) -> ProfileData:
        self.app.authorize_access_token()
        try:
            r = self.app.get("user")
            r.raise_for_status()
            id_info = r.json()
            id = id_info["login"]
        except requests.HTTPError or ValueError:
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=id_info.get("name"),
            email=id_info.get("email"),
        )
        if profile_data.email is None:
            email = ""
            try:
                r = self.app.get("user/emails")
                r.raise_for_status()
                contacts = r.json()
                for contact in contacts:
                    email = contact.get("email")
                    if contact.get("primary", False):
                        break
            except requests.HTTPError or ValueError:
                pass
            if email:
                profile_data = profile_data._replace(email=email)
        current_app.logger.debug(f"{profile_data}")
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
                current_app.logger.error(f"No client ID for OAuth provider '{slug}'.")
                continue
            g.oauth_clients[slug] = cls(
                client_id=client_id, client_secret=client_secret
            )
    return g.oauth_clients


def get_oauth_db() -> TinyDB:
    """Returns the oauth database as a TinyDB object. The object is
    cached so further calls return the same one.
    """
    if "oauth_db" not in g:
        g.oauth_db = TinyDB(current_app.config["OAUTH_DATABASE_PATH"])

    return g.oauth_db


@lm.user_loader
def load_user(id: t.Union[str, int]) -> t.Optional[User]:
    """Utility for loading users."""
    user_db = get_user_db()
    document = user_db.get(doc_id=int(id))
    if document:
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
        flash("Authentication failed.")
        return redirect(url_for("hello"))
    User = Query()
    profile = user_db.get(User.userid == userid)
    if profile:
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
            flash("Profile could not be updated, sorry.")
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
        flash("Your profile could not be deleted.")
    return redirect(url_for("hello"))


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("openid", None)
    flash("You were signed out.")
    return redirect(url_for("hello"))
