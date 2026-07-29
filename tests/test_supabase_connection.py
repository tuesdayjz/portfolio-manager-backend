import os
from pathlib import Path
import unittest
import warnings

warnings.simplefilter("ignore", DeprecationWarning)

from dotenv import load_dotenv
from supabase import create_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPABASE_TABLES = (
    "users",
    "portfolio",
    "asset_master",
    "currency",
    "asset_type",
    "transaction_type",
    "asset_data_history",
    "holdings",
    "transactions",
)


class SupabaseConnectionTest(unittest.TestCase):
    def setUp(self):
        load_dotenv(PROJECT_ROOT / ".env")
        self.url = os.getenv("SUPABASE_URL")
        self.anon_key = os.getenv("SUPABASE_ANON_KEY")
        self.service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    def test_anon_key_can_read_all_supabase_tables(self):
        if not self.url or not self.anon_key:
            self.skipTest("SUPABASE_URL or SUPABASE_ANON_KEY is not configured.")

        client = create_client(self.url, self.anon_key)
        self._assert_client_can_read_tables(client, "anon")

    def test_service_role_key_can_read_all_supabase_tables(self):
        if not self.url or not self.service_role_key:
            self.skipTest(
                "SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not configured."
            )

        client = create_client(self.url, self.service_role_key)
        self._assert_client_can_read_tables(client, "service role")

    def _assert_client_can_read_tables(self, client, key_label):
        for table_name in SUPABASE_TABLES:
            with self.subTest(key=key_label, table=table_name):
                response = client.table(table_name).select("id").limit(1).execute()
                self.assertIsNotNone(response.data)
                print(f"{key_label} key can read {table_name}")


if __name__ == "__main__":
    unittest.main(warnings="ignore")
