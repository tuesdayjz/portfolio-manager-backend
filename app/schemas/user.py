"""ユーザープロフィールと設定のスキーマ。

Figma の Settings 画面（Personal Profile / Security & MFA / Preferences &
Language / Notification Alerts / Raw Statements & Tax Export / Danger Zone）に
対応する。サイドバー下部のユーザー表示（氏名・役職・アバター）も
`UserProfileSchema` で返す。
"""

from marshmallow import Schema, ValidationError, fields, validate, validates_schema

from app.enums import ExportFormat, Theme
from app.schemas.common import (
    NON_NEGATIVE,
    POSITIVE_ID,
    DateRangeQueryMixin,
)


class UserProfileSchema(Schema):
    """ユーザープロフィール（レスポンス）。

    サイドバーの氏名・役職・アバターと、Settings の Personal Profile セクションで
    使う。`email` は Supabase Auth 側の値なので、変更は確認フロー付きの別 API に
    切り出す想定。
    """

    user_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 101}
    )
    email = fields.Email(
        required=True, metadata={"example": "david.vance@portfolioiq.com"}
    )
    full_name = fields.Str(
        required=True,
        validate=validate.Length(min=1, max=100),
        metadata={"description": "表示名（フルネーム）", "example": "David Vance"},
    )
    job_title = fields.Str(
        validate=validate.Length(max=100),
        metadata={"description": "サイドバーの肩書き", "example": "Senior Manager"},
    )
    phone_number = fields.Str(
        validate=validate.Length(max=30),
        metadata={"description": "携帯電話番号", "example": "+1 (555) 349-2041"},
    )
    avatar_url = fields.Url(
        metadata={
            "description": "アバター画像の URL。未設定ならフロントで頭文字を表示する。",
            "example": "https://example.com/avatars/101.png",
        }
    )


class UserProfileUpdateSchema(Schema):
    """プロフィールの部分更新。Settings の各行の「Edit」に対応する。"""

    full_name = fields.Str(
        validate=validate.Length(min=1, max=100), metadata={"example": "David Vance"}
    )
    job_title = fields.Str(
        validate=validate.Length(max=100), metadata={"example": "Senior Manager"}
    )
    phone_number = fields.Str(
        validate=validate.Length(max=30), metadata={"example": "+1 (555) 349-2041"}
    )
    avatar_url = fields.Url(
        metadata={"example": "https://example.com/avatars/101.png"}
    )


class SecuritySettingsSchema(Schema):
    """Security & MFA Configuration セクション（レスポンス）。"""

    two_factor_enabled = fields.Bool(
        required=True,
        metadata={
            "description": "ハードウェアキー／認証アプリによる 2 要素認証の有効／無効",
            "example": True,
        },
    )
    password_changed_at = fields.DateTime(
        required=True,
        metadata={
            "description": "最終パスワード変更日時。UI の「Last changed 42 days ago」の元になる。",
            "example": "2026-06-18T09:12:00",
        },
    )


class SecuritySettingsUpdateSchema(Schema):
    """2 要素認証トグルの更新。"""

    two_factor_enabled = fields.Bool(required=True, metadata={"example": True})


class PasswordChangeSchema(Schema):
    """Change Password。本番では Supabase Auth 側で検証・更新する。"""

    current_password = fields.Str(
        required=True, load_only=True, metadata={"example": "password123"}
    )
    new_password = fields.Str(
        required=True,
        load_only=True,
        validate=validate.Length(min=8),
        metadata={"example": "new-password456"},
    )

    @validates_schema
    def check_password_differs(self, data, **kwargs):
        if data.get("current_password") == data.get("new_password"):
            raise ValidationError(
                {"new_password": ["現在のパスワードと同じものは使えません。"]}
            )


class PreferencesSchema(Schema):
    """Preferences & Language セクション。"""

    base_currency = fields.Str(
        required=True,
        validate=validate.Length(equal=3),
        metadata={
            "description": "集計の基準通貨（ISO 4217）。評価額はこの通貨に換算して返す。",
            "example": "USD",
        },
    )
    theme = fields.Enum(
        Theme, by_value=True, required=True, metadata={"example": "light"}
    )


