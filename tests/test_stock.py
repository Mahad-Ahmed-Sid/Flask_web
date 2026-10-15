"""Stock adjustments, guards and the audit trail."""

from conftest import html

from product.extensions import db
from product.models import Product, StockAdjustment


def adjust(client, product_id, **overrides):
    """Submit the stock form; ``overrides`` replace single fields."""
    data = {
        "product_id": str(product_id),
        "direction": "increase",
        "amount": "1",
        "reason": "restock",
        "note": "",
    }
    data.update(overrides)
    return client.post(f"/stock/{product_id}", data=data)


def adjustments_for(product_id):
    return db.session.scalars(
        db.select(StockAdjustment)
        .where(StockAdjustment.product_id == product_id)
        .order_by(StockAdjustment.id)
    ).all()


# --------------------------------------------------------------------- #
# The stock page                                                        #
# --------------------------------------------------------------------- #


def test_stock_page_shows_the_product(auth_client, sample_products):
    response = auth_client.get(f"/stock/{sample_products[0].id}")

    assert response.status_code == 200
    body = html(response)
    assert "Alpha Widget" in body
    assert "Stock history" in body
    assert "Alerts at or below 10" in body


def test_stock_page_of_an_unknown_product_is_404(auth_client):
    assert auth_client.get("/stock/9999").status_code == 404


def test_stock_page_lists_history_latest_first(auth_client, sample_products):
    product = sample_products[0]
    adjust(auth_client, product.id, amount="1")
    adjust(auth_client, product.id, amount="2")

    body = html(auth_client.get(f"/stock/{product.id}"))

    assert "+1" in body and "+2" in body
    assert body.index("+2") < body.index("+1")


# --------------------------------------------------------------------- #
# Increasing and decreasing                                             #
# --------------------------------------------------------------------- #


def test_increasing_stock_persists_and_records_audited_row(auth_client, sample_products, app):
    product = sample_products[0]  # 5 units

    response = adjust(auth_client, product.id, amount="3", reason="restock", note="from supplier")

    assert response.status_code == 302  # Post/Redirect/Get

    with app.app_context():
        saved = db.session.get(Product, product.id)
        assert saved.quantity == 8
        assert saved.last_stock_change is not None

        entry = adjustments_for(product.id)[0]
        assert entry.delta == 3
        assert entry.quantity_after == 8
        assert entry.reason == "restock"
        assert entry.note == "from supplier"
        assert entry.user_id == saved.owner_id


def test_decreasing_stock_persists_and_records_a_negative_delta(auth_client, sample_products, app):
    product = sample_products[0]  # 5 units

    adjust(auth_client, product.id, direction="decrease", amount="2", reason="sale")

    with app.app_context():
        assert db.session.get(Product, product.id).quantity == 3
        entry = adjustments_for(product.id)[0]
        assert entry.delta == -2
        assert entry.quantity_after == 3


def test_adjustment_can_empty_the_stock_but_not_go_below(auth_client, sample_products, app):
    product = sample_products[0]  # 5 units

    adjust(auth_client, product.id, direction="decrease", amount="5", reason="sale")

    with app.app_context():
        assert db.session.get(Product, product.id).quantity == 0


def test_adjustment_rejects_a_negative_result(auth_client, sample_products, app):
    product = sample_products[0]  # 5 units

    response = adjust(auth_client, product.id, direction="decrease", amount="999", reason="sale")

    assert response.status_code == 200
    assert "would leave a negative quantity" in html(response)

    with app.app_context():
        assert db.session.get(Product, product.id).quantity == 5
        assert adjustments_for(product.id) == []


def test_adjustment_rejects_zero(auth_client, sample_products, app):
    product = sample_products[0]

    response = adjust(auth_client, product.id, amount="0")

    assert response.status_code == 200
    assert "1 or more" in html(response)
    with app.app_context():
        assert adjustments_for(product.id) == []


