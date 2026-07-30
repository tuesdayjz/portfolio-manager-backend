import os
from pathlib import Path
import unittest
import warnings

from dotenv import load_dotenv
from supabase import create_client

warnings.simplefilter("ignore", DeprecationWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SupabaseRealUserRlsTest(unittest.TestCase):
    """Live RLS tests that use existing Supabase Auth users."""

    def setUp(self):
        load_dotenv(PROJECT_ROOT / ".env")
        self.url = os.getenv("SUPABASE_URL")
        self.anon_key = os.getenv("SUPABASE_ANON_KEY")
        self.service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self.enabled = os.getenv("RUN_SUPABASE_REAL_USER_RLS_TESTS") == "true"
        if not self.enabled:
            self.skipTest(
                "Set RUN_SUPABASE_REAL_USER_RLS_TESTS=true to run real-user RLS tests."
            )
        if not self.url or not self.anon_key or not self.service_role_key:
            self.skipTest("Supabase URL, anon key, or service role key is missing.")

        self.primary_email = os.getenv("SUPABASE_TEST_USER_EMAIL")
        self.primary_password = os.getenv("SUPABASE_TEST_USER_PASSWORD")
        if not self.primary_email or not self.primary_password:
            self.skipTest(
                "Set SUPABASE_TEST_USER_EMAIL and SUPABASE_TEST_USER_PASSWORD."
            )

        self.second_email = os.getenv("SUPABASE_SECOND_TEST_USER_EMAIL")
        self.second_password = os.getenv("SUPABASE_SECOND_TEST_USER_PASSWORD")
        self.service_client = create_client(self.url, self.service_role_key)

    def test_real_user_can_read_only_own_holdings(self):
        client = self._signed_in_client(self.primary_email, self.primary_password)
        user = self._public_user(self.primary_email)
        own_holding_ids = self._service_holding_ids_for_user(user["id"])
        if not own_holding_ids:
            self.skipTest(f"{self.primary_email} has no holdings to verify.")

        visible_holdings = self._visible_holdings(client)
        visible_ids = {holding["id"] for holding in visible_holdings}

        self._print_real_user_holdings(self.primary_email, client, visible_holdings)
        self.assertEqual(visible_ids, own_holding_ids)

    def test_real_user_cannot_insert_holding_directly(self):
        client = self._signed_in_client(self.primary_email, self.primary_password)
        user = self._public_user(self.primary_email)
        portfolio_id = self._service_portfolio_id_for_user(user["id"])
        asset_id = self._service_asset_id()

        with self.assertRaises(Exception):
            (
                client.table("holdings")
                .insert(
                    {
                        "portfolio_id": portfolio_id,
                        "asset_id": asset_id,
                        "quantity": 1,
                        "average_cost": 1,
                    }
                )
                .execute()
            )

    def test_two_real_users_cannot_see_each_others_holdings(self):
        if not self.second_email or not self.second_password:
            self.skipTest(
                "Set SUPABASE_SECOND_TEST_USER_EMAIL and "
                "SUPABASE_SECOND_TEST_USER_PASSWORD for two-user RLS tests."
            )

        primary_client = self._signed_in_client(
            self.primary_email, self.primary_password
        )
        second_client = self._signed_in_client(self.second_email, self.second_password)

        primary_user = self._public_user(self.primary_email)
        second_user = self._public_user(self.second_email)
        primary_ids = self._service_holding_ids_for_user(primary_user["id"])
        second_ids = self._service_holding_ids_for_user(second_user["id"])
        if not primary_ids or not second_ids:
            self.skipTest("Both real users need holdings for two-user RLS tests.")

        primary_visible = {row["id"] for row in self._visible_holdings(primary_client)}
        second_visible = {row["id"] for row in self._visible_holdings(second_client)}

        self.assertTrue(primary_visible.isdisjoint(second_ids))
        self.assertTrue(second_visible.isdisjoint(primary_ids))

    def _signed_in_client(self, email, password):
        client = create_client(self.url, self.anon_key)
        client.auth.sign_in_with_password({"email": email, "password": password})
        return client

    def _public_user(self, email):
        rows = (
            self.service_client.table("users")
            .select("id,email")
            .eq("email", email)
            .limit(1)
            .execute()
            .data
        )
        if not rows:
            self.skipTest(f"public.users row is missing for {email}.")
        return rows[0]

    def _service_portfolio_id_for_user(self, user_id):
        rows = (
            self.service_client.table("portfolio")
            .select("id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
            .data
        )
        if not rows:
            self.skipTest(f"User {user_id} has no portfolio.")
        return rows[0]["id"]

    def _service_holding_ids_for_user(self, user_id):
        portfolio_rows = (
            self.service_client.table("portfolio")
            .select("id")
            .eq("user_id", user_id)
            .execute()
            .data
        )
        portfolio_ids = [row["id"] for row in portfolio_rows]
        if not portfolio_ids:
            return set()
        holding_rows = (
            self.service_client.table("holdings")
            .select("id")
            .in_("portfolio_id", portfolio_ids)
            .execute()
            .data
        )
        return {row["id"] for row in holding_rows}

    def _service_asset_id(self):
        rows = self.service_client.table("asset_master").select("id").limit(1).execute().data
        if not rows:
            self.skipTest("asset_master needs at least one row.")
        return rows[0]["id"]

    def _visible_holdings(self, client):
        return (
            client.table("holdings")
            .select("id,asset_id,quantity,average_cost")
            .execute()
            .data
        )

    def _print_real_user_holdings(self, email, client, holdings):
        print(f"reader: {email}")
        if not holdings:
            print("(no holdings visible)")
            return

        asset_ids = sorted({holding["asset_id"] for holding in holdings})
        asset_rows = (
            client.table("asset_master")
            .select("id,name")
            .in_("id", asset_ids)
            .execute()
            .data
        )
        asset_by_id = {asset["id"]: asset for asset in asset_rows}
        rows = [
            [asset_by_id.get(holding["asset_id"], {}).get("name", "(unknown)")]
            for holding in holdings
        ]
        self._print_table(["asset_name"], rows)

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


if __name__ == "__main__":
    unittest.main(warnings="ignore")
