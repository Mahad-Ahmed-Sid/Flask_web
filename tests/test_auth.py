"""Account lifecycle: registration, sign-in, sign-out, profile and adoption."""

from decimal import Decimal

import pytest
from conftest import PASSWORD, html, login

from product.extensions import db
from product.models import Category, Product, User
from product.seed import ADMIN_DEV_PASSWORD, ADMIN_EMAIL, ensure_admin_user

NEW_PASSWORD = "long-enough-passphrase"


def register(client, **overrides):
    """Submit the registration form; ``overrides`` replace single fields."""
    follow = overrides.pop("follow_redirects", False)
    data = {
        "display_name": "New User",
        "email": "new@example.com",
        "password": NEW_PASSWORD,
        "password_confirm": NEW_PASSWORD,
    }
    data.update(overrides)
    return client.post("/auth/register", data=data, follow_redirects=follow)


@pytest.fixture()
def demo_state(app):
    """A database shaped like the one the migration leaves behind."""
    admin, _created = ensure_admin_user()
    db.session.add(admin)
    db.session.flush()
    db.session.add_all(
        [
            Product(
                product_name="Legacy One",
                price=Decimal("1.00"),
                product_description="migrated",
                owner=admin,
            ),
            Product(
                product_name="Legacy Two",
                price=Decimal("2.00"),
                product_description=None,
                owner=admin,
            ),
        ]
    )
    db.session.commit()
    return admin


# --------------------------------------------------------------------- #
# Registration                                                          #
# --------------------------------------------------------------------- #


def test_register_creates_an_account_and_signs_in(client, app):
    response = register(client, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard/")

    with app.app_context():
        account = db.session.scalar(db.select(User).where(User.email == "new@example.com"))
        assert account is not None
        assert account.display_name == "New User"
        assert account.check_password(NEW_PASSWORD)


def test_register_normalises_the_email(client, app):
    register(client, email="MixedCase@Example.COM")

    with app.app_context():
        account = db.session.scalar(db.select(User))
        assert account.email == "mixedcase@example.com"


def test_register_rejects_a_duplicate_email(client, app, user):
    response = register(client, email="OWNER@example.com")

    assert response.status_code == 200
    assert "already exists" in html(response)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(User)) == 1


def test_register_rejects_mismatched_passwords(client, app):
    response = register(client, password_confirm="something-else")

    assert response.status_code == 200
    assert "do not match" in html(response)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(User)) == 0


def test_register_rejects_a_short_password(client, app):
    response = register(client, password="short", password_confirm="short")

    assert response.status_code == 200
    assert "between 8 and 128" in html(response)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(User)) == 0


def test_register_rejects_an_invalid_email(client, app):
    response = register(client, email="not-an-email")

    assert response.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(User)) == 0


def test_passwords_are_hashed_not_stored(client, app):
    register(client)

    with app.app_context():
        account = db.session.scalar(db.select(User))
        assert NEW_PASSWORD not in account.password_hash
        assert account.password_hash.startswith("scrypt:")
        assert not account.check_password("wrong-password")


