from marshmallow import Schema, fields, validate

from app.enums import AssetType
from app.schemas.asset import AssetSchema
from app.schemas.common import CURRENCY_VALIDATOR, AmountField, UTCDateTime

_SORTABLE = {"symbol", "quantity", "book_value", "realized_pnl"}


class HoldingSchema(Schema):
    """1 銘柄あたりの保有状況。取得原価は移動平均法で算出する。"""

    asset = fields.Nested(AssetSchema)
    quantity = AmountField(metadata={"description": "現在の保有数量"})
    average_cost = AmountField(
        metadata={"description": "1 単位あたりの平均取得単価（手数料込み）"}
    )
    book_value = AmountField(
        metadata={"description": "取得原価の合計 = quantity × average_cost"}
    )
    realized_pnl = AmountField(
        metadata={"description": "売却による実現損益の累計（手数料・税控除後）"}
    )
    dividend_income = AmountField(
        metadata={"description": "受取配当の累計（税控除後）"}
    )
    total_fee = AmountField(metadata={"description": "支払手数料の累計"})
    total_tax = AmountField(metadata={"description": "支払税額の累計"})
    currency = fields.Str()
    transaction_count = fields.Int()
    first_transaction_at = UTCDateTime(allow_none=True)
    last_transaction_at = UTCDateTime(allow_none=True)


class CurrencySummarySchema(Schema):
    """通貨ごとの合計。為替レートを持たないため通貨横断の合算はしない。"""

    currency = fields.Str()
    book_value = AmountField()
    realized_pnl = AmountField()
    dividend_income = AmountField()
    total_fee = AmountField()
    total_tax = AmountField()


class HoldingsResponseSchema(Schema):
    """GET /holdings/ のレスポンス。"""

    as_of = UTCDateTime(
        metadata={"description": "この時点までの取引を集計した結果であることを示す"}
    )
    base_currency = fields.Str()
    holdings = fields.List(fields.Nested(HoldingSchema))
    summary = fields.List(
        fields.Nested(CurrencySummarySchema),
        metadata={"description": "通貨ごとの集計。異なる通貨は合算しない。"},
    )


class HoldingsQuerySchema(Schema):
    """GET /holdings/ のクエリパラメータ。"""

    as_of = fields.Date(
        metadata={
            "description": "指定日終了時点の保有状況を算出する（省略時は現在）",
            "example": "2026-06-30",
        }
    )
    asset_type = fields.Enum(AssetType, by_value=True)
    currency = fields.Str(validate=CURRENCY_VALIDATOR)
    include_closed = fields.Bool(
        load_default=False,
        metadata={"description": "保有数量が 0 になった銘柄も含めるか"},
    )
    sort = fields.Str(
        load_default="-book_value",
        validate=validate.OneOf(sorted(_SORTABLE | {f"-{f}" for f in _SORTABLE})),
        metadata={"description": "並び順。先頭に `-` を付けると降順。"},
    )
