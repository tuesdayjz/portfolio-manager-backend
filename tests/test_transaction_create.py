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
        "7203.T": decimal.Decimal("3000"),
    }
    latest_closes = {
        "AAPL": decimal.Decimal("145"),
        "MSFT": decimal.Decimal("295"),
        "7203.T": decimal.Decimal("2900"),
    }
    fx_rates = {"JPY": decimal.Decimal("0.01"), "USD": decimal.Decimal("1")}
    historical_fx_rates = {}
    meta = {
        "AAPL": {"quote_type": "EQUITY", "currency": "USD"},
        "MSFT": {"quote_type": "EQUITY", "currency": "USD"},
        "7203.T": {"quote_type": "EQUITY", "currency": "JPY"},
        "IPO": {"quote_type": "EQUITY", "currency": "USD"},
        "BONDX": {"quote_type": "BOND", "currency": "USD"},
        "ZT=F": {"quote_type": "FUTURE", "currency": "USD"},
        "CL=F": {"quote_type": "FUTURE", "currency": "USD"},
        "UNKNOWNX": None,
    }
    listed_from = {}
    closed_dates = set()

    def latest_price(self, ticker):
        return self.prices.get(ticker)

    def today_order_price(self, ticker):
        price = self.latest_price(ticker)
        if price is not None:
            return price
        return self.latest_closes.get(ticker)

    def fx_to_usd(self, currency):
        return self.fx_rates.get((currency or "USD").upper())

    def fx_to_usd_on(self, currency, date):
        currency = (currency or "USD").upper()
        return self.historical_fx_rates.get((currency, date), self.fx_to_usd(currency))

    def asset_meta(self, ticker):
        return self.meta.get(ticker)

    def asset_tradable_on(self, ticker, date):
        listed_from = self.listed_from.get(ticker)
        if listed_from is not None and listed_from > date:
            return False
        return date not in self.closed_dates


