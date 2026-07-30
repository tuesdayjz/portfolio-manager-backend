"""ポートフォリオ関連のスキーマ。"""

from marshmallow import Schema, ValidationError, fields, validate, validates_schema

from app.enums import Interval, PerformanceRange
from app.schemas.common import (
    NON_NEGATIVE,
    POSITIVE_ID,
    WEIGHT,
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
    unrealized_gain_loss_percent = fields.Float(
        required=True,
        metadata={
            "description": "取得原価に対する損益率（％）。ヘッダーの Total Return。",
            "example": 8.17,
        },
    )
    day_change = fields.Float(
        required=True,
        metadata={"description": "前日終値からの評価損益の変化額", "example": 42150}
    )
    day_change_percent = fields.Float(
        required=True,
        metadata={"description": "前日終値からの騰落率（％）", "example": 1.01},
    )
    holdings_count = fields.Int(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "保有銘柄数", "example": 24},
    )
    asset_type_count = fields.Int(
        required=True, validate=NON_NEGATIVE,
        metadata={
            "description": "資産クラス数。UI の「6 Asset Classes」。",
            "example": 6,
        },
    )
    as_of = fields.DateTime(
        required=True,
        metadata={
            "description": "評価に使った市場価格の時刻",
            "example": "2026-07-30T14:25:00",
        },
    )


class AllocationItemSchema(Schema):
    """配分の 1 項目。`weight` は 0〜1 の割合。"""

    name = fields.Str(required=True, metadata={"example": "stock"})
    value = fields.Float(
        required=True, validate=NON_NEGATIVE, metadata={"example": 4220000}
    )
    weight = fields.Float(required=True, validate=WEIGHT, metadata={"example": 0.72})


class AllocationDriftItemSchema(AllocationItemSchema):
    """目標配分との乖離（Strategic Allocation Deviation & Drift Monitoring）。

    目標を設定していない資産クラスでは `target_weight` と `deviation` を null に
    する。`deviation` は `weight - target_weight` なので、目標超過なら正。
    """

    holdings_count = fields.Int(
        required=True, validate=NON_NEGATIVE,
        metadata={"description": "この資産クラスの保有銘柄数", "example": 12},
    )
    target_weight = fields.Float(
        allow_none=True, validate=WEIGHT,
        metadata={"description": "目標構成比（0〜1）", "example": 0.40},
    )
    deviation = fields.Float(
        allow_none=True,
        metadata={"description": "目標との差（weight − target_weight）", "example": 0.05},
    )


class PortfolioAllocationSchema(Schema):
    """資産配分。評価額は市場価格ベース。"""

    by_asset_type = fields.List(
        fields.Nested(AllocationDriftItemSchema),
        required=True,
        metadata={"description": "資産クラス別。目標比率と乖離を含む。"},
    )
    by_currency = fields.List(fields.Nested(AllocationItemSchema), required=True)
    by_asset = fields.List(fields.Nested(AllocationItemSchema), required=True)
    by_sector = fields.List(
        fields.Nested(AllocationItemSchema),
        required=True,
        metadata={"description": "株式のセクター別配分（Equity Sector Exposure）"},
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

    user_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 101}
    )
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
    total_purchase_value = fields.Float(
        required=True, validate=NON_NEGATIVE, metadata={"example": 3901250}
    )
    total_market_value = fields.Float(
        required=True, validate=NON_NEGATIVE, metadata={"example": 4220000}
    )
    unrealized_gain_loss = fields.Float(required=True, metadata={"example": 318750})
    benchmark_value = fields.Float(
        allow_none=True, validate=NON_NEGATIVE,
        metadata={
            "description": "同額を benchmark に投資した場合の評価額。"
            "benchmark 未指定、または当日の指数値が取れない場合は null。",
            "example": 4100000,
        },
    )


class BenchmarkSchema(Schema):
    """比較対象のベンチマーク指数（S&P 500 など）。"""

    symbol = fields.Str(
        required=True,
        metadata={"description": "Yahoo Finance symbol", "example": "^GSPC"},
    )
    name = fields.Str(required=True, metadata={"example": "S&P 500"})
    return_percent = fields.Float(
        required=True,
        metadata={
            "description": "対象期間の指数騰落率（％）。UI の「S&P 500 (+8.2% YTD)」。",
            "example": 8.2,
        },
    )


