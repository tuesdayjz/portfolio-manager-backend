"""Supabase user RLS と isolation の tests。

RUN_SUPABASE_REAL_USER=false では mock user の RLS tests を実行する。
RUN_SUPABASE_REAL_USER=true では real user の RLS tests を実行する。

Supabase client はすべて `app.services.supabase` 経由で作成するため、
アプリ本体と同じ Flask config 経路を検証できる。mock user tests では
一時的な Auth / database rows を作成し、各 test の終了時に削除する。
"""

import os
from uuid import uuid4
import warnings

from tests.database_connection.helpers import SupabaseLiveTestCase

warnings.simplefilter("ignore", DeprecationWarning)

PUBLIC_TABLES = (
    ("currency", "currency,symbol"),
    ("asset_type", "asset_type"),
    ("asset_master", "ticker,name"),
    ("asset_data_history", "price_date,close_price"),
)


class SupabaseMockPrivateRlsTest(SupabaseLiveTestCase):
    """mock users が自分の private rows だけを参照できることを確認する。"""

    def setUp(self):
        self.load_supabase_settings(
            enabled_message=(
                "Set RUN_SUPABASE_REAL_USER=false to run mock-user private RLS tests."
            ),
            rls_user_type="mock",
        )
        self.init_supabase_clients()
        self.init_tracking()
        self.password = f"Rls-test-{uuid4()}!"

    def tearDown(self):
        if getattr(self, "enabled", False):
            self.cleanup_tracked_rows(delete_auth_users=True)

    def test_mock_users_can_read_only_own_private_rows(self):
        run_id = uuid4().hex
        user_a = self.create_auth_user(f"rls-a-{run_id}@example.com", self.password)
        user_b = self.create_auth_user(f"rls-b-{run_id}@example.com", self.password)

        data_a = self._create_private_rows(
            user_a["id"],
            self._create_asset(run_id, "AAPL", "Apple Inc."),
            quantity=10,
            average_cost=150,
        )
        data_b = self._create_private_rows(
            user_b["id"],
            self._create_asset(run_id, "US10Y", "US Treasury 10Y Bond"),
            quantity=5,
            average_cost=980,
        )

        client_a = self.signed_in_client(user_a["email"], self.password)
        client_b = self.signed_in_client(user_b["email"], self.password)
        client_a._rls_test_email = user_a["email"]
        client_b._rls_test_email = user_b["email"]

        self._assert_client_sees_own_rows_only(client_a, data_a, data_b)
        self._assert_client_sees_own_rows_only(client_b, data_b, data_a)
        self._assert_private_writes_are_denied(client_a, data_a)

    def test_mock_users_can_read_only_own_holding_assets(self):
        run_id = uuid4().hex
        user_a = self.create_auth_user(
            f"rls-holdings-a-{run_id}@example.com", self.password
        )
        user_b = self.create_auth_user(
            f"rls-holdings-b-{run_id}@example.com", self.password
        )

        data_a = self._create_private_rows(
            user_a["id"],
            self._create_asset(run_id, "7203.T", "Toyota Motor Corp."),
            quantity=12,
            average_cost=2850,
        )
        data_b = self._create_private_rows(
            user_b["id"],
            self._create_asset(run_id, "MSFT", "Microsoft Corp."),
            quantity=3,
            average_cost=420,
        )

        client_a = self.signed_in_client(user_a["email"], self.password)
        client_b = self.signed_in_client(user_b["email"], self.password)
        client_a._rls_test_email = user_a["email"]
        client_b._rls_test_email = user_b["email"]

        self._assert_visible_id(
            client_a, "holdings", "id", data_a["holding_id"], data_b["holding_id"]
        )
        self._assert_visible_id(
            client_b, "holdings", "id", data_b["holding_id"], data_a["holding_id"]
        )

    def _create_asset(self, run_id, ticker, name):
        response = (
            self.service_client.table("asset_master")
            .insert(
                {
                    "ticker": f"{ticker}-{run_id[:8]}",
                    "name": name,
                    "asset_type_id": self.first_id("asset_type"),
                    "currency_id": self.first_id("currency"),
                }
            )
            .execute()
        )
        asset_id = response.data[0]["id"]
        self.created_asset_ids.append(asset_id)
        return asset_id

    def _create_private_rows(self, user_id, asset_id, *, quantity, average_cost):
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
                    "transaction_type": "BUY",
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
            self.print_holdings_asset_names(
                client,
                rows,
                reader_email=getattr(client, "_rls_test_email", ""),
                limit=2,
            )
        self.assertIn(own_id, visible_ids, f"{table_name} should show own row")
        self.assertNotIn(other_id, visible_ids, f"{table_name} leaked another user row")

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


