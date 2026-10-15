"""End-to-end route tests for the product CRUD API.

The app is multi-user now, so the tests that exercise the inventory use
``auth_client`` (a signed-in client); the anonymous ``client`` is kept for
the pages and error paths that must work signed out.
"""

import re
from decimal import Decimal

from conftest import html

from product.extensions import db
from product.models import Product

# Product names as they appear, in order, down the inventory table.
ROW_NAME = re.compile(r'<div class="fw-semibold">([^<]+)</div>')


def names_in(response):
    """Product names in the order they appear in the rendered table."""
    return ROW_NAME.findall(html(response))


def count_rows(response) -> int:
    return len(names_in(response))


# --------------------------------------------------------------------- #
# Reading                                                               #
# --------------------------------------------------------------------- #


def test_homepage_renders(auth_client, sample_products):
    response = auth_client.get("/")

    assert response.status_code == 200
    assert b"Inventory" in response.data
    assert count_rows(response) == 3
    assert "Alpha Widget" in html(response)
    assert "$5.50" in html(response)


def test_homepage_empty_state(auth_client):
    response = auth_client.get("/")

    assert response.status_code == 200
    assert "No products yet" in html(response)


def test_missing_page_returns_styled_404(client):
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert "Page not found" in html(response)


def test_edit_of_unknown_product_returns_404(auth_client):
    assert auth_client.get("/edit/9999").status_code == 404


# --------------------------------------------------------------------- #
# Creating                                                              #
# --------------------------------------------------------------------- #


def test_create_product_redirects_instead_of_rendering(auth_client, app):
    """Post/Redirect/Get: a refresh must not create a second row."""
    response = auth_client.post(
        "/",
        data={
            "product_name": "New thing",
            "price": "3.25",
            "product_description": "shiny",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Product)) == 1


def test_create_shows_flash_message(auth_client):
    response = auth_client.post(
        "/",
        data={"product_name": "Juice box", "price": "1.00"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Juice box" in html(response)
    assert "was added" in html(response)


def test_create_requires_a_name(auth_client, app):
    response = auth_client.post(
        "/",
        data={"product_name": "", "price": "4.00"},
    )

    assert response.status_code == 200
    assert "Product name is required." in html(response)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Product)) == 0


def test_create_rejects_negative_price(auth_client, app):
    response = auth_client.post("/", data={"product_name": "Bad", "price": "-0.01"})

    assert response.status_code == 200
    assert "Price must be between" in html(response)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Product)) == 0


def test_create_rejects_non_numeric_price(auth_client, app):
    response = auth_client.post("/", data={"product_name": "Bad", "price": "free"})

    assert response.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Product)) == 0


def test_create_missing_price_field_is_rejected(auth_client, app):
    response = auth_client.post("/", data={"product_name": "No price"})

    assert response.status_code == 200
    assert "Price is required." in html(response)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Product)) == 0


