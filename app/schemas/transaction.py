from decimal import Decimal

from marshmallow import Schema, ValidationError, fields, validate, validates_schema

from app.enums import TransactionType
from app.schemas.asset import AssetSchema
from app.schemas.common import AmountField, UTCDateTime

_SORTABLE = {"executed_at", "created_at"}

_TYPE_SEMANTICS = (
    "種別ごとの意味:\n"
    "- `BUY` / `SELL`: quantity=約定数量, price=単価\n"
    "- `DIVIDEND`: quantity は 0、price に配当総額（税引前）を入れる\n"
    "- `SPLIT`: quantity に分割比率（1→2 の分割なら 2）、price は 0"
)


class TransactionSchema(Schema):
    """取引（レスポンス）。"""

    id = fields.Str(dump_only=True)
    asset_id = fields.Str(dump_only=True)
    asset = fields.Nested(AssetSchema, dump_only=True)
    transaction_type = fields.Enum(TransactionType, by_value=True, dump_only=True)
    quantity = AmountField(dump_only=True)
    price = AmountField(dump_only=True)
    fee = AmountField(dump_only=True)
    tax = AmountField(dump_only=True)
    currency = fields.Str(dump_only=True)
    gross_amount = AmountField(
        dump_only=True, metadata={"description": "手数料・税を除いた約定金額"}
    )
    net_amount = AmountField(
        dump_only=True,
        metadata={"description": "キャッシュフロー。プラスが入金、マイナスが出金。"},
    )
    executed_at = UTCDateTime(dump_only=True)
    note = fields.Str(dump_only=True, allow_none=True)
    created_at = UTCDateTime(dump_only=True)
    updated_at = UTCDateTime(dump_only=True)


class _TransactionWriteBase(Schema):
    quantity = fields.Decimal(
        as_string=True, places=10, validate=validate.Range(min=Decimal("0")),
        metadata={"example": "100"},
    )
    price = fields.Decimal(
        as_string=True, places=6, validate=validate.Range(min=Decimal("0")),
        metadata={"example": "2850.5"},
    )
    fee = fields.Decimal(
        as_string=True, places=6, validate=validate.Range(min=Decimal("0")),
        metadata={"example": "550"},
    )
    tax = fields.Decimal(
        as_string=True, places=6, validate=validate.Range(min=Decimal("0")),
        metadata={"example": "0"},
    )
    executed_at = UTCDateTime(metadata={"example": "2026-04-01T00:30:00Z"})
    note = fields.Str(allow_none=True, validate=validate.Length(max=1000))

    @validates_schema
    def check_type_semantics(self, data, **kwargs):
        tx_type = data.get("transaction_type")
        if tx_type is None:
            return
        errors: dict[str, list[str]] = {}
        quantity = data.get("quantity")
        price = data.get("price")

        if tx_type in (TransactionType.BUY, TransactionType.SELL):
            if quantity is not None and quantity <= 0:
                errors["quantity"] = [f"{tx_type.value} では quantity は 0 より大きい必要があります。"]
        elif tx_type is TransactionType.DIVIDEND:
            if price is not None and price <= 0:
                errors["price"] = ["DIVIDEND では price に配当総額（0 より大きい値）を指定してください。"]
        elif tx_type is TransactionType.SPLIT:
            if quantity is not None and quantity <= 0:
                errors["quantity"] = ["SPLIT では quantity に分割比率（0 より大きい値）を指定してください。"]

        if errors:
            raise ValidationError(errors)


class TransactionCreateSchema(_TransactionWriteBase):
    """取引の新規登録。通貨は対象銘柄の設定を引き継ぐ。"""

    class Meta:
        description = _TYPE_SEMANTICS

    asset_id = fields.Str(required=True)
    transaction_type = fields.Enum(
        TransactionType, by_value=True, required=True,
        metadata={"description": _TYPE_SEMANTICS},
    )
    quantity = fields.Decimal(
        as_string=True, places=10, load_default=Decimal("0"),
        validate=validate.Range(min=Decimal("0")), metadata={"example": "100"},
    )
    price = fields.Decimal(
        as_string=True, places=6, load_default=Decimal("0"),
        validate=validate.Range(min=Decimal("0")), metadata={"example": "2850.5"},
    )
    fee = fields.Decimal(
        as_string=True, places=6, load_default=Decimal("0"),
        validate=validate.Range(min=Decimal("0")),
    )
    tax = fields.Decimal(
        as_string=True, places=6, load_default=Decimal("0"),
        validate=validate.Range(min=Decimal("0")),
    )
    executed_at = UTCDateTime(
        required=True, metadata={"example": "2026-04-01T00:30:00Z"}
    )


class TransactionUpdateSchema(_TransactionWriteBase):
    """取引の部分更新。`asset_id` は変更不可（削除して登録し直す）。"""

    transaction_type = fields.Enum(TransactionType, by_value=True)


class TransactionQuerySchema(Schema):
    """GET /transactions/ のクエリパラメータ。"""

    asset_id = fields.Str(
        metadata={"description": "特定銘柄の取引だけを返す"}
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
    transaction_type = fields.Enum(TransactionType, by_value=True)
    sort = fields.Str(
        load_default="-executed_at",
        validate=validate.OneOf(sorted(_SORTABLE | {f"-{f}" for f in _SORTABLE})),
        metadata={"description": "並び順。先頭に `-` を付けると降順。"},
    )

    @validates_schema
    def check_date_range(self, data, **kwargs):
        start, end = data.get("start_date"), data.get("end_date")
        if start and end and start > end:
            raise ValidationError(
                {"end_date": ["end_date は start_date 以降にしてください。"]}
            )
