"""POST /api/v1/portfolios/ の実装 tests。"""

import datetime
import uuid
import unittest
from unittest.mock import patch

from flask import g
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.models import AssetType, Currency, Holdings, Portfolio, Users


class PortfolioCreateEndpointTest(unittest.TestCase):
    """portfolio 作成と initial cash holding の挙動を確認する。"""

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.user_id = uuid.uuid4()
        self.user_email = "portfolio-owner@example.com"

        self.app_context = self.app.app_context()
        self.app_context.push()
        self._create_sqlite_schema()
        self._seed_reference_data()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        engine = db.engine
        db.session.remove()
        self._drop_sqlite_schema()
        engine.dispose()
        self.app_context.pop()

    def _create_sqlite_schema(self):
        """Postgres 専用 default を避け、unit test 用の最小 schema だけ作る。"""

        statements = [
            """
            CREATE TABLE users (
                id CHAR(32) PRIMARY KEY,
                email VARCHAR NOT NULL UNIQUE,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                name VARCHAR,
                password TEXT
            )
            """,
            """
            CREATE TABLE currency (
                id CHAR(32) PRIMARY KEY,
                currency TEXT NOT NULL,
                symbol TEXT
            )
            """,
            """
            CREATE TABLE asset_type (
                id CHAR(32) PRIMARY KEY,
                asset_type TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE asset_master (
                id CHAR(32) PRIMARY KEY,
                ticker TEXT NOT NULL,
                name TEXT,
                asset_type_id CHAR(32),
                currency_id CHAR(32)
            )
            """,
            """
            CREATE TABLE portfolio (
                id CHAR(32) PRIMARY KEY,
                user_id CHAR(32) NOT NULL UNIQUE,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """,
            """
            CREATE TABLE holdings (
                id CHAR(32) PRIMARY KEY,
                portfolio_id CHAR(32) NOT NULL,
                asset_id CHAR(32) NOT NULL,
                quantity NUMERIC NOT NULL,
                updated_at DATETIME NOT NULL,
                average_cost NUMERIC,
                UNIQUE (portfolio_id, asset_id)
            )
            """,
            """
            CREATE TABLE transactions (
                id CHAR(32) PRIMARY KEY,
                holding_id CHAR(32) NOT NULL,
                trade_date DATE NOT NULL,
                quantity NUMERIC NOT NULL,
                price NUMERIC NOT NULL,
                fees NUMERIC NOT NULL,
                average_cost_before_sale NUMERIC,
                created_at DATETIME NOT NULL,
                transaction_type TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE asset_data_history (
                id CHAR(32) PRIMARY KEY,
                asset_id CHAR(32) NOT NULL,
                price_date DATE NOT NULL,
                close_price NUMERIC NOT NULL,
                UNIQUE (asset_id, price_date)
            )
            """,
        ]
        for statement in statements:
            db.session.execute(text(statement))
        db.session.commit()

    def _drop_sqlite_schema(self):
        for table_name in (
            "transactions",
            "holdings",
            "asset_data_history",
            "portfolio",
            "asset_master",
            "asset_type",
            "currency",
            "users",
        ):
            db.session.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        db.session.commit()

    def _seed_reference_data(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        db.session.add_all(
            [
                Users(
                    id=self.user_id,
                    email=self.user_email,
                    created_at=now,
                    updated_at=now,
                ),
                Currency(id=uuid.uuid4(), currency="USD"),
                AssetType(id=uuid.uuid4(), asset_type="cash"),
            ]
        )
        db.session.commit()

    def _auth(self):
        g.current_user_id = str(self.user_id)
        g.current_user_email = self.user_email
        g.current_access_token = "test-token"

    def _post_portfolio(self, payload):
        with patch("app.api.portfolios.require_auth", side_effect=self._auth):
            return self.client.post("/api/v1/portfolios/", json=payload)

    def test_create_portfolio_returns_message(self):
        response = self._post_portfolio(
            {"currency": "USD", "cash_balance": 1000000}
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), {"message": "Portfolio created"})
        self.assertEqual(Portfolio.query.count(), 1)

    def test_create_portfolio_rejects_existing_user_portfolio(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        db.session.add(
            Portfolio(
                id=uuid.uuid4(),
                user_id=self.user_id,
                created_at=now,
                updated_at=now,
            )
        )
        db.session.commit()

        response = self._post_portfolio({})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Portfolio.query.count(), 1)

    def test_create_portfolio_requires_bearer_token(self):
        response = self.client.post("/api/v1/portfolios/", json={})

        self.assertEqual(response.status_code, 401)

    def test_create_portfolio_stores_cash_balance_as_cash_holding(self):
        response = self._post_portfolio(
            {"currency": "USD", "cash_balance": 1000000}
        )

        self.assertEqual(response.status_code, 201)
        holding = Holdings.query.one()
        self.assertEqual(float(holding.quantity), 1.0)
        self.assertEqual(float(holding.average_cost), 1000000.0)
        self.assertEqual(holding.asset.ticker, "CASH-USD")
        self.assertEqual(holding.asset.name, "Cash USD")

    def test_create_portfolio_with_zero_cash_creates_no_holding(self):
        response = self._post_portfolio({"currency": "USD", "cash_balance": 0})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Portfolio.query.count(), 1)
        self.assertEqual(Holdings.query.count(), 0)

    def test_create_portfolio_defaults_currency_to_usd(self):
        response = self._post_portfolio({"cash_balance": 1000000})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Holdings.query.one().asset.ticker, "CASH-USD")

    def test_create_portfolio_defaults_cash_balance_to_one_million(self):
        response = self._post_portfolio({})

        self.assertEqual(response.status_code, 201)
        holding = Holdings.query.one()
        self.assertEqual(float(holding.quantity), 1.0)
        self.assertEqual(float(holding.average_cost), 1_000_000.0)
        self.assertEqual(holding.asset.ticker, "CASH-USD")


if __name__ == "__main__":
    unittest.main()