def test_price_of_zero_is_allowed(auth_client, app):
    response = auth_client.post(
        "/",
        data={"product_name": "Free sample", "price": "0"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        product = db.session.scalar(db.select(Product))
        assert product is not None
        assert Decimal(product.price) == Decimal("0")


def test_description_is_optional(auth_client):
    response = auth_client.post(
        "/",
        data={"product_name": "No description", "price": "9.99"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "—" in html(response)  # placeholder instead of a blank cell


def test_oversized_description_is_rejected(auth_client, app):
    response = auth_client.post(
        "/",
        data={"product_name": "Long one", "price": "1.00", "product_description": "x" * 201},
    )

    assert response.status_code == 200
    assert "200 characters or fewer" in html(response)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Product)) == 0


# --------------------------------------------------------------------- #
# Editing                                                               #
# --------------------------------------------------------------------- #


def test_edit_form_is_prefilled(auth_client, sample_products):
    product = sample_products[1]
    response = auth_client.get(f"/edit/{product.id}")

    assert response.status_code == 200
    body = html(response)
    assert 'value="Beta Gadget"' in body
    assert 'value="5.50"' in body
    assert "The second product" in body


def test_edit_updates_the_product(auth_client, sample_products, app):
    product = sample_products[0]
    response = auth_client.post(
        f"/edit/{product.id}",
        data={
            "product_name": "Renamed Widget",
            "price": "11.50",
            "product_description": "updated",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Renamed Widget" in html(response)
    assert "was updated" in html(response)

    with app.app_context():
        saved = db.session.get(Product, product.id)
        assert saved.product_name == "Renamed Widget"
        assert Decimal(saved.price) == Decimal("11.50")
        assert saved.product_description == "updated"


def test_edit_keeps_row_count(auth_client, sample_products, app):
    product = sample_products[0]
    auth_client.post(
        f"/edit/{product.id}",
        data={"product_name": "Renamed", "price": "1.00"},
    )

    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Product)) == 3


def test_edit_validation_failure_keeps_other_rows(auth_client, sample_products, app):
    product = sample_products[0]
    response = auth_client.post(
        f"/edit/{product.id}",
        data={"product_name": "", "price": "-3"},
    )

    assert response.status_code == 200
    assert "Product name is required." in html(response)
    with app.app_context():
        saved = db.session.get(Product, product.id)
        assert saved.product_name == "Alpha Widget"  # unchanged


# --------------------------------------------------------------------- #
# Deleting                                                              #
# --------------------------------------------------------------------- #


def test_delete_requires_post(auth_client, sample_products):
    """A GET link could be followed by any crawler and wipe the table."""
    product = sample_products[0]
    assert auth_client.get(f"/delete/{product.id}").status_code == 405


def test_delete_removes_the_product(auth_client, sample_products, app):
    product = sample_products[0]
    response = auth_client.post(f"/delete/{product.id}", follow_redirects=True)

    assert response.status_code == 200
    assert "was deleted" in html(response)
    assert "Alpha Widget" not in names_in(response)

    with app.app_context():
        assert db.session.get(Product, product.id) is None


def test_delete_unknown_product_returns_404(auth_client):
    assert auth_client.post("/delete/9999").status_code == 404


def test_delete_button_is_a_post_form(auth_client, sample_products):
    body = html(auth_client.get("/"))

    assert 'method="post"' in body
    assert 'name="csrf_token"' in body  # token rendered for every delete form


# --------------------------------------------------------------------- #
# Search                                                                #
# --------------------------------------------------------------------- #


def test_search_matches_product_name(auth_client, sample_products):
    response = auth_client.get("/?q=alpha")

    assert response.status_code == 200
    assert names_in(response) == ["Alpha Widget"]


def test_search_is_case_insensitive(auth_client, sample_products):
    assert names_in(auth_client.get("/?q=ALPHA")) == ["Alpha Widget"]
    assert names_in(auth_client.get("/?q=alpha")) == ["Alpha Widget"]


def test_search_matches_description(auth_client, sample_products):
    assert names_in(auth_client.get("/?q=second product")) == ["Beta Gadget"]


def test_search_with_no_results_shows_empty_state(auth_client, sample_products):
    response = auth_client.get("/?q=zzzz-nothing")

    assert response.status_code == 200
    body = html(response)
    assert "No products match" in body
    assert count_rows(response) == 0


def test_search_survives_sql_wildcards(auth_client, sample_products):
    """A literal ``%`` or ``_`` must not act as a wildcard."""
    for term in ("%", "_", "%25", "%5F"):
        response = auth_client.get(f"/?q={term}")

        assert response.status_code == 200, term
        assert count_rows(response) == 0, f"{term!r} matched every row"


def test_search_box_keeps_the_query(auth_client, sample_products):
    body = html(auth_client.get("/?q=alpha"))

    assert 'name="q"' in body
    assert 'value="alpha"' in body
    assert "Clear search" in body


# --------------------------------------------------------------------- #
# Sorting                                                               #
# --------------------------------------------------------------------- #


def test_sort_by_price_ascending(auth_client, sample_products):
    response = auth_client.get("/?sort=price&dir=asc")

    assert response.status_code == 200
    assert names_in(response) == ["Beta Gadget", "Alpha Widget", "Gamma Gizmo"]


def test_sort_by_price_descending(auth_client, sample_products):
    assert names_in(auth_client.get("/?sort=price&dir=desc")) == [
        "Gamma Gizmo",
        "Alpha Widget",
        "Beta Gadget",
    ]


def test_sort_by_name(auth_client, sample_products):
    assert names_in(auth_client.get("/?sort=product_name&dir=asc")) == [
        "Alpha Widget",
        "Beta Gadget",
        "Gamma Gizmo",
    ]


def test_unknown_sort_column_falls_back_to_default(auth_client, sample_products):
    response = auth_client.get("/?sort=price; DROP TABLE product&dir=asc")

    assert response.status_code == 200
    assert count_rows(response) == 3  # no injection, still sorted safely


def test_unknown_direction_falls_back_to_default(auth_client, sample_products):
    assert auth_client.get("/?dir=sideways").status_code == 200


def test_sort_survives_search(auth_client, sample_products):
    response = auth_client.get("/?q=product&sort=price&dir=asc")

    assert response.status_code == 200
    assert names_in(response) == ["Beta Gadget", "Alpha Widget"]


# --------------------------------------------------------------------- #
# Pagination                                                            #
# --------------------------------------------------------------------- #


def test_first_page_holds_ten_rows(auth_client, many_products):
    response = auth_client.get("/")

    assert response.status_code == 200
    assert count_rows(response) == 10
    assert "of 15" in html(response)


def test_second_page_holds_the_rest(auth_client, many_products):
    response = auth_client.get("/?page=2")

    assert response.status_code == 200
    assert count_rows(response) == 5
    assert "Showing 11" in html(response)


def test_page_out_of_range_redirects_to_last_page(auth_client, many_products):
    response = auth_client.get("/?page=99")

    assert response.status_code == 302
    follow = auth_client.get(response.headers["Location"])
    assert count_rows(follow) == 5


def test_negative_page_is_clamped(auth_client, many_products):
    assert auth_client.get("/?page=-3").status_code == 200


def test_pagination_is_kept_while_sorting(auth_client, many_products):
    response = auth_client.get("/?sort=price&dir=asc&page=2")

    assert response.status_code == 200
    assert count_rows(response) == 5
    assert "sort=price" in html(response)


def test_pagination_disappears_for_single_page(auth_client, sample_products):
    assert "pagination" not in html(auth_client.get("/"))


# --------------------------------------------------------------------- #
# Security                                                              #
# --------------------------------------------------------------------- #


def test_forms_carry_a_csrf_token(app, auth_client, sample_products):
    """The add form, every delete form and sign-out must ship a token."""
    app.config["WTF_CSRF_ENABLED"] = True

    body = html(auth_client.get("/"))

    # one token for the add form + one per row's delete form + one for the
    # sidebar's sign-out form
    assert body.count('name="csrf_token"') == 2 + len(sample_products)


def test_post_without_csrf_token_is_rejected(app, auth_client):
    app.config["WTF_CSRF_ENABLED"] = True

    response = auth_client.post(
        "/",
        data={"product_name": "Sneaky", "price": "1.00"},
    )

    assert response.status_code == 400
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Product)) == 0
