"""rename average cost before sale column

Revision ID: 0cbc8209c234
Revises: 03e5cde5c394
Create Date: 2026-08-03 20:45:58.310458

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0cbc8209c234'
down_revision = '03e5cde5c394'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'transactions',
        'average_cost_before_sale',
        new_column_name='average_cost_before',
        existing_type=sa.Numeric(),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        'transactions',
        'average_cost_before',
        new_column_name='average_cost_before_sale',
        existing_type=sa.Numeric(),
        existing_nullable=True,
    )
