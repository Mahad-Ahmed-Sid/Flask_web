"""Shared pytest fixtures.

Every test gets a brand-new in-memory database, so the suite never touches
``instance/products.db``.
"""

from decimal import Decimal

import pytest

from product import create_app
from product.extensions import db
from product.models import Product


@pytest.fixture()
def app():
    app = create_app("testing")

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def sample_products(app):
    """Three products with deliberately different names and prices."""
    products = [
        Product(
            product_name="Alpha Widget",
            price=Decimal("10.00"),
            product_description="The first product",
        ),
        Product(
            product_name="Beta Gadget",
            price=Decimal("5.50"),
            product_description="The second product",
        ),
        Product(
            product_name="Gamma Gizmo",
            price=Decimal("20.00"),
            product_description=None,
        ),
    ]
    db.session.add_all(products)
    db.session.commit()
    return products


@pytest.fixture()
def many_products(app):
    """More rows than fit on one page (PRODUCTS_PER_PAGE is 10)."""
    products = [
        Product(
            product_name=f"Bulk item {n:02d}",
            price=Decimal(n),
            product_description=f"Bulk row {n}",
        )
        for n in range(1, 16)
    ]
    db.session.add_all(products)
    db.session.commit()
    return products


def html(response) -> str:
    """Decoded response body."""
    return response.get_data(as_text=True)
