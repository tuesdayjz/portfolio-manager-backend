"""GET /api/v1/portfolios/transactions の実装 tests。"""

import datetime
import decimal
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
    CurrencyRateHistory,
    Holdings,
    Portfolio,
    Transactions,
    Users,
)


class TransactionHistoryEndpointTest(unittest.TestCase):
    """取引履歴の ownership join、filter、pagination、実現損益を確認する。"""

    def setUp(self):
        self.app = create_app("testing")
        self.app.config["DEFAULT_BASE_CURRENCY"] = "USD"
        self.client = self.app.test_client()
        self.user_id = uuid.uuid4()
        self.other_user_id = uuid.uuid4()
        self.portfolio_id = uuid.uuid4()
        self.other_portfolio_id = uuid.uuid4()

        self.app_context = self.app.app_context()
        self.app_context.push()
        self._create_sqlite_schema()
        self._seed_data()
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
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                transaction_type TEXT NOT NULL,
                position TEXT NOT NULL DEFAULT 'long'
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
            "currency_rate_history",
            "holdings",
            "portfolio",
            "asset_master",
            "asset_type",
            "currency",
            "users",
        ):
            db.session.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        db.session.commit()

    def _seed_data(self):
        now = datetime.datetime(2026, 5, 28, tzinfo=datetime.timezone.utc)
        currency = Currency(id=uuid.uuid4(), currency="USD", symbol="$")
        jpy = Currency(id=uuid.uuid4(), currency="JPY", symbol="¥")
        stock_type = AssetType(id=uuid.uuid4(), asset_type="stock")
        etf_type = AssetType(id=uuid.uuid4(), asset_type="etf")
        aapl = AssetMaster(
            id=uuid.uuid4(),
            ticker="AAPL",
            name="Apple Inc.",
            asset_type=stock_type,
            currency=currency,
        )
        spy = AssetMaster(
            id=uuid.uuid4(),
            ticker="SPY",
            name="SPDR S&P 500 ETF",
            asset_type=etf_type,
            currency=currency,
        )
        other_asset = AssetMaster(
            id=uuid.uuid4(),
            ticker="MSFT",
            name="Microsoft Corp.",
            asset_type=stock_type,
            currency=currency,
        )
        toyota = AssetMaster(
            id=uuid.uuid4(),
            ticker="7203.T",
            name="Toyota Motor Corp.",
            asset_type=stock_type,
            currency=jpy,
        )
        aapl_holding = Holdings(
            id=uuid.uuid4(),
            portfolio_id=self.portfolio_id,
            asset=aapl,
            quantity=decimal.Decimal("7"),
            average_cost=decimal.Decimal("100"),
            updated_at=now,
        )
        spy_holding = Holdings(
            id=uuid.uuid4(),
            portfolio_id=self.portfolio_id,
            asset=spy,
            quantity=decimal.Decimal("2"),
            average_cost=decimal.Decimal("400"),
            updated_at=now,
        )
        other_holding = Holdings(
            id=uuid.uuid4(),
            portfolio_id=self.other_portfolio_id,
            asset=other_asset,
            quantity=decimal.Decimal("1"),
            average_cost=decimal.Decimal("250"),
            updated_at=now,
        )

        db.session.add_all(
            [
                Users(
                    id=self.user_id,
                    email="history@example.com",
                    created_at=now,
                    updated_at=now,
                ),
                Users(
                    id=self.other_user_id,
                    email="other-history@example.com",
                    created_at=now,
                    updated_at=now,
                ),
                currency,
                jpy,
                stock_type,
                etf_type,
                Portfolio(
                    id=self.portfolio_id,
                    user_id=self.user_id,
                    created_at=now,
                    updated_at=now,
                ),
                Portfolio(
                    id=self.other_portfolio_id,
                    user_id=self.other_user_id,
                    created_at=now,
                    updated_at=now,
                ),
                aapl,
                spy,
                other_asset,
                toyota,
                CurrencyRateHistory(
                    id=uuid.uuid4(),
                    currency=jpy,
                    rate_date=datetime.date(2026, 5, 26),
                    close_price=decimal.Decimal("0.01"),
                ),
                aapl_holding,
                spy_holding,
                other_holding,
                Transactions(
                    id=uuid.uuid4(),
                    holding=aapl_holding,
                    trade_date=datetime.date(2026, 5, 26),
                    quantity=decimal.Decimal("10"),
                    price=decimal.Decimal("100"),
                    fees=decimal.Decimal("0"),
                    created_at=now,
                    transaction_type="buy",
                ),
                Transactions(
                    id=uuid.uuid4(),
                    holding=aapl_holding,
                    trade_date=datetime.date(2026, 5, 27),
                    quantity=decimal.Decimal("3"),
                    price=decimal.Decimal("150"),
                    fees=decimal.Decimal("15"),
                    average_cost_before=decimal.Decimal("100"),
                    created_at=now + datetime.timedelta(minutes=1),
                    transaction_type="sell",
                ),
                Transactions(
                    id=uuid.uuid4(),
                    holding=spy_holding,
                    trade_date=datetime.date(2026, 6, 1),
                    quantity=decimal.Decimal("1"),
                    price=decimal.Decimal("420"),
                    fees=decimal.Decimal("0"),
                    average_cost_before=decimal.Decimal("400"),
                    created_at=now + datetime.timedelta(minutes=2),
                    transaction_type="sell",
                ),
                Transactions(
                    id=uuid.uuid4(),
                    holding=other_holding,
                    trade_date=datetime.date(2026, 6, 2),
                    quantity=decimal.Decimal("1"),
                    price=decimal.Decimal("300"),
                    fees=decimal.Decimal("0"),
                    average_cost_before=decimal.Decimal("250"),
                    created_at=now + datetime.timedelta(minutes=3),
                    transaction_type="sell",
                ),
            ]
        )
        db.session.commit()

    def _auth(self):
        g.current_user_id = str(self.user_id)
        g.current_user_email = "history@example.com"
        g.current_access_token = "test-token"

    def _get_history(self, query_string=None):
        with patch("app.api.transactions.require_auth", side_effect=self._auth):
            return self.client.get(
                "/api/v1/portfolios/transactions", query_string=query_string or {}
            )

    def test_get_transactions_requires_bearer_token(self):
        response = self.client.get("/api/v1/portfolios/transactions")

        self.assertEqual(response.status_code, 401)

    def test_get_transactions_returns_404_without_portfolio(self):
        portfolioless_user_id = uuid.uuid4()

        def auth_as_portfolioless_user():
            g.current_user_id = str(portfolioless_user_id)
            g.current_user_email = "no-portfolio@example.com"
            g.current_access_token = "test-token"

        with patch(
            "app.api.transactions.require_auth",
            side_effect=auth_as_portfolioless_user,
        ):
            response = self.client.get("/api/v1/portfolios/transactions")

        self.assertEqual(response.status_code, 404)

    def test_get_transactions_returns_history_shape_and_totals(self):
        response = self._get_history({"page": 1, "per_page": 5})

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(len(body["items"]), 3)
        self.assertEqual([item["symbol"] for item in body["items"]], ["SPY", "AAPL", "AAPL"])
        self.assertEqual(body["items"][0]["position"], "long")
        self.assertEqual(body["items"][0]["transaction_type"], "sell")
        self.assertEqual(body["items"][0]["quantity"], 1.0)
        self.assertEqual(body["items"][0]["executed_unit_price"], 420.0)
        self.assertEqual(body["items"][0]["executed_price"], 420.0)
        self.assertEqual(body["items"][0]["realized_pl"], 20.0)
        self.assertEqual(body["items"][0]["realized_pl_percent"], 5.0)
        self.assertEqual(body["items"][1]["realized_pl"], 150.0)
        self.assertEqual(body["items"][1]["realized_pl_percent"], 50.0)
        self.assertIsNone(body["items"][2]["realized_pl"])
        self.assertIsNone(body["items"][2]["realized_pl_percent"])
        self.assertEqual(body["totals"]["realized_pl"], 170.0)
        self.assertEqual(body["totals"]["realized_pl_percent"], 24.285714285714285)
        self.assertEqual(body["totals"]["currency"], "USD")
        self.assertEqual(
            body["pagination"],
            {"page": 1, "per_page": 5, "total_items": 3, "total_pages": 1},
        )

    def test_get_transactions_short_position_realized_pl_on_cover(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        currency = Currency.query.filter_by(currency="USD").one()
        stock_type = AssetType.query.filter_by(asset_type="stock").one()
        tsla = AssetMaster(
            id=uuid.uuid4(),
            ticker="TSLA",
            name="Tesla Inc.",
            asset_type=stock_type,
            currency=currency,
        )
        tsla_holding = Holdings(
            id=uuid.uuid4(),
            portfolio_id=self.portfolio_id,
            asset=tsla,
            quantity=decimal.Decimal("0"),
            average_cost=decimal.Decimal("200"),
            updated_at=now,
        )
        db.session.add_all(
            [
                tsla,
                tsla_holding,
                Transactions(
                    id=uuid.uuid4(),
                    holding=tsla_holding,
                    trade_date=datetime.date(2026, 6, 3),
                    quantity=decimal.Decimal("5"),
                    price=decimal.Decimal("200"),
                    fees=decimal.Decimal("0"),
                    average_cost_before=decimal.Decimal("0"),
                    created_at=now + datetime.timedelta(minutes=4),
                    transaction_type="sell",
                    position="short",
                ),
                Transactions(
                    id=uuid.uuid4(),
                    holding=tsla_holding,
                    trade_date=datetime.date(2026, 6, 4),
                    quantity=decimal.Decimal("5"),
                    price=decimal.Decimal("150"),
                    fees=decimal.Decimal("0"),
                    average_cost_before=decimal.Decimal("200"),
                    created_at=now + datetime.timedelta(minutes=5),
                    transaction_type="buy",
                    position="short",
                ),
            ]
        )
        db.session.commit()

        response = self._get_history({"page": 1, "per_page": 10})

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        items_by_key = {
            (item["symbol"], item["transaction_type"], item["executed_unit_price"]): item
            for item in body["items"]
        }
        open_short = items_by_key[("TSLA", "sell", 200.0)]
        cover = items_by_key[("TSLA", "buy", 150.0)]
        self.assertEqual(open_short["position"], "short")
        self.assertEqual(cover["position"], "short")
        # Opening a short (sell) doesn't realize P&L, same as opening a long (buy).
        self.assertIsNone(open_short["realized_pl"])
        self.assertIsNone(open_short["realized_pl_percent"])
        # Covering a short (buy) realizes P&L inverted from closing a long:
        # profit when the cover price is below the average entry price.
        self.assertEqual(cover["realized_pl"], 250.0)
        self.assertEqual(cover["realized_pl_percent"], 25.0)

    def test_get_transactions_filters_by_type_asset_and_date(self):
        response = self._get_history(
            {
                "transaction_type": "sell",
                "asset_type": "stock",
                "start_date": "2026-05-27",
                "end_date": "2026-05-31",
            }
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["symbol"], "AAPL")
        self.assertEqual(body["items"][0]["realized_pl"], 150.0)
        self.assertEqual(body["items"][0]["realized_pl_percent"], 50.0)
        self.assertEqual(body["totals"]["realized_pl"], 150.0)

    def test_get_transactions_converts_monetary_fields_to_usd(self):
        self.app.config["DEFAULT_BASE_CURRENCY"] = "JPY"
        now = datetime.datetime(2026, 5, 28, tzinfo=datetime.timezone.utc)
        toyota = AssetMaster.query.filter_by(ticker="7203.T").one()
        holding = Holdings(
            id=uuid.uuid4(),
            portfolio_id=self.portfolio_id,
            asset=toyota,
            quantity=decimal.Decimal("0"),
            average_cost=decimal.Decimal("3000"),
            updated_at=now,
        )
        db.session.add_all(
            [
                holding,
                Transactions(
                    id=uuid.uuid4(),
                    holding=holding,
                    trade_date=datetime.date(2026, 5, 27),
                    quantity=decimal.Decimal("2"),
                    price=decimal.Decimal("3000"),
                    fees=decimal.Decimal("0"),
                    created_at=now + datetime.timedelta(minutes=4),
                    transaction_type="buy",
                ),
                Transactions(
                    id=uuid.uuid4(),
                    holding=holding,
                    trade_date=datetime.date(2026, 5, 28),
                    quantity=decimal.Decimal("2"),
                    price=decimal.Decimal("3500"),
                    fees=decimal.Decimal("0"),
                    average_cost_before=decimal.Decimal("3000"),
                    created_at=now + datetime.timedelta(minutes=5),
                    transaction_type="sell",
                ),
            ]
        )
        db.session.commit()

        response = self._get_history({"asset_type": "stock", "start_date": "2026-05-27"})

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        toyota_sell = next(
            item
            for item in body["items"]
            if item["symbol"] == "7203.T" and item["transaction_type"] == "sell"
        )
        toyota_buy = next(
            item
            for item in body["items"]
            if item["symbol"] == "7203.T" and item["transaction_type"] == "buy"
        )
        self.assertEqual(toyota_buy["executed_unit_price"], 30.0)
        self.assertEqual(toyota_buy["executed_price"], 60.0)
        self.assertEqual(toyota_sell["executed_unit_price"], 35.0)
        self.assertEqual(toyota_sell["executed_price"], 70.0)
        self.assertEqual(toyota_sell["realized_pl"], 10.0)
        self.assertAlmostEqual(toyota_sell["realized_pl_percent"], 16.666666666666664)
        self.assertEqual(body["totals"]["realized_pl"], 160.0)
        self.assertAlmostEqual(body["totals"]["realized_pl_percent"], 44.44444444444444)
        self.assertEqual(body["totals"]["currency"], "USD")

    def test_get_transactions_paginates_filtered_rows(self):
        response = self._get_history({"page": 2, "per_page": 2})

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual([item["symbol"] for item in body["items"]], ["AAPL"])
        self.assertEqual(
            body["pagination"],
            {"page": 2, "per_page": 2, "total_items": 3, "total_pages": 2},
        )


if __name__ == "__main__":
    unittest.main()
