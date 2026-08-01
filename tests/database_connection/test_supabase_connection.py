"""Supabase connection setup、基本 query、例外、teardown の tests。"""

import warnings

from app.services.supabase import close_supabase_client, get_supabase_client
from tests.database_connection.helpers import (
    SupabaseLiveTestCase,
)

warnings.simplefilter("ignore", DeprecationWarning)

SUPABASE_TABLES = (
    "users",
    "portfolio",
    "asset_master",
    "currency",
    "asset_type",
    "asset_data_history",
    "holdings",
    "transactions",
)


class SupabaseConnectionTest(SupabaseLiveTestCase):
    """ローカル test configuration で Supabase client が接続できることを確認する。

    この tests では data の create/update/delete は行わない。
    設定済み client が接続できること、軽量 read を実行できること、
    不正な config を例外として扱えること、HTTP resources を解放できることだけを確認する。
    """

    def setUp(self):
        self.load_supabase_settings(
            enabled_var="RUN_SUPABASE_CONNECTION_TESTS",
            enabled_message=(
                "Set RUN_SUPABASE_CONNECTION_TESTS=true to run live connection tests."
            ),
            require_anon=True,
            require_service=True,
        )

    def test_connection_setup_uses_config_and_active_client(self):
        client = self.anon_client_or_skip()
        self.assertIsNotNone(client)
        self.assertEqual(str(client.supabase_url).rstrip("/"), self.url.rstrip("/"))
        self.assertEqual(client.supabase_key, self.anon_key)

        response = client.table("currency").select("id").limit(1).execute()
        self.assertIsNotNone(response.data)
        print("connection setup: anon client is active")
        close_supabase_client(client)

    def test_basic_read_query_returns_reference_rows(self):
        client = self.service_client_or_skip()
        response = (
            client.table("currency")
            .select("id,currency,symbol")
            .limit(1)
            .execute()
        )
        self.assertIsInstance(response.data, list)
        print(f"basic operation: currency query returned {len(response.data)} row(s)")
        close_supabase_client(client)

    def test_service_role_can_read_core_tables(self):
        client = self.service_client_or_skip()
        self._assert_client_can_read_tables(client, "service role")
        close_supabase_client(client)

    def test_invalid_key_is_reported_as_exception(self):
        self.app.config["SUPABASE_INVALID_TEST_KEY"] = "invalid-local-test-key"
        client = get_supabase_client("SUPABASE_INVALID_TEST_KEY")
        with self.assertRaises(Exception):
            client.table("currency").select("id").limit(1).execute()
        print("exception handling: invalid key raised an exception")
        close_supabase_client(client)

    def test_client_resources_can_be_released(self):
        client = self.anon_client_or_skip()
        released = close_supabase_client(client)
        self.assertTrue(released)
        print("teardown: Supabase HTTP client resources released")

    def _assert_client_can_read_tables(self, client, key_label):
        for table_name in SUPABASE_TABLES:
            with self.subTest(key=key_label, table=table_name):
                response = client.table(table_name).select("id").limit(1).execute()
                self.assertIsNotNone(response.data)
                print(f"{key_label} key can read {table_name}")


if __name__ == "__main__":
    import unittest

    unittest.main(warnings="ignore")
