"""Portfolio business logic backed by SQLAlchemy."""

import datetime
import decimal
import math
import uuid

from flask import g
from flask_smorest import abort
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

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
from app.services.market_data import YahooFinanceMarketData

PORTFOLIO_CREATED_MESSAGE = "Portfolio created"
PORTFOLIO_ALREADY_EXISTS_MESSAGE = "Portfolio already exists for this user."
PORTFOLIO_NOT_FOUND_MESSAGE = "The specified portfolio does not exist"
SUMMARY_CURRENCY = "USD"
DEFAULT_USD_SYMBOL = "$"


def create_portfolio(payload):
    """Create the current user's only portfolio and optional initial cash holding."""

    user_id = _current_user_id()
    currency_code = payload.get("currency", "USD").upper()
    cash_balance = decimal.Decimal(str(payload.get("cash_balance", 0)))

    try:
        _ensure_user(user_id)
        # 現行仕様では 1 user = 1 portfolio。作成前に明示的に確認する。
        existing_portfolio = db.session.execute(
            select(Portfolio).where(Portfolio.user_id == user_id)
        ).scalar_one_or_none()
        if existing_portfolio:
            abort(409, message=PORTFOLIO_ALREADY_EXISTS_MESSAGE)

        now = datetime.datetime.now(datetime.timezone.utc)
        portfolio = Portfolio(
            id=uuid.uuid4(),
            user_id=user_id,
            name=payload["name"],
            created_at=now,
            updated_at=now,
        )
        db.session.add(portfolio)
        db.session.flush()

        if cash_balance > 0:
            cash_asset = _cash_asset(currency_code)
            # cash_balance は portfolio table ではなく cash holding に quantity=1 で保存する。
            db.session.add(
                Holdings(
                    id=uuid.uuid4(),
                    portfolio_id=portfolio.id,
                    asset_id=cash_asset.id,
                    quantity=decimal.Decimal("1"),
                    average_cost=cash_balance,
                    updated_at=now,
                )
            )

        db.session.commit()
    except HTTPException:
        db.session.rollback()
        raise
    except IntegrityError:
        db.session.rollback()
        abort(409, message=PORTFOLIO_ALREADY_EXISTS_MESSAGE)
    except SQLAlchemyError:
        db.session.rollback()
        abort(500, message="Could not create portfolio.")

    return {"message": PORTFOLIO_CREATED_MESSAGE}


def get_portfolio_summary(market_data=None):
    """Return USD summary values for the current user's portfolio."""

    user_id = _current_user_id()
    portfolio = db.session.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if not portfolio:
        abort(404, message=PORTFOLIO_NOT_FOUND_MESSAGE)

    market_data = market_data or YahooFinanceMarketData()
    cash_balance = decimal.Decimal("0")
    total_market_value = decimal.Decimal("0")
    total_cost_basis = decimal.Decimal("0")

    holdings = db.session.execute(
        select(Holdings)
        .join(Holdings.asset)
        .where(Holdings.portfolio_id == portfolio.id)
        .order_by(AssetMaster.ticker)
    ).scalars()

    for holding in holdings:
        quantity = _decimal_or_zero(holding.quantity)
        average_cost = _decimal_or_zero(holding.average_cost)
        asset = holding.asset
        asset_type = getattr(getattr(asset, "asset_type", None), "asset_type", None)
        currency = _asset_currency(asset)
        fx_rate = _decimal_or_none(market_data.fx_to_usd(currency))
        if fx_rate is None:
            continue

        if asset_type == "cash":
            cash_balance += quantity * average_cost * fx_rate
            continue

        current_price = _decimal_or_none(
            market_data.latest_price(getattr(asset, "ticker", None))
        )
        if current_price is None:
            continue

        total_market_value += quantity * current_price * fx_rate
        total_cost_basis += quantity * average_cost * fx_rate

    return {
        "currency": SUMMARY_CURRENCY,
        "currency_symbol": _summary_currency_symbol(),
        "cash_balance": float(cash_balance),
        "total_market_value": float(total_market_value),
        "total_return_percent": float(
            _return_percent(total_market_value, total_cost_basis)
        ),
    }


