"""ポートフォリオエンドポイントの API 定義。

パスと入出力スキーマの宣言のみ。処理は未実装。
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.api.parameters import PORTFOLIO_ID
from app.schemas.holding import HoldingSchema, HoldingsQuerySchema
from app.schemas.portfolio import (
    PerformanceGraphSchema,
    PerformanceQuerySchema,
    PortfolioAllocationSchema,
    PortfolioCreateSchema,
    PortfolioQuerySchema,
    PortfolioSchema,
    PortfolioSummarySchema,
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
    @blp.arguments(PortfolioCreateSchema)
    @blp.response(201, PortfolioSchema)
    def post(self, payload):
        """ポートフォリオを作成する。"""
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/<int:portfolio_id>/summary", parameters=[PORTFOLIO_ID])
class PortfolioSummary(MethodView):
    @blp.arguments(PortfolioQuerySchema, location="query")
    @blp.response(200, PortfolioSummarySchema)
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def get(self, args, portfolio_id):
        """ポートフォリオサマリーを取得する。

        取得価額・評価額・総資産・含み損益を返す。評価額の市場価格は
        Yahoo Finance または `asset_data_history` から取得する想定で、
        `holdings` には保存しない。
        """
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/<int:portfolio_id>/holdings", parameters=[PORTFOLIO_ID])
class PortfolioHoldings(MethodView):
    @blp.arguments(HoldingsQuerySchema, location="query")
    @blp.response(200, HoldingSchema(many=True))
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def get(self, args, portfolio_id):
        """保有残高一覧を取得する。

        1 つのポートフォリオに含まれる複数の資産を返す。`current_price` は
        Yahoo Finance 由来の市場価格で、Supabase holdings には保存しない。
        """
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/<int:portfolio_id>/allocation", parameters=[PORTFOLIO_ID])
class PortfolioAllocation(MethodView):
    @blp.arguments(PortfolioQuerySchema, location="query")
    @blp.response(200, PortfolioAllocationSchema)
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def get(self, args, portfolio_id):
        """資産配分を取得する。

        資産種別・通貨・銘柄それぞれの内訳を返す。評価額計算の市場価格は
        Yahoo Finance から取得する想定。
        """
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/<int:portfolio_id>/performance", parameters=[PORTFOLIO_ID])
class PortfolioPerformance(MethodView):
    @blp.arguments(PerformanceQuerySchema, location="query")
    @blp.response(200, PerformanceGraphSchema)
    @blp.alt_response(400, description="start_date must be before or equal to end_date")
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def get(self, args, portfolio_id):
        """ポートフォリオ推移グラフを取得する。

        取引履歴から日付ごとの保有残高を復元し、`asset_data_history` または
        Yahoo Finance の価格データで評価額と含み損益を計算する想定。
        """
        abort(501, message=NOT_IMPLEMENTED)
