"""ポートフォリオ推移グラフの business logic。

取引履歴から日付ごとの保有数量を復元し、`asset_data_history` の終値で
日次の USD 評価額を組み立てる。グラフの点も各期間の騰落も、すべてこの
1 本の評価額系列から計算する。

現時点の割り切り:

- 過去の FX レートは保存していないため、全期間を通して現在のレートで換算する。
- cash holding は取引履歴を持たないため、期間中は一定額として扱う。
"""

import bisect
import calendar
import datetime
import decimal

from sqlalchemy import select

from app.enums import Interval, PerformanceRange, TransactionType
from app.extensions import db
from app.models import AssetDataHistory, AssetMaster, Holdings, Transactions
from app.services.common import (
    SUMMARY_CURRENCY,
    asset_currency,
    current_portfolio,
    decimal_or_none,
    decimal_or_zero,
    percent_of,
)
from app.services.market_data import YahooFinanceMarketData

_RANGE_DAYS = {
    PerformanceRange.DAY: 1,
    PerformanceRange.WEEK: 7,
}
_RANGE_MONTHS = {
    PerformanceRange.MONTH: 1,
    PerformanceRange.THREE_MONTHS: 3,
    PerformanceRange.YEAR: 12,
}


def get_portfolio_performance(args, market_data=None):
    """Return the USD value series and period returns for the current user's portfolio."""

    portfolio = current_portfolio()
    market_data = market_data or YahooFinanceMarketData()
    interval = args.get("interval") or Interval.DAILY
    asset_type = args.get("asset_type")
    today = datetime.date.today()
    # 未来日を指定されても、評価できるのは今日までしかない。
    end_date = min(args.get("end_date") or today, today)

    positions, cash_value = _performance_positions(portfolio.id, market_data, asset_type=asset_type)
    price_history = _price_history(positions, end_date)
    inception = _inception_date(positions, price_history, end_date)
    start_date, response_range = _performance_window(args, inception, end_date)

    # 表示期間の外にある起点（1 年前など）も引けるよう、系列は運用開始来で作る。
    dates, values = _value_series(
        positions, cash_value, price_history, inception, end_date
    )
    as_of_value = values[-1]
    returns = _performance_returns(dates, values, end_date)

    return {
        "currency": SUMMARY_CURRENCY,
        "interval": interval,
        "range": response_range,
        "start_date": start_date,
        "end_date": end_date,
        "metrics": {
            "portfolio_value": float(as_of_value),
            "today": returns["return_1d"],
            "return": _performance_change(
                as_of_value, _value_as_of(dates, values, start_date)
            ),
            "total_return": returns["return_total"],
        },
        **returns,
        "points": _performance_points(dates, values, start_date, end_date, interval),
    }


def _performance_positions(portfolio_id, market_data, asset_type=None):
    """Split holdings into priced positions and a flat USD cash balance."""

    holdings = (
        db.session.execute(
            select(Holdings)
            .join(Holdings.asset)
            .where(Holdings.portfolio_id == portfolio_id)
            .order_by(AssetMaster.ticker)
        )
        .scalars()
        .all()
    )

    filter_asset_type = asset_type.lower() if asset_type and asset_type.lower() != "all" else None

    positions = []
    cash_value = decimal.Decimal("0")
    for holding in holdings:
        asset = holding.asset
        holding_asset_type = getattr(getattr(asset, "asset_type", None), "asset_type", None) or ""
        
        # If filtering by asset_type, match against asset_type string
        if filter_asset_type:
            # Simple substring matching for broader asset class groups (e.g. stock/equities, fx, bond)
            hat = holding_asset_type.lower()
            match = False
            if filter_asset_type in ("equities", "stock") and ("stock" in hat or "equity" in hat or hat in ("etf", "mutualfund", "reit", "")):
                match = True
            elif filter_asset_type in ("fx", "forex", "currency") and ("fx" in hat or "forex" in hat or "currency" in hat):
                match = True
            elif filter_asset_type in ("fixed-income", "bond") and ("bond" in hat or "fixed" in hat):
                match = True
            elif filter_asset_type in ("commodities", "commodity") and ("commodity" in hat or "metal" in hat or "energy" in hat):
                match = True
            elif filter_asset_type == hat:
                match = True
            
            if not match:
                continue

        fx_rate = decimal_or_none(market_data.fx_to_usd(asset_currency(asset)))
        if fx_rate is None:
            continue

        quantity = decimal_or_zero(holding.quantity)
        if holding_asset_type.lower() == "cash":
            # Cash balance is only included when not filtering or explicitly requesting cash/all
            if not filter_asset_type or filter_asset_type == "cash":
                cash_value += quantity * decimal_or_zero(holding.average_cost) * fx_rate
            continue

        positions.append(
            {
                "holding_id": holding.id,
                "asset_id": holding.asset_id,
                "quantity": quantity,
                "fx_rate": fx_rate,
                "trades": [],
            }
        )

    _attach_trades(positions)
    return positions, cash_value


def _attach_trades(positions):
    """Attach signed trade quantities so past holding quantities can be replayed."""

    by_holding = {position["holding_id"]: position for position in positions}
    if not by_holding:
        return

    trades = db.session.execute(
        select(Transactions)
        .where(Transactions.holding_id.in_(by_holding.keys()))
        .order_by(Transactions.trade_date)
    ).scalars()
    for trade in trades:
        position = by_holding.get(trade.holding_id)
        if position is None:
            continue
        quantity = decimal_or_zero(trade.quantity)
        if (trade.transaction_type or "").lower() == TransactionType.SELL.value:
            quantity = -quantity
        position["trades"].append((trade.trade_date, quantity))


