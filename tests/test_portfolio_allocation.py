"""GET /api/v1/portfolios/allocation の実装 tests。"""

import datetime
import unittest
import uuid
from unittest.mock import patch

from flask import g
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.models import (
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
    sectors = {}

    def latest_price(self, ticker):
        return self.prices.get(ticker)

    def fx_to_usd(self, currency):
        if currency == "USD":
            return 1
        return self.fx_rates.get(currency)

    def sector(self, ticker):
        return self.sectors.get(ticker)


class PortfolioAllocationEndpointTest(unittest.TestCase):
    """集計基準ごとの区分・評価額・構成比を確認する。"""

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.user_id = uuid.uuid4()
        self.user_email = "portfolio-owner@example.com"

        self.app_context = self.app.app_context()
        self.app_context.push()
        self._create_sqlite_schema()
        self._seed_reference_data()
        FakeMarketData.prices = {}
        FakeMarketData.fx_rates = {}
        FakeMarketData.sectors = {}
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
                name TEXT NOT NULL,
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

    def _get_allocation(self, query="?group_by=asset_type"):
        with (
            patch("app.api.portfolios.require_auth", side_effect=self._auth),
            patch("app.services.portfolio.YahooFinanceMarketData", FakeMarketData),
        ):
            return self.client.get(f"/api/v1/portfolios/allocation{query}")

    def _create_portfolio(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        portfolio = Portfolio(
            id=uuid.uuid4(),
            user_id=self.user_id,
            name="Main Portfolio",
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

    def _seed_mixed_portfolio(self):
        portfolio = self._create_portfolio()
        cash = self._asset("CASH-USD", "Cash USD", self.cash_type, self.usd)
        apple = self._asset("AAPL", "Apple Inc.", self.stock_type, self.usd)
        toyota = self._asset("7203.T", "Toyota Motor Corp.", self.stock_type, self.jpy)
        etf = self._asset("VOO", "Vanguard S&P 500 ETF", self.etf_type, self.usd)
        self._holding(portfolio, cash, quantity=1, average_cost=1000)
        self._holding(portfolio, apple, quantity=10, average_cost=80)
        self._holding(portfolio, toyota, quantity=2, average_cost=1000)
        self._holding(portfolio, etf, quantity=1, average_cost=300)
        FakeMarketData.prices = {"AAPL": 100, "7203.T": 1500, "VOO": 320}
        FakeMarketData.fx_rates = {"JPY": 0.01}
        FakeMarketData.sectors = {"AAPL": "Technology", "7203.T": "Consumer Cyclical"}
        return portfolio

    def test_allocation_groups_by_asset_type(self):
        self._seed_mixed_portfolio()

        response = self._get_allocation("?group_by=asset_type")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["group_by"], "asset_type")
        self.assertEqual(data["currency"], "USD")
        # stock: AAPL 1000 + Toyota 30、cash: 1000、etf: 320
        self.assertEqual(data["total_value"], 2350)
        self.assertEqual(
            [(item["category"], item["value"]) for item in data["items"]],
            [("stock", 1030), ("cash", 1000), ("etf", 320)],
        )
        self.assertAlmostEqual(data["items"][0]["weight"], 1030 / 2350, places=6)
        self.assertEqual(data["items"][0]["holdings_count"], 2)
        self.assertEqual(data["items"][1]["holdings_count"], 1)
        self.assertIn("as_of", data)

    def test_allocation_groups_by_currency(self):
        self._seed_mixed_portfolio()

        response = self._get_allocation("?group_by=currency")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        # USD: cash 1000 + AAPL 1000 + VOO 320、JPY: Toyota 30
        self.assertEqual(
            [(item["category"], item["value"]) for item in data["items"]],
            [("USD", 2320), ("JPY", 30)],
        )
        self.assertEqual(data["items"][0]["holdings_count"], 3)

    def test_allocation_groups_by_asset(self):
        self._seed_mixed_portfolio()

        response = self._get_allocation("?group_by=asset")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(
            [(item["category"], item["value"]) for item in data["items"]],
            [
                ("Apple Inc.", 1000),
                ("Cash USD", 1000),
                ("Vanguard S&P 500 ETF", 320),
                ("Toyota Motor Corp.", 30),
            ],
        )
        self.assertTrue(all(item["holdings_count"] == 1 for item in data["items"]))

    def test_allocation_by_sector_covers_stocks_only(self):
        self._seed_mixed_portfolio()

        response = self._get_allocation("?group_by=sector")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        # cash と etf は除外され、株式ぶんだけの合計になる。
        self.assertEqual(data["total_value"], 1030)
        self.assertEqual(
            [(item["category"], item["value"]) for item in data["items"]],
            [("Technology", 1000), ("Consumer Cyclical", 30)],
        )
        self.assertAlmostEqual(data["items"][0]["weight"], 1000 / 1030, places=6)

    def test_allocation_skips_stock_without_sector(self):
        self._seed_mixed_portfolio()
        FakeMarketData.sectors = {"AAPL": "Technology"}

        response = self._get_allocation("?group_by=sector")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual([item["category"] for item in data["items"]], ["Technology"])
        self.assertEqual(data["total_value"], 1000)

    def test_allocation_skips_missing_price_and_fx(self):
        portfolio = self._create_portfolio()
        apple = self._asset("AAPL", "Apple Inc.", self.stock_type, self.usd)
        toyota = self._asset("7203.T", "Toyota Motor Corp.", self.stock_type, self.jpy)
        etf = self._asset("VOO", "Vanguard S&P 500 ETF", self.etf_type, self.usd)
        self._holding(portfolio, apple, quantity=10, average_cost=80)
        self._holding(portfolio, toyota, quantity=2, average_cost=1000)
        self._holding(portfolio, etf, quantity=1, average_cost=300)
        # VOO は価格なし、Toyota は FX なしで除外される。
        FakeMarketData.prices = {"AAPL": 100, "7203.T": 1500}
        FakeMarketData.fx_rates = {}

        response = self._get_allocation("?group_by=asset")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual([item["category"] for item in data["items"]], ["Apple Inc."])
        self.assertEqual(data["total_value"], 1000)
        self.assertEqual(data["items"][0]["weight"], 1)

    def test_allocation_returns_empty_items_for_empty_portfolio(self):
        self._create_portfolio()

        response = self._get_allocation("?group_by=asset_type")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["total_value"], 0)

    def test_allocation_requires_group_by(self):
        self._create_portfolio()

        response = self._get_allocation("")

        self.assertEqual(response.status_code, 422)

    def test_allocation_rejects_unknown_group_by(self):
        self._create_portfolio()

        response = self._get_allocation("?group_by=country")

        self.assertEqual(response.status_code, 422)

    def test_allocation_returns_404_when_portfolio_is_missing(self):
        response = self._get_allocation("?group_by=asset_type")

        self.assertEqual(response.status_code, 404)

    def test_allocation_requires_bearer_token(self):
        response = self.client.get("/api/v1/portfolios/allocation?group_by=asset_type")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
