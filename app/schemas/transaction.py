"""取引履歴のスキーマ。"""

from marshmallow import Schema, fields, validate

from app.enums import TransactionStatus, TransactionType
from app.schemas.common import (
    NON_NEGATIVE,
    POSITIVE,
    POSITIVE_ID,
    DateRangeQueryMixin,
    PaginationQueryMixin,
    PaginationSchema,
)


class TransactionItemSchema(Schema):
    """一括登録の 1 件分。`user_id` はリクエスト全体で 1 つなので持たない。"""

    asset_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 1}
    )
    transaction_type = fields.Enum(
        TransactionType, by_value=True, required=True, metadata={"example": "buy"}
    )
    quantity = fields.Float(
        required=True, validate=POSITIVE,
        # apispec は Range の min_inclusive を見ないので exclusiveMinimum は手で入れる
        metadata={"example": 5.4, "exclusiveMinimum": True},
    )
    price = fields.Float(
        required=True, validate=NON_NEGATIVE, metadata={"example": 2980.5}
    )
    fees = fields.Float(
        load_default=0, validate=NON_NEGATIVE, metadata={"example": 0.0}
    )
    date = fields.DateTime(
        required=True, metadata={"example": "2026-05-26T18:00:00"}
    )
    status = fields.Enum(
        TransactionStatus, by_value=True, load_default=TransactionStatus.COMPLETED,
        metadata={
            "description": "`pending` の取引は保有残高に反映しない。",
            "example": "completed",
        },
    )


class TransactionCreateSchema(TransactionItemSchema):
    """取引の新規登録（単件）。"""

    user_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 101}
    )


class TransactionSchema(TransactionCreateSchema):
    """取引（レスポンス）。`portfolio_id` はパスから、`transaction_id` は採番される。"""

    portfolio_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 1}
    )
    transaction_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 1}
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
    total_amount = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={
            "description": "約定代金（quantity × price）。手数料は含めない。",
            "example": 16094.70,
        },
    )
    status = fields.Enum(
        TransactionStatus, by_value=True, required=True,
        metadata={"example": "completed"},
    )
    currency = fields.Str(
        required=True, metadata={"description": "通貨", "example": "JPY"}
    )


class TransactionPageSchema(Schema):
    """取引履歴（ページング付き）。UI の「Page 1 of 5」に対応する。"""

    items = fields.List(fields.Nested(TransactionSchema), required=True)
    pagination = fields.Nested(PaginationSchema, required=True)


class TransactionBatchCreateSchema(Schema):
    """取引の一括登録。全件を検証してから保有残高を更新する。"""

    user_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 101}
    )
    transactions = fields.List(
        fields.Nested(TransactionItemSchema),
        required=True,
        validate=validate.Length(min=1),
    )


class TransactionQuerySchema(DateRangeQueryMixin, PaginationQueryMixin, Schema):
    """GET /portfolios/{portfolio_id}/transactions のクエリパラメータ。"""

    user_id = fields.Int(
        required=True, validate=POSITIVE_ID,
        metadata={"description": "User ID", "example": 101},
    )
    asset_id = fields.Int(
        validate=POSITIVE_ID,
        metadata={"description": "特定銘柄の取引だけを返す", "example": 1},
    )
    search = fields.Str(
        validate=validate.Length(min=1, max=100),
        metadata={
            "description": "銘柄名またはティッカーの部分一致（大文字小文字を区別しない）",
            "example": "7203",
        },
    )
    transaction_type = fields.Enum(
        TransactionType, by_value=True,
        metadata={
            "description": "取引種別で絞り込む。省略時は全件（UI の `Type: All`）。",
            "example": "buy",
        },
    )
    asset_type = fields.Str(
        validate=validate.Length(max=20),
        metadata={
            "description": "資産クラスで絞り込む。省略時は全件（UI の `Asset Class: All`）。",
            "example": "stock",
        },
    )
    status = fields.Enum(
        TransactionStatus, by_value=True,
        metadata={"description": "約定ステータスで絞り込む", "example": "completed"},
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
