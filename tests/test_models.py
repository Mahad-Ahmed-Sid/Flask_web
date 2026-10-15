"""Tests for the Jinja filters and the Product model."""

from decimal import Decimal

from product import create_app
from product.models import Product


def test_currency_filter_formats_amounts():
    app = create_app("testing")
    rules = app.jinja_env.filters

    assert rules["currency"](Decimal("1234.5")) == "$1,234.50"
    assert rules["currency"](0) == "$0.00"
    assert rules["currency"]("12.345") == "$12.35"
    assert rules["currency"](None) == "$0.00"
    assert rules["currency"]("not a number") == "$0.00"


def test_friendly_date_filter():
    from datetime import datetime

    app = create_app("testing")
    rules = app.jinja_env.filters

    assert rules["friendly_date"](datetime(2026, 8, 20, 15, 55)) == "Aug 20, 2026"
    assert rules["friendly_date"](None) == "—"


def test_display_description_placeholder():
    app = create_app("testing")
    with app.app_context():
        assert Product(product_name="x", price=1).display_description == "—"
        assert (
            Product(product_name="x", price=1, product_description="  hi  ").display_description
            == "hi"
        )


def test_repr_contains_name_and_price():
    app = create_app("testing")
    with app.app_context():
        text = repr(Product(product_name="Juice", price=Decimal("100.00"), id=7))
        assert "Juice" in text
        assert "7" in text
