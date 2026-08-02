"""ポートフォリオエンドポイントの API 定義。

POST / は作成処理まで実装済み。その他のエンドポイントは現時点では
仕様の宣言のみで、処理は未実装。
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.auth import require_auth
from app.schemas.holding import HoldingsPageSchema, HoldingsQuerySchema
from app.schemas.portfolio import (
    AllocationQuerySchema,
    PerformanceGraphSchema,
    PerformanceQuerySchema,
    PortfolioAllocationSchema,
    PortfolioCreateConflictSchema,
    PortfolioCreateResultSchema,
    PortfolioCreateSchema,
    PortfolioSummarySchema,
)
from app.services.portfolio import (
    create_portfolio,
    get_portfolio_holdings,
    get_portfolio_summary,
)

blp = Blueprint(
    "portfolio",
    __name__,
    url_prefix="/api/v1/portfolios",
    description="ポートフォリオ関連",
)

NOT_IMPLEMENTED = "未実装。API 設計のみ定義済み。"
PORTFOLIO_NOT_FOUND = "The specified portfolio does not exist"


@blp.route("/")
class PortfolioCollection(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.arguments(PortfolioCreateSchema)
    @blp.response(201, PortfolioCreateResultSchema)
    @blp.alt_response(
        409,
        schema=PortfolioCreateConflictSchema,
        description="Portfolio already exists for this user",
        example={"message": "Portfolio already exists for this user."},
    )
    def post(self, payload):
        """ポートフォリオを作成する。"""
        require_auth()
        return create_portfolio(payload)


@blp.route("/summary")
class PortfolioSummary(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.response(200, PortfolioSummarySchema)
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def get(self):
        """ポートフォリオサマリーを取得する。

        現金残高・評価額・損益率を返す。評価額の市場価格は
        Yahoo Finance または `asset_data_history` から取得する想定で、
        `holdings` には保存しない。
        """
        require_auth()
        return get_portfolio_summary()


@blp.route("/holdings")
class PortfolioHoldings(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.arguments(HoldingsQuerySchema, location="query")
    @blp.response(200, HoldingsPageSchema)
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def get(self, args):
        """保有残高一覧を取得する。

        1 つのポートフォリオに含まれる複数の資産を `items` に、フィルタ適用後の
        全件を集計した合計行を `totals` に入れて返す。`current_price` は
        Yahoo Finance 由来の市場価格で、Supabase holdings には保存しない。
        """
        require_auth()
        return get_portfolio_holdings(args)


@blp.route("/allocation")
class PortfolioAllocation(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.arguments(AllocationQuerySchema, location="query")
    @blp.response(200, PortfolioAllocationSchema)
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def get(self, args):
        """資産配分を取得する。

        `group_by` で指定した 1 つの基準（資産クラス・通貨・銘柄・セクター）で
        集計した内訳を返す。評価額計算の市場価格は Yahoo Finance から取得する想定。
        """
        require_auth()
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/performance")
class PortfolioPerformance(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.arguments(PerformanceQuerySchema, location="query")
    @blp.response(200, PerformanceGraphSchema)
    @blp.alt_response(400, description="start_date must be before or equal to end_date")
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def get(self, args):
        """ポートフォリオ推移グラフを取得する。

        取引履歴から日付ごとの保有残高を復元し、`asset_data_history` または
        Yahoo Finance の価格データで評価額と含み損益を計算する想定。
        `today` は今日の close price と前日の close price の差分で計算する。
        各期間の return は、今日の close price と対象期間の起点 close price
        （例: `1w` なら 1 週間前）との差分で計算する。
        """
        require_auth()
        abort(501, message=NOT_IMPLEMENTED)
