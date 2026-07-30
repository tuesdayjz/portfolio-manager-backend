"""取引履歴のスキーマ。"""

from marshmallow import Schema, fields, validate

from app.enums import TransactionType
from app.schemas.common import (
    NON_NEGATIVE,
    POSITIVE,
    POSITIVE_ID,
    DateRangeQueryMixin,
    PaginationQueryMixin,
    PaginationSchema,
)


class TransactionItemSchema(Schema):
    """取引 1 件分の登録内容。単件登録のボディと一括登録の 1 要素に使う。

    登録先のポートフォリオはログイン情報から解決するため、クライアントは
    `portfolio_id` を送らない。1 リクエストで複数のポートフォリオにまたがる
    登録はできない。
    """

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


class TransactionSchema(TransactionItemSchema):
    """取引（レスポンス）。

    `transaction_id` は登録時に採番される。`price` と `date` は約定時に
    サーバー側で確定するため、登録リクエストには含めない。`portfolio_id` は
    サーバーが解決した登録先を返すだけで、リクエストでは受け取らない。
    """

    transaction_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 1}
    )
    portfolio_id = fields.Int(
        required=True, validate=POSITIVE_ID,
        metadata={"description": "登録先のポートフォリオ", "example": 1},
    )
    price = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "約定単価", "example": 2980.5},
    )
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
    total_amount = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={
            "description": "約定代金（quantity × price）。手数料は含めない。",
            "example": 16094.70,
        },
    )
    cost_basis = fields.Float(
        allow_none=True, validate=NON_NEGATIVE,
        metadata={
            "description": "売却分の取得原価（売却時点の平均取得単価 × quantity）。"
            "`buy` では null。",
            "example": 5917.32,
        },
    )
    realized_pl = fields.Float(
        allow_none=True,
        metadata={
            "description": "実現損益（total_amount − cost_basis）。損失なら負。"
            "`buy` はこの時点で損益が確定しないため null。",
            "example": 10177.38,
        },
    )
    realized_pl_percent = fields.Float(
        allow_none=True,
        metadata={
            "description": "取得原価に対する実現損益率（％）。`buy` では null。",
            "example": 171.99,
        },
    )
    currency = fields.Str(
        required=True, metadata={"description": "通貨", "example": "JPY"}
    )


class TransactionTotalsSchema(Schema):
    """取引履歴の合計行。

    ページを送っても値が変わらないよう、フィルタ適用後の全件で集計する。
    `buy` は実現損益を持たないため、どの値も `sell` だけを対象にする。
    """

    cost_basis = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "売却分の取得原価の合計", "example": 2850000},
    )
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
    sell_count = fields.Int(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "合計の対象になった売却取引の件数", "example": 42},
    )
    currency = fields.Str(required=True, metadata={"example": "JPY"})


class TransactionPageSchema(Schema):
    """取引履歴（ページング付き）。UI の「Page 1 of 5」に対応する。"""

    items = fields.List(fields.Nested(TransactionSchema), required=True)
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
    """GET /portfolios/{portfolio_id}/transactions のクエリパラメータ。"""

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
