"""スキーマ共通の部品。"""

from marshmallow import Schema, ValidationError, fields, validate, validates_schema

#: 数量・金額の下限（0 以上）。
NON_NEGATIVE = validate.Range(min=0)

#: 数量の下限（0 より大きい）。
POSITIVE = validate.Range(min=0, min_inclusive=False)

#: ID の下限（1 以上）。
POSITIVE_ID = validate.Range(min=1)


class ErrorSchema(Schema):
    """flask-smorest の abort() が返すエラーレスポンス。"""

    code = fields.Int(metadata={"description": "HTTP ステータスコード"})
    status = fields.Str(metadata={"description": "HTTP ステータス名"})
    message = fields.Str(metadata={"description": "エラーの概要"})
    errors = fields.Dict(
        metadata={"description": "バリデーションエラーの詳細（フィールド単位）"}
    )


class UserIdQuerySchema(Schema):
    """所有者チェック用の `user_id`。

    モック／開発中は private な API に `user_id` をクエリパラメータで渡す。
    本番ではログイン情報から解決する想定なので、その際はこのスキーマを外す。
    """

    user_id = fields.Int(
        required=True,
        validate=POSITIVE_ID,
        metadata={"description": "User ID", "example": 101},
    )


class DateRangeQueryMixin:
    """`start_date` / `end_date` を持つクエリスキーマ用の検証。"""

    @validates_schema
    def check_date_range(self, data, **kwargs):
        start, end = data.get("start_date"), data.get("end_date")
        if start and end and start > end:
            raise ValidationError(
                {"end_date": ["start_date は end_date 以前にしてください。"]}
            )
