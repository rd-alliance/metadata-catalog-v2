#!/usr/bin/env python3

# Dependencies
# ============
# Standard
# --------
from collections.abc import Mapping
from datetime import datetime, timezone
import logging.config
import os
import subprocess
from typing import Any

# Non-standard
# ------------
from flask import Flask, render_template, redirect, url_for
from github_webhook import Webhook

# Local
# -----
from .records import VocabTerm
from .utils import from_url_slug, has_day, is_list, to_url_slug, url_for_subject


logging.config.dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "%(name)s - %(levelname)s: %(message)s",
            }
        },
        "handlers": {
            "wsgi": {
                "class": "logging.StreamHandler",
                "stream": "ext://flask.logging.wsgi_errors_stream",
                "formatter": "default",
            }
        },
        "root": {"level": "WARNING", "handlers": ["wsgi"]},
    }
)


def create_app(
    test_config: Mapping[str, Any] | None = None, instance_path: str | None = None
) -> Flask:
    """Factory for initialising the Flask application."""
    kwargs: dict[str, Any] = {"instance_relative_config": True}
    if instance_path:
        kwargs["instance_path"] = instance_path
    elif "FLASK_INSTANCE_PATH" in os.environ:
        kwargs["instance_path"] = os.environ["FLASK_INSTANCE_PATH"]

    # Create the app:
    app = Flask(__name__, **kwargs)

    # Set default configuration:
    app.config.from_mapping(
        SECRET_KEY="Do not use this in production.",
        WEBHOOK_SECRET="Do not use this in production either.",
        MAIN_DATABASE_PATH=os.path.join(app.instance_path, "data", "db.json"),
        VOCAB_DATABASE_PATH=os.path.join(app.instance_path, "data", "vocab.json"),
        TERM_DATABASE_PATH=os.path.join(app.instance_path, "data", "terms.json"),
        USER_DATABASE_PATH=os.path.join(app.instance_path, "users", "db.json"),
        DEBUG=False,
        TESTING=False,
    )
    app.json.ensure_ascii = False  # pyright: ignore[reportAttributeAccessIssue]

    # Override these settings as appropriate:
    if test_config is None:
        # Load the instance config, if it exists:
        app.config.from_pyfile("config.py", silent=True)
    else:
        # Load the test configuration that was passed in:
        app.config.from_mapping(test_config)

    # Override with environment variable if set:
    app.config.from_envvar("MSC_SETTINGS", silent=True)

    # Make sure all these directories exist:
    for path in [
        os.path.dirname(app.config["MAIN_DATABASE_PATH"]),
        os.path.dirname(app.config["VOCAB_DATABASE_PATH"]),
        os.path.dirname(app.config["TERM_DATABASE_PATH"]),
        os.path.dirname(app.config["USER_DATABASE_PATH"]),
    ]:
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
    @app.route("/")
    def hello():
        return render_template("home.html")

    # Scope note:
    @app.route("/scope")
    def scope():
        return render_template("scope.html")

    # Terms of use:
    @app.route("/terms-of-use")
    def terms_of_use():
        return render_template("terms-of-use.html")

    # Accessibility statement:
    @app.route("/accessibility")
    def accessibility():
        return render_template("accessibility.html")

    # Accessibility statement:
    @app.route("/contributing")
    def contributing():
        return render_template("contributing.html")

    # Dynamic pages:
    from . import auth

    auth.lm.init_app(app)
    app.register_blueprint(auth.bp)

    from . import records

    app.register_blueprint(records.bp)

    from . import lists

    app.register_blueprint(lists.bp)

    from . import search

    app.register_blueprint(search.bp)

    from . import api1

    app.register_blueprint(api1.bp, url_prefix="/api")

    from . import api2

    app.register_blueprint(api2.bp, url_prefix="/api2")

    # Redirects:
    @app.route("/thesaurus")
    def redirect_thesaurus_scheme():
        return redirect(url_for("api2.get_thesaurus_scheme"))

    @app.route("/thesaurus/<any(domain, subdomain, concept):level><int:number>")
    def redirect_thesaurus_concept(level: str, number: int):
        return redirect(
            url_for("api2.get_thesaurus_concept", level=level, number=number)
        )

    @app.route("/favicon.ico")
    def redirect_favicon():
        return redirect(url_for("static", filename="favicon.ico"))

    # Webhook:
    webhook = Webhook(app, secret=app.config["WEBHOOK_SECRET"])
    git_work_dir = os.path.dirname(os.path.dirname(__file__))

    @webhook.hook()
    def on_push(data):
        # Check mod time of requirements.txt:
        req_path = os.path.join(git_work_dir, "requirements.txt")
        req_mtime = os.stat(req_path).st_mtime

        # Run git pull
        app.logger.warning("Upstream code repository has been updated.")
        app.logger.warning("Initiating git pull to update codebase.")
        call = subprocess.run(
            ["git", *["-C", git_work_dir], "pull", "--rebase"], capture_output=True
        )
        msg = f"Git pull completed with exit code {call.returncode}."
        if call.returncode:
            msg += f"\n{call.stderr.decode()}"
            app.logger.error(msg)
        else:
            app.logger.warning(msg)

        # Update dependencies if changed:
        if req_mtime != os.stat(req_path).st_mtime:
            app.logger.warning("Requirements have changed. Updating.")
            call = subprocess.run(
                [
                    os.path.join(git_work_dir, "venv", "bin", "pip"),
                    "install",
                    "-U",
                    *["--upgrade-strategy", "eager"],
                    *["-r", req_path],
                ],
                capture_output=True,
            )
            msg = f"Update completed with exit code {call.returncode}."
            if call.returncode:
                msg += f"\n{call.stderr.decode()}"
                app.logger.error(msg)
            else:
                app.logger.warning(msg)

        wsgi_path = app.config.get("WSGI_PATH")
        if wsgi_path:  # pragma: no cover
            if os.path.isfile(wsgi_path):
                os.utime(wsgi_path, None)
                app.logger.warning("Application reloaded.")
            else:
                app.logger.error(
                    f"Value of WSGI_PATH ({wsgi_path}) is not a valid file."
                )

    # Utility functions used in templates:
    @app.context_processor
    def utility_processor():
        return {
            "toURLSlug": to_url_slug,
            "fromURLSlug": from_url_slug,
            "urlForSubject": url_for_subject,
            "hasDay": has_day,
            "isList": is_list,
        }

    @app.context_processor
    def activate_fontawesome():
        return {"fa_kit": app.config.get("FA_KIT")}

    @app.context_processor
    def inject_maintenance():
        vars = {
            "maintenance_ongoing": False,
            "maintenance_start": None,
            "maintenance_end": None,
        }
        now = datetime.now(timezone.utc)
        if m_start_iso := app.config.get("MAINTENANCE_START"):
            try:
                m_start = datetime.fromisoformat(m_start_iso).replace(
                    tzinfo=timezone.utc
                )
                vars["maintenance_start"] = (
                    f"on {m_start.day} {m_start.strftime('%B %Y from %H:%M')}"
                )
                if now > m_start:
                    vars["maintenance_ongoing"] = True
                if m_end_iso := app.config.get("MAINTENANCE_END"):
                    m_end = datetime.fromisoformat(m_end_iso).replace(
                        tzinfo=timezone.utc
                    )
                    if now > m_end and vars["maintenance_ongoing"]:
                        vars["maintenance_ongoing"] = False
                        vars["maintenance_start"] = None
                    elif m_end > m_start:
                        if vars["maintenance_ongoing"]:
                            vars["maintenance_end"] = (
                                f"until {m_end.day} {m_end.strftime('%B %Y at %H:%M')}"
                                if m_end.date() > now.date()
                                else f"until {m_end.strftime('%H:%M')}"
                            )
                        elif m_end.date() > m_start.date():
                            vars["maintenance_start"] = (
                                f"from {m_start.day} "
                                f"{m_start.strftime('%B %Y at %H:%M')} UTC"
                            )
                            vars["maintenance_end"] = (
                                f"until {m_end.day} {m_end.strftime('%B at %H:%M')}"
                            )
                        else:
                            vars["maintenance_end"] = (
                                "until " if vars["maintenance_ongoing"] else "to "
                            )
                            vars["maintenance_end"] = f"to {m_end.strftime('%H:%M')}"
            except ValueError:
                pass
        return vars

    return app
