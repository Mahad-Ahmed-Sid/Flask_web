"""Dashboard: the at-a-glance health of the signed-in user's inventory."""

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from .extensions import db
from .models import Product
from .queries import inventory_stats

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

# The restock list is a nudge, not a report: ten rows is plenty.
RESTOCK_LIMIT = 10


@bp.get("/")
@login_required
def index():
    owner_id = current_user.id

    low_stock = db.session.scalars(
        db.select(Product)
        .where(
            Product.owner_id == owner_id,
            Product.quantity <= Product.low_stock_threshold,
        )
        .order_by(Product.quantity.asc(), Product.product_name.asc())
        .limit(RESTOCK_LIMIT)
    ).all()

    return render_template(
        "dashboard.html",
        stats=inventory_stats(owner_id),
        low_stock=low_stock,
    )
