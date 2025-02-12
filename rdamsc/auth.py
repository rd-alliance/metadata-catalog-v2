# Dependencies
# ============
# Standard
# --------
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
    """Wrapper around authlib's FlaskOAuth1App and FlaskOAuth2App.
    Supports OAuth 1.0, OAuth 2.0 and OpenID Connect.
    """

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
        return self.app.authorize_redirect(redirect_uri=self.callback_url)

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
    app_kwargs = dict(
        authorize_url="http://example.org/login/oauth/authorize",
        access_token_url="http://example.org/login/oauth/access_token",
        api_base_url="http://example.org/",
        client_kwargs=dict(scope="user"),
    )

    def authorize_redirect(self) -> Response:
        if current_app.config["TESTING"] is not True:
            abort(404)
        return self.app.authorize_redirect(redirect_uri=self.callback_url)

    def get_profile_data(self) -> ProfileData:
        if current_app.config["TESTING"] is not True:
            return ProfileData()
        current_app.logger.debug(f"Login with {self.name}.")
        self.app.authorize_access_token()
        try:
            r: requests.Response = self.app.get("user")
            r.raise_for_status()
            id_info: dict = r.json()
            current_app.logger.debug(f"id_info = {id_info}")
            id = id_info["id"]
        except requests.HTTPError or ValueError:
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
    icon = "fab fa-github"
    app_kwargs = dict(
        authorize_url="https://github.com/login/oauth/authorize",
        access_token_url="https://github.com/login/oauth/access_token",
        api_base_url="https://api.github.com/",
        client_kwargs=dict(scope="read:user user:email"),
    )

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        self.app.authorize_access_token()
        try:
            r: requests.Response = self.app.get("user")
            r.raise_for_status()
            id_info: dict = r.json()
            current_app.logger.debug(f"id_info = {id_info}")
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
    icon = "fab fa-gitlab"
    app_kwargs = dict(
        client_kwargs=dict(scope="openid email"),
        server_metadata_url="https://gitlab.com/.well-known/openid-configuration",
    )

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        self.app.authorize_access_token()
        try:
            user_info = self.app.userinfo()
            current_app.logger.debug(f"user_info = {user_info}")
            id = user_info["sub"]
        except requests.HTTPError or ValueError:
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=user_info.get("name"),
            email=user_info.get("email"),
        )
        current_app.logger.debug(f"parsed as {profile_data}")
        return profile_data


class GoogleClient(OAuthClient):  # pragma: no cover
    """Google using OpenID Connect.

    Not actively supported.
    """

    slug = "google"
    name = "Google"
    icon = "fab fa-google"
    app_kwargs = dict(
        client_kwargs=dict(scope="openid name email"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    )

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        self.app.authorize_access_token()
        try:
            user_info = self.app.userinfo()
            current_app.logger.debug(f"user_info = {user_info}")
            id = user_info["sub"]
        except requests.HTTPError or ValueError:
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=user_info.get("name"),
            email=user_info.get("email"),
        )
        current_app.logger.debug(f"parsed as {profile_data}")
        return profile_data


class LinkedInClient(OAuthClient):  # pragma: no cover
    """LinkedIn using OAuth 2.0.

    Not actively supported.
    """

    slug = "linkedin"
    name = "LinkedIn"
    icon = "fab fa-linkedin"
    app_kwargs = dict(
        authorize_url="https://www.linkedin.com/oauth/v2/authorization",
        access_token_url="https://www.linkedin.com/oauth/v2/accessToken",
        api_base_url="https://api.linkedin.com/v1/people/",
        client_kwargs={"scope": "r_basicprofile r_emailaddress"},
    )

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        self.app.authorize_access_token()
        try:
            r: requests.Response = self.app.get(
                "~:(id,formatted-name,email-address)?format=json"
            )
            r.raise_for_status()
            id_info: dict = r.json()
            current_app.logger.debug(f"id_info = {id_info}")
            id = id_info["id"]
        except requests.HTTPError or ValueError:
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
    icon = "fab fa-orcid"
    app_kwargs = dict(
        api_base_url="https://pub.orcid.org/v2.0/",
        client_kwargs=dict(scope="openid"),
        server_metadata_url="https://orcid.org/.well-known/openid-configuration",
    )

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        self.app.authorize_access_token()
        try:
            user_info = self.app.userinfo()
            current_app.logger.debug(f"user_info = {user_info}")
            id = user_info["sub"]
        except requests.HTTPError or ValueError:
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=user_info.get("name"),
            email=user_info.get("email"),
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
            except requests.HTTPError or ValueError:
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
    icon = "fab fa-twitter"
    app_kwargs = dict(
        request_token_url="https://api.x.com/oauth/request_token",
        authorize_url="https://api.x.com/oauth/authorize",
        access_token_url="https://api.x.com/oauth/access_token",
        api_base_url="https://api.x.com/1.1/",
    )

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        self.app.authorize_access_token()
        try:
            r: requests.Response = self.app.get("account/verify_credentials.json")
            r.raise_for_status()
            id_info: dict = r.json()
            current_app.logger.debug(f"id_info = {id_info}")
            id = id_info["id"]
        except requests.HTTPError or ValueError:
            return ProfileData()
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=id_info.get("name"),
            # Need to write policy pages before retrieving email addresses
            email=None,
        )
        current_app.logger.debug(f"parsed as {profile_data}")
        return profile_data


class WicketClient(OAuthClient):  # pragma: no cover
    """Wicket using OAuth 2.0."""

    slug = "wicket"
    name = "RDA"
    main = True
    app_kwargs = dict(
        authorize_url="https://rda-login.wicketcloud.com/oauth2.0/authorize",
        access_token_url="https://rda-login.wicketcloud.com/oauth2.0/accessToken",
        api_base_url="https://rda-login.wicketcloud.com/oauth2.0/",
    )

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        self.app.authorize_access_token()
        try:
            r: requests.Response = self.app.get("profile")
            r.raise_for_status()
            id_info: dict = r.json()
            current_app.logger.debug(f"id_info = {id_info}")
            id = id_info["id"]
        except requests.HTTPError or ValueError:
            return ProfileData()
        user_attr: dict = id_info.get("attributes", dict())
        name_parts = list()
        for part in ["givenName", "familyName"]:
            if name_part := user_attr.get(part):
                name_parts.append(name_part)
        profile_data = ProfileData(
            userid=f"{self.slug}${id}",
            username=" ".join(name_parts) if name_parts else None,
            email=user_attr.get("email"),
        )
        current_app.logger.debug(f"parsed as {profile_data}")
        return profile_data


class XClient(OAuthClient):  # pragma: no cover
    """X (formerly Twitter) using OAuth 2.0.

    Not actively supported. Do not configure alongside TwitterClient.
    """

    slug = "x"
    name = "X"
    icon = "fab fa-twitter"
    app_kwargs = dict(
        authorize_url="https://x.com/i/oauth2/authorize",
        access_token_url="https://api.x.com/2/oauth2/token",
        api_base_url="https://api.x.com/2/",
        client_kwargs=dict(scope="users.read"),
    )

    def get_profile_data(self) -> ProfileData:
        current_app.logger.debug(f"Login with {self.name}.")
        self.app.authorize_access_token()
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
            except requests.HTTPError or ValueError:
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
