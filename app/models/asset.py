"""資産マスタ関連のモデル（asset_type / currency / asset_master / asset_data_history）。"""

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
        "AssetMaster", back_populates="asset_type_"
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
    # asset_type_id を参照する前の名残のカラム。参照は asset_type_ 側を使う。
    asset_type: Mapped[Optional[str]] = mapped_column(Text)
    asset_type_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, server_default=text("gen_random_uuid()")
    )
    currency_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, server_default=text("gen_random_uuid()")
    )

    # カラム名 asset_type と衝突するため、リレーション側に末尾のアンダースコアを付ける。
    asset_type_: Mapped[Optional["AssetType"]] = relationship(
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
