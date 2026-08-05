"""add position to transactions

Revision ID: 7a1f2c9b3d4e
Revises: 9c7d5e2a1b4f
Create Date: 2026-08-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7a1f2c9b3d4e'
down_revision = '9c7d5e2a1b4f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'position',
                sa.Text(),
                nullable=False,
                server_default=sa.text("'long'"),
            )
        )


def downgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_column('position')