class PreferencesUpdateSchema(Schema):
    """Preferences の部分更新。"""

    base_currency = fields.Str(
        validate=validate.Length(equal=3), metadata={"example": "USD"}
    )
    theme = fields.Enum(Theme, by_value=True, metadata={"example": "light"})


class NotificationSettingsSchema(Schema):
    """Notification Alerts セクション。"""

    email_alerts = fields.Bool(
        required=True,
        metadata={
            "description": "重要な取引・リバランス警告をメールで受け取る",
            "example": True,
        },
    )
    weekly_performance_summary = fields.Bool(
        required=True,
        metadata={"description": "毎週金曜のサマリーレポートを送る", "example": True},
    )
    price_alert_threshold = fields.Float(
        required=True,
        validate=validate.Range(min=0, max=100),
        metadata={
            "description": "価格アラートの閾値（％）。日次騰落率がこの値を超えたら通知する。",
            "example": 5.0,
        },
    )


class NotificationSettingsUpdateSchema(Schema):
    """Notification Alerts の部分更新。"""

    email_alerts = fields.Bool(metadata={"example": True})
    weekly_performance_summary = fields.Bool(metadata={"example": True})
    price_alert_threshold = fields.Float(
        validate=validate.Range(min=0, max=100), metadata={"example": 5.0}
    )


class UserSettingsSchema(Schema):
    """Settings 画面をまとめて返すレスポンス。"""

    profile = fields.Nested(UserProfileSchema, required=True)
    security = fields.Nested(SecuritySettingsSchema, required=True)
    preferences = fields.Nested(PreferencesSchema, required=True)
    notifications = fields.Nested(NotificationSettingsSchema, required=True)


class UserSettingsUpdateSchema(Schema):
    """Settings のセクション単位の部分更新。"""

    profile = fields.Nested(UserProfileUpdateSchema)
    security = fields.Nested(SecuritySettingsUpdateSchema)
    preferences = fields.Nested(PreferencesUpdateSchema)
    notifications = fields.Nested(NotificationSettingsUpdateSchema)


class StatementExportQuerySchema(DateRangeQueryMixin, Schema):
    """Raw Statements & Tax Export のクエリパラメータ。

    `Export Portfolio CSV` は `format=csv`、`Download Tax Statement` は
    `format=pdf` + 対象年（`tax_year`）で呼ぶ想定。
    """

    portfolio_id = fields.Int(
        validate=POSITIVE_ID,
        metadata={
            "description": "省略時は全ポートフォリオをまとめて出力する",
            "example": 1,
        },
    )
    format = fields.Enum(
        ExportFormat,
        by_value=True,
        load_default=ExportFormat.CSV,
        metadata={"example": "csv"},
    )
    start_date = fields.Date(metadata={"example": "2026-01-01"})
    end_date = fields.Date(metadata={"example": "2026-12-31"})
    tax_year = fields.Int(
        validate=validate.Range(min=1970),
        metadata={"description": "税務明細の対象年", "example": 2026},
    )


class ExportJobSchema(Schema):
    """エクスポートの結果（ダウンロード先）。"""

    download_url = fields.Url(
        required=True,
        metadata={
            "description": "期限付きの署名付き URL",
            "example": "https://example.com/exports/101/portfolio-2026.csv",
        },
    )
    format = fields.Enum(
        ExportFormat, by_value=True, required=True, metadata={"example": "csv"}
    )
    expires_at = fields.DateTime(
        required=True,
        metadata={"description": "URL の失効日時", "example": "2026-07-30T12:00:00"},
    )
    size_bytes = fields.Int(
        validate=NON_NEGATIVE, metadata={"example": 20480}
    )


class AccountDeleteSchema(Schema):
    """Danger Zone のアカウント削除。ポートフォリオと履歴を全て消すため確認を必須にする。"""

    password = fields.Str(
        required=True,
        load_only=True,
        metadata={"description": "本人確認用のパスワード", "example": "password123"},
    )
    confirmation = fields.Str(
        required=True,
        validate=validate.Equal("DELETE"),
        metadata={
            "description": "確認のため `DELETE` を入力させる",
            "example": "DELETE",
        },
    )
