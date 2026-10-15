"""Reports and CSV export — always scoped to the signed-in user."""

import csv
import io
from datetime import UTC, datetime

import sqlalchemy as sa
from flask import Blueprint, make_response, render_template
from flask_login import current_user, login_required

from .extensions import db
from .models import Product, StockAdjustment
from .queries import build_product_query, inventory_stats, parse_list_params

bp = Blueprint("reports", __name__, url_prefix="/reports")

CSV_HEADERS = [
    "id",
    "name",
    "category",
    "price",
    "quantity",
    "low_stock_threshold",
    "stock_status",
    "total_value",
    "description",
    "created",
]

STOCK_LABELS = {"out": "Out of stock", "low": "Low stock", "in": "In stock"}

# The valuation table shows the biggest lines; the CSV export carries
# everything.
VALUATION_LIMIT = 25


@bp.get("/")
@login_required
def index():
    params = parse_list_params()
    owner_id = current_user.id

    valuation = db.session.scalars(
        build_product_query(owner_id, {**params, "stock": "all"})
        # Clear the list's ordering, then rank by value instead.
        .order_by(None)
        .order_by(sa.desc(Product.price * Product.quantity), Product.product_name.asc())
        .limit(VALUATION_LIMIT)
    ).all()

    low_stock = db.session.scalars(
        build_product_query(owner_id, {**params, "stock": "low"}).order_by(
            sa.nullslast(Product.quantity.asc()), Product.product_name.asc()
        )
    ).all()

    adjustments = db.session.scalars(
        db.select(StockAdjustment)
        .where(StockAdjustment.user_id == owner_id)
        .order_by(StockAdjustment.date_created.desc(), StockAdjustment.id.desc())
        .limit(15)
    ).all()

    return render_template(
        "reports.html",
        stats=inventory_stats(owner_id),
        valuation=valuation,
        low_stock=low_stock,
        adjustments=adjustments,
        stock_labels=STOCK_LABELS,
        params=params,
    )


@bp.get("/export.csv")
@login_required
def export_csv():
    """Download the current user's products, honouring active filters.

    ``build_product_query`` applies the owner constraint, so no filter value
    — however it is crafted — can widen the export beyond this account.
    """
    params = parse_list_params()
    products = db.session.scalars(build_product_query(current_user.id, params)).all()

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADERS)
    for product in products:
        writer.writerow(
            [
                product.id,
                product.product_name,
                product.category_name if product.category else "",
                f"{product.price:.2f}",
                product.quantity,
                product.low_stock_threshold,
                STOCK_LABELS[product.stock_status],
                f"{product.total_value:.2f}",
                product.product_description or "",
                product.date_created.strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )

    stamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    # utf-8-sig so Excel opens the file without mangling non-ASCII names.
    body = "﻿" + buffer.getvalue()

    response = make_response(body)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f"attachment; filename=inventory-{stamp}.csv"
    response.headers["X-Export-Count"] = str(len(products))
    return response
