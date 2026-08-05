"""GET /api/v1/portfolios/holdings の実装 tests。"""

import datetime
import unittest
import uuid
from unittest.mock import patch

from flask import g
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.models import (
    AssetDataHistory,
    AssetMaster,
    AssetType,
    Currency,
    Holdings,
    Portfolio,
    Users,
)


class FakeMarketData:
    prices = {}
    fx_rates = {}

    def latest_price(self, ticker):
        return self.prices.get(ticker)

    def fx_to_usd(self, currency):
        if currency == "USD":
            return 1
        return self.fx_rates.get(currency)


class PortfolioHoldingsEndpointTest(unittest.TestCase):
    """holdings 一覧の USD 換算、騰落率、ページングを確認する。"""

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
                average_cost_before NUMERIC,
                cash_balance_before NUMERIC,
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
        self.jpy = Currency(id=uuid.uuid4(), currency="JPY", symbol="JPY")
        self.cash_type = AssetType(id=uuid.uuid4(), asset_type="cash")
        self.stock_type = AssetType(id=uuid.uuid4(), asset_type="stock")
        self.etf_type = AssetType(id=uuid.uuid4(), asset_type="etf")
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
                self.etf_type,
            ]
        )
        db.session.commit()

    def _auth(self):
        g.current_user_id = str(self.user_id)
        g.current_user_email = self.user_email
        g.current_access_token = "test-token"

    def _get_holdings(self, query=""):
        with (
            patch("app.api.portfolios.require_auth", side_effect=self._auth),
            patch("app.services.portfolio.YahooFinanceMarketData", FakeMarketData),
        ):
            return self.client.get(f"/api/v1/portfolios/holdings{query}")

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

    def _asset(self, ticker, name, asset_type, currency):
        asset = AssetMaster(
            id=uuid.uuid4(),
            ticker=ticker,
            name=name,
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

    def _history(self, asset, close_price, *, days_ago=1):
        row = AssetDataHistory(
            id=uuid.uuid4(),
            asset_id=asset.id,
            price_date=datetime.date.today() - datetime.timedelta(days=days_ago),
            close_price=close_price,
        )
        db.session.add(row)
        db.session.commit()
        return row

    def test_holdings_calculates_usd_stock(self):
        portfolio = self._create_portfolio()
        stock = self._asset("AAPL", "Apple Inc.", self.stock_type, self.usd)
        self._holding(portfolio, stock, quantity=10, average_cost=80)
        self._history(stock, 90)
        FakeMarketData.prices = {"AAPL": 100}
        FakeMarketData.fx_rates = {}

        response = self._get_holdings()

        self.assertEqual(response.status_code, 200)
        item = response.get_json()["items"][0]
        self.assertEqual(item["ticker"], "AAPL")
        self.assertEqual(item["name"], "Apple Inc.")
        self.assertEqual(item["asset_type"], "stock")
        self.assertEqual(item["quantity"], 10)
        self.assertEqual(item["average_purchase_price"], 80)
        self.assertEqual(item["total_purchase_price"], 800)
        self.assertEqual(item["current_price"], 100)
        self.assertEqual(item["total_market_value"], 1000)
        self.assertEqual(item["today_return_percent"], 25)
        self.assertEqual(item["total_return_percent"], 25)
        self.assertEqual(item["currency"], "USD")

    def test_holdings_converts_non_usd_stock_to_usd(self):
        portfolio = self._create_portfolio()
        stock = self._asset("7203.T", "Toyota Motor Corp.", self.stock_type, self.jpy)
        self._holding(portfolio, stock, quantity=2, average_cost=1000)
        self._history(stock, 1200)
        FakeMarketData.prices = {"7203.T": 1500}
        FakeMarketData.fx_rates = {"JPY": 0.01}

        response = self._get_holdings()

        self.assertEqual(response.status_code, 200)
        item = response.get_json()["items"][0]
        self.assertEqual(item["average_purchase_price"], 10)
        self.assertEqual(item["total_purchase_price"], 20)
        self.assertEqual(item["current_price"], 15)
        self.assertEqual(item["total_market_value"], 30)
        self.assertEqual(item["today_return_percent"], 50)
        self.assertEqual(item["total_return_percent"], 50)

    def test_holdings_totals_cover_all_valid_items_not_current_page(self):
        portfolio = self._create_portfolio()
        inputs = [
            ("AAA", 100, 90),
            ("BBB", 200, 180),
            ("CCC", 300, 250),
        ]
        for ticker, current, previous in inputs:
            asset = self._asset(ticker, ticker, self.stock_type, self.usd)
            self._holding(portfolio, asset, quantity=1, average_cost=50)
            self._history(asset, previous)
        FakeMarketData.prices = {ticker: current for ticker, current, _ in inputs}
        FakeMarketData.fx_rates = {}

        response = self._get_holdings("?page=2&per_page=1")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual([item["ticker"] for item in data["items"]], ["BBB"])
        self.assertEqual(data["pagination"]["total_items"], 3)
        self.assertEqual(data["pagination"]["total_pages"], 3)
        self.assertEqual(data["totals"]["market_value"], 600)
        self.assertEqual(data["totals"]["day_change"], 450)
        self.assertEqual(data["totals"]["day_change_percent"], 300)

    def test_holdings_filters_asset_type(self):
        portfolio = self._create_portfolio()
        stock = self._asset("AAPL", "Apple Inc.", self.stock_type, self.usd)
        etf = self._asset("VOO", "Vanguard S&P 500 ETF", self.etf_type, self.usd)
        self._holding(portfolio, stock, quantity=1, average_cost=80)
        self._holding(portfolio, etf, quantity=1, average_cost=300)
        self._history(stock, 90)
        self._history(etf, 310)
        FakeMarketData.prices = {"AAPL": 100, "VOO": 320}
        FakeMarketData.fx_rates = {}

        response = self._get_holdings("?asset_type=etf")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual([item["ticker"] for item in data["items"]], ["VOO"])
        self.assertEqual(data["pagination"]["total_items"], 1)

    def test_holdings_excludes_cash(self):
        portfolio = self._create_portfolio()
        cash = self._asset("CASH-USD", "Cash USD", self.cash_type, self.usd)
        stock = self._asset("AAPL", "Apple Inc.", self.stock_type, self.usd)
        self._holding(portfolio, cash, quantity=1, average_cost=1000)
        self._holding(portfolio, stock, quantity=1, average_cost=80)
        self._history(stock, 90)
        FakeMarketData.prices = {"AAPL": 100}
        FakeMarketData.fx_rates = {}

        response = self._get_holdings()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual([item["ticker"] for item in data["items"]], ["AAPL"])
        self.assertEqual(data["pagination"]["total_items"], 1)

    def test_holdings_excludes_fully_sold_position(self):
        """A holding left at quantity 0 after a full sell (the row isn't deleted,
        just zeroed) shouldn't reappear in the positions list."""
        portfolio = self._create_portfolio()
        stock = self._asset("AAPL", "Apple Inc.", self.stock_type, self.usd)
        self._holding(portfolio, stock, quantity=0, average_cost=80)
        self._history(stock, 90)
        FakeMarketData.prices = {"AAPL": 100}
        FakeMarketData.fx_rates = {}

        response = self._get_holdings()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["totals"]["market_value"], 0)
        self.assertEqual(data["pagination"]["total_items"], 0)

    def test_holdings_returns_empty_for_cash_filter(self):
        portfolio = self._create_portfolio()
        cash = self._asset("CASH-USD", "Cash USD", self.cash_type, self.usd)
        self._holding(portfolio, cash, quantity=1, average_cost=1000)
        FakeMarketData.prices = {}
        FakeMarketData.fx_rates = {}

        response = self._get_holdings("?asset_type=cash")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["totals"]["market_value"], 0)
        self.assertEqual(data["pagination"]["total_items"], 0)

    def test_holdings_skips_missing_current_price(self):
        portfolio = self._create_portfolio()
        stock = self._asset("AAPL", "Apple Inc.", self.stock_type, self.usd)
        self._holding(portfolio, stock, quantity=1, average_cost=80)
        self._history(stock, 90)
        FakeMarketData.prices = {}
        FakeMarketData.fx_rates = {}

        response = self._get_holdings()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["items"], [])

    def test_holdings_skips_missing_fx(self):
        portfolio = self._create_portfolio()
        stock = self._asset("7203.T", "Toyota Motor Corp.", self.stock_type, self.jpy)
        self._holding(portfolio, stock, quantity=1, average_cost=1000)
        self._history(stock, 1200)
        FakeMarketData.prices = {"7203.T": 1500}
        FakeMarketData.fx_rates = {}

        response = self._get_holdings()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["items"], [])

    def test_holdings_skips_missing_previous_close(self):
        portfolio = self._create_portfolio()
        stock = self._asset("AAPL", "Apple Inc.", self.stock_type, self.usd)
        self._holding(portfolio, stock, quantity=1, average_cost=80)
        FakeMarketData.prices = {"AAPL": 100}
        FakeMarketData.fx_rates = {}

        response = self._get_holdings()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["items"], [])

    def test_holdings_returns_404_when_portfolio_is_missing(self):
        response = self._get_holdings()

        self.assertEqual(response.status_code, 404)

    def test_holdings_requires_bearer_token(self):
        response = self.client.get("/api/v1/portfolios/holdings")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
