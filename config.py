"""Application configuration objects.

Every environment gets its own class so that development, testing and
production never share secrets or databases.  The active config is chosen
through the ``FLASK_CONFIG`` environment variable (defaults to development).
"""

import os

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


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or sqlite_uri("products.db")


class TestingConfig(BaseConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ProductionConfig(BaseConfig):
    DEBUG = False

    # SQLite default, but a real deployment should set DATABASE_URL
    # (for example postgresql://user:pass@host/dbname).
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or sqlite_uri("products.db")


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
