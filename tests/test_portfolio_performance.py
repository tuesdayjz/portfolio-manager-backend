"""GET /api/v1/portfolios/performance の実装 tests。"""

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
    CurrencyRateHistory,
    Holdings,
    Portfolio,
    Transactions,
    Users,
)


class FakeMarketData:
    """performance は価格を DB から読むので、FX だけを差し替える。"""

    fx_rates = {}

    def latest_price(self, ticker):
        return None

    def fx_to_usd(self, currency):
        if currency == "USD":
            return 1
        return self.fx_rates.get(currency)

    def sector(self, ticker):
        return None


class PortfolioPerformanceEndpointTest(unittest.TestCase):
    """評価額の系列・期間ごとの騰落・グラフの粒度を確認する。"""

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.user_id = uuid.uuid4()
        self.user_email = "portfolio-owner@example.com"
        self.today = datetime.date.today()

        self.app_context = self.app.app_context()
        self.app_context.push()
        self._create_sqlite_schema()
        self._seed_reference_data()
        FakeMarketData.fx_rates = {}
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
                average_cost_before NUMERIC,
                cash_balance_before NUMERIC,
                created_at DATETIME NOT NULL,
                transaction_type TEXT NOT NULL DEFAULT ''
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
            """
            CREATE TABLE currency_rate_history (
                id CHAR(32) PRIMARY KEY,
                currency_id CHAR(32) NOT NULL,
                rate_date DATE NOT NULL,
                close_price NUMERIC NOT NULL,
                UNIQUE (currency_id, rate_date)
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
            "currency_rate_history",
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

    def _get_performance(self, query=""):
        with (
            patch("app.api.portfolios.require_auth", side_effect=self._auth),
            patch("app.services.performance.YahooFinanceMarketData", FakeMarketData),
        ):
            return self.client.get(f"/api/v1/portfolios/performance{query}")

    def _days_ago(self, days):
        return self.today - datetime.timedelta(days=days)

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

    def _prices(self, asset, prices_by_date):
        db.session.add_all(
            [
                AssetDataHistory(
                    id=uuid.uuid4(),
                    asset_id=asset.id,
                    price_date=price_date,
                    close_price=close_price,
                )
                for price_date, close_price in prices_by_date.items()
            ]
        )
        db.session.commit()

    def _rates(self, currency, rates_by_date):
        db.session.add_all(
            [
                CurrencyRateHistory(
                    id=uuid.uuid4(),
                    currency_id=currency.id,
                    rate_date=rate_date,
                    close_price=close_price,
                )
                for rate_date, close_price in rates_by_date.items()
            ]
        )
        db.session.commit()

    def _trade(self, holding, *, trade_date, quantity, price, transaction_type):
        db.session.add(
            Transactions(
                id=uuid.uuid4(),
                holding_id=holding.id,
                trade_date=trade_date,
                quantity=quantity,
                price=price,
                fees=0,
                created_at=datetime.datetime.now(datetime.timezone.utc),
                transaction_type=transaction_type,
            )
        )
        db.session.commit()

    def _seed_cash_and_stock(self):
        """現金 1000 USD と AAPL 10 株。現金を除く評価額は 800 → 900 → 950 → 1000。"""

        portfolio = self._create_portfolio()
        cash = self._asset("CASH-USD", "Cash USD", self.cash_type, self.usd)
        apple = self._asset("AAPL", "Apple Inc.", self.stock_type, self.usd)
        self._holding(portfolio, cash, quantity=1, average_cost=1000)
        self._holding(portfolio, apple, quantity=10, average_cost=50)
        self._prices(
            apple,
            {
                self._days_ago(10): 80,
                self._days_ago(7): 90,
                self._days_ago(1): 95,
                self.today: 100,
            },
        )
        return portfolio

    def test_performance_returns_full_history_by_default(self):
        self._seed_cash_and_stock()

        response = self._get_performance()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["currency"], "USD")
        self.assertEqual(data["interval"], "1d")
        self.assertEqual(data["range"], "all")
        # range=all の起点は最も古い価格データの日。
        self.assertEqual(data["start_date"], self._days_ago(10).isoformat())
        self.assertEqual(data["end_date"], self.today.isoformat())
        self.assertEqual(
            [(point["date"], point["total_market_value"]) for point in data["points"]],
            [
                (self._days_ago(10).isoformat(), 800),
                (self._days_ago(7).isoformat(), 900),
                (self._days_ago(1).isoformat(), 950),
                (self.today.isoformat(), 1000),
            ],
        )

    def test_performance_metrics_and_returns(self):
        self._seed_cash_and_stock()

        response = self._get_performance()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        metrics = data["metrics"]
        self.assertEqual(metrics["portfolio_value"], 1000)
        # 今日 1000 と前日 950 の差分。
        self.assertEqual(metrics["today"]["amount"], 50)
        self.assertAlmostEqual(metrics["today"]["percent"], 50 / 950 * 100, places=6)
        self.assertEqual(data["return_1d"], metrics["today"])
        # 1 週間前は 900。
        self.assertEqual(data["return_1w"]["amount"], 100)
        self.assertAlmostEqual(
            data["return_1w"]["percent"], 100 / 900 * 100, places=6
        )
        # 起点より前のデータが無い期間は、最も古い評価額 800 を起点にする。
        self.assertEqual(data["return_1m"]["amount"], 200)
        self.assertEqual(data["return_total"]["amount"], 200)
        self.assertAlmostEqual(
            data["return_total"]["percent"], 200 / 800 * 100, places=6
        )
        self.assertEqual(metrics["total_return"], data["return_total"])
        # range=all の period return は総損益と一致する。
        self.assertEqual(metrics["return"], data["return_total"])

    def test_performance_range_limits_points_only(self):
        self._seed_cash_and_stock()

        response = self._get_performance("?range=1w")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["range"], "1w")
        self.assertEqual(data["start_date"], self._days_ago(7).isoformat())
        self.assertEqual(
            [point["date"] for point in data["points"]],
            [
                self._days_ago(7).isoformat(),
                self._days_ago(1).isoformat(),
                self.today.isoformat(),
            ],
        )
        # 表示期間を絞っても、全期間の騰落は変わらない。
        self.assertEqual(data["return_total"]["amount"], 200)
        self.assertEqual(data["metrics"]["return"], data["return_1w"])

    def test_performance_explicit_dates_take_priority_over_range(self):
        self._seed_cash_and_stock()

        response = self._get_performance(
            f"?range=1y&start_date={self._days_ago(7)}&end_date={self._days_ago(1)}"
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsNone(data["range"])
        self.assertEqual(data["start_date"], self._days_ago(7).isoformat())
        self.assertEqual(data["end_date"], self._days_ago(1).isoformat())
        # end_date 時点で評価するので、今日の 1000 は入らない。
        self.assertEqual(data["metrics"]["portfolio_value"], 950)
        self.assertEqual(
            [point["date"] for point in data["points"]],
            [self._days_ago(7).isoformat(), self._days_ago(1).isoformat()],
        )

    def test_performance_ignores_future_end_date(self):
        self._seed_cash_and_stock()

        response = self._get_performance(
            f"?end_date={self.today + datetime.timedelta(days=30)}"
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["end_date"], self.today.isoformat())
        self.assertEqual(data["metrics"]["portfolio_value"], 1000)

    def test_performance_replays_transactions_for_past_quantities(self):
        portfolio = self._create_portfolio()
        cash = self._asset("CASH-USD", "Cash USD", self.cash_type, self.usd)
        apple = self._asset("AAPL", "Apple Inc.", self.stock_type, self.usd)
        microsoft = self._asset("MSFT", "Microsoft Corp.", self.stock_type, self.usd)
        self._holding(portfolio, cash, quantity=1, average_cost=1000)
        apple_holding = self._holding(portfolio, apple, quantity=10, average_cost=50)
        microsoft_holding = self._holding(
            portfolio, microsoft, quantity=2, average_cost=10
        )
        self._prices(
            apple, {self._days_ago(10): 80, self._days_ago(1): 95, self.today: 100}
        )
        self._prices(
            microsoft, {self._days_ago(10): 10, self._days_ago(1): 10, self.today: 10}
        )
        # 10 日前に AAPL 4 株と MSFT 5 株を買い、前日に AAPL を 6 株買い増して
        # MSFT を 3 株売却した。
        self._trade(
            apple_holding,
            trade_date=self._days_ago(10),
            quantity=4,
            price=80,
            transaction_type="buy",
        )
        self._trade(
            apple_holding,
            trade_date=self._days_ago(1),
            quantity=6,
            price=95,
            transaction_type="buy",
        )
        self._trade(
            microsoft_holding,
            trade_date=self._days_ago(10),
            quantity=5,
            price=10,
            transaction_type="buy",
        )
        self._trade(
            microsoft_holding,
            trade_date=self._days_ago(1),
            quantity=3,
            price=10,
            transaction_type="sell",
        )

        response = self._get_performance()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(
            [point["total_market_value"] for point in data["points"]],
            [
                # 買い増し前: AAPL 4 株 * 80 + MSFT 5 株 * 10
                370,
                # 売買当日: AAPL 10 株 * 95 + MSFT 2 株 * 10
                970,
                1020,
            ],
        )
        # 運用開始日は最初の取引日。
        self.assertEqual(data["start_date"], self._days_ago(10).isoformat())

    def test_performance_samples_points_by_week(self):
        portfolio = self._create_portfolio()
        apple = self._asset("AAPL", "Apple Inc.", self.stock_type, self.usd)
        self._holding(portfolio, apple, quantity=1, average_cost=50)
        # 週の初日とその週の今日は同じ ISO 週にまとまる。
        monday = self.today - datetime.timedelta(days=self.today.weekday())
        self._prices(
            apple, {monday - datetime.timedelta(days=3): 80, monday: 90, self.today: 100}
        )

        response = self._get_performance("?interval=1wk")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["interval"], "1wk")
        self.assertEqual(len(data["points"]), 2)
        # 各週の最後の点だけが残る。
        self.assertEqual(data["points"][-1]["date"], self.today.isoformat())
        self.assertEqual(data["points"][-1]["total_market_value"], 100)

    def test_performance_samples_points_by_month(self):
        portfolio = self._create_portfolio()
        apple = self._asset("AAPL", "Apple Inc.", self.stock_type, self.usd)
        self._holding(portfolio, apple, quantity=1, average_cost=50)
        first_of_month = self.today.replace(day=1)
        self._prices(
            apple,
            {
                first_of_month - datetime.timedelta(days=15): 80,
                first_of_month: 90,
                self.today: 100,
            },
        )

        response = self._get_performance("?interval=1mo")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["points"]), 2)
        self.assertEqual(data["points"][-1]["date"], self.today.isoformat())
        self.assertEqual(data["points"][-1]["total_market_value"], 100)

    def test_performance_converts_foreign_currency_with_current_fx(self):
        portfolio = self._create_portfolio()
        toyota = self._asset("7203.T", "Toyota Motor Corp.", self.stock_type, self.jpy)
        self._holding(portfolio, toyota, quantity=2, average_cost=1000)
        self._prices(toyota, {self._days_ago(1): 1000, self.today: 1500})
        FakeMarketData.fx_rates = {"JPY": 0.01}

        response = self._get_performance()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(
            [point["total_market_value"] for point in data["points"]], [20, 30]
        )

    def test_performance_uses_stored_fx_history_when_available(self):
        portfolio = self._create_portfolio()
        toyota = self._asset("7203.T", "Toyota Motor Corp.", self.stock_type, self.jpy)
        self._holding(portfolio, toyota, quantity=2, average_cost=1000)
        self._prices(toyota, {self._days_ago(1): 1000, self.today: 1500})
        # 保存済みレートが現在レートより優先される。
        self._rates(self.jpy, {self._days_ago(1): "0.005"})
        FakeMarketData.fx_rates = {"JPY": 0.01}

        response = self._get_performance()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(
            [point["total_market_value"] for point in data["points"]],
            # 前日は 2 * 1000 * 0.005、今日はレートが無いので前日分を横引きする。
            [10, 15],
        )

    def test_performance_uses_earliest_stored_fx_before_history_starts(self):
        portfolio = self._create_portfolio()
        toyota = self._asset("7203.T", "Toyota Motor Corp.", self.stock_type, self.jpy)
        self._holding(portfolio, toyota, quantity=2, average_cost=1000)
        self._prices(toyota, {self._days_ago(1): 1000, self.today: 1500})
        # 今日のレートしか無い。前日は現在レートではなく最も古い保存済み
        # レートまで遡って換算する。
        self._rates(self.jpy, {self.today: "0.005"})
        FakeMarketData.fx_rates = {"JPY": 0.01}

        response = self._get_performance()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(
            [point["total_market_value"] for point in data["points"]], [10, 15]
        )

    def test_performance_converts_cash_with_stored_fx(self):
        portfolio = self._create_portfolio()
        cash = self._asset("CASH-JPY", "Cash JPY", self.cash_type, self.jpy)
        self._holding(portfolio, cash, quantity=1, average_cost=100000)
        self._rates(self.jpy, {self._days_ago(3): "0.004", self._days_ago(1): "0.005"})
        FakeMarketData.fx_rates = {"JPY": 0.01}

        response = self._get_performance("?asset_type=cash")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        # 現在レートの 0.01 ではなく、直近の保存済みレート 0.005 で換算する。
        self.assertEqual(
            data["points"],
            [{"date": self.today.isoformat(), "total_market_value": 500}],
        )

    def test_performance_values_currency_with_history_but_no_current_fx(self):
        portfolio = self._create_portfolio()
        toyota = self._asset("7203.T", "Toyota Motor Corp.", self.stock_type, self.jpy)
        self._holding(portfolio, toyota, quantity=2, average_cost=1000)
        self._prices(toyota, {self.today: 1500})
        self._rates(self.jpy, {self.today: "0.005"})
        # Yahoo が落ちていても、保存済みレートがあれば評価できる。
        FakeMarketData.fx_rates = {}

        response = self._get_performance()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(
            [point["total_market_value"] for point in data["points"]], [15]
        )

    def test_performance_skips_holdings_without_fx_or_prices(self):
        portfolio = self._create_portfolio()
        cash = self._asset("CASH-USD", "Cash USD", self.cash_type, self.usd)
        toyota = self._asset("7203.T", "Toyota Motor Corp.", self.stock_type, self.jpy)
        unlisted = self._asset("NEW", "Newly Added", self.stock_type, self.usd)
        self._holding(portfolio, cash, quantity=1, average_cost=1000)
        self._holding(portfolio, toyota, quantity=2, average_cost=1000)
        self._holding(portfolio, unlisted, quantity=5, average_cost=10)
        self._prices(toyota, {self.today: 1500})
        # Toyota は FX が無く、NEW は価格データが無い。現金も集計外なので 0。
        FakeMarketData.fx_rates = {}

        response = self._get_performance()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(
            [point["total_market_value"] for point in data["points"]], [0]
        )
        self.assertEqual(data["metrics"]["portfolio_value"], 0)

    def test_performance_returns_flat_series_for_cash_asset_type(self):
        portfolio = self._create_portfolio()
        cash = self._asset("CASH-USD", "Cash USD", self.cash_type, self.usd)
        self._holding(portfolio, cash, quantity=1, average_cost=1000)

        response = self._get_performance("?asset_type=cash")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["asset_type"], "cash")
        self.assertEqual(
            data["points"],
            [{"date": self.today.isoformat(), "total_market_value": 1000}],
        )
        self.assertEqual(data["return_total"], {"amount": 0, "percent": 0})

    def test_performance_excludes_cash_from_the_default_series(self):
        portfolio = self._create_portfolio()
        cash = self._asset("CASH-USD", "Cash USD", self.cash_type, self.usd)
        self._holding(portfolio, cash, quantity=1, average_cost=1000)

        response = self._get_performance()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["asset_type"], "all")
        # 現金しか持っていなくても、評価額には算入しない。
        self.assertEqual(
            data["points"],
            [{"date": self.today.isoformat(), "total_market_value": 0}],
        )

    def test_performance_filters_series_by_asset_type(self):
        portfolio = self._create_portfolio()
        bond_type = AssetType(id=uuid.uuid4(), asset_type="bond")
        db.session.add(bond_type)
        db.session.commit()
        cash = self._asset("CASH-USD", "Cash USD", self.cash_type, self.usd)
        apple = self._asset("AAPL", "Apple Inc.", self.stock_type, self.usd)
        bond = self._asset("US10Y", "US 10Y", bond_type, self.usd)
        self._holding(portfolio, cash, quantity=1, average_cost=1000)
        self._holding(portfolio, apple, quantity=10, average_cost=50)
        self._holding(portfolio, bond, quantity=5, average_cost=100)
        self._prices(apple, {self._days_ago(1): 90, self.today: 100})
        self._prices(bond, {self._days_ago(1): 200, self.today: 300})

        response = self._get_performance("?asset_type=bond")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["asset_type"], "bond")
        # 債券 5 口だけ。株式と現金は集計しない。
        self.assertEqual(
            [point["total_market_value"] for point in data["points"]], [1000, 1500]
        )
        self.assertEqual(data["metrics"]["portfolio_value"], 1500)
        self.assertEqual(data["return_total"]["amount"], 500)

    def test_performance_returns_zeros_for_unknown_asset_type(self):
        self._seed_cash_and_stock()

        response = self._get_performance("?asset_type=crypto")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["asset_type"], "crypto")
        self.assertEqual(
            data["points"],
            [{"date": self.today.isoformat(), "total_market_value": 0}],
        )

    def test_performance_asset_type_filter_is_case_insensitive(self):
        self._seed_cash_and_stock()

        response = self._get_performance("?asset_type=STOCK")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["asset_type"], "stock")
        self.assertEqual(data["metrics"]["portfolio_value"], 1000)

    def test_performance_returns_zeros_for_empty_portfolio(self):
        self._create_portfolio()

        response = self._get_performance()

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["metrics"]["portfolio_value"], 0)
        self.assertEqual(
            data["points"],
            [{"date": self.today.isoformat(), "total_market_value": 0}],
        )
        self.assertEqual(data["return_1d"], {"amount": 0, "percent": 0})

    def test_performance_defaults_asset_type_to_all(self):
        self._seed_cash_and_stock()

        response = self._get_performance()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["asset_type"], "all")

    def test_performance_filters_series_by_asset_type(self):
        self._seed_cash_and_stock()

        response = self._get_performance("?asset_type=stock")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["asset_type"], "stock")
        # 現金 1000 を除いた AAPL 10 株ぶんだけの系列になる。
        self.assertEqual(
            [(point["date"], point["total_market_value"]) for point in data["points"]],
            [
                (self._days_ago(10).isoformat(), 800),
                (self._days_ago(7).isoformat(), 900),
                (self._days_ago(1).isoformat(), 950),
                (self.today.isoformat(), 1000),
            ],
        )
        self.assertEqual(data["metrics"]["portfolio_value"], 1000)
        self.assertEqual(data["return_total"]["amount"], 200)
        self.assertAlmostEqual(
            data["return_total"]["percent"], 200 / 800 * 100, places=6
        )

    def test_performance_filters_cash_only(self):
        self._seed_cash_and_stock()

        response = self._get_performance("?asset_type=cash")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        # cash holding は取引履歴を持たないため、期間中は一定額になる。
        self.assertEqual(
            data["points"],
            [{"date": self.today.isoformat(), "total_market_value": 1000}],
        )
        self.assertEqual(data["return_total"], {"amount": 0, "percent": 0})

    def test_performance_returns_zeros_for_unheld_asset_type(self):
        self._seed_cash_and_stock()

        response = self._get_performance("?asset_type=bond")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["metrics"]["portfolio_value"], 0)
        self.assertEqual(
            data["points"],
            [{"date": self.today.isoformat(), "total_market_value": 0}],
        )

    def test_performance_rejects_start_date_after_end_date(self):
        self._create_portfolio()

        response = self._get_performance(
            f"?start_date={self.today}&end_date={self._days_ago(1)}"
        )

        self.assertEqual(response.status_code, 422)

    def test_performance_rejects_unknown_range(self):
        self._create_portfolio()

        response = self._get_performance("?range=5y")

        self.assertEqual(response.status_code, 422)

    def test_performance_returns_404_when_portfolio_is_missing(self):
        response = self._get_performance()

        self.assertEqual(response.status_code, 404)

    def test_performance_requires_bearer_token(self):
        response = self.client.get("/api/v1/portfolios/performance")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