class SupabaseMockSharedTableRlsTest(SupabaseLiveTestCase):
    """mock users が shared tables を読めるが、直接書き込めないことを確認する。"""

    def setUp(self):
        self.load_supabase_settings(
            enabled_message=(
                "Set RUN_SUPABASE_REAL_USER=false to run mock-user shared RLS tests."
            ),
            rls_user_type="mock",
        )
        self.init_supabase_clients()
        self.init_tracking()
        self.password = f"Rls-public-test-{uuid4()}!"

    def tearDown(self):
        if getattr(self, "enabled", False):
            self.cleanup_tracked_rows(delete_auth_users=True)

    def test_mock_user_can_read_shared_tables(self):
        user = self.create_auth_user(
            f"rls-public-{uuid4().hex}@example.com", self.password
        )
        client = self.signed_in_client(user["email"], self.password)

        for table_name, columns in PUBLIC_TABLES:
            with self.subTest(table=table_name):
                rows = client.table(table_name).select(columns).limit(2).execute().data
                self.assertIsNotNone(rows)
                self._print_sample_table(user["email"], table_name, rows)

    def test_mock_user_cannot_write_shared_tables(self):
        user = self.create_auth_user(
            f"rls-public-write-{uuid4().hex}@example.com", self.password
        )
        client = self.signed_in_client(user["email"], self.password)

        with self.assertRaises(Exception):
            client.table("currency").insert(
                {"currency": f"RLS-{uuid4().hex[:6]}", "symbol": "RLS"}
            ).execute()

    def _print_sample_table(self, reader_email, table_name, rows):
        print(f"reader: {reader_email}")
        print(f"public table: {table_name}")
        if not rows:
            print("(no rows visible)")
            return

        headers = list(rows[0].keys())
        values = [[str(row.get(header, "")) for header in headers] for row in rows]
        self.print_table(headers, values)