class PerformerSchema(Schema):
    """最も上がった／下がった銘柄（Best / Worst Performer）。"""

    asset_id = fields.Int(
        required=True, validate=POSITIVE_ID, metadata={"example": 1}
    )
    symbol = fields.Str(required=True, metadata={"example": "7203.T"})
    name = fields.Str(required=True, metadata={"example": "Toyota Motor Corp."})
    return_percent = fields.Float(
        required=True,
        metadata={"description": "対象期間の損益率（％）", "example": 48.2},
    )


class PerformanceMetricsSchema(Schema):
    """Performance 画面の指標カード。

    保有銘柄が 1 件もない、または期間内のデータ点が足りない場合、
    `best_performer` / `worst_performer` / `sharpe_ratio` は null になる。
    """

    total_return = fields.Float(
        required=True,
        metadata={"description": "対象期間の損益額", "example": 149832.50},
    )
    total_return_percent = fields.Float(
        required=True, metadata={"description": "対象期間の損益率（％）", "example": 12.4}
    )
    best_performer = fields.Nested(PerformerSchema, allow_none=True)
    worst_performer = fields.Nested(PerformerSchema, allow_none=True)
    sharpe_ratio = fields.Float(
        allow_none=True,
        metadata={
            "description": "リスク調整後リターン。日次リターンの平均÷標準偏差を年率換算する。",
            "example": 1.42,
        },
    )


class MonthlyReturnSchema(Schema):
    """月次リターンとベンチマーク超過（Historical Returns Benchmark Excess Audit）。"""

    month = fields.Str(
        required=True,
        validate=validate.Regexp(r"^\d{4}-\d{2}$"),
        metadata={"description": "対象月（YYYY-MM）", "example": "2026-05"},
    )
    portfolio_return_percent = fields.Float(
        required=True, metadata={"example": 2.41}
    )
    benchmark_return_percent = fields.Float(
        required=True, allow_none=True, metadata={"example": 1.60}
    )
    excess_return_percent = fields.Float(
        required=True,
        allow_none=True,
        metadata={
            "description": "ベンチマークに対する超過リターン"
            "（portfolio_return_percent − benchmark_return_percent）",
            "example": 0.81,
        },
    )


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
    benchmark = fields.Nested(
        BenchmarkSchema,
        allow_none=True,
        metadata={"description": "benchmark 未指定なら null"},
    )
    metrics = fields.Nested(PerformanceMetricsSchema, required=True)
    points = fields.List(fields.Nested(PerformanceGraphPointSchema), required=True)
    monthly_returns = fields.List(
        fields.Nested(MonthlyReturnSchema),
        required=True,
        metadata={"description": "新しい月が先頭。対象期間に満たない月は含めない。"},
    )


class PortfolioQuerySchema(UserIdQuerySchema):
    """所有者チェックだけを行う GET のクエリパラメータ。"""


class PerformanceQuerySchema(DateRangeQueryMixin, UserIdQuerySchema):
    """GET /portfolios/{portfolio_id}/performance のクエリパラメータ。

    期間は `range`（1D〜ALL のセレクタ）か `start_date` / `end_date` の
    どちらかで指定する。両方指定した場合は日付のほうを優先する。
    """

    start_date = fields.Date(metadata={"example": "2026-07-26"})
    end_date = fields.Date(metadata={"example": "2026-07-28"})
    range = fields.Enum(
        PerformanceRange, by_value=True, load_default=PerformanceRange.SIX_MONTHS,
        metadata={"description": "期間セレクタ", "example": "1y"},
    )
    interval = fields.Enum(
        Interval, by_value=True, load_default=Interval.DAILY,
        metadata={"description": "グラフの粒度", "example": "1d"},
    )
    benchmark = fields.Str(
        metadata={
            "description": "比較する指数の Yahoo Finance symbol。省略すると"
            "ベンチマーク系列を返さない。",
            "example": "^GSPC",
        }
    )
