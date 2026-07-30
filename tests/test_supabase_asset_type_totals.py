import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import unittest
import warnings

from dotenv import load_dotenv
from supabase import create_client

warnings.simplefilter("ignore", DeprecationWarning)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SupabaseAssetTypeTotalsTest(unittest.TestCase):
    """Live database test for stock/bond holding totals."""

    def setUp(self):
        load_dotenv(PROJECT_ROOT / ".env")
        self.url = os.getenv("SUPABASE_URL")
        self.service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self.enabled = os.getenv("RUN_SUPABASE_DB_TESTS") == "true"
        if not self.enabled:
            self.skipTest("Set RUN_SUPABASE_DB_TESTS=true to run live DB tests.")
        if not self.url or not self.service_role_key:
            self.skipTest("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing.")

        self.client = create_client(self.url, self.service_role_key)
        self.password = f"Db-test-{uuid4()}!"
        self.created_user_ids = []
        self.created_portfolio_ids = []
        self.created_holding_ids = []
        self.created_asset_ids = []

    def tearDown(self):
        if not getattr(self, "enabled", False):
            return

        for holding_id in reversed(self.created_holding_ids):
            self._delete_row("holdings", holding_id)
        for portfolio_id in reversed(self.created_portfolio_ids):
            self._delete_row("portfolio", portfolio_id)
        for asset_id in reversed(self.created_asset_ids):
            self._delete_row("asset_master", asset_id)
        for user_id in reversed(self.created_user_ids):
            self._delete_row("users", user_id)
            try:
                self.client.auth.admin.delete_user(user_id)
            except Exception:
                pass

    def test_calculates_stock_and_bond_totals_from_database_rows(self):
        run_id = uuid4().hex
        user_id = self._create_user(run_id)
        portfolio_id = self._create_portfolio(user_id)
        stock_asset_id = self._create_asset(run_id, "stock", "A")
        second_stock_asset_id = self._create_asset(run_id, "stock", "B")
        bond_asset_id = self._create_asset(run_id, "bond")

        self._create_holding(portfolio_id, stock_asset_id, quantity="3", average_cost="10")
        self._create_holding(
            portfolio_id, second_stock_asset_id, quantity="4", average_cost="5"
        )
        self._create_holding(portfolio_id, bond_asset_id, quantity="2", average_cost="50")

        totals = self._asset_type_totals(portfolio_id)

        self.assertEqual(totals["stock"], Decimal("50"))
        self.assertEqual(totals["bond"], Decimal("100"))

    def _create_user(self, run_id):
        email = f"db-total-{run_id}@example.com"
        response = self.client.auth.admin.create_user(
            {
                "email": email,
                "password": self.password,
                "email_confirm": True,
            }
        )
        user_id = str(response.user.id)
        self.client.table("users").insert(
            {"id": user_id, "email": email}
        ).execute()
        self.created_user_ids.append(user_id)
        return user_id

    def _create_portfolio(self, user_id):
        response = (
            self.client.table("portfolio")
            .insert({"user_id": user_id, "name": "DB Totals Test Portfolio"})
            .execute()
        )
        portfolio_id = response.data[0]["id"]
        self.created_portfolio_ids.append(portfolio_id)
        return portfolio_id

    def _create_asset(self, run_id, asset_type, suffix=""):
        response = (
            self.client.table("asset_master")
            .insert(
                {
                    "ticker": f"{asset_type.upper()}{suffix}-{run_id[:8]}",
                    "name": f"{asset_type.title()} DB Totals Test Asset",
                    "asset_type_id": self._asset_type_id(asset_type),
                    "currency_id": self._first_id("currency"),
                }
            )
            .execute()
        )
        asset_id = response.data[0]["id"]
        self.created_asset_ids.append(asset_id)
        return asset_id

    def _create_holding(self, portfolio_id, asset_id, *, quantity, average_cost):
        response = (
            self.client.table("holdings")
            .insert(
                {
                    "portfolio_id": portfolio_id,
                    "asset_id": asset_id,
                    "quantity": quantity,
                    "average_cost": average_cost,
                }
            )
            .execute()
        )
        self.created_holding_ids.append(response.data[0]["id"])

    def _asset_type_totals(self, portfolio_id):
        holdings = (
            self.client.table("holdings")
            .select("asset_id,quantity,average_cost")
            .eq("portfolio_id", portfolio_id)
            .execute()
            .data
        )
        asset_ids = {row["asset_id"] for row in holdings}
        assets = (
            self.client.table("asset_master")
            .select("id,asset_type_id")
            .in_("id", list(asset_ids))
            .execute()
            .data
        )
        asset_type_ids = {row["asset_type_id"] for row in assets}
        asset_types = (
            self.client.table("asset_type")
            .select("id,asset_type")
            .in_("id", list(asset_type_ids))
            .execute()
            .data
        )

        asset_to_type_id = {row["id"]: row["asset_type_id"] for row in assets}
        type_id_to_name = {row["id"]: row["asset_type"] for row in asset_types}
        totals = {"stock": Decimal("0"), "bond": Decimal("0")}

        for holding in holdings:
            asset_type = type_id_to_name[asset_to_type_id[holding["asset_id"]]]
            if asset_type in totals:
                totals[asset_type] += Decimal(str(holding["quantity"])) * Decimal(
                    str(holding["average_cost"])
                )
        return totals

    def _asset_type_id(self, asset_type):
        response = (
            self.client.table("asset_type")
            .select("id")
            .eq("asset_type", asset_type)
            .limit(1)
            .execute()
        )
        if not response.data:
            self.skipTest(f"asset_type row '{asset_type}' is missing.")
        return response.data[0]["id"]

    def _first_id(self, table_name):
        response = self.client.table(table_name).select("id").limit(1).execute()
        if not response.data:
            self.skipTest(f"{table_name} needs at least one row for DB tests.")
        return response.data[0]["id"]

    def _delete_row(self, table_name, row_id):
        try:
            self.client.table(table_name).delete().eq("id", row_id).execute()
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main(warnings="ignore")
