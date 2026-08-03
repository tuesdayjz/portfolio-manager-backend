"""取引履歴モデル。保有残高に紐づく売買の記録。"""

import datetime
import decimal
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.holding import Holdings


class Transactions(db.Model):
    __tablename__ = "transactions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["holding_id"],
            ["holdings.id"],
            ondelete="CASCADE",
            name="transactions_holding_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="transactions_pkey"),
        Index("transactions_holding_id_idx", "holding_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    holding_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    trade_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    quantity: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    price: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    fees: Mapped[decimal.Decimal] = mapped_column(
        Numeric, nullable=False, server_default=text("0")
    )
    average_cost_before_sale: Mapped[decimal.Decimal | None] = mapped_column(Numeric)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text("now()")
    )
    transaction_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''::text")
    )

    holding: Mapped["Holdings"] = relationship(
        "Holdings", back_populates="transactions"
    )
