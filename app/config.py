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


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

    JSON_SORT_KEYS = False
    PROPAGATE_EXCEPTIONS = True

    # ---- Database (Supabase / PostgreSQL) --------------------------------
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
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
                "- `assets` … 資産マスタと Yahoo Finance の市場価格\n"
                "- `transactions` … 売買の取引履歴\n\n"
                "実際の証券発注は行わない。売買は取引履歴の記録と保有残高の更新だけを行う。\n\n"
                "private なデータの対象ポートフォリオはログイン情報から解決する。"
                "クライアントは `portfolio_id` も `user_id` も送らない。"
                "公開の資産・市場データはポートフォリオに紐づかない。"
            ),
            "contact": {"name": "Portfolio Manager Team"},
        },
        "servers": [
            # macOS の AirPlay レシーバーが 5000 を占有し 403 を返すため 5001 を使う。
            {"url": "http://localhost:5001", "description": "Local development"},
        ],
    }


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    # 本番の Supabase を汚さないよう、テストは専用の DB に向ける。
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    SQLALCHEMY_ENGINE_OPTIONS: dict = {}


class ProductionConfig(BaseConfig):
    DEBUG = False


_CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    name = name or os.getenv("FLASK_ENV", "development")
    return _CONFIGS.get(name, DevelopmentConfig)
