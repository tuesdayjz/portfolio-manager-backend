"""取引のビジネスロジック。履歴取得と、買い/売りによる holdings 更新を扱う。"""

import datetime
import decimal
import math
import uuid

from flask import current_app, g
from flask_smorest import abort
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from app.enums import TransactionType
from app.extensions import db
from app.models import AssetMaster, AssetType, Currency, Holdings, Portfolio, Transactions
from app.services.asset_history import schedule_asset_history_backfill
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


def get_portfolio_transactions(args):
    """ログイン user の portfolio に紐づく取引履歴を返す。"""

    portfolio = _portfolio_for_current_user()

    try:
        rows = _transaction_history_rows(portfolio.id, args)
    except SQLAlchemyError:
        db.session.rollback()
        abort(500, message="Could not fetch transactions.")

    items = [_transaction_history_item(*row) for row in rows]
    total_items = len(items)
    page = args.get("page", 1)
    per_page = args.get("per_page", 20)
    total_pages = math.ceil(total_items / per_page) if total_items else 0
    start = (page - 1) * per_page
    end = start + per_page

    # totals はページング前の filtered rows 全件を対象にする。
    total_realized_pl, total_cost_basis = _transaction_history_totals(rows)

    return {
        "items": items[start:end],
        "totals": {
            "realized_pl": float(total_realized_pl),
            "realized_pl_percent": float(
                _percent_of(total_realized_pl, total_cost_basis)
            ),
            "currency": current_app.config["DEFAULT_BASE_CURRENCY"],
        },
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_items": total_items,
            "total_pages": total_pages,
        },
    }


def create_transaction(payload, market_data=None):
    """1 件の取引を作成し、約定サマリーを返す。"""

    portfolio = _portfolio_for_current_user()
    market_data = market_data or YahooFinanceMarketData()
    touched_asset_ids = set()

    try:
        result = _create_transaction_line(
            portfolio, payload, market_data, {}, touched_asset_ids
        )
        db.session.commit()
    except HTTPException:
        db.session.rollback()
        raise
    except SQLAlchemyError:
        db.session.rollback()
        abort(500, message="Could not create transaction.")

    schedule_asset_history_backfill(current_app._get_current_object(), touched_asset_ids)
    return result


def create_transactions_batch(payload, market_data=None):
    """複数件の取引を 1 トランザクションで作成する。1 件でも不正なら何も作成しない。"""

    portfolio = _portfolio_for_current_user()
    market_data = market_data or YahooFinanceMarketData()
    holdings_cache = {}
    touched_asset_ids = set()

    try:
        results = [
            _create_transaction_line(
                portfolio, item, market_data, holdings_cache, touched_asset_ids
            )
            for item in payload["transactions"]
        ]
        db.session.commit()
    except HTTPException:
        db.session.rollback()
        raise
    except SQLAlchemyError:
        db.session.rollback()
        abort(500, message="Could not create transactions.")

    schedule_asset_history_backfill(current_app._get_current_object(), touched_asset_ids)
    return results


def _transaction_history_rows(portfolio_id, args):
    query = (
        select(Transactions, Holdings, AssetMaster, AssetType)
        # ownership は transactions -> holdings -> portfolio で解決する。
        .join(Holdings, Transactions.holding_id == Holdings.id)
        .join(AssetMaster, Holdings.asset_id == AssetMaster.id)
        .outerjoin(AssetType, AssetMaster.asset_type_id == AssetType.id)
        .where(Holdings.portfolio_id == portfolio_id)
    )

    transaction_type = args.get("transaction_type") or "all"
    if transaction_type != "all":
        query = query.where(Transactions.transaction_type == transaction_type)

    asset_type = (args.get("asset_type") or "all").lower()
    if asset_type != "all":
        query = query.where(AssetType.asset_type == asset_type)

    start_date = args.get("start_date")
    if start_date:
        query = query.where(Transactions.trade_date >= start_date)

    end_date = args.get("end_date")
    if end_date:
        query = query.where(Transactions.trade_date <= end_date)

    query = query.order_by(Transactions.trade_date.desc(), Transactions.created_at.desc())
    return db.session.execute(query).all()


def _transaction_history_item(transaction, holding, asset, asset_type):
    quantity = _decimal_or_zero(transaction.quantity)
    unit_price = _decimal_or_zero(transaction.price)
    realized_pl = _realized_pl(transaction, holding)
    cost_basis = _transaction_cost_basis(transaction, holding)
    realized_pl_percent = (
        _percent_of(realized_pl, cost_basis) if realized_pl is not None else None
    )

    return {
        "date": transaction.trade_date,
        "symbol": asset.ticker,
        "name": asset.name,
        "asset_type": getattr(asset_type, "asset_type", None),
        "quantity": float(quantity),
        "transaction_type": transaction.transaction_type,
        "executed_price": float(unit_price * quantity),
        "executed_unit_price": float(unit_price),
        "realized_pl": float(realized_pl) if realized_pl is not None else None,
        "realized_pl_percent": (
            float(realized_pl_percent) if realized_pl_percent is not None else None
        ),
    }


def _transaction_history_totals(rows):
    realized_pl = decimal.Decimal("0")
    cost_basis = decimal.Decimal("0")

    for transaction, holding, _asset, _asset_type in rows:
        line_realized_pl = _realized_pl(transaction, holding)
        if line_realized_pl is None:
            continue
        realized_pl += line_realized_pl
        cost_basis += _transaction_cost_basis(transaction, holding)

    return realized_pl, cost_basis


def _realized_pl(transaction, holding):
    # buy は売却時まで損益が確定しないため null にする。
    if transaction.transaction_type != TransactionType.SELL.value:
        return None

    quantity = _decimal_or_zero(transaction.quantity)
    unit_price = _decimal_or_zero(transaction.price)
    average_cost = _transaction_average_cost_before(transaction, holding)
    return (unit_price - average_cost) * quantity


def _transaction_average_cost_before(transaction, holding):
    average_cost_before = getattr(transaction, "average_cost_before", None)
    if average_cost_before is not None:
        return _decimal_or_zero(average_cost_before)
    return _decimal_or_zero(holding.average_cost)


def _transaction_cost_basis(transaction, holding):
    quantity = _decimal_or_zero(transaction.quantity)
    average_cost = _transaction_average_cost_before(transaction, holding)
    return average_cost * quantity


def _create_transaction_line(
    portfolio, item, market_data, holdings_cache, touched_asset_ids
):
    asset = _get_or_create_asset(item["ticker"], item["name"], market_data)
    touched_asset_ids.add(asset.id)

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


def _percent_of(amount, base):
    if base == 0:
        return decimal.Decimal("0")
    return amount / base * 100
