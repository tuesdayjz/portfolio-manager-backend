from marshmallow import Schema, fields, validate

from app.schemas.common import CURRENCY_VALIDATOR, UTCDateTime


class UserSchema(Schema):
    """ユーザープロフィール（レスポンス）。"""

    id = fields.Str(dump_only=True)
    email = fields.Email(dump_only=True)
    display_name = fields.Str(dump_only=True)
    base_currency = fields.Str(
        dump_only=True, metadata={"description": "集計の基準通貨", "example": "JPY"}
    )
    created_at = UTCDateTime(dump_only=True)
    updated_at = UTCDateTime(dump_only=True)


class UserRegisterSchema(Schema):
    """ユーザー登録リクエスト。"""

    email = fields.Email(required=True, metadata={"example": "investor@example.com"})
    display_name = fields.Str(
        required=True, validate=validate.Length(min=1, max=100),
        metadata={"example": "山田 太郎"},
    )
    base_currency = fields.Str(
        load_default="JPY", validate=CURRENCY_VALIDATOR, metadata={"example": "JPY"}
    )


class UserUpdateSchema(Schema):
    """プロフィール更新リクエスト（部分更新）。"""

    display_name = fields.Str(validate=validate.Length(min=1, max=100))
    base_currency = fields.Str(validate=CURRENCY_VALIDATOR)


class UserRegisteredSchema(Schema):
    """登録直後のレスポンス。API キーはこのときだけ平文で返す。"""

    user = fields.Nested(UserSchema)
    api_key = fields.Str(
        metadata={
            "description": "以降のリクエストで X-API-Key ヘッダーに指定する。"
            "再表示はできないため必ず保管すること。",
            "example": "pmk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        }
    )
