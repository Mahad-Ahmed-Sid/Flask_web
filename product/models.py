"""Data models for the application."""

from datetime import UTC, datetime

from .extensions import db


def _utcnow() -> datetime:
    """Naive UTC timestamp — SQLite stores no timezone information."""
    return datetime.now(tz=UTC).replace(tzinfo=None)


class Product(db.Model):
    """A single product in the inventory."""

    __tablename__ = "product"

    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(100), nullable=False, index=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    product_description = db.Column(db.String(200), nullable=True)
    date_created = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)

    def __repr__(self) -> str:
        return f"<Product {self.id} {self.product_name!r} {self.price}>"

    @property
    def display_description(self) -> str:
        """Description trimmed for table cells, or a placeholder if empty."""
        text = (self.product_description or "").strip()
        return text or "—"
