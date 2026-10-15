"""Application factory.

``create_app`` wires configuration, extensions, blueprints and error pages
together.  Nothing is bound to a global ``app`` object, so tests can build
as many isolated instances as they need.
"""

import os
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import flask
from flask import render_template, request
from flask_wtf.csrf import CSRFError

from config import config

from .extensions import csrf, db, migrate

__all__ = ["create_app"]


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
    _register_template_helpers(app)
    _register_error_handlers(app)
    _register_shell_context(app)

    # Imported here so the blueprint can safely import the models.
    from . import routes

    app.register_blueprint(routes.bp)

    return app


def _init_extensions(app: flask.Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)


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
    """Make ``Product`` available inside ``flask shell``."""

    @app.shell_context_processor
    def make_shell_context():
        from .models import Product

        return {"Product": Product, "db": db, "request": request}
