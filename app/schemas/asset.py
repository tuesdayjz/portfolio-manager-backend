from marshmallow import Schema, fields, validate

from app.enums import AssetType
from app.schemas.common import CURRENCY_VALIDATOR, UTCDateTime

_SORTABLE = {"symbol", "name", "asset_type", "created_at"}


class AssetSchema(Schema):
    """銘柄（レスポンス）。"""

    id = fields.Str(dump_only=True)
    symbol = fields.Str(dump_only=True, metadata={"example": "7203.T"})
    name = fields.Str(dump_only=True, metadata={"example": "トヨタ自動車"})
    asset_type = fields.Enum(AssetType, by_value=True, dump_only=True)
    currency = fields.Str(dump_only=True, metadata={"example": "JPY"})
    exchange = fields.Str(dump_only=True, allow_none=True, metadata={"example": "TSE"})
    created_at = UTCDateTime(dump_only=True)
    updated_at = UTCDateTime(dump_only=True)


class AssetCreateSchema(Schema):
    """銘柄の新規登録。"""

    symbol = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=32),
        metadata={"description": "ティッカー / 証券コード", "example": "7203.T"},
    )
    name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=200),
        metadata={"example": "トヨタ自動車"},
    )
    asset_type = fields.Enum(AssetType, by_value=True, required=True)
    currency = fields.Str(load_default="JPY", validate=CURRENCY_VALIDATOR)
    exchange = fields.Str(
        load_default=None, allow_none=True, validate=validate.Length(max=50),
        metadata={"example": "TSE"},
    )


class AssetUpdateSchema(Schema):
    """銘柄の部分更新。`symbol` は取引履歴との整合のため変更不可。"""

    name = fields.Str(validate=validate.Length(min=1, max=200))
    asset_type = fields.Enum(AssetType, by_value=True)
    currency = fields.Str(validate=CURRENCY_VALIDATOR)
    exchange = fields.Str(allow_none=True, validate=validate.Length(max=50))


class AssetQuerySchema(Schema):
    """GET /assets/ のクエリパラメータ。"""

    asset_type = fields.Enum(
        AssetType, by_value=True, metadata={"description": "資産種別で絞り込む"}
    )
    currency = fields.Str(validate=CURRENCY_VALIDATOR)
    q = fields.Str(
        metadata={"description": "symbol / name の部分一致検索", "example": "トヨタ"}
    )
    sort = fields.Str(
        load_default="symbol",
        metadata={
            "description": "並び順。先頭に `-` を付けると降順。",
            "example": "-created_at",
        },
        validate=validate.OneOf(
            sorted(_SORTABLE | {f"-{f}" for f in _SORTABLE})
        ),
    )