def test_register_while_signed_in_goes_to_the_dashboard(auth_client):
    response = auth_client.post(
        "/auth/register",
        data={
            "display_name": "Another",
            "email": "another@example.com",
            "password": NEW_PASSWORD,
            "password_confirm": NEW_PASSWORD,
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard/")


# --------------------------------------------------------------------- #
# Signing in and out                                                    #
# --------------------------------------------------------------------- #


def test_login_and_logout_roundtrip(client, user):
    assert login(client, user.email).status_code == 302

    assert client.get("/dashboard/").status_code == 200

    signed_out = client.post("/auth/logout", follow_redirects=True)
    assert signed_out.status_code == 200
    assert "You have been signed out." in html(signed_out)

    # The session really is gone.
    assert client.get("/dashboard/").status_code == 302


def test_logout_is_post_only(client, user):
    """A GET link would let any page sign your users out."""
    login(client, user.email)

    assert client.get("/auth/logout").status_code == 405


def test_login_with_the_wrong_password(client, user):
    response = login(client, user.email, password="not-the-password")

    assert response.status_code == 200
    assert "Invalid email or password." in html(response)
    assert client.get("/dashboard/").status_code == 302  # not signed in


def test_login_with_an_unknown_email_gives_the_same_message(client):
    response = login(client, "nobody@example.com")

    assert response.status_code == 200
    assert "Invalid email or password." in html(response)


def test_login_with_an_invalid_email_renders_the_form(client):
    response = login(client, "not-an-email")

    assert response.status_code == 200
    assert "Invalid email or password." not in html(response)


def test_remember_me_is_an_option(client, user):
    response = login(client, user.email)  # checkbox unticked

    assert response.status_code == 302
    assert "remember" not in response.headers.get("Set-Cookie", "").lower()


# --------------------------------------------------------------------- #
# Profile and password                                                  #
# --------------------------------------------------------------------- #


def test_profile_page_shows_the_account(auth_client, user):
    response = auth_client.get("/auth/profile")

    assert response.status_code == 200
    body = html(response)
    assert user.email in body
    assert "Account details" in body


def test_profile_update_persists(auth_client, user, app):
    response = auth_client.post(
        "/auth/profile",
        data={"display_name": "Renamed Owner", "email": "renamed@example.com"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Renamed Owner" in html(response)

    with app.app_context():
        saved = db.session.get(User, user.id)
        assert saved.display_name == "Renamed Owner"
        assert saved.email == "renamed@example.com"


def test_profile_rejects_an_email_used_by_someone_else(auth_client, other_user):
    response = auth_client.post(
        "/auth/profile",
        data={"display_name": "Owner", "email": other_user.email},
    )

    assert response.status_code == 200
    assert "Another account already uses that email." in html(response)


def test_profile_may_keep_its_own_email(auth_client, user):
    response = auth_client.post(
        "/auth/profile",
        data={"display_name": "Owner", "email": user.email.upper()},
    )

    assert response.status_code == 302


def test_change_password_rejects_a_wrong_current_password(auth_client, user, app):
    response = auth_client.post(
        "/auth/profile/password",
        data={
            "current_password": "not-the-password",
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert "not your current password" in html(response)
    with app.app_context():
        assert db.session.get(User, user.id).check_password(PASSWORD)


def test_change_password_updates_the_hash(auth_client, user, app):
    response = auth_client.post(
        "/auth/profile/password",
        data={
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "new_password_confirm": NEW_PASSWORD,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Your password was changed." in html(response)

    with app.app_context():
        saved = db.session.get(User, user.id)
        assert saved.check_password(NEW_PASSWORD)
        assert not saved.check_password(PASSWORD)


def test_set_password_cli_works(app, user):
    runner = app.test_cli_runner()

    result = runner.invoke(args=["set-password", user.email, "--password", "from-the-cli-pass"])

    assert result.exit_code == 0, result.output
    with app.app_context():
        assert db.session.get(User, user.id).check_password("from-the-cli-pass")


def test_set_password_cli_reports_unknown_accounts(app):
    runner = app.test_cli_runner()

    result = runner.invoke(args=["set-password", "ghost@example.com", "--password", "x" * 9])

    assert result.exit_code != 0
    assert "No account found" in result.output


# --------------------------------------------------------------------- #
# Adopting the migrated inventory                                       #
# --------------------------------------------------------------------- #


def test_first_registration_adopts_the_demo_products(app, client, demo_state):
    response = register(client, email="first@example.com", follow_redirects=True)

    assert response.status_code == 200
    assert "2 products from the demo account were moved" in html(response)

    with app.app_context():
        first = db.session.scalar(db.select(User).where(User.email == "first@example.com"))
        owners = {
            product.id: product.owner_id for product in db.session.scalars(db.select(Product)).all()
        }
        assert set(owners.values()) == {first.id}


def test_adopted_products_keep_their_categories(app, client, demo_state):
    category = Category(name="Migrated Cat", user_id=demo_state.id)
    db.session.add(category)
    db.session.commit()

    with app.app_context():
        legacy = db.session.scalar(db.select(Product).where(Product.product_name == "Legacy One"))
        legacy.category_id = category.id
        db.session.commit()

    register(client, email="first@example.com")

    with app.app_context():
        first = db.session.scalar(db.select(User).where(User.email == "first@example.com"))
        moved = db.session.scalar(db.select(Category).where(Category.name == "Migrated Cat"))
        assert moved.user_id == first.id  # the category came along


def test_second_registration_adopts_nothing(app, client, demo_state):
    # Follow the first registration's redirect so its adoption flash is
    # consumed before the second account registers.
    first_page = register(client, email="first@example.com", follow_redirects=True)
    assert "moved into your inventory" in html(first_page)

    # Registration is only possible from a signed-out session.
    client.post("/auth/logout", follow_redirects=True)

    second = register(client, email="second@example.com", follow_redirects=True)

    assert second.status_code == 200
    assert "moved into your inventory" not in html(second)

    with app.app_context():
        first_user = db.session.scalar(db.select(User).where(User.email == "first@example.com"))
        second_user = db.session.scalar(db.select(User).where(User.email == "second@example.com"))
        owner_ids = {product.owner_id for product in db.session.scalars(db.select(Product)).all()}
        assert owner_ids == {first_user.id}  # only the first account holds stock
        assert second_user.id not in owner_ids
        assert second_user.product_count == 0


def test_seeded_admin_password_is_the_documented_default(app):
    """The README documents this password — keep the two in step."""
    user, created = ensure_admin_user()
    db.session.add(user)
    db.session.commit()

    assert created is True
    assert user.email == ADMIN_EMAIL
    assert user.check_password(ADMIN_DEV_PASSWORD)
