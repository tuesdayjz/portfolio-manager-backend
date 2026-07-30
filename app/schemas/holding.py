"""保有残高のスキーマ。"""

from marshmallow import Schema, fields, validate

from app.schemas.common import (
    NON_NEGATIVE,
    POSITIVE_ID,
    PaginationQueryMixin,
    PaginationSchema,
)


class HoldingSchema(Schema):
    """1 銘柄あたりの保有残高（レスポンス）。

    数量と平均取得単価は Supabase `holdings` の値。`current_price` は
    Yahoo Finance 由来の市場価格で、`holdings` には保存しない。評価額・騰落率・
    評価損益も市場価格から都度計算するため保存しない。
    """

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
    asset_type = fields.Str(
        required=True, validate=validate.Length(max=20),
        metadata={
            "description": "資産クラス。配分の `group_by=asset_type` と同じ区分。",
            "example": "stock",
        },
    )
    sector = fields.Str(
        validate=validate.Length(max=50),
        metadata={
            "description": "株式のセクター。株式以外の資産では null。",
            "example": "Technology",
        },
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
    market_value = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={
            "description": "評価額（quantity × current_price）",
            "example": 25334.25,
        },
    )
    day_change_percent = fields.Float(
        required=True,
        metadata={
            "description": "前日終値からの騰落率（％）。下落なら負。",
            "example": 1.8,
        },
    )
    total_return = fields.Float(
        required=True,
        metadata={
            "description": "評価損益（評価額 − 取得原価）。損失なら負。",
            "example": 16019.95,
        },
    )
    total_return_percent = fields.Float(
        required=True,
        metadata={"description": "取得原価に対する損益率（％）", "example": 171.98},
    )
    currency = fields.Str(
        required=True, metadata={"description": "通貨", "example": "JPY"}
    )


class HoldingsTotalSchema(Schema):
    """Positions 画面の合計行（Total Positions Valuation）。

    ページングしても値が変わらないよう、フィルタ適用後の全件で集計する。
    """

    market_value = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "評価額の合計", "example": 4220000},
    )
    total_return = fields.Float(
        required=True, metadata={"description": "評価損益の合計", "example": 318750}
    )
    total_return_percent = fields.Float(
        required=True,
        metadata={"description": "取得原価に対する損益率（％）", "example": 8.17},
    )
    currency = fields.Str(required=True, metadata={"example": "JPY"})


class HoldingsPageSchema(Schema):
    """Positions 一覧（ページング付き）。

    Dashboard の「Showing 5 of 24 positions」と Positions 画面の一覧は同じ形で、
    `per_page` だけが違う。
    """

    items = fields.List(fields.Nested(HoldingSchema), required=True)
    totals = fields.Nested(HoldingsTotalSchema, required=True)
    pagination = fields.Nested(PaginationSchema, required=True)


class HoldingsQuerySchema(PaginationQueryMixin, Schema):
    """GET /portfolios/{portfolio_id}/holdings のクエリパラメータ。"""

    asset_id = fields.Int(
        validate=POSITIVE_ID,
        metadata={"description": "特定銘柄の保有残高だけを返す", "example": 1},
    )
    search = fields.Str(
        validate=validate.Length(min=1, max=100),
        metadata={
            "description": "銘柄名またはティッカーの部分一致（大文字小文字を区別しない）",
            "example": "7203",
        },
    )
    asset_type = fields.Str(
        validate=validate.Length(max=20),
        metadata={
            "description": "資産クラスで絞り込む。省略時は全件（UI の `All`）。",
            "example": "stock",
        },
    )
    sector = fields.Str(
        validate=validate.Length(max=50),
        metadata={
            "description": "セクターで絞り込む。省略時は全件（UI の `All`）。",
            "example": "Technology",
        },
    )
