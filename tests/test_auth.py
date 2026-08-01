"""Supabase Auth token helper の unit tests。"""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask, g
from werkzeug.exceptions import HTTPException


class SupabaseAuthHelperTest(unittest.TestCase):
    """Bearer token から Flask の current user context を作れることを確認する。"""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_ANON_KEY": "anon-test-key",
            }
        )

    def test_require_auth_sets_current_user_context(self):
        from app.auth import require_auth

        user = SimpleNamespace(id="user-123", email="user001@gmail.com")
        response = SimpleNamespace(user=user)
        auth = SimpleNamespace(get_user=lambda token: response)
        client = SimpleNamespace(auth=auth)

        with self.app.test_request_context(
            "/api/v1/transactions",
            headers={"Authorization": "Bearer access-token-123"},
        ), patch("app.auth.get_supabase_anon_client", return_value=client):
            result = require_auth()

            self.assertIs(result, user)
            self.assertEqual(g.current_user_id, "user-123")
            self.assertEqual(g.current_user_email, "user001@gmail.com")
            self.assertEqual(g.current_access_token, "access-token-123")

    def test_require_auth_rejects_missing_bearer_token(self):
        from app.auth import require_auth

        with self.app.test_request_context("/api/v1/transactions"):
            with self.assertRaises(HTTPException) as error:
                require_auth()

        self.assertEqual(error.exception.code, 401)

    def test_require_auth_rejects_invalid_token(self):
        from app.auth import require_auth

        def raise_invalid_token(token):
            raise RuntimeError("invalid token")

        auth = SimpleNamespace(get_user=raise_invalid_token)
        client = SimpleNamespace(auth=auth)

        with self.app.test_request_context(
            "/api/v1/transactions",
            headers={"Authorization": "Bearer invalid-token"},
        ), patch("app.auth.get_supabase_anon_client", return_value=client):
            with self.assertRaises(HTTPException) as error:
                require_auth()

        self.assertEqual(error.exception.code, 401)


if __name__ == "__main__":
    unittest.main()
