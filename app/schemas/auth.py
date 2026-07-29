"""認証関連のスキーマ。"""

from marshmallow import Schema, fields, validate


class SignupRequestSchema(Schema):
    """ユーザー登録リクエスト。

    本番では Supabase Auth の email/password signup を使い、password は
    public schema に保存しない。
    """

    email = fields.Email(required=True, metadata={"example": "user@example.com"})
    password = fields.Str(
        required=True,
        validate=validate.Length(min=8),
        load_only=True,
        metadata={"example": "password123"},
    )
    portfolio_name = fields.Str(
        required=True, metadata={"example": "Main Portfolio"}
    )
    base_currency = fields.Str(required=True, metadata={"example": "JPY"})


class LoginRequestSchema(Schema):
    """ログインリクエスト。"""

    email = fields.Email(required=True, metadata={"example": "user@example.com"})
    password = fields.Str(
        required=True,
        load_only=True,
        metadata={"example": "password123"},
    )


class AuthUserSchema(Schema):
    """認証レスポンス内のユーザー情報。"""

    user_id = fields.Int(required=True, metadata={"example": 101})
    email = fields.Email(required=True, metadata={"example": "user@example.com"})


class AuthPortfolioSchema(Schema):
    """認証レスポンス内のデフォルトポートフォリオ情報。"""

    portfolio_id = fields.Int(required=True, metadata={"example": 1})
    name = fields.Str(required=True, metadata={"example": "Main Portfolio"})
    base_currency = fields.Str(required=True, metadata={"example": "JPY"})


class AuthResponseSchema(Schema):
    """ログイン・登録成功レスポンス。"""

    access_token = fields.Str(
        required=True, metadata={"example": "mock-access-token-101"}
    )
    token_type = fields.Str(required=True, metadata={"example": "bearer"})
    user = fields.Nested(AuthUserSchema, required=True)
    portfolio = fields.Nested(AuthPortfolioSchema, required=True)


class LogoutResponseSchema(Schema):
    """ログアウトレスポンス。"""

    message = fields.Str(required=True, metadata={"example": "Logged out"})
