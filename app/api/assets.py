"""銘柄エンドポイントの API 定義。

パスと入出力スキーマの宣言のみ。処理は未実装。
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.schemas.asset import (
    AssetCreateSchema,
    AssetQuerySchema,
    AssetSchema,
    AssetUpdateSchema,
)

blp = Blueprint(
    "assets",
    __name__,
    url_prefix="/api/v1/assets",
    description="銘柄マスタ。取引を登録する前にここへ銘柄を作成する。",
)

NOT_IMPLEMENTED = "未実装。API 設計のみ定義済み。"


@blp.route("/")
class AssetCollection(MethodView):
    @blp.arguments(AssetQuerySchema, location="query")
    @blp.response(200, AssetSchema(many=True))
    @blp.alt_response(401, description="認証エラー")
    @blp.paginate()
    def get(self, args, pagination_parameters):
        """登録済みの銘柄一覧を取得する。"""
        abort(501, message=NOT_IMPLEMENTED)

    @blp.arguments(AssetCreateSchema)
    @blp.response(201, AssetSchema)
    @blp.alt_response(401, description="認証エラー")
    @blp.alt_response(409, description="同じ symbol が登録済み")
    def post(self, payload):
        """銘柄を新規登録する。`symbol` はユーザー内で一意。"""
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/<string:asset_id>")
class AssetItem(MethodView):
    @blp.response(200, AssetSchema)
    @blp.alt_response(401, description="認証エラー")
    @blp.alt_response(404, description="銘柄が見つからない")
    def get(self, asset_id):
        """銘柄を 1 件取得する。"""
        abort(501, message=NOT_IMPLEMENTED)

    @blp.arguments(AssetUpdateSchema)
    @blp.response(200, AssetSchema)
    @blp.alt_response(401, description="認証エラー")
    @blp.alt_response(404, description="銘柄が見つからない")
    def patch(self, payload, asset_id):
        """銘柄を部分更新する。"""
        abort(501, message=NOT_IMPLEMENTED)

    @blp.response(204)
    @blp.alt_response(401, description="認証エラー")
    @blp.alt_response(404, description="銘柄が見つからない")
    @blp.alt_response(409, description="取引が紐づいているため削除できない")
    def delete(self, asset_id):
        """銘柄を削除する。取引が 1 件でも紐づいている場合は削除できない。"""
        abort(501, message=NOT_IMPLEMENTED)
