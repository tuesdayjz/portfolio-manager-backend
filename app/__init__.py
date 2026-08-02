import os

import click
from dotenv import load_dotenv
from flask import Flask

load_dotenv()

from app.api import register_blueprints
from app.config import get_config
from app.extensions import api, db, migrate


def create_app(config_name: str | None = None) -> Flask:
    """API 設計（OpenAPI 仕様）を生成するためのアプリ。

    現時点ではエンドポイントの中身は未実装で、仕様の定義だけを持つ。
    """
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    db.init_app(app)
    # マイグレーションの自動生成が拾えるよう、モデルを db より後に import する。
    from app import models  # noqa: F401

    migrate.init_app(app, db)

    api.init_app(app)
    register_blueprints(api)
    _register_cli(app)

    if app.config.get("AUTH_DISABLED"):
        app.logger.warning(
            "AUTH_DISABLED=true: token 検証を飛ばして DEBUG_USER_ID=%s として動作する。",
            app.config.get("DEBUG_USER_ID"),
        )

    return app


def _register_cli(app: Flask) -> None:
    @app.cli.command("export-openapi")
    @click.option(
        "-f",
        "--format",
        "fmt",
        type=click.Choice(["yaml", "json"]),
        default="yaml",
        help="出力形式。",
    )
    @click.option("-o", "--output", default=None, help="出力先ファイル。")
    def export_openapi(fmt, output):
        """OpenAPI 仕様をファイルに書き出す。

        組み込みの `flask openapi write` と違い、日本語を \\uXXXX に
        エスケープせずそのまま出力する（差分レビューできるようにするため）。
        """
        import json
        from pathlib import Path

        import yaml

        spec = api.spec.to_dict()
        target = Path(output or os.getenv("OPENAPI_OUTPUT", f"openapi.{fmt}"))

        if fmt == "yaml":
            text = yaml.safe_dump(spec, allow_unicode=True, sort_keys=True, indent=2)
        else:
            text = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"

        target.write_text(text, encoding="utf-8")
        click.echo(f"OpenAPI spec written to {target}")
