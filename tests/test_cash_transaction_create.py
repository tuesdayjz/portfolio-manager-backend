"""POST /api/v1/portfolios/capital の実装 tests。"""

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
    def fx_to_usd(self, currency):
        return decimal.Decimal("1") if (currency or "USD").upper() == "USD" else None

    def fx_to_usd_on(self, currency, date):
        return self.fx_to_usd(currency)


class CashTransactionCreateEndpointTest(unittest.TestCase):
    """入金・出金による cash holding の残高更新と取引記録を確認する。"""

    INITIAL_CASH_BALANCE = decimal.Decimal("1000000")

    def setUp(self):
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
                average_cost_before NUMERIC,
                cash_balance_before NUMERIC,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                transaction_type TEXT NOT NULL,
                position TEXT NOT NULL DEFAULT 'long'
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
        usd_currency_id = uuid.uuid4()
        cash_asset_type_id = uuid.uuid4()
        cash_asset_id = uuid.uuid4()
        db.session.add_all(
            [
                Users(
                    id=self.user_id,
                    email=self.user_email,
                    created_at=now,
                    updated_at=now,
                ),
                Currency(id=usd_currency_id, currency="USD", symbol="$"),
                AssetType(id=cash_asset_type_id, asset_type="cash"),
                Portfolio(
                    id=self.portfolio_id,
                    user_id=self.user_id,
                    created_at=now,
                    updated_at=now,
                ),
                AssetMaster(
                    id=cash_asset_id,
                    ticker="CASH-USD",
                    name="Cash USD",
                    asset_type_id=cash_asset_type_id,
                    currency_id=usd_currency_id,
                ),
                Holdings(
                    id=uuid.uuid4(),
                    portfolio_id=self.portfolio_id,
                    asset_id=cash_asset_id,
                    quantity=decimal.Decimal("1"),
                    average_cost=self.INITIAL_CASH_BALANCE,
                    updated_at=now,
                ),
            ]
        )
        db.session.commit()

    def _auth(self):
        g.current_user_id = str(self.user_id)
        g.current_user_email = self.user_email
        g.current_access_token = "test-token"

    def _post_capital(self, payload):
        with (
            patch("app.api.portfolios.require_auth", side_effect=self._auth),
            patch("app.services.transaction.YahooFinanceMarketData", FakeMarketData),
        ):
            return self.client.post("/api/v1/portfolios/capital", json=payload)

    def _cash_holding(self):
        return (
            Holdings.query.join(Holdings.asset)
            .filter(AssetMaster.ticker == "CASH-USD")
            .one()
        )

    def test_create_capital_transaction_requires_bearer_token(self):
        response = self.client.post(
            "/api/v1/portfolios/capital",
            json={"transaction_type": "deposit", "amount": 5000},
        )

        self.assertEqual(response.status_code, 401)

    def test_create_capital_transaction_returns_404_without_portfolio(self):
        portfolioless_user_id = uuid.uuid4()

        def auth_as_portfolioless_user():
            g.current_user_id = str(portfolioless_user_id)
            g.current_user_email = "no-portfolio@example.com"
            g.current_access_token = "test-token"

        with patch(
            "app.api.portfolios.require_auth",
            side_effect=auth_as_portfolioless_user,
        ):
            response = self.client.post(
                "/api/v1/portfolios/capital",
                json={"transaction_type": "deposit", "amount": 5000},
            )

        self.assertEqual(response.status_code, 404)

    def test_deposit_increases_cash_balance(self):
        response = self._post_capital({"transaction_type": "deposit", "amount": 5000})

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["transaction_type"], "deposit")
        self.assertEqual(body["amount"], 5000.0)
        self.assertEqual(
            body["cash_balance"], float(self.INITIAL_CASH_BALANCE + 5000)
        )

        cash_holding = self._cash_holding()
        self.assertEqual(
            float(cash_holding.average_cost), float(self.INITIAL_CASH_BALANCE + 5000)
        )
        transaction = Transactions.query.one()
        self.assertEqual(transaction.transaction_type, "deposit")
        self.assertEqual(float(transaction.quantity), 5000.0)
        self.assertEqual(float(transaction.price), 1.0)
        self.assertIsNone(transaction.average_cost_before)
        self.assertEqual(float(transaction.cash_balance_before), 1000000.0)

    def test_deposit_replays_existing_trade_cash_balance_before_as_initial_cash(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        cash_holding = self._cash_holding()
        cash_holding.average_cost = decimal.Decimal("0")
        usd = Currency.query.filter_by(currency="USD").one()
        stock_type = AssetType(id=uuid.uuid4(), asset_type="stock")
        asset = AssetMaster(
            id=uuid.uuid4(),
            ticker="AAPL",
            name="Apple Inc.",
            asset_type=stock_type,
            currency=usd,
        )
        holding = Holdings(
            id=uuid.uuid4(),
            portfolio_id=self.portfolio_id,
            asset=asset,
            quantity=decimal.Decimal("2"),
            average_cost=decimal.Decimal("50"),
            updated_at=now,
        )
        buy = Transactions(
            id=uuid.uuid4(),
            holding=holding,
            trade_date=now.date() - datetime.timedelta(days=1),
            quantity=decimal.Decimal("2"),
            price=decimal.Decimal("50"),
            average_cost_before=decimal.Decimal("0"),
            cash_balance_before=decimal.Decimal("100"),
            transaction_type="buy",
            created_at=now,
        )
        db.session.add_all([stock_type, asset, holding, buy])
        db.session.commit()

        response = self._post_capital({"transaction_type": "deposit", "amount": 100})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(float(self._cash_holding().average_cost), 100.0)
        db.session.refresh(buy)
        self.assertEqual(float(buy.cash_balance_before), 200.0)

    def test_withdrawal_decreases_cash_balance(self):
        response = self._post_capital(
            {"transaction_type": "withdrawal", "amount": 2500}
        )

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(
            body["cash_balance"], float(self.INITIAL_CASH_BALANCE - 2500)
        )
        cash_holding = self._cash_holding()
        self.assertEqual(
            float(cash_holding.average_cost), float(self.INITIAL_CASH_BALANCE - 2500)
        )
        transaction = Transactions.query.one()
        self.assertEqual(transaction.transaction_type, "withdrawal")
        self.assertEqual(float(transaction.cash_balance_before), 1000000.0)

    def test_withdrawal_more_than_balance_returns_400(self):
        response = self._post_capital(
            {
                "transaction_type": "withdrawal",
                "amount": float(self.INITIAL_CASH_BALANCE) + 1,
            }
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transactions.query.count(), 0)
        cash_holding = self._cash_holding()
        self.assertEqual(float(cash_holding.average_cost), float(self.INITIAL_CASH_BALANCE))

    def test_rejects_non_positive_amount(self):
        response = self._post_capital({"transaction_type": "deposit", "amount": 0})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(Transactions.query.count(), 0)

    def test_rejects_negative_amount(self):
        response = self._post_capital({"transaction_type": "deposit", "amount": -100})

        self.assertEqual(response.status_code, 422)

    def test_rejects_buy_sell_transaction_types(self):
        response = self._post_capital({"transaction_type": "buy", "amount": 100})

        self.assertEqual(response.status_code, 422)

    def test_rejects_missing_amount(self):
        response = self._post_capital({"transaction_type": "deposit"})

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
