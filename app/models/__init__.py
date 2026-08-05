"""SQLAlchemy モデル。

`flask db migrate` は `db.metadata` に登録済みのモデルしか見ないので、
新しいモデルを追加したらこのモジュールで import すること。

テーブル定義は Supabase 上の既存スキーマから sqlacodegen で起こしたもの。
以下 2 点だけ生成結果から変えてある。

- ログイン情報を持つ `auth.users` は Supabase Auth の管理対象なのでモデル化しない。
  アプリ側のユーザー行は `public.users` を写した `Users` だけ。
- スキーマ修飾（`schema="public"`）は付けない。Postgres 側は search_path の
  既定が public なので不要で、付けると Alembic の autogenerate が
  リフレクション結果（スキーマ無し）と別テーブル扱いして差分を出すため。

`server_default` は DB から起こしたままなので `gen_random_uuid()` や
`'...'::text` を含む。これらは Postgres 専用で、SQLite に `create_all()` は通らない。
"""

from app.models.asset import (
    AssetDataHistory,
    AssetMaster,
    AssetType,
    Currency,
    CurrencyRateHistory,
)
from app.models.holding import Holdings
from app.models.portfolio import Portfolio
from app.models.transaction import Transactions
from app.models.user import Users

__all__ = [
    "AssetDataHistory",
    "AssetMaster",
    "AssetType",
    "Currency",
    "CurrencyRateHistory",
    "Holdings",
    "Portfolio",
    "Transactions",
    "Users",
]
