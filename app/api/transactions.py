"""取引履歴エンドポイントの API 定義。

パスと入出力スキーマの宣言のみ。処理は未実装。
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.schemas.transaction import (
    TransactionBatchCreateSchema,
    TransactionItemSchema,
    TransactionPageSchema,
    TransactionQuerySchema,
    TransactionSchema,
)

blp = Blueprint(
    "transactions",
    __name__,
    url_prefix="/api/v1",
    description="取引履歴関連",
)

NOT_IMPLEMENTED = "未実装。API 設計のみ定義済み。"
PORTFOLIO_NOT_FOUND = "The specified portfolio does not exist"


@blp.route("/portfolios/transactions")
class PortfolioTransactionCollection(MethodView):
    @blp.arguments(TransactionQuerySchema, location="query")
    @blp.response(200, TransactionPageSchema)
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def get(self, args):
        """取引履歴を取得する。

        `transaction_type` / `asset_type` / `start_date` / `end_date` で
        絞り込める。検索や銘柄単位の細かい絞り込みはフロントエンド側で行う。
        日付はどちらも指定日を含む（inclusive）。

        各取引の実現損益は `realized_pl`、絞り込み後の全件の合計は `totals`
        で返す。`buy` は売却時まで損益が確定しないため、どちらも `sell` だけを
        対象にする。
        """
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/transactions")
class TransactionCollection(MethodView):
    @blp.arguments(TransactionItemSchema)
    @blp.response(201, TransactionSchema)
    @blp.alt_response(400, description="Cannot sell more than current holding")
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def post(self, payload):
        """取引を作成する。

        リクエストでは `asset_id` ではなく `ticker` と `name` で asset を特定する。
        新しい asset を追加する場合は、Yahoo Finance API から取得した情報を
        `asset_master` に登録してから取引を作成する。
        作成した取引の成功確認として、約定日時・銘柄・最終約定金額を返す。
        """
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/transactions/batch")
class TransactionBatch(MethodView):
    @blp.arguments(TransactionBatchCreateSchema)
    @blp.response(201, TransactionSchema(many=True))
    @blp.alt_response(400, description="One or more transactions are invalid")
    @blp.alt_response(404, description=PORTFOLIO_NOT_FOUND)
    def post(self, payload):
        """複数の取引を一括作成する。

        各 item は単件作成と同じ形で、成功時は各取引に対応する約定サマリーを返す。
        全件を検証してから作成するため、1 件でも不正なら何も作成しない。
        """
        abort(501, message=NOT_IMPLEMENTED)
