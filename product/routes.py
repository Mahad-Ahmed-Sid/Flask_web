"""Product CRUD routes.

The list endpoint also implements the three listing features:

* ``?q=``      – case-insensitive search over name and description
* ``?sort=``   – sort by an allow-listed column, ``?dir=asc|desc``
* ``?page=``   – pagination, combined freely with search and sort
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from .extensions import db
from .forms import ProductForm
from .models import Product

bp = Blueprint("product", __name__)

# Query-string values are never used as SQL identifiers: they are mapped
# through this allow-list to real columns instead.
SORT_COLUMNS = {
    "id": Product.id,
    "product_name": Product.product_name,
    "price": Product.price,
    "date_created": Product.date_created,
}
DIRECTIONS = {"asc", "desc"}
DEFAULT_SORT = "date_created"
DEFAULT_DIRECTION = "desc"


def _list_params() -> tuple[str, str, str, int]:
    """Read and sanitise ``q``, ``sort``, ``dir`` and ``page``."""
    query = (request.args.get("q") or "").strip()

    sort = request.args.get("sort", DEFAULT_SORT)
    if sort not in SORT_COLUMNS:
        sort = DEFAULT_SORT

    direction = request.args.get("dir", DEFAULT_DIRECTION)
    if direction not in DIRECTIONS:
        direction = DEFAULT_DIRECTION

    page = request.args.get("page", 1, type=int) or 1
    if page < 1:
        page = 1

    return query, sort, direction, page


def _escape_like(value: str) -> str:
    """Escape ``%``, ``_`` and ``\\`` so they are matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _base_query(query: str) -> sa.Select:
    """SELECT statement filtered by the search term (if any)."""
    statement = db.select(Product)
    if query:
        pattern = f"%{_escape_like(query)}%"
        statement = statement.where(
            sa.or_(
                Product.product_name.ilike(pattern, escape="\\"),
                Product.product_description.ilike(pattern, escape="\\"),
            )
        )
    return statement


@bp.route("/", methods=["GET", "POST"])
def index():
    form = ProductForm()

    # Post/Redirect/Get: without this, refreshing the page would create a
    # duplicate row on every reload.
    if form.validate_on_submit():
        product = Product(
            product_name=form.product_name.data.strip(),
            price=form.price.data,
            product_description=(form.product_description.data or "").strip() or None,
        )
        db.session.add(product)
        db.session.commit()
        flash(f"“{product.product_name}” was added.", "success")
        return redirect(url_for("product.index"))

    query, sort, direction, page = _list_params()
    statement = _base_query(query).order_by(
        SORT_COLUMNS[sort].asc() if direction == "asc" else SORT_COLUMNS[sort].desc()
    )

    pagination = db.paginate(
        statement,
        page=page,
        per_page=current_app.config["PRODUCTS_PER_PAGE"],
        error_out=False,
    )

    # ?page=999 on a 3-page list: send the user to the last real page.
    if pagination.pages and pagination.page > pagination.pages:
        return redirect(
            url_for(
                "product.index",
                q=query,
                sort=sort,
                dir=direction,
                page=pagination.pages,
            )
        )

    total_products = db.session.scalar(db.select(db.func.count()).select_from(Product))

    return render_template(
        "index.html",
        form=form,
        products=pagination.items,
        pagination=pagination,
        q=query,
        sort=sort,
        direction=direction,
        total_products=total_products or 0,
    )


@bp.route("/edit/<int:product_id>", methods=["GET", "POST"])
def edit(product_id: int):
    product = db.get_or_404(Product, product_id)
    form = ProductForm.prefill(product)

    if form.validate_on_submit():
        product.product_name = form.product_name.data.strip()
        product.price = form.price.data
        product.product_description = (form.product_description.data or "").strip() or None
        db.session.commit()
        flash(f"“{product.product_name}” was updated.", "success")
        return redirect(url_for("product.index"))

    return render_template("edit.html", form=form, product=product)


@bp.post("/delete/<int:product_id>")
def delete(product_id: int):
    """DELETE is a POST: a plain link would be triggerable by any crawler."""
    product = db.get_or_404(Product, product_id)
    name = product.product_name
    db.session.delete(product)
    db.session.commit()
    flash(f"“{name}” was deleted.", "danger")
    return redirect(url_for("product.index"))


@bp.app_context_processor
def inject_globals():
    """Values every template needs: the active search term and the year."""
    return {
        "current_query": (request.args.get("q") or "").strip(),
        "now_year": datetime.now(tz=UTC).year,
    }
