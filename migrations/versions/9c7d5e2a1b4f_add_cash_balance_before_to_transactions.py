"""add cash balance before to transactions

Revision ID: 9c7d5e2a1b4f
Revises: 0cbc8209c234
Create Date: 2026-08-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c7d5e2a1b4f'
down_revision = '0cbc8209c234'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cash_balance_before', sa.Numeric(), nullable=True))


def downgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_column('cash_balance_before')