def test_adjustment_rejects_a_negative_amount(auth_client, sample_products, app):
    product = sample_products[0]

    response = adjust(auth_client, product.id, amount="-4")

    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(Product, product.id).quantity == 5
        assert adjustments_for(product.id) == []


def test_adjustment_rejects_a_non_numeric_amount(auth_client, sample_products, app):
    product = sample_products[0]

    response = adjust(auth_client, product.id, amount="lots")

    assert response.status_code == 200
    with app.app_context():
        assert adjustments_for(product.id) == []


def test_adjustment_requires_a_reason(auth_client, sample_products, app):
    product = sample_products[0]

    response = adjust(auth_client, product.id, reason="")

    assert response.status_code == 200
    assert "Choose a reason." in html(response)
    with app.app_context():
        assert adjustments_for(product.id) == []


def test_adjustment_note_is_optional(auth_client, sample_products, app):
    product = sample_products[0]

    adjust(auth_client, product.id, amount="1", note="")

    with app.app_context():
        assert adjustments_for(product.id)[0].note is None


# --------------------------------------------------------------------- #
# Stock status rules                                                    #
# --------------------------------------------------------------------- #


def test_zero_is_out_of_stock(auth_client, sample_products):
    body = html(auth_client.get("/"))

    assert "Out of stock" in body  # Beta Gadget has 0


def test_at_the_threshold_is_low_stock(auth_client, app, user):
    product = Product(
        product_name="Exactly At Limit",
        price="1.00",
        owner=user,
        quantity=10,
        low_stock_threshold=10,
    )
    db.session.add(product)
    db.session.commit()

    body = html(auth_client.get("/"))

    assert "Low stock" in body
    assert "Exactly At Limit" in body


def test_above_the_threshold_is_in_stock(auth_client, app, user):
    product = Product(
        product_name="Comfortably Above",
        price="1.00",
        owner=user,
        quantity=11,
        low_stock_threshold=10,
    )
    db.session.add(product)
    db.session.commit()

    body = html(auth_client.get("/"))

    assert "In stock" in body
    assert "Comfortably Above" in body


def test_each_product_may_have_its_own_threshold(auth_client, app, user):
    strict = Product(
        product_name="Strict Alert", price="1.00", owner=user, quantity=3, low_stock_threshold=3
    )
    relaxed = Product(
        product_name="Relaxed Alert", price="1.00", owner=user, quantity=3, low_stock_threshold=0
    )
    db.session.add_all([strict, relaxed])
    db.session.commit()

    body = html(auth_client.get("/"))

    assert "Low stock" in body  # strict is at its limit

    # The relaxed one is at 3 with a threshold of 0, so it counts as in stock.
    in_stock = html(auth_client.get("/?stock=in"))
    assert "Relaxed Alert" in in_stock
    assert "Strict Alert" not in in_stock


# --------------------------------------------------------------------- #
# Keeping the audit trail honest                                        #
# --------------------------------------------------------------------- #


def test_editing_the_quantity_records_a_correction(auth_client, sample_products, app):
    product = sample_products[0]  # 5 units

    auth_client.post(
        f"/edit/{product.id}",
        data={
            "product_name": product.product_name,
            "price": "10.00",
            "quantity": "42",
            "low_stock_threshold": "10",
        },
    )

    with app.app_context():
        saved = db.session.get(Product, product.id)
        assert saved.quantity == 42

        entry = adjustments_for(product.id)[0]
        assert entry.delta == 37
        assert entry.quantity_after == 42
        assert entry.reason == "correction"


def test_deleting_a_product_removes_its_audit_trail(auth_client, sample_products, app):
    product = sample_products[0]
    adjust(auth_client, product.id, amount="2")

    auth_client.post(f"/delete/{product.id}")

    with app.app_context():
        assert db.session.get(Product, product.id) is None
        assert adjustments_for(product.id) == []
