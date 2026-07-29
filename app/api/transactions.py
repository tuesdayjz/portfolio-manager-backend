"""取引エンドポイントの API 定義。

パスと入出力スキーマの宣言のみ。処理は未実装。
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.schemas.transaction import (
    TransactionCreateSchema,
    TransactionQuerySchema,
    TransactionSchema,
    TransactionUpdateSchema,
)

blp = Blueprint(
    "transactions",
    __name__,
    url_prefix="/api/v1/transactions",
    description="売買・配当などの取引履歴。保有状況はここから算出される。",
)

NOT_IMPLEMENTED = "未実装。API 設計のみ定義済み。"


@blp.route("/")
class TransactionCollection(MethodView):
    @blp.arguments(TransactionQuerySchema, location="query")
    @blp.response(200, TransactionSchema(many=True))
    @blp.alt_response(401, description="認証エラー")
    @blp.paginate()
    def get(self, args, pagination_parameters):
        """取引履歴を検索する。

        `asset_id` / `start_date` / `end_date` で絞り込める。
        日付は UTC 基準で、どちらも指定日を含む（inclusive）。
        """
        abort(501, message=NOT_IMPLEMENTED)

    @blp.arguments(TransactionCreateSchema)
    @blp.response(201, TransactionSchema)
    @blp.alt_response(401, description="認証エラー")
    @blp.alt_response(422, description="バリデーションエラー / 銘柄が存在しない")
    def post(self, payload):
        """取引を登録する。通貨は対象銘柄の設定を引き継ぐ。"""
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/<string:transaction_id>")
class TransactionItem(MethodView):
    @blp.response(200, TransactionSchema)
    @blp.alt_response(401, description="認証エラー")
    @blp.alt_response(404, description="取引が見つからない")
    def get(self, transaction_id):
        """取引を 1 件取得する。"""
        abort(501, message=NOT_IMPLEMENTED)

    @blp.arguments(TransactionUpdateSchema)
    @blp.response(200, TransactionSchema)
    @blp.alt_response(401, description="認証エラー")
    @blp.alt_response(404, description="取引が見つからない")
    def patch(self, payload, transaction_id):
        """取引を部分更新する。銘柄の変更はできない。"""
        abort(501, message=NOT_IMPLEMENTED)

    @blp.response(204)
    @blp.alt_response(401, description="認証エラー")
    @blp.alt_response(404, description="取引が見つからない")
    def delete(self, transaction_id):
        """取引を削除する。"""
        abort(501, message=NOT_IMPLEMENTED)
