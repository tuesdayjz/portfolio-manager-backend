"""保有残高モデル。ポートフォリオ × 銘柄で 1 行。"""

import datetime
import decimal
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.asset import AssetMaster
    from app.models.portfolio import Portfolio
    from app.models.transaction import Transactions


class Holdings(db.Model):
    __tablename__ = "holdings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["asset_id"],
            ["asset_master.id"],
            ondelete="RESTRICT",
            name="holdings_asset_id_fkey",
        ),
        ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolio.id"],
            ondelete="CASCADE",
            name="holdings_portfolio_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="holdings_pkey"),
        UniqueConstraint(
            "portfolio_id", "asset_id", name="holdings_portfolio_id_asset_id_key"
        ),
        Index("holdings_asset_id_idx", "asset_id"),
        Index("holdings_portfolio_id_idx", "portfolio_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    quantity: Mapped[decimal.Decimal] = mapped_column(
        Numeric, nullable=False, server_default=text("0")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )
    average_cost: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric)

    asset: Mapped["AssetMaster"] = relationship(
        "AssetMaster", back_populates="holdings"
    )
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio", back_populates="holdings"
    )
    transactions: Mapped[list["Transactions"]] = relationship(
        "Transactions", back_populates="holding"
    )