def get_portfolio_holdings(args, market_data=None):
    """Return paginated non-cash holdings in USD."""

    user_id = _current_user_id()
    portfolio = db.session.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    ).scalar_one_or_none()
    if not portfolio:
        abort(404, message=PORTFOLIO_NOT_FOUND_MESSAGE)

    market_data = market_data or YahooFinanceMarketData()
    asset_type_filter = (args.get("asset_type") or "all").lower()
    page = args.get("page", 1)
    per_page = args.get("per_page", 20)
    items = []
    total_market_value = decimal.Decimal("0")
    total_day_change = decimal.Decimal("0")
    total_previous_value = decimal.Decimal("0")

    holdings = db.session.execute(
        select(Holdings)
        .join(Holdings.asset)
        .where(Holdings.portfolio_id == portfolio.id)
        .order_by(AssetMaster.ticker)
    ).scalars()
   
    for holding in holdings:
        quantity = _decimal_or_zero(holding.quantity)
        average_cost = _decimal_or_zero(holding.average_cost)
        asset = holding.asset
        asset_type = getattr(getattr(asset, "asset_type", None), "asset_type", None)
        asset_type_value = (asset_type or "").lower()
        if asset_type_value == "cash":
            continue
        if asset_type_filter != "all" and asset_type_value != asset_type_filter:
            continue
        currency = _asset_currency(asset)
        fx_rate = _decimal_or_none(market_data.fx_to_usd(currency))
        if fx_rate is None:
            continue
        current_price = _decimal_or_none(
            market_data.latest_price(getattr(asset, "ticker", None))
        )
        previous_close = _previous_close_price(holding.asset_id)
        if current_price is None or previous_close is None:
            continue
        current_price_usd = current_price * fx_rate
        previous_close_usd = previous_close * fx_rate
        average_purchase_price = average_cost * fx_rate
        total_purchase_price = average_purchase_price * quantity
        holding_market_value = current_price_usd * quantity
        day_change = (current_price_usd - previous_close_usd) * quantity

        total_market_value += holding_market_value
        total_day_change += day_change
        total_previous_value += previous_close_usd * quantity

        items.append(
            {
                "ticker": asset.ticker,
                "name": asset.name,
                "asset_type": asset_type,
                "quantity": float(quantity),
                "average_purchase_price": float(average_purchase_price),
                "total_purchase_price": float(total_purchase_price),
                "current_price": float(current_price_usd),
                "total_market_value": float(holding_market_value),
                "today_return_percent": float(
                    _return_percent(current_price_usd, previous_close_usd)
                ),
                "total_return_percent": float(
                    _return_percent(current_price_usd, average_purchase_price)
                ),
                "currency": SUMMARY_CURRENCY,
            }
        )

    total_items = len(items)
    total_pages = math.ceil(total_items / per_page) if total_items else 0
    start = (page - 1) * per_page
    end = start + per_page

    return {
        "items": items[start:end],
        "totals": {
            "market_value": float(total_market_value),
            "day_change": float(total_day_change),
            "day_change_percent": float(
                _percent_of(total_day_change, total_previous_value)
            ),
            "currency": SUMMARY_CURRENCY,
        },
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_items": total_items,
            "total_pages": total_pages,
        },
    }


def _current_user_id():
    try:
        return uuid.UUID(str(g.current_user_id))
    except (AttributeError, TypeError, ValueError):
        abort(401, message="Missing authenticated user context.")


def _ensure_user(user_id):
    user = db.session.get(Users, user_id)
    if user:
        return user

    email = getattr(g, "current_user_email", None)
    if not email:
        abort(400, message="Authenticated user email is required.")

    now = datetime.datetime.now(datetime.timezone.utc)
    user = Users(id=user_id, email=email, created_at=now, updated_at=now)
    db.session.add(user)
    db.session.flush()
    return user


def _cash_asset(currency_code):
    currency = db.session.execute(
        select(Currency).where(Currency.currency == currency_code)
    ).scalar_one_or_none()
    if not currency:
        abort(400, message=f"Currency {currency_code} does not exist.")

    cash_type = db.session.execute(
        select(AssetType).where(AssetType.asset_type == "cash")
    ).scalar_one_or_none()
    if not cash_type:
        abort(400, message="Cash asset type does not exist.")

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


def _asset_currency(asset):
    return (
        getattr(getattr(asset, "currency", None), "currency", None) or SUMMARY_CURRENCY
    ).upper()


def _summary_currency_symbol():
    currency = db.session.execute(
        select(Currency).where(Currency.currency == SUMMARY_CURRENCY)
    ).scalar_one_or_none()
    return getattr(currency, "symbol", None) or DEFAULT_USD_SYMBOL


def _previous_close_price(asset_id):
    today = datetime.date.today()
    row = db.session.execute(
        select(AssetDataHistory)
        .where(AssetDataHistory.asset_id == asset_id)
        .where(AssetDataHistory.price_date < today)
        .order_by(AssetDataHistory.price_date.desc())
        .limit(1)
    ).scalar_one_or_none()
    return _decimal_or_none(getattr(row, "close_price", None))


def _return_percent(total_market_value, total_cost_basis):
    if total_cost_basis == 0:
        return decimal.Decimal("0")
    return (total_market_value - total_cost_basis) / total_cost_basis * 100


def _percent_of(amount, base):
    if base == 0:
        return decimal.Decimal("0")
    return amount / base * 100
