"""Category management for the signed-in user."""

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from .extensions import db
from .forms import CategoryForm
from .models import Category, Product
from .queries import get_owned_or_404

bp = Blueprint("categories", __name__, url_prefix="/categories")


def owned_categories():
    """The signed-in user's categories, alphabetically."""
    return db.session.scalars(
        db.select(Category).where(Category.user_id == current_user.id).order_by(Category.name)
    ).all()


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    form = CategoryForm()

    if form.validate_on_submit():
        category = Category(name=form.name.data.strip(), user_id=current_user.id)
        db.session.add(category)
        db.session.commit()
        flash(f"Category “{category.name}” was created.", "success")
        return redirect(url_for("categories.index"))

    return render_template("categories.html", form=form, categories=owned_categories())


@bp.post("/<int:category_id>/delete")
@login_required
def delete(category_id: int):
    """Delete a category; its products become uncategorised, never lost."""
    category = get_owned_or_404(Category, category_id, current_user.id, owner_column="user_id")

    db.session.execute(
        db.update(Product).where(Product.category_id == category.id).values(category_id=None)
    )
    db.session.delete(category)
    db.session.commit()

    flash(
        f"Category “{category.name}” was deleted. Its products are now uncategorised.",
        "warning",
    )
    return redirect(url_for("categories.index"))
