"""保有状況エンドポイントの API 定義。

パスと入出力スキーマの宣言のみ。処理は未実装。
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.schemas.holding import (
    HoldingSchema,
    HoldingsQuerySchema,
    HoldingsResponseSchema,
)

blp = Blueprint(
    "holdings",
    __name__,
    url_prefix="/api/v1/holdings",
    description=(
        "取引履歴から算出した保有状況（読み取り専用）。"
        "取得原価は移動平均法。時価情報は保持していないため含み損益は返さない。"
    ),
)

NOT_IMPLEMENTED = "未実装。API 設計のみ定義済み。"


@blp.route("/")
class HoldingCollection(MethodView):
    @blp.arguments(HoldingsQuerySchema, location="query")
    @blp.response(200, HoldingsResponseSchema)
    @blp.alt_response(401, description="認証エラー")
    def get(self, args):
        """現在（または指定日時点）の保有状況を算出して返す。

        取引を時系列に再生して数量・平均取得単価・実現損益・受取配当を求める。
        `summary` は通貨ごとの合計で、為替レートを持たないため通貨横断の合算はしない。
        """
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/<string:asset_id>")
class HoldingItem(MethodView):
    @blp.arguments(HoldingsQuerySchema, location="query")
    @blp.response(200, HoldingSchema)
    @blp.alt_response(401, description="認証エラー")
    @blp.alt_response(404, description="銘柄が見つからない / 取引が 1 件もない")
    def get(self, args, asset_id):
        """特定銘柄の保有状況を取得する。"""
        abort(501, message=NOT_IMPLEMENTED)
