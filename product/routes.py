"""Product CRUD and stock-adjustment routes (the "Inventory" section).

The list endpoint implements the listing features:

* ``?q=``       – case-insensitive search over name and description
* ``?sort=``    – sort by an allow-listed column, ``?dir=asc|desc``
* ``?category=``– filter by category id, ``none`` for uncategorised
* ``?stock=``   – filter by stock status (``in``/``low``/``out``/``all``)
* ``?page=``    – pagination, combined freely with the filters above

Every query is scoped to ``current_user.id`` via
:func:`product.queries.build_product_query`, so one account can never see
another account's stock.
"""

from datetime import UTC, datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from .extensions import db
from .forms import ProductForm, StockAdjustForm, category_choices
from .models import Product, StockAdjustment
from .queries import build_product_query, get_owned_or_404, parse_list_params

bp = Blueprint("product", __name__)


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    form = ProductForm()

    # Post/Redirect/Get: without this, refreshing the page would create a
    # duplicate row on every reload.
    if form.validate_on_submit():
        product = Product(
            product_name=form.product_name.data.strip(),
            price=form.price.data,
            product_description=(form.product_description.data or "").strip() or None,
            quantity=form.quantity.data if form.quantity.data is not None else 0,
            low_stock_threshold=(
                form.low_stock_threshold.data
                if form.low_stock_threshold.data is not None
                else current_app.config["LOW_STOCK_THRESHOLD"]
            ),
            category_id=form.category_id.data or None,
            owner_id=current_user.id,
        )
        db.session.add(product)
        db.session.commit()
        flash(f"“{product.product_name}” was added.", "success")
        return redirect(url_for("product.index"))

    params = parse_list_params()
    pagination = db.paginate(
        build_product_query(current_user.id, params),
        page=params["page"],
        per_page=current_app.config["PRODUCTS_PER_PAGE"],
        error_out=False,
    )

    # ?page=999 on a 3-page list: send the user to the last real page.
    if pagination.pages and pagination.page > pagination.pages:
        return redirect(
            url_for(
                "product.index",
                q=params["q"],
                sort=params["sort"],
                dir=params["direction"],
                category=params["category"],
                stock=params["stock"],
                page=pagination.pages,
            )
        )

    total_products = db.session.scalar(
        db.select(db.func.count()).select_from(Product).where(Product.owner_id == current_user.id)
    )

    # Filter dropdown options, prefixed with "All" and "Uncategorised".
    filter_categories = category_choices(current_user.id, include_all=True)
    filter_categories.insert(1, ("none", "Uncategorised"))

    return render_template(
        "index.html",
        form=form,
        products=pagination.items,
        pagination=pagination,
        params=params,
        category_options=filter_categories,
        total_products=total_products or 0,
    )


@bp.route("/edit/<int:product_id>", methods=["GET", "POST"])
@login_required
def edit(product_id: int):
    product = get_owned_or_404(Product, product_id, current_user.id)
    form = ProductForm.prefill(product)

    if form.validate_on_submit():
        product.product_name = form.product_name.data.strip()
        product.price = form.price.data
        product.product_description = (form.product_description.data or "").strip() or None
        product.low_stock_threshold = (
            form.low_stock_threshold.data
            if form.low_stock_threshold.data is not None
            else current_app.config["LOW_STOCK_THRESHOLD"]
        )
        product.category_id = form.category_id.data or None

        # A quantity typed here still leaves an audit row, so the history on
        # the Stock page never disagrees with the number shown in the list.
        new_quantity = form.quantity.data if form.quantity.data is not None else 0
        if new_quantity != product.quantity:
            delta = new_quantity - product.quantity
            product.quantity = new_quantity
            product.last_stock_change = datetime.now(tz=UTC).replace(tzinfo=None)
            db.session.add(
                StockAdjustment(
                    product_id=product.id,
                    user_id=current_user.id,
                    delta=delta,
                    quantity_after=new_quantity,
                    reason="correction",
                    note="Quantity edited on the product form",
                )
            )

        db.session.commit()
        flash(f"“{product.product_name}” was updated.", "success")
        return redirect(url_for("product.index"))

    return render_template("edit.html", form=form, product=product)


@bp.post("/delete/<int:product_id>")
@login_required
def delete(product_id: int):
    """DELETE is a POST: a plain link would be triggerable by any crawler."""
    product = get_owned_or_404(Product, product_id, current_user.id)
    name = product.product_name

    # The audit trail belongs to the product, so it goes with it.
    db.session.execute(db.delete(StockAdjustment).where(StockAdjustment.product_id == product.id))
    db.session.delete(product)
    db.session.commit()
    flash(f"“{name}” was deleted.", "danger")
    return redirect(url_for("product.index"))


@bp.route("/stock/<int:product_id>", methods=["GET", "POST"])
@login_required
def stock(product_id: int):
    """Increase or decrease stock, recording why, and show the history.

    The signed delta is computed from a positive amount plus a direction, and
    a guard refuses any adjustment that would take the quantity below zero.
    Valid adjustments redirect (Post/Redirect/Get); invalid ones re-render the
    form with the error next to the field.
    """
    product = get_owned_or_404(Product, product_id, current_user.id)
    form = StockAdjustForm()

    if form.validate_on_submit():
        amount = form.amount.data
        delta = amount if form.direction.data == "increase" else -amount
        resulting = product.quantity + delta

        if resulting < 0:
            # Checked on the server regardless of what the form allowed: the
            # browser may have been showing a stale quantity.
            form.amount.errors = (
                f"Only {product.quantity} unit(s) are in stock — that would "
                "leave a negative quantity.",
            )
        else:
            product.quantity = resulting
            product.last_stock_change = datetime.now(tz=UTC).replace(tzinfo=None)
            db.session.add(
                StockAdjustment(
                    product_id=product.id,
                    user_id=current_user.id,
                    delta=delta,
                    quantity_after=resulting,
                    reason=form.reason.data,
                    note=(form.note.data or "").strip() or None,
                )
            )
            db.session.commit()
            verb = "added to" if delta > 0 else "removed from"
            flash(
                f"{abs(delta)} unit(s) {verb} “{product.product_name}”. Now {resulting} in stock.",
                "success",
            )
            return redirect(url_for("product.stock", product_id=product.id))

    adjustments = db.session.scalars(
        db.select(StockAdjustment)
        .where(StockAdjustment.product_id == product.id)
        .order_by(StockAdjustment.date_created.desc(), StockAdjustment.id.desc())
        .limit(20)
    ).all()

    return render_template("stock.html", product=product, form=form, adjustments=adjustments)


@bp.app_context_processor
def inject_globals():
    """Values every template needs.

    ``low_stock_count`` drives the badge on the sidebar's Inventory link, so
    it is cheap to compute once per request and only for signed-in users.
    """
    low_stock_count = 0
    if current_user.is_authenticated:
        low_stock_count = (
            db.session.scalar(
                db.select(db.func.count())
                .select_from(Product)
                .where(
                    Product.owner_id == current_user.id,
                    Product.quantity <= Product.low_stock_threshold,
                )
            )
            or 0
        )

    return {
        "current_query": (request.args.get("q") or "").strip(),
        "now_year": datetime.now(tz=UTC).year,
        "low_stock_count": low_stock_count,
    }
