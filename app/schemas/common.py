"""スキーマ共通の部品。"""

from marshmallow import Schema, ValidationError, fields, validate, validates_schema

#: 数量・金額の下限（0 以上）。
NON_NEGATIVE = validate.Range(min=0)

#: 数量の下限（0 より大きい）。
POSITIVE = validate.Range(min=0, min_inclusive=False)

#: ID の下限（1 以上）。
POSITIVE_ID = validate.Range(min=1)

#: 構成比・目標比率（0〜1）。
WEIGHT = validate.Range(min=0, max=1)


class ErrorSchema(Schema):
    """flask-smorest の abort() が返すエラーレスポンス。"""

    code = fields.Int(metadata={"description": "HTTP ステータスコード"})
    status = fields.Str(metadata={"description": "HTTP ステータス名"})
    message = fields.Str(metadata={"description": "エラーの概要"})
    errors = fields.Dict(
        metadata={"description": "バリデーションエラーの詳細（フィールド単位）"}
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


class PaginationQueryMixin:
    """ページングするクエリスキーマ用の `page` / `per_page`。

    一覧画面は「Showing 5 of 24 positions」「Page 1 of 5」のように総件数と
    ページ数を出すため、レスポンスは `PaginationSchema` を添えて返す。
    """

    page = fields.Int(
        load_default=1,
        validate=validate.Range(min=1),
        metadata={"description": "1 始まりのページ番号", "example": 1},
    )
    per_page = fields.Int(
        load_default=20,
        validate=validate.Range(min=1, max=100),
        metadata={"description": "1 ページあたりの件数", "example": 20},
    )


class PaginationSchema(Schema):
    """一覧レスポンスのページ情報。"""

    page = fields.Int(
        required=True, validate=validate.Range(min=1), metadata={"example": 1}
    )
    per_page = fields.Int(
        required=True, validate=validate.Range(min=1), metadata={"example": 5}
    )
    total_items = fields.Int(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "フィルタ適用後の総件数", "example": 24},
    )
    total_pages = fields.Int(
        required=True, validate=NON_NEGATIVE, metadata={"example": 5}
    )


class MessageSchema(Schema):
    """処理結果だけを返すレスポンス。"""

    message = fields.Str(required=True, metadata={"example": "Updated"})