class TransactionCreateEndpointTest(unittest.TestCase):
    """取引作成の holdings 更新・平均取得単価の再計算・oversell 拒否を確認する。"""

    def setUp(self):
        FakeMarketData.prices = {
            "AAPL": decimal.Decimal("150"),
            "MSFT": decimal.Decimal("300"),
            "7203.T": decimal.Decimal("3000"),
            "IPO": decimal.Decimal("50"),
            "BONDX": decimal.Decimal("98.75"),
            "ZT=F": decimal.Decimal("103.00"),
            "CL=F": decimal.Decimal("68.34"),
        }
        FakeMarketData.latest_closes = {
            "AAPL": decimal.Decimal("145"),
            "MSFT": decimal.Decimal("295"),
            "7203.T": decimal.Decimal("2900"),
            "IPO": decimal.Decimal("45"),
            "BONDX": decimal.Decimal("98.5"),
            "ZT=F": decimal.Decimal("102.99"),
            "CL=F": decimal.Decimal("68.10"),
        }
        FakeMarketData.fx_rates = {"JPY": decimal.Decimal("0.01"), "USD": decimal.Decimal("1")}
        FakeMarketData.historical_fx_rates = {}
        FakeMarketData.listed_from = {}
        FakeMarketData.closed_dates = set()

        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.user_id = uuid.uuid4()
        self.user_email = "trader@example.com"
        self.portfolio_id = uuid.uuid4()
        self.initial_cash = decimal.Decimal("10000")

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
        usd = Currency(id=uuid.uuid4(), currency="USD", symbol="$")
        jpy = Currency(id=uuid.uuid4(), currency="JPY", symbol="¥")
        stock_type = AssetType(id=uuid.uuid4(), asset_type="stock")
        cash_type = AssetType(id=uuid.uuid4(), asset_type="cash")
        portfolio = Portfolio(
            id=self.portfolio_id,
            user_id=self.user_id,
            created_at=now,
            updated_at=now,
        )
        cash_asset = AssetMaster(
            id=uuid.uuid4(),
            ticker="CASH-USD",
            name="Cash USD",
            asset_type=cash_type,
            currency=usd,
        )
        db.session.add_all(
            [
                Users(
                    id=self.user_id,
                    email=self.user_email,
                    created_at=now,
                    updated_at=now,
                ),
                usd,
                jpy,
                stock_type,
                cash_type,
                portfolio,
                cash_asset,
                Holdings(
                    id=uuid.uuid4(),
                    portfolio=portfolio,
                    asset=cash_asset,
                    quantity=decimal.Decimal("1"),
                    average_cost=self.initial_cash,
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

    def _holding_for_ticker(self, ticker):
        return (
            Holdings.query.join(Holdings.asset)
            .filter(AssetMaster.ticker == ticker)
            .one()
        )

    def _cash_balance(self):
        return float(self._holding_for_ticker("CASH-USD").average_cost)

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

    @staticmethod
    def _short_payload(ticker, name, quantity):
        return {
            "ticker": ticker,
            "name": name,
            "position": "short",
            "order_type": "market",
            "transaction_type": "sell",
            "quantity": quantity,
        }

    @staticmethod
    def _cover_payload(ticker, name, quantity):
        return {
            "ticker": ticker,
            "name": name,
            "position": "short",
            "order_type": "market",
            "transaction_type": "buy",
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

        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 10.0)
        self.assertEqual(float(holding.average_cost), 150.0)
        cash_holding = self._holding_for_ticker("CASH-USD")
        self.assertEqual(float(cash_holding.quantity), 1.0)
        self.assertEqual(float(cash_holding.average_cost), 8500.0)
        transaction = Transactions.query.one()
        self.assertEqual(float(transaction.average_cost_before), 0.0)
        self.assertEqual(float(transaction.cash_balance_before), 10000.0)

    def test_create_transaction_buy_bond_resolves_bond_asset_type(self):
        bond_type = AssetType(id=uuid.uuid4(), asset_type="bond")
        db.session.add(bond_type)
        db.session.commit()

        response = self._post_transaction(
            self._buy_payload("BONDX", "US Treasury 10-Year Note", 10)
        )

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["asset_type"], "bond")

        asset = AssetMaster.query.filter_by(ticker="BONDX").one()
        self.assertEqual(asset.asset_type.asset_type, "bond")

    def test_create_transaction_buy_bond_without_asset_type_row_returns_400(self):
        response = self._post_transaction(
            self._buy_payload("BONDX", "US Treasury 10-Year Note", 10)
        )

        self.assertEqual(response.status_code, 400)

    def test_create_transaction_buy_treasury_future_resolves_bond_asset_type(self):
        """`ZT=F` is `quote_type=FUTURE` in Yahoo - only resolves to "bond" because
        it's on the manual allowlist, not because of its quote_type."""
        bond_type = AssetType(id=uuid.uuid4(), asset_type="bond")
        db.session.add(bond_type)
        db.session.commit()

        response = self._post_transaction(
            self._buy_payload("ZT=F", "2-Year T-Note Futures", 5)
        )

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["asset_type"], "bond")

        asset = AssetMaster.query.filter_by(ticker="ZT=F").one()
        self.assertEqual(asset.asset_type.asset_type, "bond")

    def test_create_transaction_buy_commodity_future_resolves_futures_asset_type(self):
        """`CL=F` (crude oil futures) is `quote_type=FUTURE` and isn't on the manual
        bond allowlist, so it resolves to "futures" like any other non-Treasury future.

        The seeded `asset_type` row is plural, so this fixture deliberately mirrors
        the deployed table rather than whatever string the mapping happens to use.
        """
        futures_type = AssetType(id=uuid.uuid4(), asset_type="futures")
        db.session.add(futures_type)
        db.session.commit()

        response = self._post_transaction(self._buy_payload("CL=F", "Crude Oil Futures", 5))

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["asset_type"], "futures")

        asset = AssetMaster.query.filter_by(ticker="CL=F").one()
        self.assertEqual(asset.asset_type.asset_type, "futures")

    def test_create_transaction_buy_future_without_asset_type_row_returns_400(self):
        response = self._post_transaction(self._buy_payload("CL=F", "Crude Oil Futures", 5))

        self.assertEqual(response.status_code, 400)

    def test_create_transaction_buy_jpy_asset_updates_usd_cash(self):
        response = self._post_transaction(
            self._buy_payload("7203.T", "Toyota Motor Corp.", 2)
        )

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("7203.T")
        self.assertEqual(float(holding.quantity), 2.0)
        self.assertEqual(float(holding.average_cost), 3000.0)
        cash_holding = self._holding_for_ticker("CASH-USD")
        self.assertEqual(float(cash_holding.average_cost), 9940.0)
        self.assertEqual(AssetMaster.query.filter_by(ticker="CASH-JPY").count(), 0)

    def test_create_transaction_buy_existing_holding_recomputes_average_cost(self):
        first = self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 10))
        self.assertEqual(first.status_code, 201)

        FakeMarketData.prices["AAPL"] = decimal.Decimal("200")
        second = self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 10))
        self.assertEqual(second.status_code, 201)

        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 20.0)
        self.assertEqual(float(holding.average_cost), 175.0)
        cash_holding = self._holding_for_ticker("CASH-USD")
        self.assertEqual(float(cash_holding.average_cost), 6500.0)
        self.assertEqual(Transactions.query.count(), 2)
        second_buy = Transactions.query.filter_by(price=decimal.Decimal("200")).one()
        self.assertEqual(float(second_buy.average_cost_before), 150.0)
        self.assertEqual(float(second_buy.cash_balance_before), 8500.0)

    def test_create_transaction_sell_partial_reduces_quantity(self):
        self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 10))

        response = self._post_transaction(self._sell_payload("AAPL", "Apple Inc.", 4))

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 6.0)
        self.assertEqual(float(holding.average_cost), 150.0)
        cash_holding = self._holding_for_ticker("CASH-USD")
        self.assertEqual(float(cash_holding.average_cost), 9100.0)
        sell = Transactions.query.filter_by(transaction_type="sell").one()
        self.assertEqual(float(sell.average_cost_before), 150.0)
        self.assertEqual(float(sell.cash_balance_before), 8500.0)

    def test_create_transaction_sell_long_with_existing_long_succeeds(self):
        self.assertEqual(
            self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 5)).status_code,
            201,
        )

        response = self._post_transaction(self._sell_payload("AAPL", "Apple Inc.", 2))

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 3.0)

    def test_create_transaction_sell_more_than_holding_returns_400(self):
        self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 5))

        response = self._post_transaction(self._sell_payload("AAPL", "Apple Inc.", 10))

        self.assertEqual(response.status_code, 400)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 5.0)
        self.assertEqual(Transactions.query.count(), 1)
        cash_holding = self._holding_for_ticker("CASH-USD")
        self.assertEqual(float(cash_holding.average_cost), 9250.0)

    def test_create_transaction_short_sell_opens_negative_holding(self):
        response = self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 5))

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), -5.0)
        self.assertEqual(float(holding.average_cost), 150.0)
        cash_holding = self._holding_for_ticker("CASH-USD")
        self.assertEqual(float(cash_holding.average_cost), 10750.0)
        short = Transactions.query.filter_by(transaction_type="sell").one()
        self.assertEqual(short.position, "short")
        self.assertEqual(float(short.average_cost_before), 0.0)

    def test_create_transaction_service_accepts_string_short_sell(self):
        from app.services.transaction import create_transaction

        self._auth()
        payload = self._short_payload("AAPL", "Apple Inc.", 5)
        payload["transaction_type"] = "sell"

        create_transaction(payload, market_data=FakeMarketData())

        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), -5.0)
        self.assertEqual(float(holding.average_cost), 150.0)
        transaction = Transactions.query.filter_by(transaction_type="sell").one()
        self.assertEqual(transaction.position, "short")

    def test_create_transaction_short_sell_adds_to_existing_short_recomputes_average_cost(self):
        self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 10))

        FakeMarketData.prices["AAPL"] = decimal.Decimal("200")
        response = self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 10))

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), -20.0)
        self.assertEqual(float(holding.average_cost), 175.0)
        cash_holding = self._holding_for_ticker("CASH-USD")
        self.assertEqual(float(cash_holding.average_cost), 13500.0)

    def test_create_transaction_buy_to_cover_short_partial_reduces_magnitude(self):
        self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 10))

        FakeMarketData.prices["AAPL"] = decimal.Decimal("100")
        response = self._post_transaction(self._cover_payload("AAPL", "Apple Inc.", 4))

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), -6.0)
        # Covering doesn't change the average entry price, mirroring how selling
        # part of a long doesn't change its average cost.
        self.assertEqual(float(holding.average_cost), 150.0)
        cash_holding = self._holding_for_ticker("CASH-USD")
        self.assertEqual(float(cash_holding.average_cost), 11100.0)
        cover = Transactions.query.filter_by(transaction_type="buy").one()
        self.assertEqual(cover.position, "short")
        self.assertEqual(float(cover.average_cost_before), 150.0)

    def test_create_transaction_buy_to_cover_short_in_full_returns_holding_to_zero(self):
        self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 5))

        response = self._post_transaction(self._cover_payload("AAPL", "Apple Inc.", 5))

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 0.0)

    def test_create_transaction_cover_more_than_short_returns_400(self):
        self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 5))

        response = self._post_transaction(self._cover_payload("AAPL", "Apple Inc.", 10))

        self.assertEqual(response.status_code, 400)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), -5.0)
        self.assertEqual(Transactions.query.count(), 1)

    def test_create_transaction_short_sell_rejected_while_long_position_open(self):
        self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 5))

        response = self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 5))

        self.assertEqual(response.status_code, 400)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 5.0)

    def test_create_transaction_short_sell_with_existing_long_uses_neutral_message(self):
        self.assertEqual(
            self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 5)).status_code,
            201,
        )

        response = self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 1))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["message"],
            "Open long position exists for this asset; sell to close it first.",
        )

    def test_create_transaction_buy_long_rejected_while_short_position_open(self):
        self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 5))

        response = self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 5))

        self.assertEqual(response.status_code, 400)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), -5.0)

    def test_create_transaction_sell_long_rejected_while_short_position_open(self):
        self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 5))

        response = self._post_transaction(self._sell_payload("AAPL", "Apple Inc.", 1))

        self.assertEqual(response.status_code, 400)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), -5.0)

    def test_create_transaction_sell_short_with_existing_short_succeeds(self):
        self.assertEqual(
            self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 5)).status_code,
            201,
        )

        response = self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 2))

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), -7.0)

    def test_create_transaction_sell_long_with_existing_short_uses_neutral_message(self):
        self.assertEqual(
            self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 5)).status_code,
            201,
        )

        response = self._post_transaction(self._sell_payload("AAPL", "Apple Inc.", 1))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["message"],
            "Open short position exists for this asset; buy to cover it first.",
        )

    def test_create_transaction_buy_without_enough_cash_returns_400(self):
        FakeMarketData.prices["AAPL"] = decimal.Decimal("20000")
        payload = self._buy_payload("AAPL", "Apple Inc.", 1)

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transactions.query.count(), 0)
        self.assertEqual(self._cash_balance(), 10000.0)

    def test_create_transaction_rejects_fractional_quantity(self):
        response = self._post_transaction(
            self._buy_payload("AAPL", "Apple Inc.", 1.5)
        )

        self.assertEqual(response.status_code, 422)

    def test_create_transaction_rejects_future_date(self):
        payload = self._buy_payload("AAPL", "Apple Inc.", 1)
        payload["trade_date"] = (
            datetime.datetime.now(datetime.timezone.utc).date()
            + datetime.timedelta(days=1)
        ).isoformat()

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 422)

    def test_create_transaction_today_uses_request_price_when_present(self):
        trade_date = datetime.datetime.now(datetime.timezone.utc).date()
        payload = self._buy_payload("AAPL", "Apple Inc.", 2)
        payload["price"] = 125
        payload["trade_date"] = trade_date.isoformat()

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["executed_unit_price"], 125.0)
        self.assertEqual(body["executed_price"], 250.0)
        transaction = Transactions.query.one()
        self.assertEqual(transaction.trade_date, trade_date)
        self.assertEqual(float(transaction.price), 125.0)
        self.assertEqual(float(transaction.average_cost_before), 0.0)
        self.assertEqual(float(transaction.cash_balance_before), 10000.0)
        self.assertEqual(self._cash_balance(), 9750.0)

    def test_create_transaction_backdated_buy_replays_later_costs_and_cash(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        current_buy = self._buy_payload("AAPL", "Apple Inc.", 10)
        current_buy["price"] = 200
        self.assertEqual(self._post_transaction(current_buy).status_code, 201)

        historical_buy = self._buy_payload("AAPL", "Apple Inc.", 10)
        historical_buy["price"] = 100
        historical_buy["trade_date"] = (
            today - datetime.timedelta(days=10)
        ).isoformat()
        response = self._post_transaction(historical_buy)

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 20.0)
        self.assertEqual(float(holding.average_cost), 150.0)
        self.assertEqual(self._cash_balance(), 7000.0)
        later_buy = (
            Transactions.query.filter_by(price=decimal.Decimal("200"))
            .one()
        )
        self.assertEqual(float(later_buy.average_cost_before), 100.0)
        self.assertEqual(float(later_buy.cash_balance_before), 9000.0)
        earliest_buy = (
            Transactions.query.filter_by(price=decimal.Decimal("100"))
            .one()
        )
        self.assertEqual(float(earliest_buy.average_cost_before), 0.0)
        self.assertEqual(float(earliest_buy.cash_balance_before), 10000.0)

    def test_create_transaction_backdated_buy_replays_all_trade_cash_after_capital_changes(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        current_buy = self._buy_payload("AAPL", "Apple Inc.", 10)
        current_buy["price"] = 200
        self.assertEqual(self._post_transaction(current_buy).status_code, 201)

        current_sell = self._sell_payload("AAPL", "Apple Inc.", 2)
        current_sell["price"] = 250
        self.assertEqual(self._post_transaction(current_sell).status_code, 201)

        cash_holding = self._holding_for_ticker("CASH-USD")
        cash_holding.average_cost += decimal.Decimal("4000")
        now = datetime.datetime.now(datetime.timezone.utc)
        db.session.add_all(
            [
                Transactions(
                    id=uuid.uuid4(),
                    holding_id=cash_holding.id,
                    trade_date=today,
                    quantity=decimal.Decimal("5000"),
                    price=decimal.Decimal("1"),
                    average_cost_before=None,
                    cash_balance_before=decimal.Decimal("8500"),
                    transaction_type="deposit",
                    created_at=now + datetime.timedelta(seconds=1),
                ),
                Transactions(
                    id=uuid.uuid4(),
                    holding_id=cash_holding.id,
                    trade_date=today,
                    quantity=decimal.Decimal("1000"),
                    price=decimal.Decimal("1"),
                    average_cost_before=None,
                    cash_balance_before=decimal.Decimal("13500"),
                    transaction_type="withdrawal",
                    created_at=now + datetime.timedelta(seconds=2),
                ),
            ]
        )
        db.session.commit()

        historical_buy = self._buy_payload("AAPL", "Apple Inc.", 5)
        historical_buy["price"] = 100
        historical_buy["trade_date"] = (
            today - datetime.timedelta(days=10)
        ).isoformat()
        response = self._post_transaction(historical_buy)

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 13.0)
        self.assertAlmostEqual(float(holding.average_cost), 166.6666667, places=5)
        self.assertEqual(self._cash_balance(), 12000.0)
        earliest_buy = Transactions.query.filter_by(price=decimal.Decimal("100")).one()
        current_buy_transaction = (
            Transactions.query.filter_by(price=decimal.Decimal("200"))
            .one()
        )
        current_sell_transaction = (
            Transactions.query.filter_by(transaction_type="sell")
            .one()
        )
        deposit = Transactions.query.filter_by(transaction_type="deposit").one()
        withdrawal = Transactions.query.filter_by(transaction_type="withdrawal").one()
        self.assertEqual(float(earliest_buy.cash_balance_before), 14000.0)
        self.assertEqual(float(current_buy_transaction.cash_balance_before), 13500.0)
        self.assertEqual(float(current_sell_transaction.cash_balance_before), 11500.0)
        self.assertEqual(float(deposit.cash_balance_before), 8500.0)
        self.assertEqual(float(withdrawal.cash_balance_before), 13500.0)

    def test_create_transaction_historical_buy_after_first_buy_replays_later_costs(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        first_buy = self._buy_payload("AAPL", "Apple Inc.", 10)
        first_buy["price"] = 100
        first_buy["trade_date"] = (today - datetime.timedelta(days=20)).isoformat()
        self.assertEqual(self._post_transaction(first_buy).status_code, 201)

        current_buy = self._buy_payload("AAPL", "Apple Inc.", 10)
        current_buy["price"] = 200
        self.assertEqual(self._post_transaction(current_buy).status_code, 201)

        middle_buy = self._buy_payload("AAPL", "Apple Inc.", 10)
        middle_buy["price"] = 120
        middle_buy["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()
        response = self._post_transaction(middle_buy)

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 30.0)
        self.assertEqual(float(holding.average_cost), 140.0)
        self.assertEqual(self._cash_balance(), 5800.0)
        middle = Transactions.query.filter_by(price=decimal.Decimal("120")).one()
        self.assertEqual(float(middle.average_cost_before), 100.0)
        self.assertEqual(float(middle.cash_balance_before), 9000.0)
        current = Transactions.query.filter_by(price=decimal.Decimal("200")).one()
        self.assertEqual(float(current.average_cost_before), 110.0)
        self.assertEqual(float(current.cash_balance_before), 7800.0)

    def test_create_transaction_historical_buy_same_day_as_existing_buy(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        existing_buy = self._buy_payload("AAPL", "Apple Inc.", 10)
        existing_buy["price"] = 100
        existing_buy["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()
        self.assertEqual(self._post_transaction(existing_buy).status_code, 201)

        same_day_buy = self._buy_payload("AAPL", "Apple Inc.", 5)
        same_day_buy["price"] = 200
        same_day_buy["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()
        response = self._post_transaction(same_day_buy)

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 15.0)
        self.assertAlmostEqual(float(holding.average_cost), 133.3333333, places=5)
        self.assertEqual(self._cash_balance(), 8000.0)
        existing = Transactions.query.filter_by(price=decimal.Decimal("100")).one()
        same_day = Transactions.query.filter_by(price=decimal.Decimal("200")).one()
        self.assertEqual(float(existing.average_cost_before), 0.0)
        self.assertEqual(float(existing.cash_balance_before), 10000.0)
        self.assertEqual(float(same_day.average_cost_before), 100.0)
        self.assertEqual(float(same_day.cash_balance_before), 9000.0)

    def test_create_transaction_backdated_sell_replays_later_costs_and_cash(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        first_buy = self._buy_payload("AAPL", "Apple Inc.", 10)
        first_buy["price"] = 100
        first_buy["trade_date"] = (today - datetime.timedelta(days=20)).isoformat()
        self.assertEqual(self._post_transaction(first_buy).status_code, 201)

        later_buy = self._buy_payload("AAPL", "Apple Inc.", 10)
        later_buy["price"] = 200
        self.assertEqual(self._post_transaction(later_buy).status_code, 201)

        backdated_sell = self._sell_payload("AAPL", "Apple Inc.", 5)
        backdated_sell["price"] = 120
        backdated_sell["trade_date"] = (
            today - datetime.timedelta(days=10)
        ).isoformat()
        response = self._post_transaction(backdated_sell)

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 15.0)
        self.assertAlmostEqual(float(holding.average_cost), 166.6666667, places=5)
        self.assertEqual(self._cash_balance(), 7600.0)
        later = Transactions.query.filter_by(price=decimal.Decimal("200")).one()
        self.assertEqual(float(later.average_cost_before), 100.0)
        self.assertEqual(float(later.cash_balance_before), 9600.0)

    def test_create_transaction_historical_sell_after_first_sell_replays_cash(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        first_buy = self._buy_payload("AAPL", "Apple Inc.", 20)
        first_buy["price"] = 100
        first_buy["trade_date"] = (today - datetime.timedelta(days=30)).isoformat()
        self.assertEqual(self._post_transaction(first_buy).status_code, 201)

        first_sell = self._sell_payload("AAPL", "Apple Inc.", 5)
        first_sell["price"] = 110
        first_sell["trade_date"] = (today - datetime.timedelta(days=20)).isoformat()
        self.assertEqual(self._post_transaction(first_sell).status_code, 201)

        current_sell = self._sell_payload("AAPL", "Apple Inc.", 5)
        self.assertEqual(self._post_transaction(current_sell).status_code, 201)

        middle_sell = self._sell_payload("AAPL", "Apple Inc.", 5)
        middle_sell["price"] = 120
        middle_sell["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()
        response = self._post_transaction(middle_sell)

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 5.0)
        self.assertEqual(float(holding.average_cost), 100.0)
        self.assertEqual(self._cash_balance(), 9900.0)
        for sell in Transactions.query.filter_by(transaction_type="sell").all():
            self.assertEqual(float(sell.average_cost_before), 100.0)
        middle = Transactions.query.filter_by(price=decimal.Decimal("120")).one()
        current = Transactions.query.filter_by(price=decimal.Decimal("150")).one()
        self.assertEqual(float(middle.cash_balance_before), 8550.0)
        self.assertEqual(float(current.cash_balance_before), 9150.0)

    def test_create_transaction_historical_sell_before_first_sell_replays_later_sells(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        first_buy = self._buy_payload("AAPL", "Apple Inc.", 20)
        first_buy["price"] = 100
        first_buy["trade_date"] = (today - datetime.timedelta(days=30)).isoformat()
        self.assertEqual(self._post_transaction(first_buy).status_code, 201)

        later_sell = self._sell_payload("AAPL", "Apple Inc.", 5)
        later_sell["price"] = 120
        later_sell["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()
        self.assertEqual(self._post_transaction(later_sell).status_code, 201)

        earlier_sell = self._sell_payload("AAPL", "Apple Inc.", 5)
        earlier_sell["price"] = 110
        earlier_sell["trade_date"] = (today - datetime.timedelta(days=20)).isoformat()
        response = self._post_transaction(earlier_sell)

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 10.0)
        self.assertEqual(float(holding.average_cost), 100.0)
        self.assertEqual(self._cash_balance(), 9150.0)
        later = Transactions.query.filter_by(price=decimal.Decimal("120")).one()
        self.assertEqual(float(later.average_cost_before), 100.0)
        self.assertEqual(float(later.cash_balance_before), 8550.0)

    def test_create_transaction_historical_sell_same_day_as_existing_sell(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        first_buy = self._buy_payload("AAPL", "Apple Inc.", 20)
        first_buy["price"] = 100
        first_buy["trade_date"] = (today - datetime.timedelta(days=20)).isoformat()
        self.assertEqual(self._post_transaction(first_buy).status_code, 201)

        existing_sell = self._sell_payload("AAPL", "Apple Inc.", 5)
        existing_sell["price"] = 110
        existing_sell["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()
        self.assertEqual(self._post_transaction(existing_sell).status_code, 201)

        same_day_sell = self._sell_payload("AAPL", "Apple Inc.", 5)
        same_day_sell["price"] = 120
        same_day_sell["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()
        response = self._post_transaction(same_day_sell)

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 10.0)
        self.assertEqual(float(holding.average_cost), 100.0)
        self.assertEqual(self._cash_balance(), 9150.0)
        for sell in Transactions.query.filter_by(transaction_type="sell").all():
            self.assertEqual(float(sell.average_cost_before), 100.0)
        existing = Transactions.query.filter_by(price=decimal.Decimal("110")).one()
        same_day = Transactions.query.filter_by(price=decimal.Decimal("120")).one()
        self.assertEqual(float(existing.cash_balance_before), 8000.0)
        self.assertEqual(float(same_day.cash_balance_before), 8550.0)

    def test_create_transaction_backdated_short_replays_later_costs_and_cash(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        first_short = self._short_payload("AAPL", "Apple Inc.", 10)
        first_short["price"] = 100
        first_short["trade_date"] = (today - datetime.timedelta(days=20)).isoformat()
        self.assertEqual(self._post_transaction(first_short).status_code, 201)

        later_short = self._short_payload("AAPL", "Apple Inc.", 10)
        later_short["price"] = 200
        self.assertEqual(self._post_transaction(later_short).status_code, 201)

        backdated_short = self._short_payload("AAPL", "Apple Inc.", 5)
        backdated_short["price"] = 120
        backdated_short["trade_date"] = (
            today - datetime.timedelta(days=10)
        ).isoformat()
        response = self._post_transaction(backdated_short)

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), -25.0)
        self.assertAlmostEqual(float(holding.average_cost), 144.0, places=5)
        self.assertEqual(self._cash_balance(), 13600.0)

    def test_create_transaction_backdated_cover_before_short_exists_rolls_back(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        self.assertEqual(
            self._post_transaction(self._short_payload("AAPL", "Apple Inc.", 5)).status_code,
            201,
        )
        payload = self._cover_payload("AAPL", "Apple Inc.", 1)
        payload["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transactions.query.count(), 1)
        self.assertEqual(float(self._holding_for_ticker("AAPL").quantity), -5.0)
        self.assertEqual(self._cash_balance(), 10750.0)

    def test_create_transaction_backdated_sell_oversell_rolls_back(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        self.assertEqual(
            self._post_transaction(self._buy_payload("AAPL", "Apple Inc.", 5)).status_code,
            201,
        )
        payload = self._sell_payload("AAPL", "Apple Inc.", 1)
        payload["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transactions.query.count(), 1)
        self.assertEqual(float(self._holding_for_ticker("AAPL").quantity), 5.0)
        self.assertEqual(self._cash_balance(), 9250.0)

    def test_create_transaction_backdated_buy_conflicts_with_future_buy(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        first_buy = self._buy_payload("AAPL", "Apple Inc.", 100)
        first_buy["price"] = 60
        first_buy["trade_date"] = (today - datetime.timedelta(days=20)).isoformat()
        self.assertEqual(self._post_transaction(first_buy).status_code, 201)

        future_buy = self._buy_payload("MSFT", "Microsoft Corp.", 1)
        future_buy["price"] = 3990
        self.assertEqual(self._post_transaction(future_buy).status_code, 201)

        backdated_buy = self._buy_payload("MSFT", "Microsoft Corp.", 1)
        backdated_buy["price"] = 100
        backdated_buy["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()
        response = self._post_transaction(backdated_buy)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["message"], "Conflict with future transaction"
        )
        self.assertEqual(Transactions.query.count(), 2)
        self.assertEqual(self._cash_balance(), 10.0)

    def test_create_transaction_backdated_sell_conflicts_with_future_sell(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        first_buy = self._buy_payload("AAPL", "Apple Inc.", 10)
        first_buy["price"] = 100
        first_buy["trade_date"] = (today - datetime.timedelta(days=20)).isoformat()
        self.assertEqual(self._post_transaction(first_buy).status_code, 201)

        future_sell = self._sell_payload("AAPL", "Apple Inc.", 8)
        future_sell["price"] = 100
        self.assertEqual(self._post_transaction(future_sell).status_code, 201)

        backdated_sell = self._sell_payload("AAPL", "Apple Inc.", 3)
        backdated_sell["price"] = 120
        backdated_sell["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()
        response = self._post_transaction(backdated_sell)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["message"], "Conflict with future transaction"
        )
        self.assertEqual(Transactions.query.count(), 2)
        self.assertEqual(float(self._holding_for_ticker("AAPL").quantity), 2.0)

    def test_create_transaction_backdated_buy_without_cash_rolls_back(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        payload = self._buy_payload("AAPL", "Apple Inc.", 1)
        payload["price"] = 20000
        payload["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transactions.query.count(), 0)
        self.assertEqual(self._cash_balance(), 10000.0)

    def test_create_transaction_backdated_buy_before_ticker_exists_rolls_back(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        FakeMarketData.listed_from = {"IPO": today - datetime.timedelta(days=5)}
        payload = self._buy_payload("IPO", "Recent IPO", 1)
        payload["price"] = 50
        payload["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transactions.query.count(), 0)
        self.assertEqual(AssetMaster.query.filter_by(ticker="IPO").count(), 0)
        self.assertEqual(self._cash_balance(), 10000.0)

    def test_create_transaction_backdated_existing_asset_before_listing_rolls_back(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        FakeMarketData.listed_from = {"IPO": today - datetime.timedelta(days=5)}
        payload = self._buy_payload("IPO", "Recent IPO", 1)
        payload["price"] = 50
        self.assertEqual(self._post_transaction(payload).status_code, 201)

        backdated_buy = self._buy_payload("IPO", "Recent IPO", 1)
        backdated_buy["price"] = 40
        backdated_buy["trade_date"] = (today - datetime.timedelta(days=10)).isoformat()
        response = self._post_transaction(backdated_buy)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transactions.query.count(), 1)
        holding = self._holding_for_ticker("IPO")
        self.assertEqual(float(holding.quantity), 1.0)
        self.assertEqual(self._cash_balance(), 9950.0)

    def test_create_transaction_rejects_closed_trade_date(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        closed_date = today - datetime.timedelta(days=1)
        FakeMarketData.closed_dates = {closed_date}
        payload = self._buy_payload("AAPL", "Apple Inc.", 1)
        payload["price"] = 150
        payload["trade_date"] = closed_date.isoformat()

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transactions.query.count(), 0)
        self.assertEqual(self._cash_balance(), 10000.0)

    def test_create_transaction_today_closed_uses_latest_close_when_price_omitted(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        FakeMarketData.closed_dates = {today}
        FakeMarketData.prices["AAPL"] = None
        FakeMarketData.latest_closes["AAPL"] = decimal.Decimal("145")
        payload = self._buy_payload("AAPL", "Apple Inc.", 1)

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 201)
        transaction = Transactions.query.one()
        self.assertEqual(float(transaction.price), 145.0)
        self.assertEqual(self._cash_balance(), 9855.0)

    def test_create_transaction_today_closed_uses_request_price_when_present(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        FakeMarketData.closed_dates = {today}
        FakeMarketData.prices["AAPL"] = None
        payload = self._buy_payload("AAPL", "Apple Inc.", 1)
        payload["price"] = 125

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 201)
        transaction = Transactions.query.one()
        self.assertEqual(float(transaction.price), 125.0)
        self.assertEqual(self._cash_balance(), 9875.0)

    def test_create_transaction_today_without_price_or_latest_close_returns_502(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        FakeMarketData.closed_dates = {today}
        FakeMarketData.prices["AAPL"] = None
        FakeMarketData.latest_closes["AAPL"] = None
        payload = self._buy_payload("AAPL", "Apple Inc.", 1)

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(Transactions.query.count(), 0)
        self.assertEqual(self._cash_balance(), 10000.0)

    def test_create_transaction_backdated_jpy_uses_historical_fx(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        trade_date = today - datetime.timedelta(days=10)
        FakeMarketData.historical_fx_rates = {
            ("JPY", trade_date): decimal.Decimal("0.02")
        }
        payload = self._buy_payload("7203.T", "Toyota Motor Corp.", 2)
        payload["price"] = 3000
        payload["trade_date"] = trade_date.isoformat()

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self._cash_balance(), 9880.0)

    def test_create_transaction_backdated_missing_fx_rolls_back(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        trade_date = today - datetime.timedelta(days=10)
        FakeMarketData.historical_fx_rates = {("JPY", trade_date): None}
        payload = self._buy_payload("7203.T", "Toyota Motor Corp.", 2)
        payload["trade_date"] = trade_date.isoformat()

        response = self._post_transaction(payload)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(Transactions.query.count(), 0)
        self.assertEqual(self._cash_balance(), 10000.0)

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
        self.assertEqual(Holdings.query.count(), 3)
        self.assertEqual(Transactions.query.count(), 2)
        cash_holding = self._holding_for_ticker("CASH-USD")
        self.assertEqual(float(cash_holding.average_cost), 7000.0)

    def test_create_transactions_batch_with_history_replays_once(self):
        today = datetime.datetime.now(datetime.timezone.utc).date()
        response = self._post_batch(
            {
                "transactions": [
                    {
                        **self._buy_payload("AAPL", "Apple Inc.", 10),
                        "trade_date": (
                            today - datetime.timedelta(days=10)
                        ).isoformat(),
                        "price": 100,
                    },
                    {
                        **self._buy_payload("AAPL", "Apple Inc.", 10),
                        "price": 200,
                    },
                ]
            }
        )

        self.assertEqual(response.status_code, 201)
        holding = self._holding_for_ticker("AAPL")
        self.assertEqual(float(holding.quantity), 20.0)
        self.assertEqual(float(holding.average_cost), 150.0)
        self.assertEqual(self._cash_balance(), 7000.0)

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
        self.assertEqual(AssetMaster.query.count(), 1)
        self.assertEqual(Holdings.query.count(), 1)
        self.assertEqual(Transactions.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
