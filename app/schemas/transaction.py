"""取引履歴のスキーマ。"""

import datetime

from marshmallow import (
    Schema,
    ValidationError,
    fields,
    pre_load,
    validate,
    validates_schema,
)

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
    quantity = fields.Int(
        required=True,
        validate=validate.Range(min=1),
        metadata={"example": 5},
    )
    trade_date = fields.Date(
        load_default=lambda: datetime.datetime.now(datetime.timezone.utc).date(),
        metadata={"description": "Trade date", "example": "2026-05-26"},
    )
    price = fields.Float(
        validate=POSITIVE,
        metadata={
            "description": (
                "Executed unit price for historical trades. Same-day trades use "
                "market price."
            ),
            "example": 2980.5,
            "exclusiveMinimum": True,
        },
    )

    @pre_load
    def reject_non_integer_quantity(self, data, **kwargs):
        quantity = data.get("quantity") if isinstance(data, dict) else None
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise ValidationError({"quantity": ["quantity must be an integer."]})
        return data

    @validates_schema
    def check_not_future_date(self, data, **kwargs):
        trade_date = data.get("trade_date")
        today = datetime.datetime.now(datetime.timezone.utc).date()
        if trade_date and trade_date > today:
            raise ValidationError(
                {"trade_date": ["trade_date cannot be later than today."]}
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
        metadata={"description": "取引通貨建ての最終約定金額", "example": 14902.5},
    )
    executed_unit_price = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "取引通貨建ての約定単価", "example": 2980.5},
    )


class TransactionHistoryItemSchema(Schema):
    """取引履歴 1 件。作成レスポンスより UI 一覧向けの情報を多く返す。"""

    transaction_id = fields.Str(
        required=True,
        metadata={"description": "取引 id", "example": "b93f26c4-66b3-4069-a93a-1f94f1828921"},
    )
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
        metadata={
            "description": "USD 換算後の約定金額（約定単価 × 数量 × FX rate）",
            "example": 16094.70,
        },
    )
    executed_unit_price = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={
            "description": "USD 換算後の約定単価（約定単価 × FX rate）",
            "example": 2980.5,
        },
    )
    realized_pl = fields.Float(
        required=True,
        allow_none=True,
        metadata={
            "description": "USD 換算後の実現損益。buy は未確定のため null。",
            "example": 318750,
        },
    )
    realized_pl_percent = fields.Float(
        required=True,
        allow_none=True,
        metadata={
            "description": "USD 換算後の売却前取得原価に対する実現損益率（％）。buy は null。",
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
        metadata={"description": "USD 換算後の実現損益の合計。損失なら負。", "example": 318750},
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


class CashTransactionItemSchema(Schema):
    """現金の入金・出金 1 件分の作成内容。ポートフォリオの現金残高だけを変更し、
    どの holding の quantity / average_cost にも影響しない。
    """

    transaction_type = fields.Enum(
        TransactionType, by_value=True, required=True,
        validate=validate.OneOf([TransactionType.DEPOSIT, TransactionType.WITHDRAWAL]),
        metadata={"example": "deposit"},
    )
    amount = fields.Float(
        required=True, validate=POSITIVE,
        metadata={"description": "入金・出金額", "example": 5000},
    )


class CashTransactionSchema(Schema):
    """入金・出金作成成功時に返す約定サマリー。"""

    date = fields.DateTime(
        required=True,
        metadata={"description": "約定日時", "example": "2026-08-05T18:00:00"},
    )
    transaction_type = fields.Str(
        required=True,
        validate=validate.OneOf(
            [TransactionType.DEPOSIT.value, TransactionType.WITHDRAWAL.value]
        ),
        metadata={"example": "deposit"},
    )
    amount = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "入金・出金額", "example": 5000},
    )
    cash_balance = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "取引後の現金残高", "example": 15000},
    )


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
