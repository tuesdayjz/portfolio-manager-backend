"""保有残高のスキーマ。"""

from marshmallow import Schema, fields, validate

from app.schemas.common import (
    NON_NEGATIVE,
    PaginationQueryMixin,
    PaginationSchema,
)


class HoldingSchema(Schema):
    """1 銘柄あたりの保有残高（レスポンス）。

    数量と平均取得単価は Supabase `holdings` の値。`current_price` は
    Yahoo Finance 由来の市場価格で、`holdings` には保存しない。評価額と騰落率も
    市場価格から都度計算するため保存しない。
    """

    ticker = fields.Str(
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
    quantity = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "Current holding quantity", "example": 8.5},
    )
    average_purchase_price = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "平均取得単価", "example": 1095.80},
    )
    total_purchase_price = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "合計取得価額", "example": 9314.30},
    )
    current_price = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={
            "description": "Yahoo Finance 由来の市場価格。Supabase holdings には保存しない。",
            "example": 2980.50,
        },
    )
    total_market_value = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={
            "description": "評価額（quantity × current_price）",
            "example": 25334.25,
        },
    )
    today_return_percent = fields.Float(
        required=True,
        metadata={
            "description": "前日終値からの騰落率（％）。下落なら負。",
            "example": 1.8,
        },
    )
    total_return_percent = fields.Float(
        required=True,
        metadata={
            "description": "平均取得単価に対する損益率（％）。下落なら負。",
            "example": 12.4,
        },
    )
    currency = fields.Str(
        required=True, metadata={"description": "通貨", "example": "USD"}
    )


class HoldingsTotalSchema(Schema):
    """Positions 画面の合計行（Total Positions Valuation）。

    ページングしても値が変わらないよう、フィルタ適用後の全件で集計する。
    損益は当日ぶん（前日終値からの騰落）だけを返す。
    """

    market_value = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "評価額の合計", "example": 4220000},
    )
    day_change = fields.Float(
        required=True,
        metadata={
            "description": "前日終値からの評価損益の変化額の合計。下落なら負。",
            "example": 42150,
        },
    )
    day_change_percent = fields.Float(
        required=True,
        metadata={
            "description": "前日終値の評価額合計に対する騰落率（％）。下落なら負。",
            "example": 1.01,
        },
    )
    currency = fields.Str(required=True, metadata={"example": "USD"})


class HoldingsPageSchema(Schema):
    """Positions 一覧（ページング付き）。

    Dashboard の「Showing 5 of 24 positions」と Positions 画面の一覧は同じ形で、
    `per_page` だけが違う。
    """

    items = fields.List(fields.Nested(HoldingSchema), required=True)
    totals = fields.Nested(HoldingsTotalSchema, required=True)
    pagination = fields.Nested(PaginationSchema, required=True)


class HoldingsQuerySchema(PaginationQueryMixin, Schema):
    """GET /portfolios/holdings のクエリパラメータ。"""

    # Search is handled by the frontend after the backend returns holdings data.
    asset_type = fields.Str(
        load_default="all",
        validate=validate.Length(max=20),
        metadata={
            "description": "資産クラスで絞り込む。省略時は全件（UI の `All`）。",
            "example": "all",
        },
    )
