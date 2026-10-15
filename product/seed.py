"""Seeding helpers shared by the database migration and the Flask CLI.

The migration that introduces user accounts has to give the three products
that already exist an owner.  It does that by creating this account, which is
also a handy way to look around the app right after upgrading.

The password below is a **development default, not a secret**: it is
documented in the README and can be changed at any time with::

    flask --app app set-password admin@inventory.local

Set ``ADMIN_EMAIL`` / ``ADMIN_DEV_PASSWORD`` in the environment *before*
running the migration if you want different values.
"""

import os

from .extensions import db
from .models import User

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@inventory.local").strip().lower()
ADMIN_DISPLAY_NAME = os.environ.get("ADMIN_DISPLAY_NAME", "Inventory Admin")
ADMIN_DEV_PASSWORD = os.environ.get("ADMIN_DEV_PASSWORD", "ChangeMe-Admin1!")


def find_admin() -> User | None:
    """The seeded admin account, or ``None`` if it does not exist yet."""
    return db.session.scalar(db.select(User).where(User.email == ADMIN_EMAIL))


def create_admin_user(password: str = ADMIN_DEV_PASSWORD) -> User:
    """Create (but do not commit) the admin account."""
    user = User(
        email=ADMIN_EMAIL,
        display_name=ADMIN_DISPLAY_NAME,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    return user


def ensure_admin_user(password: str = ADMIN_DEV_PASSWORD) -> tuple[User, bool]:
    """Return ``(user, created)`` — idempotent, does not commit."""
    existing = find_admin()
    if existing is not None:
        return existing, False
    return create_admin_user(password=password), True
