"""ポートフォリオモデル。ユーザーごとに 1 件。"""

import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.holding import Holdings
    from app.models.user import Users


class Portfolio(db.Model):
    __tablename__ = "portfolio"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="portfolio_user_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="portfolio_pkey"),
        UniqueConstraint("user_id", name="portfolio_user_id_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, nullable=False, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )

    user: Mapped["Users"] = relationship("Users", back_populates="portfolio")
    holdings: Mapped[list["Holdings"]] = relationship(
        "Holdings", back_populates="portfolio"
    )
