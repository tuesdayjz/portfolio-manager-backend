"""取引履歴エンドポイントの API 定義。

パスと入出力スキーマの宣言のみ。処理は未実装。
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.api.parameters import PORTFOLIO_ID
from app.schemas.transaction import (
    TransactionBatchCreateSchema,
    TransactionItemSchema,
    TransactionQuerySchema,
    TransactionSchema,
)

blp = Blueprint(
    "transactions",
    __name__,
    url_prefix="/api/v1/portfolios",
    description="取引履歴関連",
)

NOT_IMPLEMENTED = "未実装。API 設計のみ定義済み。"
PORTFOLIO_NOT_FOUND = "The specified portfolio does not exist"


@blp.route("/<int:portfolio_id>/transactions", parameters=[PORTFOLIO_ID])
class TransactionCollection(MethodView):
    @blp.arguments(TransactionQuerySchema, location="query")
    @blp.response(200, TransactionSchema(many=True))
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def get(self, args, portfolio_id):
        """取引履歴を取得する。

        `asset_id` / `start_date` / `end_date` で絞り込める。
        日付はどちらも指定日を含む（inclusive）。
        """
        abort(501, message=NOT_IMPLEMENTED)

    @blp.arguments(TransactionItemSchema)
    @blp.response(201, TransactionSchema)
    @blp.alt_response(400, description="Cannot sell more than current holding")
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def post(self, payload, portfolio_id):
        """取引を登録し、保有残高（holdings）を更新する。

        `buy` は保有数量を増やして平均取得単価を再計算し、`sell` は保有数量を
        減らす。保有数量を超える売却は 400。
        """
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/<int:portfolio_id>/transactions/batch", parameters=[PORTFOLIO_ID])
class TransactionBatch(MethodView):
    @blp.arguments(TransactionBatchCreateSchema)
    @blp.response(201, TransactionSchema(many=True))
    @blp.alt_response(400, description="One or more transactions are invalid")
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def post(self, payload, portfolio_id):
        """複数の取引を一括登録し、各取引ごとに保有残高を更新する。

        ネットワーク通信回数を減らし、データベースの一括登録・一括更新効率を
        高める。全件を検証してから更新するため、1 件でも不正なら何も更新しない。
        """
        abort(501, message=NOT_IMPLEMENTED)
