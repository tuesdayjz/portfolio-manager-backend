"""GET /api/v1/portfolios/summary の実装 tests。"""

import datetime
import unittest
import uuid
from unittest.mock import patch

from flask import g
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.models import AssetMaster, AssetType, Currency, Holdings, Portfolio, Users


class FakeMarketData:
    prices = {}
    fx_rates = {}

    def latest_price(self, ticker):
        return self.prices.get(ticker)

    def fx_to_usd(self, currency):
        if currency == "USD":
            return 1
        return self.fx_rates.get(currency)


class PortfolioSummaryEndpointTest(unittest.TestCase):
    """portfolio summary の集計と skip 挙動を確認する。"""

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
        self.usd = Currency(id=uuid.uuid4(), currency="USD", symbol="$")
        self.jpy = Currency(id=uuid.uuid4(), currency="JPY", symbol="¥")
        self.cash_type = AssetType(id=uuid.uuid4(), asset_type="cash")
        self.stock_type = AssetType(id=uuid.uuid4(), asset_type="stock")
        db.session.add_all(
            [
                Users(
                    id=self.user_id,
                    email=self.user_email,
                    created_at=now,
                    updated_at=now,
                ),
                self.usd,
                self.jpy,
                self.cash_type,
                self.stock_type,
            ]
        )
        db.session.commit()

    def _auth(self):
        g.current_user_id = str(self.user_id)
        g.current_user_email = self.user_email
        g.current_access_token = "test-token"

    def _get_summary(self):
        with (
            patch("app.api.portfolios.require_auth", side_effect=self._auth),
            patch("app.services.portfolio.YahooFinanceMarketData", FakeMarketData),
        ):
            return self.client.get("/api/v1/portfolios/summary")

    def _create_portfolio(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        portfolio = Portfolio(
            id=uuid.uuid4(),
            user_id=self.user_id,
            created_at=now,
            updated_at=now,
        )
        db.session.add(portfolio)
        db.session.commit()
        return portfolio

    def _asset(self, ticker, asset_type, currency):
        asset = AssetMaster(
            id=uuid.uuid4(),
            ticker=ticker,
            name=ticker,
            asset_type_id=asset_type.id,
            currency_id=currency.id,
        )
        db.session.add(asset)
        db.session.commit()
        return asset

    def _holding(self, portfolio, asset, *, quantity, average_cost):
        holding = Holdings(
            id=uuid.uuid4(),
            portfolio_id=portfolio.id,
            asset_id=asset.id,
            quantity=quantity,
            average_cost=average_cost,
            updated_at=datetime.datetime.now(datetime.timezone.utc),
        )
        db.session.add(holding)
        db.session.commit()
        return holding

    def test_summary_calculates_usd_cash_and_stock(self):
        portfolio = self._create_portfolio()
        cash = self._asset("CASH-USD", self.cash_type, self.usd)
        stock = self._asset("AAPL", self.stock_type, self.usd)
        self._holding(portfolio, cash, quantity=1, average_cost=1250000)
        self._holding(portfolio, stock, quantity=10, average_cost=100)
        FakeMarketData.prices = {"AAPL": 120}
        FakeMarketData.fx_rates = {}

        response = self._get_summary()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["currency"], "USD")
        self.assertEqual(data["currency_symbol"], "$")
        self.assertEqual(data["cash_balance"], 1250000)
        self.assertEqual(data["total_market_value"], 1200)
        self.assertEqual(data["total_return_percent"], 20)

    def test_summary_converts_non_usd_stock_to_usd(self):
        portfolio = self._create_portfolio()
        stock = self._asset("7203.T", self.stock_type, self.jpy)
        self._holding(portfolio, stock, quantity=2, average_cost=1000)
        FakeMarketData.prices = {"7203.T": 1500}
        FakeMarketData.fx_rates = {"JPY": 0.01}

        response = self._get_summary()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["total_market_value"], 30)
        self.assertEqual(data["total_return_percent"], 50)

    def test_summary_converts_multiple_cash_holdings_to_usd(self):
        portfolio = self._create_portfolio()
        usd_cash = self._asset("CASH-USD", self.cash_type, self.usd)
        jpy_cash = self._asset("CASH-JPY", self.cash_type, self.jpy)
        self._holding(portfolio, usd_cash, quantity=1, average_cost=1000)
        self._holding(portfolio, jpy_cash, quantity=2, average_cost=10000)
        FakeMarketData.prices = {}
        FakeMarketData.fx_rates = {"JPY": 0.01}

        response = self._get_summary()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["cash_balance"], 1200)

    def test_summary_skips_holding_when_price_is_missing(self):
        portfolio = self._create_portfolio()
        included = self._asset("AAPL", self.stock_type, self.usd)
        skipped = self._asset("MSFT", self.stock_type, self.usd)
        self._holding(portfolio, included, quantity=1, average_cost=50)
        self._holding(portfolio, skipped, quantity=1, average_cost=100)
        FakeMarketData.prices = {"AAPL": 100}
        FakeMarketData.fx_rates = {}

        response = self._get_summary()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["total_market_value"], 100)
        self.assertEqual(data["total_return_percent"], 100)

    def test_summary_skips_holding_when_fx_is_missing(self):
        portfolio = self._create_portfolio()
        stock = self._asset("7203.T", self.stock_type, self.jpy)
        self._holding(portfolio, stock, quantity=2, average_cost=1000)
        FakeMarketData.prices = {"7203.T": 1500}
        FakeMarketData.fx_rates = {}

        response = self._get_summary()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["total_market_value"], 0)
        self.assertEqual(data["total_return_percent"], 0)

    def test_summary_returns_404_when_portfolio_is_missing(self):
        response = self._get_summary()

        self.assertEqual(response.status_code, 404)

    def test_summary_requires_bearer_token(self):
        response = self.client.get("/api/v1/portfolios/summary")

        self.assertEqual(response.status_code, 401)

    def test_summary_returns_zero_percent_when_cost_basis_is_zero(self):
        portfolio = self._create_portfolio()
        stock = self._asset("AAPL", self.stock_type, self.usd)
        self._holding(portfolio, stock, quantity=10, average_cost=0)
        FakeMarketData.prices = {"AAPL": 120}
        FakeMarketData.fx_rates = {}

        response = self._get_summary()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total_return_percent"], 0)

    def test_summary_defaults_usd_symbol(self):
        self.usd.symbol = None
        db.session.commit()
        self._create_portfolio()
        FakeMarketData.prices = {}
        FakeMarketData.fx_rates = {}

        response = self._get_summary()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["currency_symbol"], "$")


if __name__ == "__main__":
    unittest.main()
