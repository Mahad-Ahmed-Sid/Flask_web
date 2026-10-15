"""Registration, sign-in, sign-out and account management."""

import time

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from .extensions import db, login_manager
from .forms import ChangePasswordForm, LoginForm, ProfileForm, RegistrationForm, find_user_by_email
from .models import Category, Product, User
from .seed import find_admin

bp = Blueprint("auth", __name__, url_prefix="/auth")


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    """Rebuild the session's user on every request."""
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def adopt_legacy_products(new_user: User) -> int:
    """Hand the seeded admin's products to the very first registered account.

    The migration that introduces accounts has to give the pre-existing
    products an owner, so it uses the admin account.  This lets the person who
    actually runs the app take that stock over just by signing up — and only
    ever for the *first* account, so a second registration can never inherit
    somebody's inventory.
    """
    admin = find_admin()
    if admin is None or admin.id == new_user.id:
        return 0

    other_accounts = db.session.scalar(
        db.select(db.func.count())
        .select_from(User)
        .where(User.id != admin.id, User.id != new_user.id)
    )
    if other_accounts:
        return 0  # not the first account — leave the admin's stock alone

    products = db.session.scalars(db.select(Product).where(Product.owner_id == admin.id)).all()
    for product in products:
        product.owner_id = new_user.id

    # Bring the categories those products use with them, otherwise the new
    # owner would be shown category names that belong to somebody else's
    # account (and could never manage them).
    used_ids = {p.category_id for p in products if p.category_id is not None}
    if used_ids:
        categories = db.session.scalars(
            db.select(Category).where(Category.id.in_(used_ids), Category.user_id == admin.id)
        ).all()
        for category in categories:
            existing = db.session.scalar(
                db.select(Category).where(
                    Category.user_id == new_user.id,
                    Category.name.ilike(category.name),
                )
            )
            if existing is not None:
                # Merge into the new owner's same-named category.
                db.session.execute(
                    db.update(Product)
                    .where(Product.category_id == category.id)
                    .values(category_id=existing.id)
                )
                db.session.delete(category)
            else:
                category.user_id = new_user.id

    return len(products)


def _safe_next_url() -> str:
    """Where to send the user after signing in.

    Only same-site relative paths are honoured, so ``?next=https://evil.example``
    cannot turn the login form into an open redirect.
    """
    target = (request.args.get("next") or "").strip()
    if target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("dashboard.index")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            email=form.email.data.strip().lower(),
            display_name=form.display_name.data.strip(),
            is_active=True,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()  # so the adoption step can see the new user id
        adopted = adopt_legacy_products(user)
        db.session.commit()

        login_user(user)
        flash(f"Welcome, {user.display_name} — your inventory is ready.", "success")
        if adopted:
            flash(
                f"{adopted} product{'' if adopted == 1 else 's'} from the demo "
                "account were moved into your inventory.",
                "info",
            )
        return redirect(url_for("dashboard.index"))

    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        # A failed login should cost roughly the same as a successful one.
        time.sleep(current_app.config["LOGIN_RATE_LIMIT_SECONDS"])

        user = find_user_by_email(form.email.data)
        if user is None or not user.check_password(form.password.data):
            # Deliberately vague: never reveal whether the email exists.
            flash("Invalid email or password.", "danger")
        elif not user.is_active:
            flash("This account has been deactivated.", "warning")
        else:
            login_user(user, remember=form.remember.data)
            flash(f"Welcome back, {user.display_name}.", "success")
            return redirect(_safe_next_url())

    return render_template("auth/login.html", form=form)


@bp.post("/logout")
def logout():
    """POST-only: a GET link would let any page sign your users out."""
    if current_user.is_authenticated:
        logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(
        display_name=current_user.display_name,
        email=current_user.email,
    )
    if form.validate_on_submit():
        current_user.display_name = form.display_name.data.strip()
        current_user.email = form.email.data.strip().lower()
        db.session.commit()
        flash("Your profile was updated.", "success")
        return redirect(url_for("auth.profile"))

    category_count = (
        db.session.scalar(
            db.select(db.func.count())
            .select_from(Category)
            .where(Category.user_id == current_user.id)
        )
        or 0
    )

    return render_template("auth/profile.html", form=form, category_count=category_count)


@bp.route("/profile/password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        current_user.set_password(form.new_password.data)
        db.session.commit()
        flash("Your password was changed.", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/change_password.html", form=form)
