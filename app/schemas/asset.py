"""資産（銘柄）関連のスキーマ。"""

from marshmallow import Schema, fields, validate

from app.schemas.common import (
    NON_NEGATIVE,
    POSITIVE_ID,
    DateRangeQueryMixin,
)


class AssetSchema(Schema):
    """資産マスタと保有状況を結合した内部表現。

    `asset_master` の銘柄情報に、あるポートフォリオでの保有数量・取得価額と
    Yahoo Finance 由来の市場価格を重ねたもの。レスポンスとしては直接返さず、
    `AssetInfoSchema`（マスタ情報）と `HoldingSchema`（保有状況）に分けて返す。
    """

    asset_id = fields.Int(
        required=True, validate=POSITIVE_ID,
        metadata={"description": "Asset ID", "example": 1},
    )
    portfolio_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 1}
    )
    type = fields.Str(
        required=True, validate=validate.Length(max=20),
        metadata={"description": "Asset type", "example": "stock"},
    )
    name = fields.Str(
        required=True,
        metadata={"description": "Asset name", "example": "Toyota Motor Corp."},
    )
    symbol = fields.Str(
        required=True,
        metadata={"description": "Yahoo Finance symbol", "example": "7203.T"},
    )
    quantity = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={
            "description": "how many units of the asset the user has",
            "example": 8.5,
        },
    )
    purchase_price = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "取得価額", "example": 1095.80},
    )
    current_price = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={
            "description": "Yahoo Finance 由来の市場価格。Supabase holdings には保存しない。",
            "example": 2980.50,
        },
    )
    currency = fields.Str(
        required=True, metadata={"description": "通貨", "example": "JPY"}
    )


class AssetInfoSchema(Schema):
    """資産マスタ情報（レスポンス）。

    保有数量や取得価額のような private な値は含めない。それらは
    `GET /portfolios/holdings` で返す。
    """

    asset_id = fields.Int(
        required=True, validate=POSITIVE_ID,
        metadata={"description": "Asset ID", "example": 1},
    )
    type = fields.Str(
        required=True, validate=validate.Length(max=20),
        metadata={"description": "Asset type", "example": "stock"},
    )
    name = fields.Str(
        required=True,
        metadata={"description": "Asset name", "example": "Toyota Motor Corp."},
    )
    symbol = fields.Str(
        required=True,
        metadata={"description": "Yahoo Finance symbol", "example": "7203.T"},
    )
    currency = fields.Str(
        required=True, metadata={"description": "通貨", "example": "JPY"}
    )


class PriceHistoryItemSchema(Schema):
    """1 日分の OHLCV。Yahoo Finance または `asset_data_history` 由来。"""

    date = fields.Date(required=True, metadata={"example": "2026-07-28"})
    open = fields.Float(required=True, validate=NON_NEGATIVE, metadata={"example": 2950.0})
    high = fields.Float(required=True, validate=NON_NEGATIVE, metadata={"example": 3000.0})
    low = fields.Float(required=True, validate=NON_NEGATIVE, metadata={"example": 2920.0})
    close = fields.Float(required=True, validate=NON_NEGATIVE, metadata={"example": 2980.5})
    volume = fields.Int(required=True, validate=NON_NEGATIVE, metadata={"example": 1200000})


class PriceHistoryQuerySchema(DateRangeQueryMixin, Schema):
    """GET /assets/{asset_id}/price-history のクエリパラメータ。"""

    start_date = fields.Date(metadata={"example": "2026-01-01"})
    end_date = fields.Date(metadata={"example": "2026-07-28"})
    interval = fields.Str(load_default="1d", metadata={"example": "1d"})
