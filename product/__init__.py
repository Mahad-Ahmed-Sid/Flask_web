"""Application factory.

``create_app`` wires configuration, extensions, blueprints, the login guard
and error pages together.  Nothing is bound to a global ``app`` object, so
tests can build as many isolated instances as they need.
"""

import os
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import click
import flask
from flask import render_template, request
from flask_login import current_user
from flask_wtf.csrf import CSRFError

from config import config

from .extensions import csrf, db, login_manager, migrate

__all__ = ["create_app"]

# Blueprints that anonymous visitors may reach.  Everything else — including
# any blueprint added later — requires a signed-in user, so forgetting a
# ``@login_required`` decorator fails closed rather than leaking data.
PUBLIC_BLUEPRINTS = {"auth"}


def create_app(config_name: str | None = None) -> flask.Flask:
    """Build and return a configured Flask application.

    :param config_name: key of :data:`config.config` — ``development``,
        ``testing`` or ``production``.  Defaults to ``FLASK_CONFIG``.
    """
    config_name = config_name or os.environ.get("FLASK_CONFIG") or "default"
    if config_name not in config:
        raise RuntimeError(
            f"Unknown FLASK_CONFIG {config_name!r}; expected one of {', '.join(sorted(config))}"
        )

    # Templates and static assets live at the project root, next to this
    # package, so the folders are addressed relative to this file.
    app = flask.Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config.from_object(config[config_name])

    _init_extensions(app)
    _register_request_hooks(app)
    _register_login_guard(app)
    _register_template_helpers(app)
    _register_error_handlers(app)
    _register_shell_context(app)
    _register_cli(app)

    # Imported here so the blueprints can safely import the models.
    from . import auth, categories, dashboard, reports, routes

    app.register_blueprint(routes.bp)  # /            inventory
    app.register_blueprint(auth.bp)  # /auth        accounts
    app.register_blueprint(dashboard.bp)  # /dashboard  overview
    app.register_blueprint(categories.bp)  # /categories  categories
    app.register_blueprint(reports.bp)  # /reports     reports + CSV

    return app


def _init_extensions(app: flask.Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)


def _register_request_hooks(app: flask.Flask) -> None:
    """Hooks that must run before everything else, including the login guard."""

    @app.before_request
    def reset_login_user_cache() -> None:
        """Give every request a clean Flask-Login cache.

        Flask-Login 0.6.3 caches ``current_user`` on ``flask.g``.  Because a
        WSGI server pushes a fresh application context per request, that cache
        is naturally per-request in production — but whenever one context is
        reused for several requests (a test client inside
        ``with app.app_context()``, a script, a notebook), the first request's
        user would otherwise be handed to every later request, silently
        breaking account isolation.  Dropping the cache here restores the
        per-request semantics Flask-Login assumes in every hosting style.
        """
        flask.g.pop("_login_user", None)


def _register_login_guard(app: flask.Flask) -> None:
    @app.before_request
    def require_login() -> flask.Response | None:
        """Fail closed: every endpoint needs a user unless explicitly public."""
        if request.endpoint is None:
            # Unmatched URL or wrong method — let Flask raise 404/405 so the
            # error pages (which must work for signed-out visitors) render.
            return None
        if request.blueprint in PUBLIC_BLUEPRINTS or request.endpoint == "static":
            return None
        if current_user.is_authenticated:
            return None
        # flask-login builds the redirect (and the "please sign in" flash).
        return login_manager.unauthorized()


def _register_template_helpers(app: flask.Flask) -> None:
    """Formatting filters shared by every template."""

    @app.template_filter("currency")
    def currency(value) -> str:
        """``1234.5`` → ``$1,234.50`` (cash-style half-up rounding)."""
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            amount = Decimal("0")
        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"${amount:,.2f}"

    @app.template_filter("friendly_date")
    def friendly_date(value) -> str:
        """``datetime`` → ``Aug 20, 2026`` (renders an em dash if empty)."""
        if not value:
            return "—"
        try:
            return f"{value:%b %d, %Y}"
        except (TypeError, ValueError):
            return "—"

    @app.template_filter("friendly_datetime")
    def friendly_datetime(value) -> str:
        """``datetime`` → ``Aug 20, 2026 14:03`` (audit timestamps)."""
        if not value:
            return "—"
        try:
            return f"{value:%b %d, %Y %H:%M}"
        except (TypeError, ValueError):
            return "—"

    @app.template_filter("signed_delta")
    def signed_delta(value) -> str:
        """``5`` → ``+5``, ``-3`` → ``-3`` (stock adjustment rows)."""
        try:
            return f"{int(value):+d}"
        except (TypeError, ValueError):
            return "±0"


def _register_error_handlers(app: flask.Flask) -> None:
    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(_error):
        return render_template("errors/500.html"), 500

    @app.errorhandler(CSRFError)
    def csrf_expired(error):
        """A stale form instead of an opaque 400 page."""
        return (
            render_template("errors/csrf.html", description=error.description),
            400,
        )


def _register_shell_context(app: flask.Flask) -> None:
    """Make the models available inside ``flask shell``."""

    @app.shell_context_processor
    def make_shell_context():
        from .models import Category, Product, StockAdjustment, User

        return {
            "Product": Product,
            "User": User,
            "Category": Category,
            "StockAdjustment": StockAdjustment,
            "db": db,
            "request": request,
        }


def _register_cli(app: flask.Flask) -> None:
    """Maintenance commands that do not require a shell session."""

    @app.cli.command("set-password")
    @click.argument("email")
    @click.password_option(prompt="New password")
    def set_password_command(email: str, password: str) -> None:
        """Set (or reset) the password for EMAIL without logging in."""
        from .forms import find_user_by_email

        user = find_user_by_email(email)
        if user is None:
            raise click.ClickException(f"No account found for {email!r}.")

        user.set_password(password)
        db.session.commit()
        click.echo(f"Password updated for {user.email}.")

    @app.cli.command("seed-admin")
    def seed_admin_command() -> None:
        """Create the demo admin account if it does not exist yet."""
        from .seed import ensure_admin_user

        user, created = ensure_admin_user()
        db.session.commit()
        if created:
            click.echo(f"Created {user.email} — change the password in production.")
        else:
            click.echo(f"{user.email} already exists ({user.product_count} product(s)).")
