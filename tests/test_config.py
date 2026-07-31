"""Flask 設定と Supabase client 設定の unit tests。

このファイルは unittest の対象。`app/config.py` が環境変数を正しく読み、
`app.services.supabase` が直接 env を読むのではなく Flask `app.config` から
client を作成することを確認する。
"""

import importlib
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from flask import Flask

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class SupabaseConfigTest(unittest.TestCase):
    """プロジェクト設定の挙動を確認する。"""

    def test_supabase_config_reads_environment(self):
        """Supabase keys が環境変数から TestingConfig に反映されること。"""

        env = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "anon-test-key",
            "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
            "DEFAULT_BASE_CURRENCY": "USD",
        }

        with patch.dict(os.environ, env):
            config_module = importlib.reload(importlib.import_module("app.config"))
            config = config_module.get_config("testing")

        self.assertEqual(config.SUPABASE_URL, "https://example.supabase.co")
        self.assertEqual(config.SUPABASE_ANON_KEY, "anon-test-key")
        self.assertEqual(config.SUPABASE_SERVICE_ROLE_KEY, "service-role-test-key")
        self.assertEqual(config.DEFAULT_BASE_CURRENCY, "USD")

        importlib.reload(config_module)

    def test_supabase_config_has_safe_local_defaults(self):
        """ローカル secret が未設定でも安全な test default になること。"""

        env = {
            "SUPABASE_URL": "",
            "SUPABASE_ANON_KEY": "",
            "SUPABASE_SERVICE_ROLE_KEY": "",
            "DEFAULT_BASE_CURRENCY": "",
        }

        with patch.dict(os.environ, env, clear=True):
            config_module = importlib.reload(importlib.import_module("app.config"))
            config = config_module.get_config("testing")

        self.assertEqual(
            config.SUPABASE_URL,
            "https://gvtxkyimbroikdfjsacb.supabase.co",
        )
        self.assertIsNone(config.SUPABASE_ANON_KEY)
        self.assertIsNone(config.SUPABASE_SERVICE_ROLE_KEY)
        self.assertEqual(config.DEFAULT_BASE_CURRENCY, "JPY")

        importlib.reload(config_module)

    def test_supabase_clients_use_flask_app_config(self):
        """Supabase client が Flask app.config の値を使うこと。"""

        from app.services.supabase import get_supabase_anon_client

        app = Flask(__name__)
        app.config.update(
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_ANON_KEY": "anon-test-key",
            }
        )

        with app.app_context():
            client = get_supabase_anon_client()

        self.assertEqual(
            str(client.supabase_url).rstrip("/"), "https://example.supabase.co"
        )
        self.assertEqual(client.supabase_key, "anon-test-key")

    def test_supabase_client_requires_flask_config_key(self):
        """必要な config key がない場合は明確に失敗すること。"""

        from app.services.supabase import get_supabase_service_client

        app = Flask(__name__)
        app.config.update(
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "",
            }
        )

        with app.app_context(), self.assertRaises(RuntimeError):
            get_supabase_service_client()
