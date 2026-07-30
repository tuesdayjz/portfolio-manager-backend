import os
from pathlib import Path
from uuid import uuid4
import unittest
import warnings

from dotenv import load_dotenv
from supabase import create_client

warnings.simplefilter("ignore", DeprecationWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SupabasePrivateDataRlsTest(unittest.TestCase):
    """Integration test for private-table RLS ownership rules.

    This test creates two temporary Supabase Auth users and checks that each
    authenticated client can read only its own app rows.
    """

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
        self.password = f"Rls-test-{uuid4()}!"
        self.created_user_ids = []
        self.created_portfolio_ids = []
        self.created_holding_ids = []
        self.created_transaction_ids = []
        self.created_asset_ids = []

    def tearDown(self):
        if not getattr(self, "enabled", False):
            return

        for transaction_id in reversed(self.created_transaction_ids):
            self._delete_row("transactions", transaction_id)
        for holding_id in reversed(self.created_holding_ids):
            self._delete_row("holdings", holding_id)
        for portfolio_id in reversed(self.created_portfolio_ids):
            self._delete_row("portfolio", portfolio_id)
        for asset_id in reversed(self.created_asset_ids):
            self._delete_row("asset_master", asset_id)
        for user_id in reversed(self.created_user_ids):
            self._delete_row("users", user_id)
            try:
                self.service_client.auth.admin.delete_user(user_id)
            except Exception:
                pass

    def test_authenticated_users_can_read_only_their_own_private_data(self):
        run_id = uuid4().hex
        user_a = self._create_auth_user(f"rls-a-{run_id}@example.com")
        user_b = self._create_auth_user(f"rls-b-{run_id}@example.com")

        transaction_type_id = self._transaction_type_id()

        data_a = self._create_private_rows(
            user_a["id"],
            self._create_asset(run_id, "AAPL", "Apple Inc."),
            transaction_type_id,
            quantity=10,
            average_cost=150,
        )
        data_b = self._create_private_rows(
            user_b["id"],
            self._create_asset(run_id, "US10Y", "US Treasury 10Y Bond"),
            transaction_type_id,
            quantity=5,
            average_cost=980,
        )

        client_a = self._signed_in_client(user_a["email"])
        client_b = self._signed_in_client(user_b["email"])

        self._assert_client_sees_own_rows_only(client_a, data_a, data_b)
        self._assert_client_sees_own_rows_only(client_b, data_b, data_a)
        self._assert_private_writes_are_denied(client_a, data_a)

    def test_authenticated_users_can_read_only_their_own_holdings(self):
        run_id = uuid4().hex
        user_a = self._create_auth_user(f"rls-holdings-a-{run_id}@example.com")
        user_b = self._create_auth_user(f"rls-holdings-b-{run_id}@example.com")

        transaction_type_id = self._transaction_type_id()

        data_a = self._create_private_rows(
            user_a["id"],
            self._create_asset(run_id, "7203.T", "Toyota Motor Corp."),
            transaction_type_id,
            quantity=12,
            average_cost=2850,
        )
        data_b = self._create_private_rows(
            user_b["id"],
            self._create_asset(run_id, "MSFT", "Microsoft Corp."),
            transaction_type_id,
            quantity=3,
            average_cost=420,
        )

        client_a = self._signed_in_client(user_a["email"])
        client_b = self._signed_in_client(user_b["email"])

        self._assert_visible_id(
            client_a, "holdings", "id", data_a["holding_id"], data_b["holding_id"]
        )
        self._assert_visible_id(
            client_b, "holdings", "id", data_b["holding_id"], data_a["holding_id"]
        )

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

    def _create_asset(self, run_id, ticker, name):
        asset_type_id = self._first_id("asset_type")
        currency_id = self._first_id("currency")
        response = (
            self.service_client.table("asset_master")
            .insert(
                {
                    "ticker": f"{ticker}-{run_id[:8]}",
                    "name": name,
                    "asset_type_id": asset_type_id,
                    "currency_id": currency_id,
                }
            )
            .execute()
        )
        asset_id = response.data[0]["id"]
        self.created_asset_ids.append(asset_id)
        return asset_id

    def _first_id(self, table_name):
        response = self.service_client.table(table_name).select("id").limit(1).execute()
        if not response.data:
            self.skipTest(f"{table_name} needs at least one row for RLS tests.")
        return response.data[0]["id"]

    def _transaction_type_id(self):
        response = (
            self.service_client.table("transaction_type")
            .select("id")
            .eq("transaction_type", "buy")
            .limit(1)
            .execute()
        )
        if not response.data:
            self.skipTest("transaction_type row 'buy' is missing.")
        return response.data[0]["id"]

    def _create_private_rows(
        self,
        user_id,
        asset_id,
        transaction_type_id,
        *,
        quantity,
        average_cost,
    ):
        portfolio = (
            self.service_client.table("portfolio")
            .insert({"user_id": user_id, "name": "RLS Test Portfolio"})
            .execute()
            .data[0]
        )
        self.created_portfolio_ids.append(portfolio["id"])

        holding = (
            self.service_client.table("holdings")
            .insert(
                {
                    "portfolio_id": portfolio["id"],
                    "asset_id": asset_id,
                    "quantity": quantity,
                    "average_cost": average_cost,
                }
            )
            .execute()
            .data[0]
        )
        self.created_holding_ids.append(holding["id"])

        transaction = (
            self.service_client.table("transactions")
            .insert(
                {
                    "holding_id": holding["id"],
                    "transaction_type_id": transaction_type_id,
                    "trade_date": "2026-07-30",
                    "quantity": quantity,
                    "price": average_cost,
                    "fees": 0,
                }
            )
            .execute()
            .data[0]
        )
        self.created_transaction_ids.append(transaction["id"])

        return {
            "user_id": user_id,
            "portfolio_id": portfolio["id"],
            "holding_id": holding["id"],
            "transaction_id": transaction["id"],
        }

    def _signed_in_client(self, email):
        client = create_client(self.url, self.anon_key)
        client.auth.sign_in_with_password({"email": email, "password": self.password})
        client._rls_test_email = email
        return client

    def _assert_client_sees_own_rows_only(self, client, own, other):
        self._assert_visible_id(client, "users", "id", own["user_id"], other["user_id"])
        self._assert_visible_id(
            client, "portfolio", "id", own["portfolio_id"], other["portfolio_id"]
        )
        self._assert_visible_id(
            client, "holdings", "id", own["holding_id"], other["holding_id"]
        )
        self._assert_visible_id(
            client,
            "transactions",
            "id",
            own["transaction_id"],
            other["transaction_id"],
        )

    def _assert_visible_id(self, client, table_name, column_name, own_id, other_id):
        if table_name == "holdings":
            rows = (
                client.table(table_name)
                .select("id,asset_id,quantity,average_cost")
                .execute()
                .data
            )
        else:
            rows = client.table(table_name).select(column_name).execute().data
        visible_ids = {row[column_name] for row in rows}
        if table_name == "holdings":
            self._print_holdings_table(
                client, rows, own_id, other_id, getattr(client, "_rls_test_email", "")
            )
        self.assertIn(own_id, visible_ids, f"{table_name} should show own row")
        self.assertNotIn(other_id, visible_ids, f"{table_name} leaked another user row")

    def _print_holdings_table(self, client, holdings, own_id, other_id, reader_email):
        asset_ids = sorted({holding["asset_id"] for holding in holdings})
        assets = {}
        if asset_ids:
            asset_rows = (
                client.table("asset_master")
                .select("id,ticker,name")
                .in_("id", asset_ids)
                .execute()
                .data
            )
            assets = {asset["id"]: asset for asset in asset_rows}

        headers = ["asset_name"]
        rows = []
        for holding in holdings[:2]:
            asset = assets.get(holding["asset_id"], {})
            rows.append([asset.get("name") or "(unknown)"])
        if not rows:
            rows.append(["(none)"])

        print(f"reader: {reader_email}")
        self._print_table(headers, rows)

    def _print_table(self, headers, rows):
        widths = [
            max(len(header), *(len(row[index]) for row in rows))
            for index, header in enumerate(headers)
        ]
        line = "+" + "+".join(f"-{'-' * width}-" for width in widths) + "+"
        print(line)
        print("|" + "|".join(f" {header.ljust(width)} " for header, width in zip(headers, widths)) + "|")
        print(line)
        for row in rows:
            print("|" + "|".join(f" {value.ljust(width)} " for value, width in zip(row, widths)) + "|")
        print(line)

    def _assert_private_writes_are_denied(self, client, own):
        with self.assertRaises(Exception):
            (
                client.table("holdings")
                .insert(
                    {
                        "portfolio_id": own["portfolio_id"],
                        "asset_id": self.created_asset_ids[0],
                        "quantity": 2,
                        "average_cost": 200,
                    }
                )
                .execute()
            )

    def _delete_row(self, table_name, row_id):
        try:
            self.service_client.table(table_name).delete().eq("id", row_id).execute()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main(warnings="ignore")
