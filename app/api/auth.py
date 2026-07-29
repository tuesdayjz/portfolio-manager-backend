"""認証エンドポイントの API 定義。

パスと入出力スキーマの宣言のみ。処理は未実装。
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.schemas.auth import (
    AuthResponseSchema,
    LoginRequestSchema,
    LogoutResponseSchema,
    SignupRequestSchema,
)

blp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/v1/auth",
    description="認証関連",
)

NOT_IMPLEMENTED = "未実装。API 設計のみ定義済み。"


@blp.route("/signup")
class Signup(MethodView):
    @blp.arguments(SignupRequestSchema)
    @blp.response(201, AuthResponseSchema)
    @blp.alt_response(409, description="Email already exists")
    def post(self, payload):
        """ユーザー登録を行う。

        Mock/設計版ではユーザーとデフォルトポートフォリオを作成する想定。
        本番では Supabase Auth の signUp を使用し、password は public schema に
        保存しない。
        """
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/login")
class Login(MethodView):
    @blp.arguments(LoginRequestSchema)
    @blp.response(200, AuthResponseSchema)
    @blp.alt_response(401, description="Invalid email or password")
    def post(self, payload):
        """ログインを行う。

        本番では Supabase Auth の signInWithPassword を使用し、access token を
        private API の認証に使う想定。
        """
        abort(501, message=NOT_IMPLEMENTED)


@blp.route("/logout")
class Logout(MethodView):
    @blp.response(200, LogoutResponseSchema)
    def post(self):
        """ログアウトを行う。

        本番ではクライアント側で token/session を破棄する想定。
        """
        abort(501, message=NOT_IMPLEMENTED)
