from datetime import datetime, timezone
from decimal import Decimal

from marshmallow import Schema, fields, validate

CURRENCY_VALIDATOR = validate.Regexp(
    r"^[A-Z]{3}$", error="ISO 4217 の3文字大文字コードで指定してください (例: JPY, USD)。"
)


def tidy_decimal(value: Decimal) -> Decimal:
    """余分な末尾ゼロと指数表記を落とす。

    Decimal 同士の乗算はスケールが加算されるため、そのまま出力すると
    ``280000.0000000000000000`` のような値になる。桁を落とさずに見た目だけ整える。
    """
    normalized = value.normalize()
    if normalized.as_tuple().exponent > 0:
        # 1E+5 のような指数表記を 100000 に戻す
        normalized = normalized.quantize(Decimal(1))
    return normalized


class AmountField(fields.Decimal):
    """金額・数量用の Decimal フィールド。文字列で入出力し、精度落ちを避ける。

    JSON の number は倍精度浮動小数点なので、金額は必ず文字列として扱う。
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("as_string", True)
        super().__init__(**kwargs)

    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return None
        return super()._serialize(tidy_decimal(Decimal(value)), attr, obj, **kwargs)


class UTCDateTime(fields.DateTime):
    """常に UTC のオフセット付きで入出力する DateTime。

    SQLite など tzinfo を保存しないバックエンドから読み戻すと naive な値になる。
    保存時は必ず UTC なので、naive なら UTC とみなしてオフセットを補う。
    入力側もタイムゾーン指定の有無にかかわらず UTC に正規化する。
    """

    def _serialize(self, value, attr, obj, **kwargs):
        if isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return super()._serialize(value, attr, obj, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        result = super()._deserialize(value, attr, data, **kwargs)
        if result.tzinfo is None:
            return result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)


class ErrorSchema(Schema):
    """flask-smorest の abort() が返すエラーレスポンス。"""

    code = fields.Int(metadata={"description": "HTTP ステータスコード"})
    status = fields.Str(metadata={"description": "HTTP ステータス名"})
    message = fields.Str(metadata={"description": "エラーの概要"})
    errors = fields.Dict(
        metadata={"description": "バリデーションエラーの詳細（フィールド単位）"}
    )
