import os
from pathlib import Path
from uuid import uuid4
import unittest
import warnings

from dotenv import load_dotenv
from supabase import create_client

warnings.simplefilter("ignore", DeprecationWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_TABLES = (
    ("currency", "currency,symbol"),
    ("asset_type", "asset_type"),
    ("transaction_type", "transaction_type"),
    ("asset_master", "ticker,name"),
    ("asset_data_history", "price_date,close_price"),
)


class SupabasePublicTableRlsTest(unittest.TestCase):
    """Live RLS tests for shared/reference tables."""

    def setUp(self):
        load_dotenv(PROJECT_ROOT / ".env")
        self.url = os.getenv("SUPABASE_URL")
        self.anon_key = os.getenv("SUPABASE_ANON_KEY")
        self.service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self.enabled = os.getenv("RUN_SUPABASE_RLS_TESTS") == "true"
        if not self.enabled:
            self.skipTest("Set RUN_SUPABASE_RLS_TESTS=true to run live RLS tests.")
        if not self.url or not self.anon_key or not self.service_role_key:
            self.skipTest("Supabase URL, anon key, or service role key is missing.")

        self.service_client = create_client(self.url, self.service_role_key)
        self.password = f"Rls-public-test-{uuid4()}!"
        self.created_user_ids = []

    def tearDown(self):
        if not getattr(self, "enabled", False):
            return

        for user_id in reversed(self.created_user_ids):
            self._delete_row("users", user_id)
            try:
                self.service_client.auth.admin.delete_user(user_id)
            except Exception:
                pass

    def test_authenticated_user_can_read_public_tables(self):
        user = self._create_auth_user(f"rls-public-{uuid4().hex}@example.com")
        client = self._signed_in_client(user["email"])

        for table_name, columns in PUBLIC_TABLES:
            with self.subTest(table=table_name):
                rows = client.table(table_name).select(columns).limit(2).execute().data
                self.assertIsNotNone(rows)
                self._print_sample_table(user["email"], table_name, rows)

    def test_authenticated_user_cannot_write_public_tables(self):
        user = self._create_auth_user(f"rls-public-write-{uuid4().hex}@example.com")
        client = self._signed_in_client(user["email"])

        with self.assertRaises(Exception):
            client.table("currency").insert(
                {"currency": f"RLS-{uuid4().hex[:6]}", "symbol": "RLS"}
            ).execute()

    def _create_auth_user(self, email):
        response = self.service_client.auth.admin.create_user(
            {
                "email": email,
                "password": self.password,
                "email_confirm": True,
            }
        )
        user = response.user
        user_id = str(user.id)
        self.created_user_ids.append(user_id)
        self.service_client.table("users").insert(
            {"id": user_id, "email": email}
        ).execute()
        return {"id": user_id, "email": email}

    def _signed_in_client(self, email):
        client = create_client(self.url, self.anon_key)
        client.auth.sign_in_with_password({"email": email, "password": self.password})
        return client

    def _print_sample_table(self, reader_email, table_name, rows):
        print(f"reader: {reader_email}")
        print(f"public table: {table_name}")
        if not rows:
            print("(no rows visible)")
            return

        headers = list(rows[0].keys())
        values = [[str(row.get(header, "")) for header in headers] for row in rows]
        self._print_table(headers, values)

    def _print_table(self, headers, rows):
        widths = [
            max(len(header), *(len(row[index]) for row in rows))
            for index, header in enumerate(headers)
        ]
        line = "+" + "+".join(f"-{'-' * width}-" for width in widths) + "+"
        print(line)
        print(
            "|"
            + "|".join(
                f" {header.ljust(width)} " for header, width in zip(headers, widths)
            )
            + "|"
        )
        print(line)
        for row in rows:
            print(
                "|"
                + "|".join(
                    f" {value.ljust(width)} " for value, width in zip(row, widths)
                )
                + "|"
            )
        print(line)

    def _delete_row(self, table_name, row_id):
        try:
            self.service_client.table(table_name).delete().eq("id", row_id).execute()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main(warnings="ignore")
