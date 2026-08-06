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
OVERCOVER_MESSAGE = "Cannot cover more than current short position"
SHORT_POSITION_OPEN_MESSAGE = (
    "Cannot trade long while an open short position exists for this asset; "
    "buy to cover it first."
)
LONG_POSITION_OPEN_MESSAGE = (
    "Cannot trade short while an open long position exists for this asset; "
    "sell to close it first."
)
INSUFFICIENT_FUNDS_MESSAGE = "Cannot buy more than available cash balance"
INSUFFICIENT_CASH_FOR_WITHDRAWAL_MESSAGE = "Cannot withdraw more than current cash balance"
FUTURE_TRANSACTION_CONFLICT_MESSAGE = "Conflict with future transaction"
PRICE_UNAVAILABLE_MESSAGE = "Unable to fetch a live price for this ticker."
FX_UNAVAILABLE_MESSAGE = "Unable to fetch an FX rate for this ticker currency."
UNSUPPORTED_ASSET_MESSAGE = "Unable to register this ticker."
ASSET_NOT_TRADABLE_ON_DATE_MESSAGE = (
    "Ticker is not tradable on the requested trade_date."
)

# Yahoo Finance の `quoteType` -> `asset_type.asset_type`。
# ここで判別できない資産クラス（reit など）は未対応。取引前に
# asset_master へ手動登録しておく必要がある。
QUOTE_TYPE_TO_ASSET_TYPE = {
    "EQUITY": "stock",
    "ETF": "etf",
    "MUTUALFUND": "fund",
    "CRYPTOCURRENCY": "crypto",
    "BOND": "bond",
    "FUTURE": "futures",
    "OPTION": "option",
}

