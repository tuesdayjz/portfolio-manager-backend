import importlib
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class SupabaseConfigTest(unittest.TestCase):
    def test_supabase_config_reads_environment(self):
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
