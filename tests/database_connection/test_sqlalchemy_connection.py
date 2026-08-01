"""SQLAlchemy 経由で backend が Supabase PostgreSQL に接続できることを確認する。"""

import os
import unittest

from sqlalchemy import text

from tests.config import load_test_env


class SQLAlchemyConnectionTest(unittest.TestCase):
    """Flask app config の DATABASE_URL を使った DB 接続 smoke test。"""

    def setUp(self):
        load_test_env()
        if os.getenv("RUN_SUPABASE_CONNECTION_TESTS") != "true":
            self.skipTest(
                "Set RUN_SUPABASE_CONNECTION_TESTS=true to run live DB tests."
            )

        from app import create_app
        from app.extensions import db

        self.db = db
        self.app = create_app("development")
        self.database_url = self.app.config.get("SQLALCHEMY_DATABASE_URI")
        if not self.database_url:
            self.skipTest("DATABASE_URL is not configured.")
        if "<" in self.database_url or "YOUR_DB_PASSWORD" in self.database_url:
            self.skipTest("DATABASE_URL still contains a placeholder password.")

        self.app_context = self.app.app_context()
        self.app_context.push()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        self.db.session.remove()
        self.db.engine.dispose()
        self.app_context.pop()

    def test_backend_sqlalchemy_connects_to_public_schema(self):
        """backend と同じ db.engine で軽量 query を実行できること。"""

        row = self.db.session.execute(
            text(
                "select current_database() as database_name, "
                "current_schema() as schema_name"
            )
        ).one()

        self.assertEqual(row.database_name, "postgres")
        self.assertEqual(row.schema_name, "public")
        print("sqlalchemy connection: backend DB engine connected to public schema")


if __name__ == "__main__":
    unittest.main()