def _price_history(positions, end_date):
    """Return `{asset_id: (dates, close_prices)}`, ascending by date."""

    asset_ids = {position["asset_id"] for position in positions}
    if not asset_ids:
        return {}

    rows = db.session.execute(
        select(
            AssetDataHistory.asset_id,
            AssetDataHistory.price_date,
            AssetDataHistory.close_price,
        )
        .where(AssetDataHistory.asset_id.in_(asset_ids))
        .where(AssetDataHistory.price_date <= end_date)
        .order_by(AssetDataHistory.price_date)
    ).all()

    history = {}
    for asset_id, price_date, close_price in rows:
        price = decimal_or_none(close_price)
        if price is None:
            continue
        dates, prices = history.setdefault(asset_id, ([], []))
        dates.append(price_date)
        prices.append(price)
    return history


def _inception_date(positions, price_history, end_date):
    """Return the first day the portfolio can be valued（運用開始日）."""

    candidates = [
        trade_date for position in positions for trade_date, _ in position["trades"]
    ]
    if not candidates:
        # 取引履歴がまだ無いときは、価格データのある最も古い日を起点にする。
        candidates = [dates[0] for dates, _ in price_history.values() if dates]
    if not candidates:
        return end_date
    return min(min(candidates), end_date)


def _value_series(positions, cash_value, price_history, inception, end_date):
    """Build the USD value series over `[inception, end_date]`."""

    dates = sorted(
        {
            price_date
            for date_list, _ in price_history.values()
            for price_date in date_list
            if inception <= price_date <= end_date
        }
    )
    # 期間末の点は必ず 1 つ作る。終値がまだ無い日は直近の終値で評価する。
    if not dates or dates[-1] != end_date:
        dates.append(end_date)

    values = [
        _value_at(positions, cash_value, price_history, price_date)
        for price_date in dates
    ]
    return dates, values


def _value_at(positions, cash_value, price_history, target):
    """Return the USD value of everything held on `target`, cash included."""

    total = cash_value
    for position in positions:
        quantity = _quantity_at(position, target)
        if quantity <= 0:
            continue
        price = _close_price_at(price_history.get(position["asset_id"]), target)
        if price is None:
            continue
        total += quantity * price * position["fx_rate"]
    return total


def _quantity_at(position, target):
    """Replay trades backwards from the current quantity to `target`."""

    quantity = position["quantity"]
    for trade_date, signed_quantity in position["trades"]:
        if trade_date > target:
            quantity -= signed_quantity
    return quantity


def _close_price_at(series, target):
    """Return the latest close price on or before `target`."""

    if not series:
        return None
    dates, prices = series
    index = bisect.bisect_right(dates, target) - 1
    if index < 0:
        return None
    return prices[index]


def _value_as_of(dates, values, target):
    """Return the portfolio value on or before `target`.

    起点より前のデータが無い期間（運用 3 か月で `1y` を見た場合など）は、
    記録のある最も古い評価額を起点として扱う。
    """

    index = bisect.bisect_right(dates, target) - 1
    return values[max(index, 0)]


def _performance_returns(dates, values, as_of):
    """Compare the as-of value with the starting value of each range."""

    as_of_value = values[-1]

    def change(target):
        return _performance_change(as_of_value, _value_as_of(dates, values, target))

    return {
        "return_1d": change(as_of - datetime.timedelta(days=1)),
        "return_1w": change(as_of - datetime.timedelta(days=7)),
        "return_1m": change(_minus_months(as_of, 1)),
        "return_3m": change(_minus_months(as_of, 3)),
        # 年初来は前年最終営業日の終値を起点にする。
        "return_YTD": change(
            datetime.date(as_of.year, 1, 1) - datetime.timedelta(days=1)
        ),
        "return_1y": change(_minus_months(as_of, 12)),
        "return_total": _performance_change(as_of_value, values[0]),
    }


def _performance_change(as_of_value, baseline_value):
    amount = as_of_value - baseline_value
    return {
        "amount": float(amount),
        "percent": float(percent_of(amount, baseline_value)),
    }


def _performance_points(dates, values, start_date, end_date, interval):
    """Sample the value series for the graph at the requested interval."""

    buckets = {}
    for price_date, value in zip(dates, values):
        if not start_date <= price_date <= end_date:
            continue
        # 同じ週・月では最後の点だけを残す。
        buckets[_interval_key(interval, price_date)] = (price_date, value)

    return [
        {"date": price_date, "total_market_value": float(value)}
        for price_date, value in sorted(buckets.values(), key=lambda point: point[0])
    ]


def _interval_key(interval, price_date):
    if interval is Interval.WEEKLY:
        return price_date.isocalendar()[:2]
    if interval is Interval.MONTHLY:
        return (price_date.year, price_date.month)
    return price_date


def _performance_window(args, inception, end_date):
    """Resolve the requested window as `(start_date, range)`.

    `start_date` / `end_date` の指定があればそちらを優先し、レスポンスの
    `range` は null にする。
    """

    start_date = args.get("start_date")
    if start_date or args.get("end_date"):
        return (start_date or inception), None

    requested_range = args.get("range") or PerformanceRange.ALL
    return _range_start(requested_range, inception, end_date), requested_range


def _range_start(performance_range, inception, end_date):
    if performance_range is PerformanceRange.ALL:
        return inception
    if performance_range is PerformanceRange.YEAR_TO_DATE:
        return datetime.date(end_date.year, 1, 1)
    days = _RANGE_DAYS.get(performance_range)
    if days is not None:
        return end_date - datetime.timedelta(days=days)
    return _minus_months(end_date, _RANGE_MONTHS[performance_range])


def _minus_months(target, months):
    """Subtract calendar months, clamping to the last day of the shorter month."""

    month_index = target.year * 12 + target.month - 1 - months
    year, month = divmod(month_index, 12)
    month += 1
    day = min(target.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)
