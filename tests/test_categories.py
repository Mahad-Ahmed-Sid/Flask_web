"""Categories: creation, uniqueness, deletion and the list filters."""

from conftest import html

from product.extensions import db
from product.models import Category, Product

# --------------------------------------------------------------------- #
# Managing categories                                                    #
# --------------------------------------------------------------------- #


def test_categories_page_renders(auth_client, category):
    response = auth_client.get("/categories/")

    assert response.status_code == 200
    assert "Widgets" in html(response)


def test_create_category(auth_client, app, user):
    response = auth_client.post("/categories/", data={"name": "Beverages"}, follow_redirects=True)

    assert response.status_code == 200
    assert "Beverages" in html(response)
    assert "was created" in html(response)

    with app.app_context():
        saved = db.session.scalar(db.select(Category).where(Category.name == "Beverages"))
        assert saved is not None
        assert saved.user_id == user.id


def test_duplicate_category_name_is_rejected(auth_client, category):
    response = auth_client.post("/categories/", data={"name": "widgets"})

    assert response.status_code == 200
    assert "already have a category" in html(response)


def test_category_name_is_required(auth_client, app):
    response = auth_client.post("/categories/", data={"name": "   "})

    assert response.status_code == 200
    assert "Category name is required." in html(response)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Category)) == 0


def test_category_name_may_not_exceed_50_characters(auth_client, app):
    response = auth_client.post("/categories/", data={"name": "x" * 51})

    assert response.status_code == 200
    assert "Category name must be 1" in html(response)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Category)) == 0


def test_delete_is_post_only(auth_client, category):
    assert auth_client.get(f"/categories/{category.id}/delete").status_code == 405


def test_delete_keeps_the_products(auth_client, app, sample_products, category):
    """Deleting a label must never delete the stock it was attached to."""
    product = sample_products[0]
    product.category_id = category.id
    db.session.commit()

    response = auth_client.post(f"/categories/{category.id}/delete", follow_redirects=True)

    assert response.status_code == 200
    assert "now uncategorised" in html(response)

    with app.app_context():
        assert db.session.get(Category, category.id) is None
        saved = db.session.get(Product, product.id)
        assert saved is not None
        assert saved.category_id is None


def test_deleting_an_unknown_category_is_404(auth_client):
    assert auth_client.post("/categories/9999/delete").status_code == 404


def test_a_stranger_cannot_delete_someone_elses_category(other_client, category):
    assert other_client.post(f"/categories/{category.id}/delete").status_code == 404


# --------------------------------------------------------------------- #
# Privacy                                                               #
# --------------------------------------------------------------------- #


def test_categories_are_private_to_their_owner(auth_client, other_client, category):
    assert "Widgets" in html(auth_client.get("/categories/"))
    assert "Widgets" not in html(other_client.get("/categories/"))


def test_the_product_form_only_offers_your_own_categories(auth_client, other_client, category):
    body = html(auth_client.get("/"))
    stranger_body = html(other_client.get("/"))

    assert ">Widgets<" in body
    assert "Widgets" not in stranger_body


# --------------------------------------------------------------------- #
# Filtering the inventory                                               #
# --------------------------------------------------------------------- #


def test_filter_by_category(auth_client, app, sample_products, category):
    sample_products[0].category_id = category.id
    db.session.commit()

    body = html(auth_client.get(f"/?category={category.id}"))

    assert "Alpha Widget" in body
    assert "Beta Gadget" not in body
    assert "Gamma Gizmo" not in body


def test_filter_by_uncategorised(auth_client, app, sample_products, category):
    sample_products[0].category_id = category.id
    db.session.commit()

    body = html(auth_client.get("/?category=none"))

    assert "Alpha Widget" not in body
    assert "Beta Gadget" in body
    assert "Gamma Gizmo" in body


def test_filter_by_an_unknown_category_matches_nothing(auth_client, sample_products):
    response = auth_client.get("/?category=999999")

    assert response.status_code == 200
    assert "No products match" in html(response)


def test_category_filter_survives_sorting(auth_client, app, sample_products, category):
    sample_products[0].category_id = category.id
    db.session.commit()

    body = html(auth_client.get(f"/?category={category.id}&sort=price&dir=asc"))

    assert "Alpha Widget" in body
    assert "Beta Gadget" not in body


def test_stock_filter_in(auth_client, sample_products):
    body = html(auth_client.get("/?stock=in"))

    assert "Gamma Gizmo" in body
    assert "Alpha Widget" not in body
    assert "Beta Gadget" not in body


def test_stock_filter_out(auth_client, sample_products):
    body = html(auth_client.get("/?stock=out"))

    assert "Beta Gadget" in body
    assert "Alpha Widget" not in body


def test_stock_filter_low_includes_the_empty_shelves(auth_client, sample_products):
    """ "Needs attention" covers out-of-stock rows as well as low ones."""
    body = html(auth_client.get("/?stock=low"))

    assert "Alpha Widget" in body
    assert "Beta Gadget" in body
    assert "Gamma Gizmo" not in body


def test_unknown_stock_filter_is_ignored(auth_client, sample_products):
    response = auth_client.get("/?stock=banana")

    assert response.status_code == 200
    assert "Alpha Widget" in html(response)  # fell back to "all"


def test_filter_state_is_visible_in_the_page(auth_client, sample_products):
    body = html(auth_client.get("/?q=widget&stock=in"))

    assert "Clear filters" in body
    assert 'value="widget"' in body  # the hidden search field kept the term
