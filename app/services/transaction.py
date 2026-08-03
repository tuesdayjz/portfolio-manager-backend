"""取引作成のビジネスロジック。買い/売りに応じて holdings を更新し、transactions を記録する。"""

import datetime
import decimal
import uuid

from flask import g
from flask_smorest import abort
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from app.enums import TransactionType
from app.extensions import db
from app.models import AssetMaster, AssetType, Currency, Holdings, Portfolio, Transactions
from app.services.market_data import YahooFinanceMarketData

PORTFOLIO_NOT_FOUND_MESSAGE = "The specified portfolio does not exist"
OVERSELL_MESSAGE = "Cannot sell more than current holding"
PRICE_UNAVAILABLE_MESSAGE = "Unable to fetch a live price for this ticker."
FX_UNAVAILABLE_MESSAGE = "Unable to fetch an FX rate for this ticker currency."
UNSUPPORTED_ASSET_MESSAGE = "Unable to register this ticker."

# Yahoo Finance の `quoteType` -> `asset_type.asset_type`。
# ここで判別できない資産クラス（bond / reit など）は未対応。取引前に
# asset_master へ手動登録しておく必要がある。
QUOTE_TYPE_TO_ASSET_TYPE = {
    "EQUITY": "stock",
    "ETF": "etf",
    "MUTUALFUND": "fund",
    "CRYPTOCURRENCY": "crypto",
}


def create_transaction(payload, market_data=None):
    """1 件の取引を作成し、約定サマリーを返す。"""

    portfolio = _portfolio_for_current_user()
    market_data = market_data or YahooFinanceMarketData()

    try:
        result = _create_transaction_line(portfolio, payload, market_data, {})
        db.session.commit()
    except HTTPException:
        db.session.rollback()
        raise
    except SQLAlchemyError:
        db.session.rollback()
        abort(500, message="Could not create transaction.")

    return result


def create_transactions_batch(payload, market_data=None):
    """複数件の取引を 1 トランザクションで作成する。1 件でも不正なら何も作成しない。"""

    portfolio = _portfolio_for_current_user()
    market_data = market_data or YahooFinanceMarketData()
    holdings_cache = {}

    try:
        results = [
            _create_transaction_line(portfolio, item, market_data, holdings_cache)
            for item in payload["transactions"]
        ]
        db.session.commit()
    except HTTPException:
        db.session.rollback()
        raise
    except SQLAlchemyError:
        db.session.rollback()
        abort(500, message="Could not create transactions.")

    return results


def _create_transaction_line(portfolio, item, market_data, holdings_cache):
    asset = _get_or_create_asset(item["ticker"], item["name"], market_data)

    price = _decimal_or_none(market_data.latest_price(asset.ticker))
    if price is None:
        abort(502, message=PRICE_UNAVAILABLE_MESSAGE)

    holding = _get_or_create_holding(portfolio.id, asset.id, holdings_cache)
    existing_quantity = _decimal_or_zero(holding.quantity)
    average_cost_before = _decimal_or_none(holding.average_cost)
    existing_average_cost = _decimal_or_zero(average_cost_before)
    quantity = decimal.Decimal(str(item["quantity"]))
    transaction_type = item["transaction_type"]
    cash_holding = _get_or_create_usd_cash_holding(portfolio.id, holdings_cache)
    cash_balance = _decimal_or_zero(cash_holding.average_cost)
    fx_rate = _decimal_or_none(market_data.fx_to_usd(_asset_currency(asset)))
    if fx_rate is None:
        abort(502, message=FX_UNAVAILABLE_MESSAGE)
    trade_amount_usd = quantity * price * fx_rate

    if transaction_type is TransactionType.SELL:
        if quantity > existing_quantity:
            abort(400, message=OVERSELL_MESSAGE)
        holding.quantity = existing_quantity - quantity
        cash_holding.average_cost = cash_balance + trade_amount_usd
    else:
        new_quantity = existing_quantity + quantity
        holding.average_cost = (
            existing_quantity * existing_average_cost + quantity * price
        ) / new_quantity
        holding.quantity = new_quantity
        cash_holding.average_cost = cash_balance - trade_amount_usd

    now = datetime.datetime.now(datetime.timezone.utc)
    holding.updated_at = now
    cash_holding.updated_at = now

    db.session.add(
        Transactions(
            id=uuid.uuid4(),
            holding_id=holding.id,
            trade_date=now.date(),
            quantity=quantity,
            price=price,
            average_cost_before=average_cost_before,
            transaction_type=transaction_type.value,
        )
    )

    asset_type = getattr(getattr(asset, "asset_type", None), "asset_type", None)

    return {
        "date": now,
        "symbol": asset.ticker,
        "name": asset.name,
        "asset_type": asset_type,
        "executed_price": float(quantity * price),
        "executed_unit_price": float(price),
    }


