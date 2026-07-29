"""アプリケーション設定。

OpenAPI (Swagger) 関連の設定もここに集約する。flask-smorest は
`API_*` / `OPENAPI_*` の設定キーを読んで仕様書と Swagger UI を生成する。
"""

import os


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

    JSON_SORT_KEYS = False
    PROPAGATE_EXCEPTIONS = True

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
                "- `assets` … 銘柄マスタ（ユーザーごとに登録）\n"
                "- `transactions` … 売買・配当などの取引履歴\n"
                "- `holdings` … 取引履歴から算出した保有状況（移動平均法）\n"
                "- `user` … 認証中ユーザーのプロフィール\n\n"
                "認証は `X-API-Key` ヘッダーで行う。"
                "`POST /api/v1/user/register` のレスポンスで一度だけ API キーが返る。"
            ),
            "contact": {"name": "Portfolio Manager Team"},
        },
        "servers": [
            # macOS の AirPlay レシーバーが 5000 を占有し 403 を返すため 5001 を使う。
            {"url": "http://localhost:5001", "description": "Local development"},
        ],
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "ユーザー登録時に払い出される API キー。",
                }
            }
        },
        "security": [{"ApiKeyAuth": []}],
    }

    # 一覧系のページネーション既定値
    PAGINATION_DEFAULT_PAGE_SIZE = 50
    PAGINATION_MAX_PAGE_SIZE = 200


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True


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
