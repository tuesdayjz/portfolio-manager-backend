"""ポートフォリオ関連のスキーマ。"""

from marshmallow import Schema, ValidationError, fields, validate, validates_schema

from app.enums import AllocationGroupBy, Interval, PerformanceRange
from app.schemas.common import (
    NON_NEGATIVE,
    WEIGHT,
    DateRangeQueryMixin,
)

_CASH_BALANCE_NOTE = (
    "Initial cash amount stored as a cash holding with quantity 1"
)


class PortfolioCreateSchema(Schema):
    """ポートフォリオの新規作成。所有者はログイン情報から解決する。"""

    name = fields.Str(required=True, metadata={"example": "Main Portfolio"})
    # Frontend defaults this to USD, but the API accepts it for future flexibility.
    currency = fields.Str(load_default="USD", metadata={"example": "USD"})
    cash_balance = fields.Float(
        load_default=0, validate=NON_NEGATIVE,
        metadata={"description": _CASH_BALANCE_NOTE, "example": 1000000},
    )


class PortfolioCreateResultSchema(Schema):
    """ポートフォリオ作成の軽量レスポンス。"""

    message = fields.Str(required=True, metadata={"example": "Portfolio created"})


class PortfolioCreateConflictSchema(Schema):
    """同一ユーザーがすでに portfolio を持つ場合のレスポンス。"""

    message = fields.Str(
        required=True,
        metadata={"example": "Portfolio already exists for this user."},
    )


class PortfolioSchema(PortfolioCreateSchema):
    """ポートフォリオ（詳細レスポンス用）。"""


class PortfolioSummarySchema(Schema):
    """ポートフォリオサマリー。

    評価額は Yahoo Finance または `asset_data_history` の価格で計算する。
    ヘッダー表示に必要な最小限の項目だけを返す。
    """

    currency = fields.Str(required=True, metadata={"example": "JPY"})
    cash_balance = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": _CASH_BALANCE_NOTE, "example": 1250000},
    )
    total_market_value = fields.Float(
        required=True, validate=NON_NEGATIVE, metadata={"example": 4220000}
    )
    total_return_percent = fields.Float(
        required=True,
        metadata={
            "description": "取得原価に対する損益率（％）。ヘッダーの Total Return。",
            "example": 8.17,
        },
    )


class AllocationItemSchema(Schema):
    """配分の 1 項目。`weight` は 0〜1 の割合。"""

    # `category` is the display bucket for the selected `group_by` value.
    category = fields.Str(
        required=True,
        metadata={
            "description": "集計基準ごとの区分名（資産クラス名・通貨コード・"
            "銘柄名・セクター名）",
            "example": "stock",
        },
    )
    value = fields.Float(
        required=True, validate=NON_NEGATIVE, metadata={"example": 4220000}
    )
    weight = fields.Float(required=True, validate=WEIGHT, metadata={"example": 0.72})
    holdings_count = fields.Int(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "この区分に含まれる保有銘柄数", "example": 12},
    )


class PortfolioAllocationSchema(Schema):
    """資産配分（1 つの集計基準ぶん）。評価額は市場価格ベース。

    どの基準で集計したかは `group_by` に入る。複数の基準を同時に描く画面
    （Allocations の資産クラス円グラフとセクター棒グラフなど）は、
    `group_by` を変えて複数回呼ぶ。
    """

    group_by = fields.Enum(
        AllocationGroupBy, by_value=True, required=True,
        metadata={"description": "集計基準", "example": "asset_type"},
    )
    currency = fields.Str(
        required=True,
        metadata={"description": "評価額の通貨（基準通貨）", "example": "JPY"},
    )
    total_value = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={
            "description": "`items` の value 合計。ドーナツ中央の Total Value。"
            "`group_by=sector` では株式ぶんだけの合計になる。",
            "example": 5860000,
        },
    )
    items = fields.List(
        fields.Nested(AllocationItemSchema),
        required=True,
        metadata={"description": "`value` の降順"},
    )
    as_of = fields.DateTime(
        required=True,
        metadata={
            "description": "配分の計算に使った市場価格の時刻。UI の「Last updated 5 mins ago」の元になる。",
            "example": "2026-07-30T14:25:00",
        },
    )


class AllocationTargetItemSchema(Schema):
    """目標配分の 1 件。"""

    name = fields.Str(required=True, metadata={"example": "stock"})
    target_weight = fields.Float(
        required=True, validate=WEIGHT, metadata={"example": 0.40}
    )


class AllocationTargetUpdateSchema(Schema):
    """資産クラス別の目標配分の設定。合計が 1（100%）になることを検証する。"""

    targets = fields.List(
        fields.Nested(AllocationTargetItemSchema),
        required=True,
        validate=validate.Length(min=1),
    )

    @validates_schema
    def check_targets(self, data, **kwargs):
        targets = data.get("targets") or []
        names = [item["name"] for item in targets]
        if len(names) != len(set(names)):
            raise ValidationError({"targets": ["資産クラスが重複しています。"]})
        total = sum(item["target_weight"] for item in targets)
        # 浮動小数の丸め誤差を許容する
        if abs(total - 1) > 1e-6:
            raise ValidationError(
                {"targets": ["target_weight の合計を 1（100%）にしてください。"]}
            )