# Treasury yields/futures from https://finance.yahoo.com/markets/bonds/ - Yahoo's
# `quoteType` for these is INDEX / FUTURE, indistinguishable from any other index
# or futures contract, so they're mapped to "bond" by ticker instead of quote_type.
MANUAL_BOND_TICKERS = {
    "^IRX",  # 13 Week Treasury Bill
    "^FVX",  # Treasury Yield 5 Years
    "^TNX",  # Treasury Yield 10 Years
    "^TYX",  # Treasury Yield 30 Years
    "ZT=F",  # 2-Year T-Note Futures
    "ZN=F",  # 10-Year T-Note Futures
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
    new_transaction_ids = set()
    today = _utc_today()
    historical = _requires_historical_replay([payload], today)

    try:
        starting_cash = (
            _starting_cash_baseline(portfolio.id, market_data, today)
            if historical
            else None
        )
        result = _create_transaction_line(
            portfolio,
            payload,
            market_data,
            {},
            touched_asset_ids,
            new_transaction_ids,
            today=today,
            apply_incremental=not historical,
        )
        if historical:
            db.session.flush()
            _validate_historical_future_margins(
                portfolio.id, market_data, today, starting_cash, new_transaction_ids
            )
            _replay_portfolio_transactions(
                portfolio.id, market_data, today, starting_cash
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
    new_transaction_ids = set()
    today = _utc_today()
    items = payload["transactions"]
    historical = _requires_historical_replay(items, today)

    try:
        starting_cash = (
            _starting_cash_baseline(portfolio.id, market_data, today)
            if historical
            else None
        )
        results = [
            _create_transaction_line(
                portfolio,
                item,
                market_data,
                holdings_cache,
                touched_asset_ids,
                new_transaction_ids,
                today=today,
                apply_incremental=not historical,
            )
            for item in items
        ]
        if historical:
            db.session.flush()
            _validate_historical_future_margins(
                portfolio.id, market_data, today, starting_cash, new_transaction_ids
            )
            _replay_portfolio_transactions(
                portfolio.id, market_data, today, starting_cash
            )
        db.session.commit()
    except HTTPException:
        db.session.rollback()
        raise
    except SQLAlchemyError:
        db.session.rollback()
        abort(500, message="Could not create transactions.")

    schedule_asset_history_backfill(current_app._get_current_object(), touched_asset_ids)
    return results


def create_cash_transaction(payload, market_data=None):
    """現金を入金・出金し、約定サマリーを返す。ticker/holdings の quantity や
    average_cost には触れず、cash holding の残高だけを更新する。
    """

    portfolio = _portfolio_for_current_user()
    market_data = market_data or YahooFinanceMarketData()
    transaction_type = payload["transaction_type"]
    amount = decimal.Decimal(str(payload["amount"]))
    today = _utc_today()

    try:
        result = _create_cash_transaction_line(portfolio, transaction_type, amount)
        db.session.flush()
        starting_cash = _starting_cash_baseline(portfolio.id, market_data, today)
        _replay_portfolio_transactions(portfolio.id, market_data, today, starting_cash)
        db.session.commit()
    except HTTPException:
        db.session.rollback()
        raise
    except SQLAlchemyError:
        db.session.rollback()
        abort(500, message="Could not create transaction.")

    return result


def _create_cash_transaction_line(portfolio, transaction_type, amount):
    cash_holding = _get_or_create_usd_cash_holding(portfolio.id, {})
    cash_balance = _decimal_or_zero(cash_holding.average_cost)

    if transaction_type is TransactionType.WITHDRAWAL:
        if amount > cash_balance:
            abort(400, message=INSUFFICIENT_CASH_FOR_WITHDRAWAL_MESSAGE)
        cash_holding.average_cost = cash_balance - amount
    else:
        cash_holding.average_cost = cash_balance + amount

    now = datetime.datetime.now(datetime.timezone.utc)
    cash_holding.updated_at = now

    db.session.add(
        Transactions(
            id=uuid.uuid4(),
            holding_id=cash_holding.id,
            trade_date=now.date(),
            quantity=amount,
            price=decimal.Decimal("1"),
            average_cost_before=None,
            cash_balance_before=cash_balance,
            transaction_type=transaction_type.value,
            position="long",
        )
    )

    return {
        "date": now,
        "transaction_type": transaction_type.value,
        "amount": float(amount),
        "cash_balance": float(cash_holding.average_cost),
    }


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
        "transaction_id": str(transaction.id),
        "date": transaction.trade_date,
        "symbol": asset.ticker,
        "name": asset.name,
        "asset_type": getattr(asset_type, "asset_type", None),
        "position": getattr(transaction, "position", None) or "long",
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
    # ロングの開始(buy)・ショートの開始(sell)では損益が確定しないため null にする。
    # 損益が確定するのは、ロングを閉じる sell とショートを閉じる(covering) buy だけ。
    position = getattr(transaction, "position", None) or "long"
    closes_long = (
        transaction.transaction_type == TransactionType.SELL.value
        and position == "long"
    )
    closes_short = (
        transaction.transaction_type == TransactionType.BUY.value
        and position == "short"
    )
    if not closes_long and not closes_short:
        return None

    quantity = _decimal_or_zero(transaction.quantity)
    unit_price = _decimal_or_zero(transaction.price)
    average_cost = _transaction_average_cost_before(transaction, holding)
    if closes_short:
        return (average_cost - unit_price) * quantity
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
    portfolio,
    item,
    market_data,
    holdings_cache,
    touched_asset_ids,
    new_transaction_ids,
    *,
    today,
    apply_incremental,
):
    asset = _get_or_create_asset(item["ticker"], item["name"], market_data)
    touched_asset_ids.add(asset.id)

    trade_date = item.get("trade_date") or today
    if trade_date > today:
        abort(400, message="trade_date cannot be later than today.")
    _ensure_asset_tradable_on_date(asset, trade_date, today, market_data)

    price = _item_price(item, asset, market_data, today, trade_date)
    if price is None:
        abort(502, message=PRICE_UNAVAILABLE_MESSAGE)

    holding = _get_or_create_holding(portfolio.id, asset.id, holdings_cache)
    existing_quantity = _decimal_or_zero(holding.quantity)
    average_cost_before = _decimal_or_none(holding.average_cost)
    existing_average_cost = _decimal_or_zero(average_cost_before)
    quantity = decimal.Decimal(str(item["quantity"]))
    transaction_type = item["transaction_type"]
    position = item["position"]
    cash_holding = _get_or_create_usd_cash_holding(portfolio.id, holdings_cache)
    cash_balance = _decimal_or_zero(cash_holding.average_cost)

    now = datetime.datetime.now(datetime.timezone.utc)
    if apply_incremental:
        transaction_average_cost_before = average_cost_before
        transaction_cash_balance_before = cash_balance
        fx_rate = _fx_to_usd_for_trade(
            market_data, _asset_currency(asset), trade_date, today
        )
        trade_amount_usd = quantity * price * fx_rate

        if transaction_type is TransactionType.SELL:
            if position == "short":
                if existing_quantity > 0:
                    abort(400, message=LONG_POSITION_OPEN_MESSAGE)
                short_quantity_before = -existing_quantity
                if short_quantity_before == 0:
                    transaction_average_cost_before = decimal.Decimal("0")
                new_short_quantity = short_quantity_before + quantity
                holding.average_cost = (
                    short_quantity_before * existing_average_cost
                    + quantity * price
                ) / new_short_quantity
            else:
                if existing_quantity < 0:
                    abort(400, message=SHORT_POSITION_OPEN_MESSAGE)
                if quantity > existing_quantity:
                    abort(400, message=OVERSELL_MESSAGE)
            holding.quantity = existing_quantity - quantity
            cash_holding.average_cost = cash_balance + trade_amount_usd
        else:
            if position == "short":
                if existing_quantity > 0:
                    abort(400, message=LONG_POSITION_OPEN_MESSAGE)
                if quantity > -existing_quantity:
                    abort(400, message=OVERCOVER_MESSAGE)
            elif existing_quantity < 0:
                abort(400, message=SHORT_POSITION_OPEN_MESSAGE)
            if trade_amount_usd > cash_balance:
                abort(400, message=INSUFFICIENT_FUNDS_MESSAGE)
            if position == "long":
                if existing_quantity == 0:
                    transaction_average_cost_before = decimal.Decimal("0")
                new_quantity = existing_quantity + quantity
                holding.average_cost = (
                    existing_quantity * existing_average_cost + quantity * price
                ) / new_quantity
            holding.quantity = existing_quantity + quantity
            cash_holding.average_cost = cash_balance - trade_amount_usd

        holding.updated_at = now
        cash_holding.updated_at = now

    transaction_id = uuid.uuid4()
    db.session.add(
        Transactions(
            id=transaction_id,
            holding_id=holding.id,
            trade_date=trade_date,
            quantity=quantity,
            price=price,
            average_cost_before=(
                transaction_average_cost_before if apply_incremental else None
            ),
            cash_balance_before=(
                transaction_cash_balance_before if apply_incremental else None
            ),
            transaction_type=transaction_type.value,
            position=position,
        )
    )
    new_transaction_ids.add(transaction_id)

    asset_type = getattr(getattr(asset, "asset_type", None), "asset_type", None)

    return {
        "date": datetime.datetime.combine(
            trade_date, datetime.time.min, tzinfo=datetime.timezone.utc
        ),
        "symbol": asset.ticker,
        "name": asset.name,
        "asset_type": asset_type,
        "executed_price": float(quantity * price),
        "executed_unit_price": float(price),
    }


def _item_price(item, asset, market_data, today, trade_date):
    price = item.get("price")
    if price is not None:
        return _decimal_or_none(price)
    if trade_date == today and hasattr(market_data, "today_order_price"):
        return _decimal_or_none(market_data.today_order_price(asset.ticker))
    return _decimal_or_none(market_data.latest_price(asset.ticker))


def _ensure_asset_tradable_on_date(asset, trade_date, today, market_data):
    if trade_date >= today:
        return
    if not hasattr(market_data, "asset_tradable_on"):
        return
    if not market_data.asset_tradable_on(asset.ticker, trade_date):
        abort(400, message=ASSET_NOT_TRADABLE_ON_DATE_MESSAGE)


def _requires_historical_replay(items, today):
    for item in items:
        trade_date = item.get("trade_date") or today
        if trade_date > today:
            abort(400, message="trade_date cannot be later than today.")
        if trade_date < today:
            return True
    return False


def _validate_historical_future_margins(
    portfolio_id, market_data, today, starting_cash, new_transaction_ids
):
    rows = _portfolio_transaction_timeline(portfolio_id)
    cash_balance = decimal.Decimal(str(starting_cash))
    asset_quantities = {}
    new_cash_outflow = decimal.Decimal("0")
    new_asset_reductions = {}

    for transaction, holding, asset in rows:
        if _is_cash_timeline_transaction(transaction, asset):
            continue

        asset_id = holding.asset_id
        quantity = _decimal_or_zero(transaction.quantity)
        price = _decimal_or_zero(transaction.price)
        fx_rate = _fx_to_usd_for_trade(
            market_data, _asset_currency(asset), transaction.trade_date, today
        )
        trade_amount_usd = quantity * price * fx_rate
        is_new_transaction = transaction.id in new_transaction_ids
        asset_quantity = asset_quantities.setdefault(asset_id, decimal.Decimal("0"))

        if is_new_transaction:
            available_cash = cash_balance - new_cash_outflow
            available_asset_quantity = asset_quantity - new_asset_reductions.get(
                asset_id, decimal.Decimal("0")
            )
            if transaction.transaction_type == TransactionType.SELL.value:
                if quantity > available_asset_quantity:
                    abort(400, message=OVERSELL_MESSAGE)
                new_asset_reductions[asset_id] = (
                    new_asset_reductions.get(asset_id, decimal.Decimal("0")) + quantity
                )
                new_cash_outflow -= trade_amount_usd
            else:
                if trade_amount_usd > available_cash:
                    abort(400, message=INSUFFICIENT_FUNDS_MESSAGE)
                new_asset_reductions[asset_id] = (
                    new_asset_reductions.get(asset_id, decimal.Decimal("0")) - quantity
                )
                new_cash_outflow += trade_amount_usd
            continue

        if new_cash_outflow > 0:
            cash_margin = cash_balance
            if transaction.transaction_type == TransactionType.BUY.value:
                cash_margin -= trade_amount_usd
            if cash_margin < new_cash_outflow:
                abort(400, message=FUTURE_TRANSACTION_CONFLICT_MESSAGE)

        asset_reduction = new_asset_reductions.get(asset_id, decimal.Decimal("0"))
        if asset_reduction > 0 and asset_quantity < asset_reduction:
            abort(400, message=FUTURE_TRANSACTION_CONFLICT_MESSAGE)

        if transaction.transaction_type == TransactionType.SELL.value:
            asset_quantity -= quantity
            cash_balance += trade_amount_usd
        else:
            asset_quantity += quantity
            cash_balance -= trade_amount_usd
        asset_quantities[asset_id] = asset_quantity

        asset_reduction = new_asset_reductions.get(asset_id, decimal.Decimal("0"))
        if asset_reduction > 0 and asset_quantity < asset_reduction:
            abort(400, message=FUTURE_TRANSACTION_CONFLICT_MESSAGE)


def _replay_portfolio_transactions(portfolio_id, market_data, today, starting_cash):
    rows = _portfolio_transaction_timeline(portfolio_id)
    cash_balance = decimal.Decimal(str(starting_cash))
    states = {}
    now = datetime.datetime.now(datetime.timezone.utc)

    for transaction, holding, asset in rows:
        if _is_cash_timeline_transaction(transaction, asset):
            transaction.average_cost_before = None
            continue

        asset_id = holding.asset_id
        state = states.setdefault(
            asset_id,
            {
                "holding": holding,
                "quantity": decimal.Decimal("0"),
                "average_cost": None,
            },
        )

        quantity = _decimal_or_zero(transaction.quantity)
        price = _decimal_or_zero(transaction.price)
        average_cost_before = state["average_cost"]
        position = getattr(transaction, "position", None) or "long"

        fx_rate = _fx_to_usd_for_trade(
            market_data, _asset_currency(asset), transaction.trade_date, today
        )
        trade_amount_usd = quantity * price * fx_rate
        transaction.cash_balance_before = cash_balance

        if transaction.transaction_type == TransactionType.SELL.value:
            transaction.average_cost_before = average_cost_before
            if position == "short":
                if state["quantity"] > 0:
                    abort(400, message=LONG_POSITION_OPEN_MESSAGE)
                short_quantity_before = -state["quantity"]
                if short_quantity_before == 0:
                    transaction.average_cost_before = decimal.Decimal("0")
                new_short_quantity = short_quantity_before + quantity
                previous_average_cost = _decimal_or_zero(average_cost_before)
                state["average_cost"] = (
                    short_quantity_before * previous_average_cost
                    + quantity * price
                ) / new_short_quantity
            else:
                if state["quantity"] < 0:
                    abort(400, message=SHORT_POSITION_OPEN_MESSAGE)
                if quantity > state["quantity"]:
                    abort(400, message=OVERSELL_MESSAGE)
            state["quantity"] -= quantity
            cash_balance += trade_amount_usd
        else:
            if position == "short":
                if state["quantity"] > 0:
                    abort(400, message=LONG_POSITION_OPEN_MESSAGE)
                if quantity > -state["quantity"]:
                    abort(400, message=OVERCOVER_MESSAGE)
                transaction.average_cost_before = average_cost_before
            else:
                if state["quantity"] < 0:
                    abort(400, message=SHORT_POSITION_OPEN_MESSAGE)
            if trade_amount_usd > cash_balance:
                abort(400, message=INSUFFICIENT_FUNDS_MESSAGE)
            if position == "long":
                transaction.average_cost_before = (
                    decimal.Decimal("0")
                    if state["quantity"] == 0
                    else average_cost_before
                )
                new_quantity = state["quantity"] + quantity
                previous_average_cost = _decimal_or_zero(average_cost_before)
                state["average_cost"] = (
                    state["quantity"] * previous_average_cost + quantity * price
                ) / new_quantity
            state["quantity"] += quantity
            cash_balance -= trade_amount_usd

    for state in states.values():
        holding = state["holding"]
        holding.quantity = state["quantity"]
        holding.average_cost = state["average_cost"]
        holding.updated_at = now

    cash_holding = _get_or_create_usd_cash_holding(portfolio_id, {})
    cash_holding.quantity = decimal.Decimal("1")
    cash_holding.average_cost = cash_balance
    cash_holding.updated_at = now


def _portfolio_transaction_timeline(portfolio_id):
    return db.session.execute(
        select(Transactions, Holdings, AssetMaster)
        .join(Holdings, Transactions.holding_id == Holdings.id)
        .join(AssetMaster, Holdings.asset_id == AssetMaster.id)
        .where(Holdings.portfolio_id == portfolio_id)
        .order_by(Transactions.trade_date.asc(), Transactions.created_at.asc())
    ).all()


def _starting_cash_baseline(portfolio_id, market_data, today):
    cash_holding = _get_or_create_usd_cash_holding(portfolio_id, {})
    cash_balance = _decimal_or_zero(cash_holding.average_cost)

    for transaction, _holding, asset in _portfolio_transaction_timeline(portfolio_id):
        if _is_cash_timeline_transaction(transaction, asset):
            continue

        quantity = _decimal_or_zero(transaction.quantity)
        price = _decimal_or_zero(transaction.price)
        fx_rate = _fx_to_usd_for_trade(
            market_data, _asset_currency(asset), transaction.trade_date, today
        )
        trade_amount_usd = quantity * price * fx_rate
        if transaction.transaction_type == TransactionType.SELL.value:
            cash_balance -= trade_amount_usd
        else:
            cash_balance += trade_amount_usd

    return cash_balance


def _is_cash_timeline_transaction(transaction, asset):
    transaction_type = transaction.transaction_type
    if transaction_type in {"deposit", "withdrawal"}:
        return True
    return getattr(asset, "ticker", None) == "CASH-USD"


def _fx_to_usd_for_trade(market_data, currency, trade_date, today):
    if trade_date < today and hasattr(market_data, "fx_to_usd_on"):
        fx_rate = _decimal_or_none(market_data.fx_to_usd_on(currency, trade_date))
    else:
        fx_rate = _decimal_or_none(market_data.fx_to_usd(currency))
    if fx_rate is None:
        abort(502, message=FX_UNAVAILABLE_MESSAGE)
    return fx_rate


def _utc_today():
    return datetime.datetime.now(datetime.timezone.utc).date()


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

    if ticker.upper() in MANUAL_BOND_TICKERS:
        asset_type_value = "bond"
    else:
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
