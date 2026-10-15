"""Shared pytest fixtures.

Every test gets a brand-new in-memory database, so the suite never touches
``instance/products.db``.

Two accounts are available so that data-isolation behaviour can be tested:

* ``user`` / ``auth_client`` – the owner of the sample products
* ``other_user`` / ``other_client`` – a stranger with their own account
"""

from decimal import Decimal

import pytest

from product import create_app
from product.extensions import db
from product.models import Category, Product, User

PASSWORD = "correct-horse-battery"


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


def login(client, email: str, password: str = PASSWORD):
    """Sign *client* in through the real login form."""
    return client.post("/auth/login", data={"email": email, "password": password})


@pytest.fixture()
def user(app):
    """The account the sample products belong to."""
    account = User(email="owner@example.com", display_name="Owner", is_active=True)
    account.set_password(PASSWORD)
    db.session.add(account)
    db.session.commit()
    return account


@pytest.fixture()
def other_user(app):
    """A second account, used to prove data stays private."""
    account = User(email="stranger@example.com", display_name="Stranger", is_active=True)
    account.set_password(PASSWORD)
    db.session.add(account)
    db.session.commit()
    return account


@pytest.fixture()
def auth_client(app, client, user):
    """A client signed in as the owner of the sample products."""
    response = login(client, user.email)
    assert response.status_code == 302, "fixture user could not sign in"
    return client


@pytest.fixture()
def other_client(app, other_user):
    """A separate client signed in as the second account.

    It gets its own test client on purpose: sharing one would overwrite the
    session cookie and quietly defeat the isolation tests.
    """
    client = app.test_client()
    response = login(client, other_user.email)
    assert response.status_code == 302, "fixture user could not sign in"
    return client


@pytest.fixture()
def category(app, user):
    """A category owned by :func:`user`."""
    category = Category(name="Widgets", user_id=user.id)
    db.session.add(category)
    db.session.commit()
    return category


@pytest.fixture()
def sample_products(app, user):
    """Three products with deliberately different names, prices and stock.

    Alpha is low, Beta is out and Gamma is comfortably in stock, so the
    status badges and the low-stock report have something to work with.
    """
    products = [
        Product(
            product_name="Alpha Widget",
            price=Decimal("10.00"),
            product_description="The first product",
            owner=user,
            quantity=5,
            low_stock_threshold=10,
        ),
        Product(
            product_name="Beta Gadget",
            price=Decimal("5.50"),
            product_description="The second product",
            owner=user,
            quantity=0,
            low_stock_threshold=10,
        ),
        Product(
            product_name="Gamma Gizmo",
            price=Decimal("20.00"),
            product_description=None,
            owner=user,
            quantity=50,
            low_stock_threshold=5,
        ),
    ]
    db.session.add_all(products)
    db.session.commit()
    return products


@pytest.fixture()
def many_products(app, user):
    """More rows than fit on one page (PRODUCTS_PER_PAGE is 10)."""
    products = [
        Product(
            product_name=f"Bulk item {n:02d}",
            price=Decimal(n),
            product_description=f"Bulk row {n}",
            owner=user,
        )
        for n in range(1, 16)
    ]
    db.session.add_all(products)
    db.session.commit()
    return products


def html(response) -> str:
    """Decoded response body."""
    return response.get_data(as_text=True)