class PerformanceGraphPointSchema(Schema):
    """推移グラフの 1 点。"""

    date = fields.Date(required=True, metadata={"example": "2026-07-28"})
    total_market_value = fields.Float(
        required=True, validate=NON_NEGATIVE, metadata={"example": 4220000}
    )


class PerformanceChangeSchema(Schema):
    """損益の 1 項目。金額と率をセットで返す。どちらも下落なら負。"""

    amount = fields.Float(
        required=True, metadata={"description": "損益額", "example": 149832.50}
    )
    percent = fields.Float(
        required=True, metadata={"description": "損益率（％）", "example": 12.4}
    )


class PerformanceMetricsSchema(Schema):
    """Performance 画面の指標カード（4 カラム）。"""

    portfolio_value = fields.Float(
        required=True, validate=NON_NEGATIVE,
        metadata={
            "description": "期間終了時点の評価額。現金を含む総資産額。",
            "example": 1247832.50,
        },
    )
    today = fields.Nested(
        PerformanceChangeSchema,
        required=True,
        metadata={
            "description": "今日の close price と前日の close price の差分で計算する騰落"
        },
    )
    period_return = fields.Nested(
        PerformanceChangeSchema,
        required=True,
        data_key="return",
        metadata={
            "description": "`range`（または start_date / end_date）で指定した"
            "対象期間の損益。今日の close price と対象期間の起点 close price の"
            "差分で計算する。"
        },
    )
    total_return = fields.Nested(
        PerformanceChangeSchema,
        required=True,
        metadata={"description": "運用開始来（全期間）の損益。対象期間の影響を受けない。"},
    )


class PerformanceGraphSchema(Schema):
    """ポートフォリオ推移グラフ。"""

    currency = fields.Str(required=True, metadata={"example": "JPY"})
    interval = fields.Enum(
        Interval, by_value=True, required=True, metadata={"example": "1d"}
    )
    range = fields.Enum(
        PerformanceRange, by_value=True, allow_none=True,
        metadata={
            "description": "期間セレクタで指定された値。start_date / end_date で"
            "直接指定された場合は null。",
            "example": "1y",
        },
    )
    start_date = fields.Date(required=True, metadata={"example": "2026-01-01"})
    end_date = fields.Date(required=True, metadata={"example": "2026-07-28"})
    metrics = fields.Nested(PerformanceMetricsSchema, required=True)
    # These returns compare today's close price with each range's start close price.
    return_1d = fields.Nested(
        PerformanceChangeSchema,
        required=True,
        metadata={"description": "今日の close price と前日の close price の差分"},
    )
    return_1w = fields.Nested(
        PerformanceChangeSchema,
        required=True,
        metadata={"description": "今日の close price と 1 週間前の close price の差分"},
    )
    return_1m = fields.Nested(
        PerformanceChangeSchema,
        required=True,
        metadata={"description": "今日の close price と 1 か月前の close price の差分"},
    )
    return_3m = fields.Nested(
        PerformanceChangeSchema,
        required=True,
        metadata={"description": "今日の close price と 3 か月前の close price の差分"},
    )
    return_YTD = fields.Nested(
        PerformanceChangeSchema,
        required=True,
        metadata={"description": "今日の close price と年初の close price の差分"},
    )
    return_1y = fields.Nested(
        PerformanceChangeSchema,
        required=True,
        metadata={"description": "今日の close price と 1 年前の close price の差分"},
    )
    return_total = fields.Nested(
        PerformanceChangeSchema,
        required=True,
        metadata={"description": "今日の close price と運用開始時点の close price の差分"},
    )
    points = fields.List(fields.Nested(PerformanceGraphPointSchema), required=True)


class AllocationQuerySchema(Schema):
    """GET /portfolios/allocation のクエリパラメータ。"""

    group_by = fields.Enum(
        AllocationGroupBy, by_value=True, required=True,
        metadata={"description": "集計基準", "example": "asset_type"},
    )


class PerformanceQuerySchema(DateRangeQueryMixin, Schema):
    """GET /portfolios/performance のクエリパラメータ。

    期間は `range`（1D〜ALL のセレクタ）か `start_date` / `end_date` の
    どちらかで指定する。両方指定した場合は日付のほうを優先する。
    """

    start_date = fields.Date(metadata={"example": "2026-07-26"})
    end_date = fields.Date(metadata={"example": "2026-07-28"})
    range = fields.Enum(
        PerformanceRange, by_value=True, load_default=PerformanceRange.ALL,
        metadata={"description": "期間セレクタ", "example": "all"},
    )
    interval = fields.Enum(
        Interval, by_value=True, load_default=Interval.DAILY,
        metadata={"description": "グラフの粒度", "example": "1d"},
    )
