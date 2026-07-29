"""ポートフォリオ関連のスキーマ。"""

from marshmallow import Schema, fields, validate

from app.enums import Interval
from app.schemas.common import (
    NON_NEGATIVE,
    POSITIVE_ID,
    DateRangeQueryMixin,
    UserIdQuerySchema,
)

_CASH_BALANCE_NOTE = (
    "Mock-only cash value; current Supabase schema has no cash balance column"
)


class PortfolioCreateSchema(Schema):
    """ポートフォリオの新規作成。"""

    user_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 101}
    )
    name = fields.Str(required=True, metadata={"example": "Main Portfolio"})
    currency = fields.Str(required=True, metadata={"example": "JPY"})
    cash_balance = fields.Float(
        load_default=0, validate=NON_NEGATIVE,
        metadata={"description": _CASH_BALANCE_NOTE, "example": 1000000},
    )


class PortfolioSchema(PortfolioCreateSchema):
    """ポートフォリオ（レスポンス）。"""

    portfolio_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 1}
    )


class PortfolioSummarySchema(Schema):
    """ポートフォリオサマリー。

    評価額は Yahoo Finance または `asset_data_history` の価格で計算する。
    """

    portfolio_id = fields.Int(required=True, metadata={"example": 1})
    user_id = fields.Int(required=True, metadata={"example": 101})
    currency = fields.Str(required=True, metadata={"example": "JPY"})
    cash_balance = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": _CASH_BALANCE_NOTE, "example": 1250000},
    )
    total_purchase_value = fields.Float(
        required=True, validate=NON_NEGATIVE, metadata={"example": 3901250}
    )
    total_market_value = fields.Float(
        required=True, validate=NON_NEGATIVE, metadata={"example": 4220000}
    )
    total_asset_value = fields.Float(
        required=True, validate=NON_NEGATIVE, metadata={"example": 5470000}
    )
    unrealized_gain_loss = fields.Float(required=True, metadata={"example": 318750})


class AllocationItemSchema(Schema):
    """配分の 1 項目。`weight` は 0〜1 の割合。"""

    name = fields.Str(required=True, metadata={"example": "stock"})
    value = fields.Float(
        required=True, validate=NON_NEGATIVE, metadata={"example": 4220000}
    )
    weight = fields.Float(
        required=True,
        validate=validate.Range(min=0, max=1),
        metadata={"example": 0.72},
    )


class PortfolioAllocationSchema(Schema):
    """資産配分。評価額は市場価格ベース。"""

    by_asset_type = fields.List(fields.Nested(AllocationItemSchema), required=True)
    by_currency = fields.List(fields.Nested(AllocationItemSchema), required=True)
    by_asset = fields.List(fields.Nested(AllocationItemSchema), required=True)


class PerformanceGraphPointSchema(Schema):
    """推移グラフの 1 点。"""

    date = fields.Date(required=True, metadata={"example": "2026-07-28"})
    total_purchase_value = fields.Float(
        required=True, validate=NON_NEGATIVE, metadata={"example": 3901250}
    )
    total_market_value = fields.Float(
        required=True, validate=NON_NEGATIVE, metadata={"example": 4220000}
    )
    unrealized_gain_loss = fields.Float(required=True, metadata={"example": 318750})


class PerformanceGraphSchema(Schema):
    """ポートフォリオ推移グラフ。"""

    user_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 101}
    )
    portfolio_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 1}
    )
    currency = fields.Str(required=True, metadata={"example": "JPY"})
    interval = fields.Enum(
        Interval, by_value=True, required=True, metadata={"example": "1d"}
    )
    points = fields.List(fields.Nested(PerformanceGraphPointSchema), required=True)


class PortfolioQuerySchema(UserIdQuerySchema):
    """所有者チェックだけを行う GET のクエリパラメータ。"""


class PerformanceQuerySchema(DateRangeQueryMixin, UserIdQuerySchema):
    """GET /portfolios/{portfolio_id}/performance のクエリパラメータ。"""

    start_date = fields.Date(metadata={"example": "2026-07-26"})
    end_date = fields.Date(metadata={"example": "2026-07-28"})
    interval = fields.Enum(
        Interval, by_value=True, load_default=Interval.DAILY,
        metadata={"description": "グラフの粒度", "example": "1d"},
    )
