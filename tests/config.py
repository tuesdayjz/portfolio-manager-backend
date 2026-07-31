"""テスト共通の設定ヘルパー。

このファイルは unittest ではない。通常のプロジェクト `.env` を読み込んだあと、
ローカル専用のテスト値を `tests/.env` で上書きするために使う。
実際のテスト用パスワードは `tests/.env` にだけ置き、Git には
`tests/.env.example` だけをコミットする。
"""

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_ENV_FILE = PROJECT_ROOT / "tests" / ".env"
ROOT_ENV_FILE = PROJECT_ROOT / ".env"


def load_test_env():
    """プロジェクト共通 env を読み込み、テスト専用 env で上書きする。

    Flask アプリ本体の設定ソースは `app/config.py`。このヘルパーは
    テストが `create_app("testing")` で Flask app を作成する前に、
    必要な環境変数を準備するだけに留める。
    """

    load_dotenv(ROOT_ENV_FILE, override=True)
    load_dotenv(TEST_ENV_FILE, override=True)
