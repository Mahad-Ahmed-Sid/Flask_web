"""Application-factory behaviour that must hold for every environment."""

import pytest

from config import TestingConfig
from product import create_app
from product.extensions import db


def test_create_app_creates_a_missing_sqlite_folder(tmp_path, monkeypatch):
    """A fresh clone has no ``instance/`` folder — SQLite needs one to exist."""
    target = tmp_path / "fresh-clone" / "products.db"
    assert not target.parent.exists()

    monkeypatch.setattr(TestingConfig, "SQLALCHEMY_DATABASE_URI", f"sqlite:///{target.as_posix()}")
    app = create_app("testing")

    assert target.parent.is_dir()

    # ...and the configured database must actually open there.
    with app.app_context():
        assert db.session.execute(db.text("SELECT 1")).scalar() == 1


def test_memory_databases_are_left_alone():
    """``sqlite:///:memory:`` has no folder to create."""
    app = create_app("testing")  # must not raise while looking for one

    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"


def test_an_unknown_config_name_fails_loudly():
    with pytest.raises(RuntimeError, match="Unknown FLASK_CONFIG"):
        create_app("staging")