class SupabaseRealUserRlsTest(SupabaseLiveTestCase):
    """real users が自分の private rows だけを参照できることを確認する。"""

    def setUp(self):
        self.load_supabase_settings(
            enabled_message=(
                "Set RUN_SUPABASE_REAL_USER=true to run real-user RLS tests."
            ),
            rls_user_type="real",
        )
        self.primary_email = os.getenv("SUPABASE_TEST_USER_EMAIL")
        self.primary_password = os.getenv("SUPABASE_TEST_USER_PASSWORD")
        if not self.primary_email or not self.primary_password:
            self.skipTest(
                "Set SUPABASE_TEST_USER_EMAIL and SUPABASE_TEST_USER_PASSWORD."
            )

        self.second_email = os.getenv("SUPABASE_SECOND_TEST_USER_EMAIL")
        self.second_password = os.getenv("SUPABASE_SECOND_TEST_USER_PASSWORD")
        self.bootstrap_data = (
            os.getenv("RUN_SUPABASE_REAL_USER_BOOTSTRAP_DATA") == "true"
        )
        self.init_supabase_clients()
        self.init_tracking()

    def tearDown(self):
        if getattr(self, "enabled", False):
            self.cleanup_tracked_rows(delete_auth_users=False)

    def test_real_user_can_read_only_own_holding_assets(self):
        client = self.signed_in_client(self.primary_email, self.primary_password)
        user = self.public_user(self.primary_email)
        self._ensure_real_user_has_holding(user, "Primary RLS Mock Asset")
        own_holding_ids = self.service_holding_ids_for_user(user["id"])
        if not own_holding_ids:
            self.skipTest(f"{self.primary_email} has no holdings to verify.")

        visible_holdings = self.visible_holdings(client)
        visible_ids = {holding["id"] for holding in visible_holdings}

        self.print_holdings_asset_names(
            client, visible_holdings, reader_email=self.primary_email
        )
        self.assertEqual(visible_ids, own_holding_ids)

    def test_real_user_cannot_directly_insert_holding(self):
        client = self.signed_in_client(self.primary_email, self.primary_password)
        user = self.public_user(self.primary_email)
        portfolio_id = self.service_portfolio_id_for_user(user["id"])
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

    def test_two_real_users_are_isolated_from_each_other(self):
        if not self.second_email or not self.second_password:
            self.skipTest(
                "Set SUPABASE_SECOND_TEST_USER_EMAIL and "
                "SUPABASE_SECOND_TEST_USER_PASSWORD for two-user RLS tests."
            )

        primary_client = self.signed_in_client(
            self.primary_email, self.primary_password
        )
        second_client = self.signed_in_client(self.second_email, self.second_password)

        primary_user = self.public_user(self.primary_email)
        second_user = self.public_user(self.second_email)
        self._ensure_real_user_has_holding(primary_user, "Primary RLS Mock Asset")
        self._ensure_real_user_has_holding(second_user, "Second RLS Mock Asset")
        primary_ids = self.service_holding_ids_for_user(primary_user["id"])
        second_ids = self.service_holding_ids_for_user(second_user["id"])
        if not primary_ids or not second_ids:
            self.skipTest(
                "Both real users need holdings for two-user RLS tests. "
                "Set RUN_SUPABASE_REAL_USER_BOOTSTRAP_DATA=true to create temporary "
                "mock holdings automatically."
            )

        primary_visible = {row["id"] for row in self.visible_holdings(primary_client)}
        second_visible = {row["id"] for row in self.visible_holdings(second_client)}

        self.assertTrue(primary_visible.isdisjoint(second_ids))
        self.assertTrue(second_visible.isdisjoint(primary_ids))
        print(f"RLS isolation passed: {self.primary_email} cannot see {self.second_email}")
        print(f"RLS isolation passed: {self.second_email} cannot see {self.primary_email}")

    def _service_asset_id(self):
        rows = self.service_client.table("asset_master").select("id").limit(1).execute().data
        if not rows:
            self.skipTest("asset_master needs at least one row.")
        return rows[0]["id"]

    def _ensure_real_user_has_holding(self, user, asset_name):
        if self.service_holding_ids_for_user(user["id"]):
            return
        if not self.bootstrap_data:
            return

        portfolio_id = self.service_portfolio_id_for_user(
            user["id"], skip_if_missing=False
        )
        if not portfolio_id:
            portfolio_id = self._create_portfolio(user["id"])
        asset_id = self._create_asset(asset_name)
        holding_id = self._create_holding(portfolio_id, asset_id)
        print(f"bootstrap data: created temporary holding for {user['email']}")
        return holding_id

    def _create_portfolio(self, user_id):
        portfolio = (
            self.service_client.table("portfolio")
            .insert({"user_id": user_id, "name": "Real User RLS Test Portfolio"})
            .execute()
            .data[0]
        )
        self.created_portfolio_ids.append(portfolio["id"])
        return portfolio["id"]

    def _create_asset(self, name):
        asset = (
            self.service_client.table("asset_master")
            .insert(
                {
                    "ticker": f"RLS-{uuid4().hex[:8]}",
                    "name": name,
                    "asset_type_id": self.first_id("asset_type"),
                    "currency_id": self.first_id("currency"),
                }
            )
            .execute()
            .data[0]
        )
        self.created_asset_ids.append(asset["id"])
        return asset["id"]

    def _create_holding(self, portfolio_id, asset_id):
        holding = (
            self.service_client.table("holdings")
            .insert(
                {
                    "portfolio_id": portfolio_id,
                    "asset_id": asset_id,
                    "quantity": 1,
                    "average_cost": 1,
                }
            )
            .execute()
            .data[0]
        )
        self.created_holding_ids.append(holding["id"])
        return holding["id"]


if __name__ == "__main__":
    import unittest

    unittest.main(warnings="ignore")
