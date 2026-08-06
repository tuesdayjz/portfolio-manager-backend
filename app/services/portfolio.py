"""Portfolio business logic backed by SQLAlchemy.

推移グラフ（`GET /portfolios/performance`）だけは計算が独立しているので
`app/services/performance.py` に分けてある。
"""

import datetime
import decimal
import math
import uuid

from flask import g
from flask_smorest import abort
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

from app.enums import AllocationGroupBy, TransactionType
from app.extensions import db
from app.models import (
    AssetDataHistory,
    AssetMaster,
    AssetType,
    Currency,
    Holdings,
    Portfolio,
    Transactions,
    Users,
)
from app.services.common import (
    SUMMARY_CURRENCY,
    asset_currency,
    current_portfolio,
    current_user_id,
    decimal_or_none,
    decimal_or_zero,
    percent_of,
)
from app.services.market_data import YahooFinanceMarketData
from app.services.performance import (
    ALL_ASSET_TYPES,
    _investment_flows,
    _performance_change,
    _performance_positions,
    _short_liability_value,
    _value_series,
    latest_investment_value,
)

PORTFOLIO_CREATED_MESSAGE = "Portfolio created"
PORTFOLIO_ALREADY_EXISTS_MESSAGE = "Portfolio already exists for this user."
DEFAULT_USD_SYMBOL = "$"
UNKNOWN_CATEGORY = "unknown"


def create_portfolio(payload):
    """Create the current user's only portfolio and its initial cash holding.

    `cash_balance` defaults to `DEFAULT_INITIAL_CASH_BALANCE` (see
    `PortfolioCreateSchema`) unless the client overrides it; other assets
    always start with no holding until the user actually trades.
    """

    user_id = current_user_id()
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

    portfolio = current_portfolio()
    market_data = market_data or YahooFinanceMarketData()
    today = datetime.date.today()
    cash_balance = decimal.Decimal("0")
    holdings = db.session.execute(
        select(Holdings)
        .join(Holdings.asset)
        .where(Holdings.portfolio_id == portfolio.id)
        .order_by(AssetMaster.ticker)
    ).scalars()

    for holding in holdings:
        quantity = decimal_or_zero(holding.quantity)
        average_cost = decimal_or_zero(holding.average_cost)
        asset = holding.asset
        asset_type = getattr(getattr(asset, "asset_type", None), "asset_type", None)
        if asset_type != "cash":
            continue
        currency = asset_currency(asset)
        fx_rate = decimal_or_none(market_data.fx_to_usd(currency))
        if fx_rate is not None:
            cash_balance += quantity * average_cost * fx_rate

    # 投資資産の系列は performance と共有し、summary の総額には現金を加える。
    # 基準日の現金は後段で売買・入出金を差し戻して復元する。
    positions, _cash_value, first_trade_date = _performance_positions(
        portfolio.id, market_data, ALL_ASSET_TYPES
    )
    dates, investment_values = _value_series(
        positions, decimal.Decimal("0"), first_trade_date, today
    )
    # 系列の末端は日次インポート待ちで前営業日の終値のことがある。総額は
    # allocation と同じライブ値に揃えたいので、現在値だけ組み直す。基準日は
    # 過去の点なので系列の値をそのまま使う。
    total_market_value = (
        latest_investment_value(positions, market_data, today) + cash_balance
    )
    total_return = _summary_total_return(
        portfolio.id,
        positions,
        dates[0],
        investment_values[0],
        cash_balance,
        total_market_value,
        today,
    )
    total_short_liability = _short_liability_value(portfolio.id, market_data, today)

    return {
        "currency": SUMMARY_CURRENCY,
        "currency_symbol": _summary_currency_symbol(),
        "cash_balance": float(cash_balance),
        "total_market_value": float(total_market_value),
        "total_short_liability": float(total_short_liability),
        "total_return_percent": total_return["percent"],
    }


def _summary_total_return(
    portfolio_id,
    positions,
    baseline_date,
    baseline_investment_value,
    current_cash_balance,
    total_market_value,
    as_of,
):
    """Return inception performance adjusted only for external capital flows.

    buy/sell は投資資産と現金の間の移動なので、外部フローには数えない。ただし
    現在の cash balance から基準日の残高を復元するためには売買金額も差し戻す。
    deposit/withdrawal だけを入出金としてリターン計算の分母・分子に反映する。
    """

    trade_flows = _investment_flows(positions, as_of)
    capital_flows = _capital_flows(portfolio_id, as_of)
    baseline_cash_balance = current_cash_balance

    for trade_date, transaction_type, amount in trade_flows:
        if not baseline_date < trade_date <= as_of:
            continue
        if transaction_type == TransactionType.BUY.value:
            baseline_cash_balance += amount
        elif transaction_type == TransactionType.SELL.value:
            baseline_cash_balance -= amount

    deposits = decimal.Decimal("0")
    withdrawals = decimal.Decimal("0")
    for trade_date, transaction_type, amount in capital_flows:
        if not baseline_date < trade_date <= as_of:
            continue
        if transaction_type == TransactionType.DEPOSIT.value:
            baseline_cash_balance -= amount
            deposits += amount
        elif transaction_type == TransactionType.WITHDRAWAL.value:
            baseline_cash_balance += amount
            withdrawals += amount

    baseline_value = baseline_investment_value + baseline_cash_balance
    return _performance_change(
        total_market_value, baseline_value, deposits, withdrawals
    )


