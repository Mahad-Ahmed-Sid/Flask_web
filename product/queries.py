"""Ownership-scoped lookups, list filtering and shared aggregates.

Every read of a :class:`~product.models.Product` in the app goes through this
module, so there is one place to audit for cross-account data leaks — the
owner constraint is applied inside :func:`build_product_query` and can never
be forgotten by a view.
"""

from typing import TypeVar

import sqlalchemy as sa
from flask import abort, current_app, request

from .extensions import db
from .models import Category, Product

ModelT = TypeVar("ModelT")

# A stranger must never learn whether an id exists on someone else's account,
# so cross-owner lookups answer 404 rather than 403.
NOT_FOUND = 404

# Query-string values are never used as SQL identifiers: they are mapped
# through this allow-list to real columns instead.
SORT_COLUMNS = {
    "id": Product.id,
    "product_name": Product.product_name,
    "price": Product.price,
    "quantity": Product.quantity,
    "date_created": Product.date_created,
}
DIRECTIONS = {"asc", "desc"}
DEFAULT_SORT = "date_created"
DEFAULT_DIRECTION = "desc"

STOCK_FILTERS = {"all", "in", "low", "out"}


def get_owned_or_404(
    model: type[ModelT], obj_id: int, owner_id: int, owner_column: str = "owner_id"
) -> ModelT:
    """Fetch one row of *model* owned by *owner_id*, or abort with 404.

    ``owner_column`` defaults to the products table's column; the categories
    table calls its foreign key ``user_id`` and passes that instead.
    """
    column = getattr(model, owner_column)
    obj = db.session.scalar(db.select(model).where(model.id == obj_id, column == owner_id))
    if obj is None:
        abort(NOT_FOUND)
    return obj


def escape_like(value: str) -> str:
    """Escape ``%``, ``_`` and ``\\`` so they are matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def parse_list_params() -> dict:
    """Read and sanitise the list query string.

    Recognised parameters: ``q`` (search), ``category`` (id, ``none`` or
    ``all``), ``stock`` (``in``/``low``/``out``/``all``), ``sort``, ``dir``
    and ``page``.  Unknown values fall back to safe defaults instead of
    raising, so a mangled URL still renders a page.
    """
    query = (request.args.get("q") or "").strip()

    sort = request.args.get("sort", DEFAULT_SORT)
    if sort not in SORT_COLUMNS:
        sort = DEFAULT_SORT

    direction = request.args.get("dir", DEFAULT_DIRECTION)
    if direction not in DIRECTIONS:
        direction = DEFAULT_DIRECTION

    stock = request.args.get("stock", "all")
    if stock not in STOCK_FILTERS:
        stock = "all"

    raw_category = (request.args.get("category") or "all").strip()
    category_id: int | None | str = "all"
    if raw_category == "none":
        category_id = None
    elif raw_category.isdigit():
        category_id = int(raw_category)

    page = request.args.get("page", 1, type=int) or 1
    if page < 1:
        page = 1

    return {
        "q": query,
        "sort": sort,
        "direction": direction,
        "stock": stock,
        "category": category_id,
        "page": page,
    }


def build_product_query(owner_id: int, params: dict) -> sa.Select:
    """Filtered + sorted SELECT for one owner's products.

    ``owner_id`` is always applied — filters narrow the result, they never
    widen it.
    """
    statement = db.select(Product).where(Product.owner_id == owner_id)

    if params["q"]:
        pattern = f"%{escape_like(params['q'])}%"
        statement = statement.where(
            sa.or_(
                Product.product_name.ilike(pattern, escape="\\"),
                Product.product_description.ilike(pattern, escape="\\"),
            )
        )

    stock = params["stock"]
    if stock == "out":
        statement = statement.where(Product.quantity <= 0)
    elif stock == "low":
        # "low" means "needs attention": out of stock, or at/below threshold.
        statement = statement.where(Product.quantity <= Product.low_stock_threshold)
    elif stock == "in":
        statement = statement.where(Product.quantity > Product.low_stock_threshold)

    category = params["category"]
    if category is None:
        statement = statement.where(Product.category_id.is_(None))
    elif category != "all":
        statement = statement.where(Product.category_id == category)

    column = SORT_COLUMNS[params["sort"]]
    return statement.order_by(column.asc() if params["direction"] == "asc" else column.desc())


def inventory_stats(owner_id: int) -> dict:
    """Aggregates for the dashboard and reports pages."""
    totals = db.session.execute(
        db.select(
            db.func.count(Product.id),
            db.func.coalesce(db.func.sum(Product.quantity), 0),
            db.func.coalesce(db.func.sum(Product.price * Product.quantity), 0),
        ).where(Product.owner_id == owner_id)
    ).one()
    product_count, units, value = totals

    low_stock_count = (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(Product)
            .where(Product.owner_id == owner_id, Product.quantity <= Product.low_stock_threshold)
        )
        or 0
    )

    out_of_stock_count = (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(Product)
            .where(Product.owner_id == owner_id, Product.quantity <= 0)
        )
        or 0
    )

    recent_products = db.session.scalars(
        db.select(Product)
        .where(Product.owner_id == owner_id)
        .order_by(Product.date_created.desc(), Product.id.desc())
        .limit(5)
    ).all()

    # Units and value per category; an outer join keeps uncategorised rows.
    category_rows = db.session.execute(
        db.select(
            Category.id,
            Category.name,
            db.func.count(Product.id),
            db.func.coalesce(db.func.sum(Product.quantity), 0),
            db.func.coalesce(db.func.sum(Product.price * Product.quantity), 0),
        )
        .outerjoin(Product, Product.category_id == Category.id)
        .where(Category.user_id == owner_id)
        .group_by(Category.id)
        .order_by(sa.func.lower(Category.name))
    ).all()

    uncategorised = db.session.execute(
        db.select(
            db.func.count(Product.id),
            db.func.coalesce(db.func.sum(Product.quantity), 0),
            db.func.coalesce(db.func.sum(Product.price * Product.quantity), 0),
        ).where(Product.owner_id == owner_id, Product.category_id.is_(None))
    ).one()

    bars = [
        {"name": name, "products": count, "units": units_, "value": val}
        for _cid, name, count, units_, val in category_rows
    ]
    if uncategorised[0]:
        bars.append(
            {
                "name": "Uncategorised",
                "products": uncategorised[0],
                "units": uncategorised[1],
                "value": uncategorised[2],
            }
        )

    return {
        "product_count": product_count or 0,
        "total_units": units or 0,
        "total_value": value or 0,
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "category_count": len(category_rows),
        "recent_products": recent_products,
        "category_bars": bars,
        "max_category_units": max((bar["units"] for bar in bars), default=0),
        "per_page": current_app.config["PRODUCTS_PER_PAGE"],
    }
