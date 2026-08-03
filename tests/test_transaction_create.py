"""POST /api/v1/transactions と /api/v1/transactions/batch の実装 tests。"""

import datetime
import decimal
import unittest
import uuid
from unittest.mock import patch

from flask import g
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.models import AssetMaster, AssetType, Currency, Holdings, Portfolio, Transactions, Users


class FakeMarketData:
    """`latest_price` / `asset_meta` だけを提供するテスト用 market data。"""

    prices = {
        "AAPL": decimal.Decimal("150"),
        "MSFT": decimal.Decimal("300"),
    }
    meta = {
        "AAPL": {"quote_type": "EQUITY", "currency": "USD"},
        "MSFT": {"quote_type": "EQUITY", "currency": "USD"},
        "UNKNOWNX": None,
    }

    def latest_price(self, ticker):
        return self.prices.get(ticker)

    def asset_meta(self, ticker):
        return self.meta.get(ticker)


class TransactionCreateEndpointTest(unittest.TestCase):
    """取引作成の holdings 更新・平均取得単価の再計算・oversell 拒否を確認する。"""

    def setUp(self):
        FakeMarketData.prices = {
            "AAPL": decimal.Decimal("150"),
            "MSFT": decimal.Decimal("300"),
        }

        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.user_id = uuid.uuid4()
        self.user_email = "trader@example.com"
        self.portfolio_id = uuid.uuid4()

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
                fees NUMERIC NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                transaction_type TEXT NOT NULL
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
                Currency(id=uuid.uuid4(), currency="USD", symbol="$"),
                AssetType(id=uuid.uuid4(), asset_type="stock"),
                Portfolio(
                    id=self.portfolio_id,
                    user_id=self.user_id,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        db.session.commit()

    def _auth(self):
        g.current_user_id = str(self.user_id)
        g.current_user_email = self.user_email
        g.current_access_token = "test-token"

    def _post_transaction(self, payload):
        with (
            patch("app.api.transactions.require_auth", side_effect=self._auth),
            patch("app.services.transaction.YahooFinanceMarketData", FakeMarketData),
        ):
            return self.client.post("/api/v1/transactions", json=payload)

    def _post_batch(self, payload):
        with (
            patch("app.api.transactions.require_auth", side_effect=self._auth),
            patch("app.services.transaction.YahooFinanceMarketData", FakeMarketData),
        ):
            return self.client.post("/api/v1/transactions/batch", json=payload)

    @staticmethod
    def _buy_payload(ticker, name, quantity):
        return {
            "ticker": ticker,
            "name": name,
            "position": "long",
            "order_type": "market",
            "transaction_type": "buy",
            "quantity": quantity,
        }

    @staticmethod
    def _sell_payload(ticker, name, quantity):
        return {
            "ticker": ticker,
            "name": name,
            "position": "long",
            "order_type": "market",
            "transaction_type": "sell",
            "quantity": quantity,
        }

    def test_create_transaction_requires_bearer_token(self):
        response = self.client.post(
            "/api/v1/transactions", json=self._buy_payload("AAPL", "Apple Inc.", 10)
        )

        self.assertEqual(response.status_code, 401)

    def test_create_transaction_returns_404_without_portfolio(self):
        portfolioless_user_id = uuid.uuid4()

        def auth_as_portfolioless_user():
            g.current_user_id = str(portfolioless_user_id)
            g.current_user_email = "no-portfolio@example.com"
            g.current_access_token = "test-token"

        with (
            patch(
                "app.api.transactions.require_auth",
                side_effect=auth_as_portfolioless_user,
            ),
            patch("app.services.transaction.YahooFinanceMarketData", FakeMarketData),
        ):
            response = self.client.post(
                "/api/v1/transactions",
                json=self._buy_payload("AAPL", "Apple Inc.", 10),
            )

        self.assertEqual(response.status_code, 404)

    def test_create_transaction_rejects_unsupported_order_type(self):
        payload = self._buy_payload("AAPL", "Apple Inc.", 10)
        payload["order_type"] = "limit"

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 422)

    def test_create_transaction_buy_new_asset_creates_holding(self):
        response = self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 10))

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["symbol"], "AAPL")
        self.assertEqual(body["name"], "Apple Inc.")
        self.assertEqual(body["asset_type"], "stock")
        self.assertEqual(body["executed_unit_price"], 150.0)
        self.assertEqual(body["executed_price"], 1500.0)

        asset = AssetMaster.query.filter_by(ticker="AAPL").one()
        self.assertEqual(asset.currency.currency, "USD")
        self.assertEqual(asset.asset_type.asset_type, "stock")

        holding = Holdings.query.one()
        self.assertEqual(float(holding.quantity), 10.0)
        self.assertEqual(float(holding.average_cost), 150.0)

    def test_create_transaction_buy_existing_holding_recomputes_average_cost(self):
        first = self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 10))
        self.assertEqual(first.status_code, 201)

        FakeMarketData.prices["AAPL"] = decimal.Decimal("200")
        second = self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 10))
        self.assertEqual(second.status_code, 201)

        holding = Holdings.query.one()
        self.assertEqual(float(holding.quantity), 20.0)
        self.assertEqual(float(holding.average_cost), 175.0)
        self.assertEqual(Transactions.query.count(), 2)

    def test_create_transaction_sell_partial_reduces_quantity(self):
        self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 10))

        response = self._post_transaction(self._sell_payload("AAPL", "Apple Inc.", 4))

        self.assertEqual(response.status_code, 201)
        holding = Holdings.query.one()
        self.assertEqual(float(holding.quantity), 6.0)
        self.assertEqual(float(holding.average_cost), 150.0)

    def test_create_transaction_sell_more_than_holding_returns_400(self):
        self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 5))

        response = self._post_transaction(self._sell_payload("AAPL", "Apple Inc.", 10))

        self.assertEqual(response.status_code, 400)
        holding = Holdings.query.one()
        self.assertEqual(float(holding.quantity), 5.0)
        self.assertEqual(Transactions.query.count(), 1)

    def test_create_transactions_batch_creates_all(self):
        response = self._post_batch(
            {
                "transactions": [
                    self._buy_payload("AAPL", "Apple Inc.", 10),
                    self._buy_payload("MSFT", "Microsoft Corp.", 5),
                ]
            }
        )

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(len(body), 2)
        self.assertEqual(Holdings.query.count(), 2)
        self.assertEqual(Transactions.query.count(), 2)

    def test_create_transactions_batch_rolls_back_all_on_failure(self):
        response = self._post_batch(
            {
                "transactions": [
                    self._buy_payload("AAPL", "Apple Inc.", 10),
                    # MSFT has no existing holding, so selling any amount oversells.
                    self._sell_payload("MSFT", "Microsoft Corp.", 5),
                ]
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AssetMaster.query.count(), 0)
        self.assertEqual(Holdings.query.count(), 0)
        self.assertEqual(Transactions.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
