"""ポートフォリオエンドポイントの API 定義。"""

from flask.views import MethodView
from flask_smorest import Blueprint

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
from app.schemas.transaction import CashTransactionItemSchema, CashTransactionSchema
from app.services.performance import get_portfolio_performance
from app.services.portfolio import (
    create_portfolio,
    get_portfolio_allocation,
    get_portfolio_holdings,
    get_portfolio_summary,
)
from app.services.transaction import create_cash_transaction

blp = Blueprint(
    "portfolio",
    __name__,
    url_prefix="/api/v1/portfolios",
    description="ポートフォリオ関連",
)

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


@blp.route("/capital")
class PortfolioCapital(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.arguments(CashTransactionItemSchema)
    @blp.response(201, CashTransactionSchema)
    @blp.alt_response(400, description="Cannot withdraw more than current cash balance")
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def post(self, payload):
        """現金を入金・出金する。

        `transaction_type` は `deposit`（入金）か `withdrawal`（出金）のみ。
        現金残高だけを更新し、他の holding には影響しない。出金額が残高を
        超える場合は 400。
        """
        require_auth()
        return create_cash_transaction(payload)


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
        集計した内訳を返す。評価額計算の市場価格は Yahoo Finance から取得する。
        `group_by=sector` 以外は cash holding も 1 区分として含める。
        """
        require_auth()
        return get_portfolio_allocation(args)


@blp.route("/performance")
class PortfolioPerformance(MethodView):
    @blp.doc(security=[{"bearerAuth": []}])
    @blp.arguments(PerformanceQuerySchema, location="query")
    @blp.response(200, PerformanceGraphSchema)
    # start_date > end_date は PerformanceQuerySchema の検証で 422 になる。
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def get(self, args):
        """ポートフォリオ推移グラフを取得する。

        取引履歴から日付ごとの保有残高を復元し、`asset_data_history` の
        close price で日次の評価額を組み立てる。各期間の return は、期間中の
        買付・売却を調整した資産総額の損益と、その投下資産に対する比率で計算する。
        `asset_type` を指定すると、その資産クラスの
        holding だけを集計した推移を返す（`cash` 以外では現金を含めない）。
        """
        require_auth()
        return get_portfolio_performance(args)
