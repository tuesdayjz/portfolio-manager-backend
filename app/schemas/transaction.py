"""取引履歴のスキーマ。"""

from marshmallow import Schema, fields, validate

from app.enums import TransactionType
from app.schemas.common import (
    NON_NEGATIVE,
    POSITIVE,
    DateRangeQueryMixin,
    PaginationQueryMixin,
    PaginationSchema,
)


class TransactionItemSchema(Schema):
    """取引 1 件分の作成内容。単件作成のボディと一括作成の 1 要素に使う。

    登録先のポートフォリオはログイン情報から解決するため、クライアントは
    `portfolio_id` を送らない。1 リクエストで複数のポートフォリオにまたがる
    作成はできない。
    """

    # ticker + name identify the asset because ticker may not be unique.
    ticker = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=50),
        metadata={"description": "Market data ticker", "example": "7203.T"},
    )
    name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=200),
        metadata={"description": "Asset name", "example": "Toyota Motor Corp."},
    )
    position = fields.Str(
        required=True,
        validate=validate.OneOf(["long"]),
        metadata={"description": "Position direction", "example": "long"},
    )
    order_type = fields.Str(
        required=True,
        validate=validate.OneOf(["market"]),
        metadata={"description": "Order execution type", "example": "market"},
    )
    transaction_type = fields.Enum(
        TransactionType, by_value=True, required=True, metadata={"example": "buy"}
    )
    quantity = fields.Float(
        required=True, validate=POSITIVE,
        # apispec は Range の min_inclusive を見ないので exclusiveMinimum は手で入れる
        metadata={"example": 5.4, "exclusiveMinimum": True},
    )


class TransactionSchema(Schema):
    """取引作成成功時に返す約定サマリー。"""

    date = fields.DateTime(
        required=True,
        metadata={"description": "約定日時", "example": "2026-05-26T18:00:00"},
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
        metadata={"description": "資産クラス", "example": "stock"},
    )
    executed_price = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "最終約定金額", "example": 16094.70},
    )
    executed_unit_price = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "約定単価", "example": 2980.5},
    )


class TransactionHistoryItemSchema(Schema):
    """取引履歴 1 件。作成レスポンスより UI 一覧向けの情報を多く返す。"""

    date = fields.Date(
        required=True,
        metadata={"description": "取引日", "example": "2026-05-26"},
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
        metadata={"description": "資産クラス", "example": "stock"},
    )
    quantity = fields.Float(
        required=True,
        validate=POSITIVE,
        metadata={"description": "取引数量", "example": 5.4},
    )
    transaction_type = fields.Str(
        required=True,
        validate=validate.OneOf([item.value for item in TransactionType]),
        metadata={"example": "sell"},
    )
    executed_price = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "約定金額（約定単価 × 数量）", "example": 16094.70},
    )
    executed_unit_price = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "約定単価", "example": 2980.5},
    )
    realized_pl = fields.Float(
        required=True,
        allow_none=True,
        metadata={
            "description": "実現損益。buy は未確定のため null。",
            "example": 318750,
        },
    )
    realized_pl_percent = fields.Float(
        required=True,
        allow_none=True,
        metadata={
            "description": "売却前取得原価に対する実現損益率（％）。buy は null。",
            "example": 11.18,
        },
    )


class TransactionTotalsSchema(Schema):
    """取引履歴の合計行。

    ページを送っても値が変わらないよう、フィルタ適用後の全件で集計する。
    `buy` は実現損益を持たないため、どの値も `sell` だけを対象にする。
    """

    realized_pl = fields.Float(
        required=True,
        metadata={"description": "実現損益の合計。損失なら負。", "example": 318750},
    )
    realized_pl_percent = fields.Float(
        required=True,
        metadata={
            "description": "取得原価の合計に対する実現損益率（％）",
            "example": 11.18,
        },
    )
    currency = fields.Str(required=True, metadata={"example": "USD"})


class TransactionPageSchema(Schema):
    """取引履歴（ページング付き）。UI の「Page 1 of 5」に対応する。"""

    items = fields.List(fields.Nested(TransactionHistoryItemSchema), required=True)
    totals = fields.Nested(TransactionTotalsSchema, required=True)
    pagination = fields.Nested(PaginationSchema, required=True)


class TransactionBatchCreateSchema(Schema):
    """取引の一括登録。全件を検証してから保有残高を更新する。"""

    transactions = fields.List(
        fields.Nested(TransactionItemSchema),
        required=True,
        validate=validate.Length(min=1),
    )


class TransactionQuerySchema(DateRangeQueryMixin, PaginationQueryMixin, Schema):
    """GET /portfolios/transactions のクエリパラメータ。"""

    # Search and detailed asset filtering are handled by the frontend.
    transaction_type = fields.Str(
        load_default="all",
        validate=validate.OneOf(["all", *[item.value for item in TransactionType]]),
        metadata={
            "description": "取引種別で絞り込む。省略時は全件（UI の `Type: All`）。",
            "example": "all",
        },
    )
    asset_type = fields.Str(
        load_default="all",
        validate=validate.Length(max=20),
        metadata={
            "description": "資産クラスで絞り込む。省略時は全件（UI の `Asset Class: All`）。",
            "example": "all",
        },
    )
    start_date = fields.Date(
        metadata={
            "description": "この日付以降（当日を含む）の取引を返す",
            "example": "2026-01-01",
        }
    )
    end_date = fields.Date(
        metadata={
            "description": "この日付以前（当日を含む）の取引を返す",
            "example": "2026-12-31",
        }
    )
