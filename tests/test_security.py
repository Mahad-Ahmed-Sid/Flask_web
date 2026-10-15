"""Security properties: login gate, data isolation, POST-only, cookies."""

import pytest
from conftest import PASSWORD, html, login

from config import ProductionConfig
from product.extensions import db
from product.models import Product, User

PRIVATE_PATHS = [
    "/",
    "/dashboard/",
    "/reports/",
    "/reports/export.csv",
    "/categories/",
    "/auth/profile",
    "/auth/profile/password",
    "/edit/1",
    "/stock/1",
]


# --------------------------------------------------------------------- #
# The login gate (fail closed)                                          #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("path", PRIVATE_PATHS)
def test_private_pages_send_anonymous_visitors_to_login(client, path):
    response = client.get(path)

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_login_redirect_remembers_the_destination(client):
    location = client.get("/reports/").headers["Location"]

    assert "next=" in location


def test_unknown_urls_still_404_for_anonymous_visitors(client):
    assert client.get("/nowhere-at-all").status_code == 404


def test_wrong_method_is_405_not_a_redirect(client):
    assert client.get("/auth/logout").status_code == 405


# --------------------------------------------------------------------- #
# Cross-account isolation                                                #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("path", ["/edit/{id}", "/stock/{id}"])
def test_a_stranger_cannot_read_your_objects(other_client, sample_products, path):
    product = sample_products[0]
    response = other_client.get(path.format(id=product.id))

    # 404, never 403: a stranger must not learn that the id exists.
    assert response.status_code == 404


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/stock/{id}"),
        ("post", "/edit/{id}"),
        ("post", "/delete/{id}"),
    ],
)
def test_a_stranger_cannot_change_your_objects(other_client, sample_products, method, path):
    product = sample_products[0]
    response = getattr(other_client, method)(
        path.format(id=product.id),
        data={
            "product_name": "Hijacked",
            "price": "1.00",
            "direction": "increase",
            "amount": "5",
            "reason": "sale",
        },
    )

    assert response.status_code == 404

    saved = db.session.get(Product, product.id)
    assert saved.product_name == "Alpha Widget"
    assert saved.quantity == 5


def test_the_list_never_shows_another_accounts_products(auth_client, other_client, sample_products):
    body = html(other_client.get("/"))

    assert "Alpha Widget" not in body
    assert "No products yet" in body


def test_dashboard_numbers_are_per_account(auth_client, other_client, sample_products):
    body = html(other_client.get("/dashboard/"))

    assert "$1,050.00" not in body


def test_a_strangers_csv_is_empty(auth_client, other_client, sample_products):
    body = other_client.get("/reports/export.csv").get_data(as_text=True)

    assert "Alpha Widget" not in body
    assert body.lstrip("\ufeff").splitlines()[0].startswith("id,name,category")


def test_a_stranger_cannot_filter_by_your_category(other_client, other_user, category):
    own = Product(
        product_name="Stranger Thing",
        price="1.00",
        owner=other_user,
        quantity=5,
        low_stock_threshold=1,
    )
    db.session.add(own)
    db.session.commit()

    response = other_client.get(f"/?category={category.id}")

    assert response.status_code == 200
    body = html(response)
    assert "Stranger Thing" not in body  # their own product, different category
    assert "No products match" in body


def test_a_stranger_cannot_delete_your_category(other_client, category):
    assert other_client.post(f"/categories/{category.id}/delete").status_code == 404


def test_a_stranger_cannot_see_your_stock_history(auth_client, other_client, sample_products):
    product = sample_products[0]
    auth_client.post(
        f"/stock/{product.id}",
        data={"direction": "increase", "amount": "3", "reason": "restock", "note": "secret"},
    )

    assert "secret" not in html(other_client.get(f"/stock/{product.id}"))


# --------------------------------------------------------------------- #
# Data-changing actions are POSTs                                       #
# --------------------------------------------------------------------- #


def test_mutations_reject_get(auth_client, sample_products, category):
    product = sample_products[0]

    # /stock/<id> is a view page (its POST is the mutation); these endpoints
    # have no GET representation at all.
    for path in (
        f"/delete/{product.id}",
        f"/categories/{category.id}/delete",
        "/auth/logout",
    ):
        assert auth_client.get(path).status_code == 405, path

    # An incomplete adjustment POST re-renders the form with inline errors
    # and leaves the stock untouched.
    response = auth_client.post(f"/stock/{product.id}", data={})

    assert response.status_code == 200
    assert "This field is required." in html(response)
    assert db.session.get(Product, product.id).quantity == 5


# --------------------------------------------------------------------- #
# Sessions and cookies                                                  #
# --------------------------------------------------------------------- #


def test_session_cookies_are_hardened(app):
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["REMEMBER_COOKIE_HTTPONLY"] is True
    assert app.config["REMEMBER_COOKIE_SAMESITE"] == "Lax"
    assert app.config["PERMANENT_SESSION_LIFETIME"].total_seconds() == 12 * 3600


def test_production_cookies_require_https():
    assert ProductionConfig.SESSION_COOKIE_SECURE is True


def test_forms_reject_oversized_bodies(app):
    assert app.config["MAX_CONTENT_LENGTH"] == 1024 * 1024


def test_login_costs_the_same_when_it_fails():
    assert ProductionConfig.LOGIN_RATE_LIMIT_SECONDS > 0


def test_passwords_are_never_echoed_back(client):
    raw = "Top-Secret-Passphrase"
    response = client.post(
        "/auth/register",
        data={
            "display_name": "Secretive",
            "email": "secret@example.com",
            "password": raw,
            "password_confirm": raw,
        },
        follow_redirects=True,
    )

    assert raw not in html(response)


def test_deactivated_accounts_cannot_sign_in(app, client, user):
    account = db.session.get(User, user.id)
    account.is_active = False
    db.session.commit()

    response = login(client, user.email)

    assert response.status_code == 200
    assert "deactivated" in html(response)
    assert client.get("/dashboard/").status_code == 302


# --------------------------------------------------------------------- #
# Open-redirect protection                                              #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example/",
        "//evil.example",
        "/\\evil.example",
        "javascript:alert(1)",
    ],
)
def test_login_refuses_off_site_next_targets(client, user, target):
    response = client.post(
        f"/auth/login?next={target}",
        data={"email": user.email, "password": PASSWORD},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard/")


def test_login_honours_a_local_next_target(client, user):
    response = client.post(
        "/auth/login?next=/reports/",
        data={"email": user.email, "password": PASSWORD},
    )

    assert response.headers["Location"].endswith("/reports/")
