"""Data models for the inventory application.

``Product`` rows belong to exactly one :class:`User`; every query in the app
filters on that ownership so one account can never read or modify another
account's stock.
"""

from datetime import UTC, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

# Reasons recorded against a stock adjustment, in the order they appear in
# the UI. Stored as plain text so the table stays readable if this list ever
# changes.
STOCK_REASONS = (
    ("restock", "Restock"),
    ("sale", "Sale"),
    ("damaged", "Damaged / written off"),
    ("correction", "Stock correction"),
    ("other", "Other"),
)
STOCK_REASON_LABELS = dict(STOCK_REASONS)


def _utcnow() -> datetime:
    """Naive UTC timestamp — SQLite stores no timezone information."""
    return datetime.now(tz=UTC).replace(tzinfo=None)


class User(UserMixin, db.Model):
    """An account that owns an inventory."""

    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    display_name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    date_created = db.Column(db.DateTime, nullable=False, default=_utcnow)

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email!r}>"

    def set_password(self, raw_password: str) -> None:
        """Hash with Werkzeug's default (scrypt) — the plaintext is discarded."""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    @property
    def product_count(self) -> int:
        return (
            db.session.scalar(
                db.select(db.func.count()).select_from(Product).where(Product.owner_id == self.id)
            )
            or 0
        )


class Category(db.Model):
    """A user-defined category. Names are unique per account."""

    __tablename__ = "category"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    date_created = db.Column(db.DateTime, nullable=False, default=_utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "name", name="uq_category_user_name"),)

    owner = db.relationship("User", backref=db.backref("categories", lazy="dynamic"))

    def __repr__(self) -> str:
        return f"<Category {self.id} {self.name!r} user={self.user_id}>"

    @property
    def product_count(self) -> int:
        return (
            db.session.scalar(
                db.select(db.func.count())
                .select_from(Product)
                .where(Product.category_id == self.id)
            )
            or 0
        )


class Product(db.Model):
    """A single product in the inventory."""

    __tablename__ = "product"

    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(100), nullable=False, index=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    product_description = db.Column(db.String(200), nullable=True)
    date_created = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)

    # --- ownership --------------------------------------------------------
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    # --- stock ------------------------------------------------------------
    quantity = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    low_stock_threshold = db.Column(db.Integer, nullable=False, default=10, server_default="10")
    last_stock_change = db.Column(db.DateTime, nullable=True)

    # --- categorisation ---------------------------------------------------
    category_id = db.Column(
        db.Integer, db.ForeignKey("category.id", ondelete="SET NULL"), nullable=True
    )

    owner = db.relationship("User", backref=db.backref("products", lazy="dynamic"))
    category = db.relationship("Category", backref=db.backref("products", lazy="dynamic"))

    def __repr__(self) -> str:
        return f"<Product {self.id} {self.product_name!r} qty={self.quantity}>"

    # --- derived values ---------------------------------------------------
    @property
    def display_description(self) -> str:
        """Description trimmed for table cells, or a placeholder if empty."""
        text = (self.product_description or "").strip()
        return text or "—"

    @property
    def stock_status(self) -> str:
        """``out`` (0), ``low`` (at or below threshold) or ``in``."""
        if self.quantity <= 0:
            return "out"
        if self.quantity <= self.low_stock_threshold:
            return "low"
        return "in"

    @property
    def is_low_stock(self) -> bool:
        """Out-of-stock items are the most urgent kind of low stock."""
        return self.stock_status in {"out", "low"}

    @property
    def total_value(self):
        """``price × quantity`` as a Decimal, safe to format as currency."""
        return (self.price or 0) * (self.quantity or 0)

    @property
    def category_name(self) -> str:
        return self.category.name if self.category else "—"


class StockAdjustment(db.Model):
    """Immutable audit record of a stock change."""

    __tablename__ = "stock_adjustment"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    delta = db.Column(db.Integer, nullable=False)
    quantity_after = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(60), nullable=False)
    note = db.Column(db.String(120), nullable=True)
    date_created = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)

    product = db.relationship("Product", backref=db.backref("adjustments", lazy="dynamic"))
    user = db.relationship("User", backref=db.backref("adjustments", lazy="dynamic"))

    def __repr__(self) -> str:
        return (
            f"<StockAdjustment {self.id} product={self.product_id} "
            f"{self.delta:+d} -> {self.quantity_after}>"
        )

    @property
    def display_reason(self) -> str:
        return STOCK_REASON_LABELS.get(self.reason, self.reason)