def _capital_flows(portfolio_id, as_of):
    """Return USD deposit/withdrawal amounts through ``as_of``."""

    rows = db.session.execute(
        select(
            Transactions.trade_date,
            Transactions.transaction_type,
            (Transactions.quantity * Transactions.price).label("amount"),
        )
        .join(Holdings, Holdings.id == Transactions.holding_id)
        .where(Holdings.portfolio_id == portfolio_id)
        .where(Transactions.trade_date <= as_of)
        .where(
            Transactions.transaction_type.in_(
                (
                    TransactionType.DEPOSIT.value,
                    TransactionType.WITHDRAWAL.value,
                )
            )
        )
        .order_by(Transactions.trade_date)
    ).all()
    return [
        (trade_date, transaction_type, decimal_or_zero(amount))
        for trade_date, transaction_type, amount in rows
    ]


def get_portfolio_holdings(args, market_data=None):
    """Return paginated non-cash holdings in USD."""

    portfolio = current_portfolio()

    market_data = market_data or YahooFinanceMarketData()
    asset_type_filter = (args.get("asset_type") or "all").lower()
    page = args.get("page", 1)
    per_page = args.get("per_page", 20)
    items = []
    total_market_value = decimal.Decimal("0")
    total_unrealized_pl = decimal.Decimal("0")
    total_previous_value = decimal.Decimal("0")
    today = datetime.date.today()

    previous_close = (
        select(AssetDataHistory.close_price)
        .where(AssetDataHistory.asset_id == Holdings.asset_id)
        .where(AssetDataHistory.price_date < today)
        .order_by(AssetDataHistory.price_date.desc())
        .limit(1)
        .correlate(Holdings)
        .scalar_subquery()
    )

    holding_rows = db.session.execute(
        select(
            Holdings,
            AssetMaster,
            AssetType.asset_type,
            Currency.currency,
            previous_close.label("previous_close"),
        )
        .join(AssetMaster, AssetMaster.id == Holdings.asset_id)
        .outerjoin(AssetType, AssetType.id == AssetMaster.asset_type_id)
        .outerjoin(Currency, Currency.id == AssetMaster.currency_id)
        .where(Holdings.portfolio_id == portfolio.id)
        .order_by(AssetMaster.ticker)
    ).all()

    priced_holdings = []
    for holding, asset, asset_type, currency, previous_close_value in holding_rows:
        quantity = decimal_or_zero(holding.quantity)
        average_cost = decimal_or_zero(holding.average_cost)
        asset_type_value = (asset_type or "").lower()
        if asset_type_value == "cash":
            continue
        if quantity == 0:
            continue
        if asset_type_filter != "all" and asset_type_value != asset_type_filter:
            continue
        currency = (currency or SUMMARY_CURRENCY).upper()
        previous_close_value = decimal_or_none(previous_close_value)
        if previous_close_value is None:
            continue
        priced_holdings.append(
            (
                asset,
                asset_type,
                quantity,
                average_cost,
                currency,
                previous_close_value,
            )
        )

    # 銘柄価格と非 USD 通貨の FX を Yahoo Finance のバッチAPIでまとめて取得する。
    # injected market data implementations that only expose latest_price remain
    # supported for callers outside the production endpoint.
    if hasattr(market_data, "latest_prices"):
        tickers = [asset.ticker for asset, *_rest in priced_holdings]
        fx_tickers = [
            f"{currency}USD=X"
            for (
                _asset,
                _asset_type,
                _quantity,
                _average_cost,
                currency,
                _close,
            ) in priced_holdings
            if currency != SUMMARY_CURRENCY
        ]
        market_data.latest_prices([*tickers, *fx_tickers])

    for (
        asset,
        asset_type,
        quantity,
        average_cost,
        currency,
        previous_close_value,
    ) in priced_holdings:
        fx_rate = decimal_or_none(market_data.fx_to_usd(currency))
        if fx_rate is None:
            continue
        current_price = decimal_or_none(
            market_data.latest_price(getattr(asset, "ticker", None))
        )
        if current_price is None:
            continue
        current_price_usd = current_price * fx_rate
        previous_close_usd = previous_close_value * fx_rate
        average_purchase_price = average_cost * fx_rate
        total_purchase_price = average_purchase_price * quantity
        holding_market_value = current_price_usd * quantity
        unrealized_pl = (current_price_usd - average_purchase_price) * quantity

        # Shorts are a liability, not an asset: they're listed individually
        # below but excluded from the aggregate totals.
        if quantity > 0:
            total_market_value += holding_market_value
            total_unrealized_pl += unrealized_pl
            total_previous_value += average_purchase_price * quantity

        # A short position gains value when the price falls, so its return
        # is the inverse of the raw price change used for a long position.
        return_sign = -1 if quantity < 0 else 1
        today_return_percent = return_sign * _return_percent(
            current_price_usd, previous_close_usd
        )
        total_return_percent = return_sign * _return_percent(
            current_price_usd, average_purchase_price
        )

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
                "today_return_percent": float(today_return_percent),
                "total_return_percent": float(total_return_percent),
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
            "day_change": float(total_unrealized_pl),
            "day_change_percent": float(
                percent_of(total_unrealized_pl, total_previous_value)
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


def get_portfolio_allocation(args, market_data=None):
    """Return USD allocation buckets grouped by the requested criterion."""

    portfolio = current_portfolio()

    market_data = market_data or YahooFinanceMarketData()
    group_by = args["group_by"]
    buckets = {}
    total_value = decimal.Decimal("0")

    holdings = db.session.execute(
        select(Holdings)
        .join(Holdings.asset)
        .where(Holdings.portfolio_id == portfolio.id)
        .order_by(AssetMaster.ticker)
    ).scalars()

    for holding in holdings:
        asset = holding.asset
        asset_type = getattr(getattr(asset, "asset_type", None), "asset_type", None)
        asset_type_value = (asset_type or "").lower()
        # sector を持つのは株式だけなので、それ以外は集計から除く。
        if group_by is AllocationGroupBy.SECTOR and asset_type_value != "stock":
            continue
        currency = asset_currency(asset)
        fx_rate = decimal_or_none(market_data.fx_to_usd(currency))
        if fx_rate is None:
            continue

        quantity = decimal_or_zero(holding.quantity)
        if asset_type_value == "cash":
            # cash holding は quantity=1、average_cost に残高が入っている。
            value = quantity * decimal_or_zero(holding.average_cost) * fx_rate
        else:
            # ショート（負の quantity）は負債であり資産ではないので、
            # 配分グラフからは除く。
            if quantity <= 0:
                continue
            current_price = decimal_or_none(
                market_data.latest_price(getattr(asset, "ticker", None))
            )
            if current_price is None:
                continue
            value = quantity * current_price * fx_rate

        category = _allocation_category(
            group_by, asset, asset_type, currency, market_data
        )
        if category is None:
            continue

        bucket = buckets.setdefault(
            category, {"value": decimal.Decimal("0"), "holdings_count": 0}
        )
        bucket["value"] += value
        bucket["holdings_count"] += 1
        total_value += value

    items = [
        {
            "category": category,
            "value": float(bucket["value"]),
            "weight": float(_ratio_of(bucket["value"], total_value)),
            "holdings_count": bucket["holdings_count"],
        }
        # value の降順。同額のときは category 名で安定させる。
        for category, bucket in sorted(
            buckets.items(), key=lambda item: (-item[1]["value"], item[0])
        )
    ]

    return {
        "group_by": group_by,
        "currency": SUMMARY_CURRENCY,
        "total_value": float(total_value),
        "items": items,
        "as_of": datetime.datetime.now(datetime.timezone.utc),
    }


def _allocation_category(group_by, asset, asset_type, currency, market_data):
    """Return the display bucket for a holding, or None to exclude it."""

    if group_by is AllocationGroupBy.ASSET_TYPE:
        return asset_type or UNKNOWN_CATEGORY
    if group_by is AllocationGroupBy.CURRENCY:
        return currency
    if group_by is AllocationGroupBy.ASSET:
        return (
            getattr(asset, "name", None)
            or getattr(asset, "ticker", None)
            or UNKNOWN_CATEGORY
        )
    # sector は Yahoo Finance 由来。取れない銘柄は集計から除く。
    sector = market_data.sector(getattr(asset, "ticker", None))
    return sector or None


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


def _summary_currency_symbol():
    currency = db.session.execute(
        select(Currency).where(Currency.currency == SUMMARY_CURRENCY)
    ).scalar_one_or_none()
    return getattr(currency, "symbol", None) or DEFAULT_USD_SYMBOL


def _return_percent(total_market_value, total_cost_basis):
    if total_cost_basis == 0:
        return decimal.Decimal("0")
    return (total_market_value - total_cost_basis) / total_cost_basis * 100


def _ratio_of(amount, base):
    if base == 0:
        return decimal.Decimal("0")
    return amount / base
