"""アプリケーション設定。

OpenAPI (Swagger) 関連の設定もここに集約する。flask-smorest は
`API_*` / `OPENAPI_*` の設定キーを読んで仕様書と Swagger UI を生成する。
DB (Supabase) 接続も同様に `SQLALCHEMY_*` の設定キーで渡す。
"""

import os

from dotenv import load_dotenv

# 設定値はクラス属性として import 時に評価されるため、
# `create_app()` を待たずにここで .env を読み込んでおく。
load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class BaseConfig:
    SECRET_KEY = _env("SECRET_KEY", "dev-secret-key-change-me")
    SUPABASE_URL = _env(
        "SUPABASE_URL",
        "https://gvtxkyimbroikdfjsacb.supabase.co",
    )
    SUPABASE_ANON_KEY = _env("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY = _env("SUPABASE_SERVICE_ROLE_KEY")
    # portfolio 作成時の既定通貨。frontend default と合わせて USD にする。
    DEFAULT_BASE_CURRENCY = _env("DEFAULT_BASE_CURRENCY", "USD")

    # ---- Debug 用の認証バイパス -------------------------------------------
    # true にすると require_auth() が token 検証を飛ばし、DEBUG_USER_ID を
    # 現在の user として扱う。ローカルの手動確認専用。production では常に無効。
    AUTH_DISABLED = _env_bool("AUTH_DISABLED", False)
    DEBUG_USER_ID = _env("DEBUG_USER_ID")
    DEBUG_USER_EMAIL = _env("DEBUG_USER_EMAIL")

    JSON_SORT_KEYS = False
    PROPAGATE_EXCEPTIONS = True

    # ---- Database (Supabase / PostgreSQL) --------------------------------
    SQLALCHEMY_DATABASE_URI = _env("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        # Supabase は待機中のコネクションを黙って切るので、
        # 使う前に生存確認し、古いコネクションは寝かせずに捨てる。
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # ---- OpenAPI / Swagger ----------------------------------------------
    API_TITLE = "Portfolio Manager API"
    API_VERSION = "1.0.0"
    OPENAPI_VERSION = "3.0.3"
    OPENAPI_JSON_PATH = "openapi.json"
    OPENAPI_URL_PREFIX = "/"
    # Swagger UI: http://localhost:5001/docs
    OPENAPI_SWAGGER_UI_PATH = "/docs"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
    # ReDoc: http://localhost:5001/redoc
    OPENAPI_REDOC_PATH = "/redoc"
    OPENAPI_REDOC_URL = (
        "https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"
    )

    API_SPEC_OPTIONS = {
        "info": {
            "description": (
                "個人向けポートフォリオ管理 API。\n\n"
                "- `portfolio` … ポートフォリオの作成、サマリー、保有残高、資産配分、推移\n"
                "- `assets` … 資産マスタと市場価格\n"
                "- `transactions` … 売買の取引履歴\n\n"
                "実際の証券発注は行わない。売買は取引履歴の記録と保有残高の更新だけを行う。\n\n"
                "private なデータの対象ポートフォリオはログイン情報から解決する。"
                "クライアントは `portfolio_id` も `user_id` も送らない。"
                "公開の資産・市場データはポートフォリオに紐づかない。"
            ),
            "contact": {"name": "Portfolio Manager Team"},
        },
        "servers": [
            {"url": "/", "description": "Current Swagger UI origin"},
        ],
        "components": {
            "securitySchemes": {
                # Swagger UI の Authorize button から React 側の Supabase access token を渡す。
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "Supabase access token",
                    "description": (
                        "React が Supabase Auth で取得した access_token を "
                        "`Authorization: Bearer <token>` として送る。"
                    ),
                }
            }
        },
    }


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    # テストは require_auth を patch する前提なので、env の影響を受けないようにする。
    AUTH_DISABLED = False
    # 本番の Supabase を汚さないよう、テストは専用の DB に向ける。
    SQLALCHEMY_DATABASE_URI = _env("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    SQLALCHEMY_ENGINE_OPTIONS = {}


class ProductionConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = _env("DATABASE_URL")
    # env に AUTH_DISABLED が紛れ込んでも本番では絶対にバイパスさせない。
    AUTH_DISABLED = False


_CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    name = name or os.getenv("FLASK_ENV", "development")
    return _CONFIGS.get(name, DevelopmentConfig)
