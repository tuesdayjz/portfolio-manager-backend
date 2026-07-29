"""保有残高のスキーマ。"""

from marshmallow import Schema, fields

from app.schemas.common import NON_NEGATIVE, POSITIVE_ID


class HoldingSchema(Schema):
    """1 銘柄あたりの保有残高（レスポンス）。

    数量と平均取得単価は Supabase `holdings` の値。`current_price` は
    Yahoo Finance 由来の市場価格で、`holdings` には保存しない。
    """

    user_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 101}
    )
    portfolio_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 1}
    )
    asset_id = fields.Int(
        required=True, validate=POSITIVE_ID,
        metadata={"description": "Asset ID", "example": 1},
    )
    symbol = fields.Str(
        required=True,
        metadata={"description": "Yahoo Finance symbol", "example": "7203.T"},
    )
    name = fields.Str(
        required=True,
        metadata={"description": "Asset name", "example": "Toyota Motor Corp."},
    )
    quantity = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "Current holding quantity", "example": 8.5},
    )
    average_purchase_price = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "平均取得単価", "example": 1095.80},
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


class HoldingsQuerySchema(Schema):
    """GET /portfolios/{portfolio_id}/holdings のクエリパラメータ。"""

    user_id = fields.Int(
        required=True, validate=POSITIVE_ID,
        metadata={"description": "User ID", "example": 101},
    )
    asset_id = fields.Int(
        validate=POSITIVE_ID,
        metadata={"description": "特定銘柄の保有残高だけを返す", "example": 1},
    )
