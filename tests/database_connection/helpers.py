import os
import unittest

from app import create_app
from app.services.supabase import (
    close_supabase_client,
    close_supabase_clients,
    create_supabase_anon_client,
    get_supabase_anon_client,
    get_supabase_service_client,
)
from tests.config import load_test_env


class SupabaseLiveTestCase(unittest.TestCase):
    """Shared helpers for live Supabase unittest cases."""

    def load_supabase_settings(
        self,
        *,
        enabled_var=None,
        enabled_message=None,
        rls_user_type=None,
        require_anon=True,
        require_service=True,
    ):
        load_test_env()
        self.app = create_app("testing")
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.addCleanup(self._cleanup_supabase_app_context)
        self.url = self.app.config.get("SUPABASE_URL")
        self.anon_key = self.app.config.get("SUPABASE_ANON_KEY")
        self.service_role_key = self.app.config.get("SUPABASE_SERVICE_ROLE_KEY")
        self.enabled = True

        if rls_user_type:
            if not self._rls_user_type_enabled(rls_user_type):
                user_type = "real user" if rls_user_type == "real" else "mock user"
                self.skipTest(enabled_message or f"Skip {user_type} RLS tests.")
        elif enabled_var:
            self.enabled = os.getenv(enabled_var) == "true"
            if not self.enabled:
                self.skipTest(enabled_message or f"Set {enabled_var}=true.")

        missing = []
        if not self.url:
            missing.append("SUPABASE_URL")
        if require_anon and not self.anon_key:
            missing.append("SUPABASE_ANON_KEY")
        if require_service and not self.service_role_key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")
        if missing:
            self.skipTest(f"Missing Supabase config: {', '.join(missing)}.")

    def _rls_user_type_enabled(self, user_type):
        value = os.getenv("RUN_SUPABASE_REAL_USER")
        if value is None:
            return False
        use_real_user = value.strip().lower() == "true"
        return use_real_user if user_type == "real" else not use_real_user

    def init_supabase_clients(self):
        self.service_client = self.service_client_or_skip()

    def init_tracking(self):
        self.created_transaction_ids = []
        self.created_holding_ids = []
        self.created_portfolio_ids = []
        self.created_asset_ids = []
        self.created_user_ids = []
        self.opened_clients = []

    def anon_client_or_skip(self):
        if not self.url or not self.anon_key:
            self.skipTest("SUPABASE_URL or SUPABASE_ANON_KEY is not configured.")
        return get_supabase_anon_client()

    def service_client_or_skip(self):
        if not self.url or not self.service_role_key:
            self.skipTest(
                "SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not configured."
            )
        return get_supabase_service_client()

    def signed_in_client(self, email, password):
        client = create_supabase_anon_client()
        client.auth.sign_in_with_password({"email": email, "password": password})
        self.opened_clients.append(client)
        return client

    def create_auth_user(self, email, password):
        response = self.service_client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
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

    def first_id(self, table_name):
        rows = self.service_client.table(table_name).select("id").limit(1).execute().data
        if not rows:
            self.skipTest(f"{table_name} needs at least one row.")
        return rows[0]["id"]

    def public_user(self, email):
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

    def service_portfolio_id_for_user(self, user_id, *, skip_if_missing=True):
        rows = (
            self.service_client.table("portfolio")
            .select("id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
            .data
        )
        if not rows:
            if skip_if_missing:
                self.skipTest(f"User {user_id} has no portfolio.")
            return None
        return rows[0]["id"]

    def service_holding_ids_for_user(self, user_id):
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

    def visible_holdings(self, client):
        return (
            client.table("holdings")
            .select("id,asset_id,quantity,average_cost")
            .execute()
            .data
        )

    def print_holdings_asset_names(self, client, holdings, *, reader_email, limit=None):
        print(f"reader: {reader_email}")
        if not holdings:
            print("(no holdings visible)")
            return

        displayed_holdings = holdings[:limit] if limit else holdings
        asset_ids = sorted({holding["asset_id"] for holding in displayed_holdings})
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
            for holding in displayed_holdings
        ]
        self.print_table(["asset_name"], rows)

    def print_table(self, headers, rows):
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

    def cleanup_tracked_rows(self, *, delete_auth_users=False):
        for transaction_id in reversed(getattr(self, "created_transaction_ids", [])):
            self.delete_row("transactions", transaction_id)
        for holding_id in reversed(getattr(self, "created_holding_ids", [])):
            self.delete_row("holdings", holding_id)
        for portfolio_id in reversed(getattr(self, "created_portfolio_ids", [])):
            self.delete_row("portfolio", portfolio_id)
        for asset_id in reversed(getattr(self, "created_asset_ids", [])):
            self.delete_row("asset_master", asset_id)
        for user_id in reversed(getattr(self, "created_user_ids", [])):
            self.delete_row("users", user_id)
            if delete_auth_users:
                try:
                    self.service_client.auth.admin.delete_user(user_id)
                except Exception:
                    pass

    def delete_row(self, table_name, row_id):
        try:
            self.service_client.table(table_name).delete().eq("id", row_id).execute()
        except Exception:
            pass

    def _cleanup_supabase_app_context(self):
        for client in getattr(self, "opened_clients", []):
            close_supabase_client(client)
        if hasattr(self, "app"):
            close_supabase_clients(self.app)
        if hasattr(self, "app_context"):
            self.app_context.pop()
