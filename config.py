"""Application configuration objects.

Every environment gets its own class so that development, testing and
production never share secrets or databases.  The active config is chosen
through the ``FLASK_CONFIG`` environment variable (defaults to development).
"""

import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


def sqlite_uri(filename: str) -> str:
    """Absolute ``sqlite://`` URI for *filename* (forward slashes only).

    Forward slashes keep the URI valid on Windows, where ``os.path.join``
    would otherwise inject backslashes into the connection string.
    """
    path = os.path.join(basedir, "instance", filename).replace("\\", "/")
    return f"sqlite:///{path}"


class BaseConfig:
    """Settings shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me-before-deploying")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Keep CSRF tokens valid for as long as a tab stays open.
    WTF_CSRF_TIME_LIMIT = None

    # Pagination page size used by the product list.
    PRODUCTS_PER_PAGE = 10

    # Products at or below this level (and anything at 0) count as low stock.
    # Each product may override it with its own threshold.
    LOW_STOCK_THRESHOLD = 10

    # --- Session hardening -------------------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    # A failed login costs the same as a successful one, so adding a small
    # delay is the cheapest defence against password spraying.
    LOGIN_RATE_LIMIT_SECONDS = 0.5

    # Forms in this app are tiny; reject absurd uploads early.
    MAX_CONTENT_LENGTH = 1 * 1024 * 1024  # 1 MB


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or sqlite_uri("products.db")


class TestingConfig(BaseConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

    # The deliberate login delay exists to slow down password spraying; in
    # tests it would only slow the suite down (each login would sleep).
    LOGIN_RATE_LIMIT_SECONDS = 0


class ProductionConfig(BaseConfig):
    DEBUG = False

    # Cookies must only travel over HTTPS. Set SESSION_COOKIE_SECURE=0 if you
    # deliberately deploy over plain HTTP (not recommended).
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "1") == "1"

    # SQLite default, but a real deployment should set DATABASE_URL
    # (for example postgresql://user:pass@host/dbname).
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or sqlite_uri("products.db")


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
