"""The dashboard: at-a-glance numbers for the signed-in account."""

from conftest import html

from product.extensions import db
from product.models import Category, Product


def test_dashboard_requires_sign_in(client):
    response = client.get("/dashboard/")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_dashboard_greets_the_user(auth_client, user):
    body = html(auth_client.get("/dashboard/"))

    assert "Dashboard" in body
    assert f"Welcome back, {user.display_name}" in body


def test_dashboard_totals(auth_client, sample_products):
    """3 products, 55 units, $1,050.00 — with low/out counts beside them."""
    body = html(auth_client.get("/dashboard/"))

    assert 'stat-value">3<' in body  # products
    assert "$1,050.00" in body  # inventory value
    assert "55 unit(s) on hand" in body  # units on hand
    assert 'stat-value">2<' in body  # needs attention (Alpha + Beta)
    assert 'stat-value">1<' in body  # out of stock (Beta)


def test_dashboard_lists_recently_added(auth_client, sample_products):
    body = html(auth_client.get("/dashboard/"))

    assert "Recently added" in body
    for product in sample_products:
        assert product.product_name in body


def test_dashboard_restock_list_links_to_the_stock_page(auth_client, sample_products):
    body = html(auth_client.get("/dashboard/"))
    # "Recently added" links every product too, so scope to the restock card.
    restock_card = body.split("Restock soon", 1)[1]

    assert "Restock soon" in body
    assert f"/stock/{sample_products[0].id}" in restock_card  # Alpha: low
    assert f"/stock/{sample_products[1].id}" in restock_card  # Beta: empty
    assert f"/stock/{sample_products[2].id}" not in restock_card  # Gamma: fine


def test_dashboard_bar_chart_has_a_row_per_category(auth_client, sample_products, category):
    other = Category(name="Gadgets", user_id=sample_products[0].owner_id)
    db.session.add(other)
    db.session.flush()
    sample_products[0].category_id = category.id
    sample_products[2].category_id = other.id
    db.session.commit()

    body = html(auth_client.get("/dashboard/"))

    assert "Stock by category" in body
    assert body.count("bar-row") >= 3  # Widgets, Gadgets, Uncategorised
    assert "Widgets" in body
    assert "Gadgets" in body
    assert "Uncategorised" in body  # Beta Gadget has no category


def test_dashboard_empty_inventory(auth_client):
    body = html(auth_client.get("/dashboard/"))

    assert "Your inventory is empty" in body


def test_dashboard_sees_only_the_owner_products(auth_client, other_client, sample_products):
    body = html(other_client.get("/dashboard/"))

    assert "Alpha Widget" not in body
    assert "Your inventory is empty" in body


def test_sidebar_counts_the_products_that_need_restocking(auth_client, sample_products):
    body = html(auth_client.get("/dashboard/"))

    assert "app-nav-badge" in body  # Alpha + Beta = 2


def test_sidebar_has_no_badge_when_everything_is_stocked(auth_client, app, user):
    product = Product(
        product_name="Plenty Stocked",
        price="2.00",
        owner=user,
        quantity=50,
        low_stock_threshold=5,
    )
    db.session.add(product)
    db.session.commit()

    assert "app-nav-badge" not in html(auth_client.get("/dashboard/"))


def test_chart_groups_uncategorised_products_when_no_category_exists(auth_client, sample_products):
    body = html(auth_client.get("/dashboard/"))

    assert "Stock by category" in body
    assert "bar-row" in body
    assert "Uncategorised" in body  # the chart degrades gracefully
