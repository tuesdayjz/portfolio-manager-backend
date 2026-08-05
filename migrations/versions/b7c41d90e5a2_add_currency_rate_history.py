"""add currency_rate_history

`currency` の全通貨について、USD 建て日次終値レートを保存するテーブルを追加する。
`close_price` は 1 通貨単位あたりの USD 額で、Yahoo Finance の `<CUR>USD=X` と
同じ向き。USD 自身は常に 1 なので行を持たなくてよい。

Revision ID: b7c41d90e5a2
Revises: 9c7d5e2a1b4f
Create Date: 2026-08-05 11:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c41d90e5a2'
down_revision = '9c7d5e2a1b4f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'currency_rate_history',
        sa.Column(
            'id',
            sa.Uuid(),
            server_default=sa.text('(gen_random_uuid())'),
            nullable=False,
        ),
        sa.Column('currency_id', sa.Uuid(), nullable=False),
        sa.Column('rate_date', sa.Date(), nullable=False),
        sa.Column('close_price', sa.Numeric(), nullable=False),
        sa.ForeignKeyConstraint(
            ['currency_id'],
            ['currency.id'],
            ondelete='CASCADE',
            name='currency_rate_history_currency_id_fkey',
        ),
        sa.PrimaryKeyConstraint('id', name='currency_rate_history_pkey'),
        sa.UniqueConstraint(
            'currency_id',
            'rate_date',
            name='currency_rate_history_currency_id_rate_date_key',
        ),
    )
    # 直近レートの参照が主用途なので asset_data_history と同じく降順で張る。
    op.create_index(
        'currency_rate_history_currency_id_rate_date_idx',
        'currency_rate_history',
        ['currency_id', sa.text('rate_date DESC')],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'currency_rate_history_currency_id_rate_date_idx',
        table_name='currency_rate_history',
    )
    op.drop_table('currency_rate_history')
