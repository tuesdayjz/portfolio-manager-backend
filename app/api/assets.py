"""資産エンドポイントの API 定義。

パスと入出力スキーマの宣言のみ。処理は未実装。
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.api.parameters import ASSET_ID
from app.schemas.asset import (
    AssetInfoSchema,
    PriceHistoryItemSchema,
    PriceHistoryQuerySchema,
)

blp = Blueprint(
    "assets",
    __name__,
    url_prefix="/api/v1/assets",
    description="資産関連（資産情報、Yahoo Finance価格）",
)

NOT_IMPLEMENTED = "未実装。API 設計のみ定義済み。"
ASSET_NOT_FOUND = "The specified asset does not exist"


@blp.route("/<int:asset_id>/", parameters=[ASSET_ID])
class AssetItem(MethodView):
    @blp.response(200, AssetInfoSchema)
    @blp.alt_response(404, description=ASSET_NOT_FOUND)
    def get(self, asset_id):
        """資産マスタ情報を取得する。

        公開データなので `user_id` は不要。保有数量や取得価額は
        `GET /portfolios/holdings` で取得する。
        """
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/<int:asset_id>/price-history", parameters=[ASSET_ID])
class AssetPriceHistory(MethodView):
    @blp.arguments(PriceHistoryQuerySchema, location="query")
    @blp.response(200, PriceHistoryItemSchema(many=True))
    @blp.alt_response(404, description=ASSET_NOT_FOUND)
    def get(self, args, asset_id):
        """過去の市場価格を取得する。

        `asset_master.symbol` を使って Yahoo Finance の履歴を取得するか、
        `asset_data_history` のキャッシュ済み終値を読む想定。
        """
        abort(501, message=NOT_IMPLEMENTED)
