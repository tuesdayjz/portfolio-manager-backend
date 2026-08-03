"""sync portfolio table with Supabase (drop portfolio.name)

初期リビジョン 2fb34ddaba88 は Supabase の当時のスキーマを写したものだが、その後
実 DB 側で `portfolio.name` が削除され、マイグレーションだけが取り残されていた。
モデル `app.models.portfolio.Portfolio` にも既に name は無い。この revision で
マイグレーションから作った DB を実 DB に合わせる。

実 DB（Supabase）には既に name が無いので upgrade は何もしない。まっさらな DB を
2fb34ddaba88 から積み上げた場合だけ実際に列が落ちる。どちらでも流せるように
DROP COLUMN IF EXISTS を使う。downgrade も同じ理由で ADD COLUMN IF NOT EXISTS。

Revision ID: 33bc04cf8fea
Revises: 2fb34ddaba88
Create Date: 2026-08-03 17:52:52.934710

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '33bc04cf8fea'
down_revision = '2fb34ddaba88'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE portfolio DROP COLUMN IF EXISTS name')


def downgrade():
    op.execute(
        "ALTER TABLE portfolio ADD COLUMN IF NOT EXISTS name text "
        "NOT NULL DEFAULT 'Default Portfolio'::text"
    )