def _get_or_create_holding(portfolio_id, asset_id, holdings_cache):
    if asset_id in holdings_cache:
        return holdings_cache[asset_id]

    holding = db.session.execute(
        select(Holdings).where(
            Holdings.portfolio_id == portfolio_id, Holdings.asset_id == asset_id
        )
    ).scalar_one_or_none()

    if not holding:
        holding = Holdings(
            id=uuid.uuid4(),
            portfolio_id=portfolio_id,
            asset_id=asset_id,
            quantity=decimal.Decimal("0"),
            average_cost=None,
            updated_at=datetime.datetime.now(datetime.timezone.utc),
        )
        db.session.add(holding)
        db.session.flush()

    holdings_cache[asset_id] = holding
    return holding


def _get_or_create_usd_cash_holding(portfolio_id, holdings_cache):
    cash_asset = _get_or_create_cash_asset("USD")
    cash_holding = _get_or_create_holding(portfolio_id, cash_asset.id, holdings_cache)
    if _decimal_or_zero(cash_holding.quantity) == 0:
        cash_holding.quantity = decimal.Decimal("1")
    return cash_holding


def _get_or_create_cash_asset(currency_code):
    cash_type = db.session.execute(
        select(AssetType).where(AssetType.asset_type == "cash")
    ).scalar_one_or_none()
    if not cash_type:
        abort(400, message="Cash asset type does not exist.")

    currency = db.session.execute(
        select(Currency).where(Currency.currency == currency_code)
    ).scalar_one_or_none()
    if not currency:
        abort(400, message=f"Currency {currency_code} does not exist.")

    ticker = f"CASH-{currency_code}"
    asset = db.session.execute(
        select(AssetMaster).where(AssetMaster.ticker == ticker)
    ).scalar_one_or_none()
    if asset:
        return asset

    asset = AssetMaster(
        id=uuid.uuid4(),
        ticker=ticker,
        name=f"Cash {currency_code}",
        asset_type_id=cash_type.id,
        currency_id=currency.id,
    )
    db.session.add(asset)
    db.session.flush()
    return asset


def _asset_currency(asset):
    currency = getattr(asset, "currency", None)
    currency_code = getattr(currency, "currency", None)
    if not currency_code:
        abort(400, message=UNSUPPORTED_ASSET_MESSAGE)
    return currency_code


def _get_or_create_asset(ticker, name, market_data):
    ticker = ticker.strip()
    asset = db.session.execute(
        select(AssetMaster).where(AssetMaster.ticker == ticker)
    ).scalar_one_or_none()
    if asset:
        return asset

    meta = market_data.asset_meta(ticker)
    if not meta:
        abort(400, message=UNSUPPORTED_ASSET_MESSAGE)

    asset_type_value = QUOTE_TYPE_TO_ASSET_TYPE.get(meta["quote_type"])
    if not asset_type_value:
        abort(400, message=UNSUPPORTED_ASSET_MESSAGE)

    asset_type = db.session.execute(
        select(AssetType).where(AssetType.asset_type == asset_type_value)
    ).scalar_one_or_none()
    if not asset_type:
        abort(400, message=UNSUPPORTED_ASSET_MESSAGE)

    currency = db.session.execute(
        select(Currency).where(Currency.currency == meta["currency"])
    ).scalar_one_or_none()
    if not currency:
        abort(400, message=UNSUPPORTED_ASSET_MESSAGE)

    asset = AssetMaster(
        id=uuid.uuid4(),
        ticker=ticker,
        name=name,
        asset_type_id=asset_type.id,
        currency_id=currency.id,
    )
    db.session.add(asset)
    db.session.flush()
    return asset


def _portfolio_for_current_user():
    user_id = _current_user_id()
    portfolio = db.session.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if not portfolio:
        abort(404, message=PORTFOLIO_NOT_FOUND_MESSAGE)
    return portfolio


def _current_user_id():
    try:
        return uuid.UUID(str(g.current_user_id))
    except (AttributeError, TypeError, ValueError):
        abort(401, message="Missing authenticated user context.")


def _decimal_or_zero(value):
    if value is None:
        return decimal.Decimal("0")
    return decimal.Decimal(str(value))


def _decimal_or_none(value):
    if value is None:
        return None
    try:
        result = decimal.Decimal(str(value))
    except (decimal.InvalidOperation, TypeError, ValueError):
        return None
    if result.is_nan() or result <= 0:
        return None
    return result
