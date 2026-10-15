"""WTForms used across the application.

Server-side validation replaces ``request.form[...]`` lookups everywhere, so
a missing or malformed field renders an inline error message instead of
crashing with a 400/500.
"""

from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DecimalField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    ValidationError,
)

from .extensions import db
from .models import STOCK_REASONS, Category, Product, User

# ``Email()`` performs DNS deliverability lookups by default, which would make
# offline runs (and the test suite) depend on network access.
EMAIL_VALIDATORS = [DataRequired(message="Email is required."), Email(check_deliverability=False)]

PASSWORD_RULES = (
    DataRequired(message="Password is required."),
    Length(min=8, max=128, message="Password must be between 8 and 128 characters."),
)


def category_choices(user_id: int | None, include_all: bool = False) -> list[tuple]:
    """``(id, name)`` pairs for *user_id*, optionally prefixed with "All".

    The "uncategorised" entry uses ``"0"`` instead of an empty string: the
    field coerces to ``int``, and WTForms compares every choice against the
    current value while rendering — ``int("")`` would raise.  ``0`` is also
    what the views treat as "no category".
    """
    prefix = [("all", "All categories")] if include_all else [("0", "Uncategorised")]
    if not user_id:
        return prefix
    categories = db.session.scalars(
        db.select(Category).where(Category.user_id == user_id).order_by(Category.name)
    )
    return prefix + [(c.id, c.name) for c in categories]


# --------------------------------------------------------------------------- #
# Products & stock                                                            #
# --------------------------------------------------------------------------- #


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
    quantity = IntegerField(
        "Quantity in stock",
        validators=[
            Optional(),
            NumberRange(
                min=0,
                max=1_000_000,
                message="Quantity must be between 0 and 1,000,000.",
            ),
        ],
        default=0,
    )
    low_stock_threshold = IntegerField(
        "Alert me at or below",
        validators=[
            Optional(),
            NumberRange(
                min=0,
                max=1_000_000,
                message="Threshold must be between 0 and 1,000,000.",
            ),
        ],
        default=10,
    )
    category_id = SelectField("Category", coerce=int, validators=[Optional()], choices=[])
    submit = SubmitField("Save Product")

    def __init__(self, *args, categories: list[tuple] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.category_id.choices = (
            category_choices(current_user.id) if categories is None else categories
        )

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
            quantity=product.quantity,
            low_stock_threshold=product.low_stock_threshold,
            category_id=product.category_id or 0,
            **kwargs,
        )


class StockAdjustForm(FlaskForm):
    """Increase or decrease the stock of one product.

    The product comes from the URL, never from the form body, so there is no
    ``product_id`` field to tamper with — the view loads the row behind
    ``/stock/<id>`` and checks that the signed-in user owns it.
    """

    direction = SelectField(
        "Direction",
        choices=[("increase", "Increase stock"), ("decrease", "Decrease stock")],
        validators=[DataRequired()],
    )
    amount = IntegerField(
        "Quantity",
        validators=[
            InputRequired(message="Quantity is required."),
            NumberRange(min=1, max=1_000_000, message="Enter a whole number of 1 or more."),
        ],
    )
    reason = SelectField(
        "Reason",
        choices=list(STOCK_REASONS),
        validators=[DataRequired(message="Choose a reason.")],
    )
    note = StringField(
        "Note",
        validators=[Optional(), Length(max=120, message="Note must be 120 characters or fewer.")],
    )
    submit = SubmitField("Record adjustment")


class CategoryForm(FlaskForm):
    """Create a category for the current user."""

    name = StringField(
        "Category name",
        validators=[
            DataRequired(message="Category name is required."),
            Length(min=1, max=50, message="Category name must be 1–50 characters."),
        ],
    )
    submit = SubmitField("Add category")

    def validate_name(self, field):
        """Reject duplicates for this account only."""
        existing = db.session.scalar(
            db.select(Category).where(
                Category.user_id == current_user.id,
                Category.name.ilike(field.data.strip()),
            )
        )
        if existing is not None:
            raise ValidationError("You already have a category with that name.")


# --------------------------------------------------------------------------- #
# Accounts                                                                    #
# --------------------------------------------------------------------------- #


class RegistrationForm(FlaskForm):
    display_name = StringField(
        "Your name",
        validators=[
            DataRequired(message="Name is required."),
            Length(min=2, max=100, message="Name must be between 2 and 100 characters."),
        ],
    )
    email = StringField("Email", validators=[*EMAIL_VALIDATORS, Length(max=255)])
    password = PasswordField("Password", validators=list(PASSWORD_RULES))
    password_confirm = PasswordField(
        "Confirm password",
        validators=[
            DataRequired(message="Please confirm your password."),
            EqualTo("password", message="The two passwords do not match."),
        ],
    )
    submit = SubmitField("Create account")

    def validate_email(self, field):
        if find_user_by_email(field.data) is not None:
            raise ValidationError("An account with that email already exists.")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=EMAIL_VALIDATORS)
    password = PasswordField("Password", validators=[DataRequired(message="Password is required.")])
    remember = BooleanField("Keep me signed in")
    submit = SubmitField("Sign in")


class ProfileForm(FlaskForm):
    display_name = StringField(
        "Your name",
        validators=[
            DataRequired(message="Name is required."),
            Length(min=2, max=100, message="Name must be between 2 and 100 characters."),
        ],
    )
    email = StringField("Email", validators=[*EMAIL_VALIDATORS, Length(max=255)])
    submit = SubmitField("Save profile")

    def validate_email(self, field):
        """Unique per account — the current user's own email is allowed."""
        existing = find_user_by_email(field.data)
        if existing is not None and existing.id != current_user.id:
            raise ValidationError("Another account already uses that email.")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField(
        "Current password", validators=[DataRequired(message="Enter your current password.")]
    )
    new_password = PasswordField("New password", validators=list(PASSWORD_RULES))
    new_password_confirm = PasswordField(
        "Confirm new password",
        validators=[
            DataRequired(message="Please confirm the new password."),
            EqualTo("new_password", message="The two passwords do not match."),
        ],
    )
    submit = SubmitField("Change password")

    def validate_current_password(self, field):
        if not current_user.check_password(field.data):
            raise ValidationError("That is not your current password.")


def find_user_by_email(email: str) -> User | None:
    """Case-insensitive lookup used by the uniqueness validators."""
    return db.session.scalar(db.select(User).where(User.email == email.strip().lower()))
