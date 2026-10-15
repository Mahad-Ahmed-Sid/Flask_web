"""add users, categories and stock tracking

Revision ID: 6ed874c53b58
Revises: fa4522522c2a
Create Date: 2026-10-15 19:49:44.832520

This is the migration that turns the single-user app into a multi-user one.
Besides the schema it also moves the data forward:

* creates the ``user``, ``category`` and ``stock_adjustment`` tables,
* seeds one development account (``admin@inventory.local``) so the products
  that already exist have an owner, and
* assigns every existing product to that account, leaving their IDs and all
  other values untouched.

SQLite cannot add a NOT NULL column to a populated table, so the product
changes run as batch operations (a copy-and-swap rebuild of the table).  New
columns therefore carry a ``server_default`` while the rows are copied.

Downgrading restores the original ``product`` table (same rows, same IDs) and
drops the user/category/audit tables.  Account data cannot survive the
downgrade — that data only exists in these new tables — which is the part
that is not reversible; the schema and the product data are.
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from werkzeug.security import generate_password_hash

# revision identifiers, used by Alembic.
revision = '6ed874c53b58'
down_revision = 'fa4522522c2a'
branch_labels = None
depends_on = None


def _seed_admin_user():
    """Create the development admin account and return its id.

    Imported lazily so this module can still be imported by tooling that only
    reads the migration files.  The password is a documented development
    default, not a secret — the README explains how to change it with
    ``flask set-password``.
    """
    from product.seed import ADMIN_DEV_PASSWORD, ADMIN_DISPLAY_NAME, ADMIN_EMAIL

    user_table = sa.table(
        'user',
        sa.column('id', sa.Integer),
        sa.column('email', sa.String),
        sa.column('display_name', sa.String),
        sa.column('password_hash', sa.String),
        sa.column('is_active', sa.Boolean),
        sa.column('date_created', sa.DateTime),
    )

    op.bulk_insert(
        user_table,
        [
            {
                'id': 1,
                'email': ADMIN_EMAIL,
                'display_name': ADMIN_DISPLAY_NAME,
                'password_hash': generate_password_hash(ADMIN_DEV_PASSWORD),
                'is_active': True,
                'date_created': datetime.now(tz=UTC).replace(tzinfo=None),
            }
        ],
    )

    # Re-read the id instead of assuming 1: an id from an earlier
    # upgrade/downgrade cycle may already have been used.
    return sa.select(user_table.c.id).where(user_table.c.email == ADMIN_EMAIL)


def upgrade():
    # 1. Accounts, so that the products below have somewhere to point.
    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('date_created', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_email'), ['email'], unique=True)

    admin_id_select = _seed_admin_user()

    # 2. Categories, so demo products can belong to one.
    op.create_table(
        'category',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date_created', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='uq_category_user_name'),
    )
    with op.batch_alter_table('category', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_category_user_id'), ['user_id'], unique=False
        )

    # 3. Stock audit trail.
    op.create_table(
        'stock_adjustment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('delta', sa.Integer(), nullable=False),
        sa.Column('quantity_after', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=60), nullable=False),
        sa.Column('note', sa.String(length=120), nullable=True),
        sa.Column('date_created', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['product.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('stock_adjustment', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_stock_adjustment_date_created'), ['date_created'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_stock_adjustment_product_id'), ['product_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_stock_adjustment_user_id'), ['user_id'], unique=False
        )

    # 4. Products gain ownership, stock and a category.
    #
    # owner_id is added with a server_default pointing at the admin account,
    # so the batch rebuild copies every existing row with that owner.  The
    # app then keeps it up to date.
    admin_id = op.get_bind().execute(admin_id_select).scalar_one()

    with op.batch_alter_table('product', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('owner_id', sa.Integer(), server_default=str(admin_id), nullable=False)
        )
        batch_op.add_column(
            sa.Column('quantity', sa.Integer(), server_default='0', nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                'low_stock_threshold', sa.Integer(), server_default='10', nullable=False
            )
        )
        batch_op.add_column(sa.Column('last_stock_change', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('category_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_product_owner_id'), ['owner_id'], unique=False)
        # Named constraints keep the downgrade deterministic.
        batch_op.create_foreign_key(
            'fk_product_owner_id', 'user', ['owner_id'], ['id']
        )
        batch_op.create_foreign_key(
            'fk_product_category_id',
            'category',
            ['category_id'],
            ['id'],
            ondelete='SET NULL',
        )

    # 5. Demo categories, so the dashboard has something to show on a fresh
    #    install.  Product ids (1, 2, 3) are matched by name for robustness.
    now = datetime.now(tz=UTC).replace(tzinfo=None)
    category_table = sa.table(
        'category',
        sa.column('id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('user_id', sa.Integer),
        sa.column('date_created', sa.DateTime),
    )
    op.bulk_insert(
        category_table,
        [
            {'id': 1, 'name': 'Beverages', 'user_id': admin_id, 'date_created': now},
            {'id': 2, 'name': 'Snacks', 'user_id': admin_id, 'date_created': now},
        ],
    )
    # One table construct, reused for the WHERE clause: building a second one
    # inside .where() would make SQLAlchemy add a second FROM element and
    # render an "UPDATE ... FROM product" statement.
    product_table = sa.table(
        'product',
        sa.column('category_id', sa.Integer),
        sa.column('product_name', sa.String),
    )
    demo_assignments = {
        'shehzan juice': 1,
        'juice': 1,
        'chocolate biscuit': 2,
    }
    for product_name, category_id in demo_assignments.items():
        op.execute(
            sa.update(product_table)
            .where(sa.func.lower(product_table.c.product_name) == product_name)
            .values(category_id=category_id)
        )


def downgrade():
    # Product rows keep their original values: dropping these columns
    # restores the 3-row, 5-column table exactly as it was before.
    with op.batch_alter_table('product', schema=None) as batch_op:
        batch_op.drop_constraint('fk_product_category_id', type_='foreignkey')
        batch_op.drop_constraint('fk_product_owner_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_product_owner_id'))
        batch_op.drop_column('category_id')
        batch_op.drop_column('last_stock_change')
        batch_op.drop_column('low_stock_threshold')
        batch_op.drop_column('quantity')
        batch_op.drop_column('owner_id')

    with op.batch_alter_table('stock_adjustment', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stock_adjustment_user_id'))
        batch_op.drop_index(batch_op.f('ix_stock_adjustment_product_id'))
        batch_op.drop_index(batch_op.f('ix_stock_adjustment_date_created'))

    op.drop_table('stock_adjustment')

    with op.batch_alter_table('category', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_category_user_id'))

    op.drop_table('category')

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_email'))

    op.drop_table('user')
