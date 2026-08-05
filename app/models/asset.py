"""資産マスタ関連のモデル。

asset_type / currency / asset_master / asset_data_history / currency_rate_history。
"""

import datetime
import decimal
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Date,
    ForeignKeyConstraint,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.models.holding import Holdings


class AssetType(db.Model):
    """資産種別（株式・投資信託など）のマスタ。"""

    __tablename__ = "asset_type"
    __table_args__ = (PrimaryKeyConstraint("id", name="asset_type_pkey"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)

    asset_master: Mapped[list["AssetMaster"]] = relationship(
        "AssetMaster", back_populates="asset_type"
    )


class Currency(db.Model):
    """通貨マスタ。"""

    __tablename__ = "currency"
    __table_args__ = (PrimaryKeyConstraint("id", name="currency_pkey"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[Optional[str]] = mapped_column(Text)

    asset_master: Mapped[list["AssetMaster"]] = relationship(
        "AssetMaster", back_populates="currency"
    )
    rate_history: Mapped[list["CurrencyRateHistory"]] = relationship(
        "CurrencyRateHistory", back_populates="currency"
    )


class AssetMaster(db.Model):
    """銘柄マスタ。ユーザーに依存しない公開データ。"""

    __tablename__ = "asset_master"
    __table_args__ = (
        ForeignKeyConstraint(
            ["asset_type_id"], ["asset_type.id"], name="asset_master_asset_type_id_fkey"
        ),
        ForeignKeyConstraint(
            ["currency_id"], ["currency.id"], name="asset_master_currency_id_fkey"
        ),
        PrimaryKeyConstraint("id", name="asset_master_pkey"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(Text)
    asset_type_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, server_default=text("gen_random_uuid()")
    )
    currency_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, server_default=text("gen_random_uuid()")
    )

    # 資産クラスは旧 text column ではなく asset_type_id 経由で参照する。
    asset_type: Mapped[Optional["AssetType"]] = relationship(
        "AssetType", back_populates="asset_master"
    )
    currency: Mapped[Optional["Currency"]] = relationship(
        "Currency", back_populates="asset_master"
    )
    asset_data_history: Mapped[list["AssetDataHistory"]] = relationship(
        "AssetDataHistory", back_populates="asset"
    )
    holdings: Mapped[list["Holdings"]] = relationship(
        "Holdings", back_populates="asset"
    )


class AssetDataHistory(db.Model):
    """銘柄ごとの日次終値。"""

    __tablename__ = "asset_data_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["asset_id"],
            ["asset_master.id"],
            ondelete="CASCADE",
            name="asset_data_history_asset_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="asset_data_history_pkey"),
        UniqueConstraint(
            "asset_id", "price_date", name="asset_data_history_asset_id_price_date_key"
        ),
        # 実 DB は price_date が降順。sqlacodegen が DESC を落とすので手で足している。
        Index(
            "asset_data_history_asset_id_price_date_idx",
            "asset_id",
            text("price_date DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    price_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    close_price: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)

    asset: Mapped["AssetMaster"] = relationship(
        "AssetMaster", back_populates="asset_data_history"
    )


class CurrencyRateHistory(db.Model):
    """通貨ごとの USD 建て日次終値レート。

    `close_price` は 1 通貨単位あたりの USD 額（Yahoo Finance の `<CUR>USD=X`
    と同じ向き）。USD 自身も他通貨と同じ日付で 1 の row を持つので、参照側は
    通貨を分岐せずにこのテーブルを join できる。
    """

    __tablename__ = "currency_rate_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["currency_id"],
            ["currency.id"],
            ondelete="CASCADE",
            name="currency_rate_history_currency_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="currency_rate_history_pkey"),
        UniqueConstraint(
            "currency_id",
            "rate_date",
            name="currency_rate_history_currency_id_rate_date_key",
        ),
        # asset_data_history と同じく、直近レートの参照が主用途なので降順で張る。
        Index(
            "currency_rate_history_currency_id_rate_date_idx",
            "currency_id",
            text("rate_date DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    currency_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    rate_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    close_price: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)

    currency: Mapped["Currency"] = relationship(
        "Currency", back_populates="rate_history"
    )
