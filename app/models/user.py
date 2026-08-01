"""ユーザーモデル（public.users）。

ログイン情報そのもの（auth.users）は Supabase Auth が持つ。ここはアプリ側の
プロフィール行で、主キー id が auth.users.id と 1:1 に対応する。auth スキーマは
Supabase の管理下にありアプリのマイグレーション対象ではないので、
DB 上の外部キー users_id_fkey (id -> auth.users.id ON DELETE CASCADE) は
モデルには宣言していない。
"""

import datetime
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.portfolio import Portfolio


class Users(db.Model):
    __tablename__ = "users"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="users_pkey"),
        UniqueConstraint("email", name="users_email_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )
    name: Mapped[Optional[str]] = mapped_column(String)
    # 認証は Supabase Auth 側で完結するため、この列はアプリからは使わない。
    password: Mapped[Optional[str]] = mapped_column(Text)

    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio", uselist=False, back_populates="user"
    )
