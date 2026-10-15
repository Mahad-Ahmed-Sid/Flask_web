"""WTForms used by the product routes.

Server-side validation replaces the old ``request.form[...]`` lookups, so a
missing or malformed field now renders an inline error message instead of
crashing with a 400/500.
"""

from flask_wtf import FlaskForm
from wtforms import DecimalField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange

from .models import Product


class ProductForm(FlaskForm):
    """Create / edit a :class:`~product.models.Product`."""

    product_name = StringField(
        "Product Name",
        validators=[
            DataRequired(message="Product name is required."),
            Length(
                min=1,
                max=100,
                message="Product name must be between 1 and 100 characters.",
            ),
        ],
    )
    # InputRequired (not DataRequired) so that a price of 0 is accepted.
    price = DecimalField(
        "Price",
        places=2,
        validators=[
            InputRequired(message="Price is required."),
            NumberRange(
                min=0,
                max=99999999.99,
                message="Price must be between 0 and 99,999,999.99.",
            ),
        ],
    )
    product_description = TextAreaField(
        "Product Description",
        validators=[
            Length(
                max=200,
                message="Description must be 200 characters or fewer.",
            )
        ],
    )
    submit = SubmitField("Save Product")

    @classmethod
    def prefill(cls, product: Product, **kwargs) -> "ProductForm":
        """Build a form pre-filled from an existing product row.

        Values submitted by the browser still win over these defaults, so a
        failed validation re-renders whatever the user typed.
        """
        return cls(
            product_name=product.product_name,
            price=product.price,
            product_description=product.product_description or "",
            **kwargs,
        )
