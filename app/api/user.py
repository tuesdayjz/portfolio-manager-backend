"""ユーザーエンドポイントの API 定義。

パスと入出力スキーマの宣言のみ。処理は未実装。
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.schemas.user import (
    UserRegisteredSchema,
    UserRegisterSchema,
    UserSchema,
    UserUpdateSchema,
)

blp = Blueprint(
    "user",
    __name__,
    url_prefix="/api/v1/user",
    description="ユーザー登録と、認証中ユーザーのプロフィール操作。",
)

NOT_IMPLEMENTED = "未実装。API 設計のみ定義済み。"


@blp.route("/register")
class UserRegister(MethodView):
    @blp.arguments(UserRegisterSchema)
    @blp.response(201, UserRegisteredSchema)
    @blp.alt_response(409, description="同じメールアドレスが登録済み")
    @blp.doc(security=[])  # 登録だけは認証不要
    def post(self, payload):
        """ユーザーを登録して API キーを払い出す。

        API キーが平文で返るのはこのレスポンスだけ。以降は取得できない。
        """
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/")
class UserProfile(MethodView):
    @blp.response(200, UserSchema)
    @blp.alt_response(401, description="認証エラー")
    def get(self):
        """認証中ユーザーのプロフィールを取得する。"""
        abort(501, message=NOT_IMPLEMENTED)

    @blp.arguments(UserUpdateSchema)
    @blp.response(200, UserSchema)
    @blp.alt_response(401, description="認証エラー")
    def patch(self, payload):
        """認証中ユーザーのプロフィールを部分更新する。"""
        abort(501, message=NOT_IMPLEMENTED)

    @blp.response(204)
    @blp.alt_response(401, description="認証エラー")
    def delete(self):
        """認証中ユーザーを削除する。銘柄・取引もまとめて削除される。"""
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/api-key/rotate")
class ApiKeyRotate(MethodView):
    @blp.response(200, UserRegisteredSchema)
    @blp.alt_response(401, description="認証エラー")
    def post(self):
        """API キーを再発行する。古いキーは即座に無効になる。"""
        abort(501, message=NOT_IMPLEMENTED)
