"""ポートフォリオ推移グラフの business logic。

取引履歴から日付ごとの保有数量を復元し、`asset_data_history` の終値で
日次の USD 評価額を組み立てる。グラフの点も各期間の騰落も、すべてこの
1 本の評価額系列から計算する。`asset_type` を指定した場合は、その資産クラスの
holding だけで系列を組み立てる。

系列の組み立ては SQL 1 本に寄せてある。以前は保有銘柄の終値を全期間ぶん
Python に読み出してから畳んでいたが、計算自体は 1ms 未満で、実測の 99% が
DB の往復とレコード転送だった（remote Supabase で約 1.3 秒）。日付ごとの
合計まで DB 側で出すことで、往復は portfolio / holdings / 系列の 3 回、
転送は表示する日数ぶんだけになる。

現時点の割り切り:

- FX は `currency_rate_history` を優先する。その日以前の直近レートを使い、
  履歴の開始より前の日付は最も古い行まで遡る。現在のレートを使うのは、
  保存済みレートがまったく無い通貨だけ。
- 現金は保有資産の評価額に含めない。`asset_type=cash` を指定したときだけ、
  残高そのものを系列として返す。cash holding は取引履歴を持たないため、
  その通貨の直近の保存済みレート（無ければ現在のレート）で一度だけ換算した
  一定額として扱う。
"""

import bisect
import calendar
import datetime
import decimal

from sqlalchemy import Date, case, func, literal, select
from sqlalchemy.orm import aliased

from app.enums import Interval, PerformanceRange, TransactionType
from app.extensions import db
from app.models import (
    AssetDataHistory,
    AssetMaster,
    AssetType,
    Currency,
    CurrencyRateHistory,
    Holdings,
    Transactions,
)
from app.services.common import (
    SUMMARY_CURRENCY,
    current_portfolio,
    decimal_or_none,
    decimal_or_zero,
    percent_of,
)
from app.services.market_data import YahooFinanceMarketData

#: `asset_type` を絞り込まないときの値（UI の `All`）。
ALL_ASSET_TYPES = "all"
#: 現金の資産クラス。集計に含まれるのはこれを明示したときだけ。
CASH_ASSET_TYPE = "cash"

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
    asset_type_filter = (args.get("asset_type") or ALL_ASSET_TYPES).lower()
    today = datetime.date.today()
    # 未来日を指定されても、評価できるのは今日までしかない。
    end_date = min(args.get("end_date") or today, today)

    positions, cash_value, first_trade_date = _performance_positions(
        portfolio.id, market_data, asset_type_filter
    )

    # 表示期間の外にある起点（1 年前など）も引けるよう、系列は運用開始来で作る。
    dates, values = _value_series(positions, cash_value, first_trade_date, end_date)
    inception = _inception_date(first_trade_date, dates, end_date)
    start_date, response_range = _performance_window(args, inception, end_date)

    as_of_value = values[-1]
    investment_flows = _investment_flows(positions, end_date)
    returns = _performance_returns(dates, values, end_date, investment_flows)

    return {
        "currency": SUMMARY_CURRENCY,
        "interval": interval,
        "range": response_range,
        "start_date": start_date,
        "end_date": end_date,
        "asset_type": asset_type_filter,
        "metrics": {
            "portfolio_value": float(as_of_value),
            "today": returns["return_1d"],
            "return": _performance_change(
                as_of_value,
                *_return_baseline(
                    dates, values, start_date, end_date, investment_flows
                ),
            ),
            "total_return": returns["return_total"],
        },
        **returns,
        "points": _performance_points(dates, values, start_date, end_date, interval),
    }


def _performance_positions(portfolio_id, market_data, asset_type_filter):
    """Split holdings into priced positions, a cash balance and the first trade date.

    `asset_type_filter` が `all` 以外なら、その資産クラスの holding だけを残す。
    現金は `cash` を指定したときだけ集計され、そのときは価格データを持たないので
    残高がそのまま一定額の系列になる。

    関連は明示的に join する。`holding.asset` などの遅延ロードに任せると
    保有銘柄ごとに往復が増え、実測では endpoint 全体の 7 割を占めていた。
    """

    first_trade = (
        select(func.min(Transactions.trade_date))
        .where(Transactions.holding_id == Holdings.id)
        .scalar_subquery()
    )
    rows = db.session.execute(
        select(
            Holdings.id,
            Holdings.asset_id,
            Holdings.quantity,
            Holdings.average_cost,
            AssetMaster.currency_id,
            AssetType.asset_type,
            Currency.currency,
            first_trade.label("first_trade_date"),
        )
        .join(AssetMaster, AssetMaster.id == Holdings.asset_id)
        .outerjoin(AssetType, AssetType.id == AssetMaster.asset_type_id)
        .outerjoin(Currency, Currency.id == AssetMaster.currency_id)
        .where(Holdings.portfolio_id == portfolio_id)
        .order_by(AssetMaster.ticker)
    ).all()

    live_rates = {
        row.currency_id: decimal_or_none(
            market_data.fx_to_usd((row.currency or SUMMARY_CURRENCY).upper())
        )
        for row in rows
    }
    stored_rates = _latest_stored_rates(live_rates)

    positions = []
    cash_value = decimal.Decimal("0")
    trade_dates = []
    for row in rows:
        asset_type = (row.asset_type or "").lower()
        if asset_type_filter != ALL_ASSET_TYPES and asset_type != asset_type_filter:
            continue

        # 保存済みレートを優先し、履歴が無い通貨だけ現在のレートを使う。
        fx_rate = stored_rates.get(row.currency_id) or live_rates[row.currency_id]
        quantity = decimal_or_zero(row.quantity)

        if asset_type == CASH_ASSET_TYPE:
            # cash holding は quantity=1、average_cost に残高が入る。期間中は
            # 一定額として扱うので、直近のレートで一度だけ換算する。
            # 保有資産の評価額には混ぜず、cash を明示したときだけ集計する。
            if asset_type_filter == CASH_ASSET_TYPE and fx_rate is not None:
                cash_value += quantity * decimal_or_zero(row.average_cost) * fx_rate
            continue

        if fx_rate is None:
            continue

        if row.first_trade_date is not None:
            trade_dates.append(row.first_trade_date)
        positions.append(
            {
                "holding_id": row.id,
                "asset_id": row.asset_id,
                "currency_id": row.currency_id,
                # 日付ごとのレートは系列を組む SQL 側で引く。ここで持たせるのは
                # 履歴がまったく無い通貨のための最終フォールバック。
                "live_fx_rate": live_rates[row.currency_id],
            }
        )

    return positions, cash_value, (min(trade_dates) if trade_dates else None)


def _latest_stored_rates(currency_ids):
    """Return `{currency_id: latest stored USD rate}` for the given currencies."""

    currency_ids = [currency_id for currency_id in currency_ids if currency_id]
    if not currency_ids:
        return {}

    same_currency = aliased(CurrencyRateHistory)
    latest_date = (
        select(func.max(same_currency.rate_date))
        .where(same_currency.currency_id == CurrencyRateHistory.currency_id)
        .scalar_subquery()
    )
    rows = db.session.execute(
        select(CurrencyRateHistory.currency_id, CurrencyRateHistory.close_price)
        .where(CurrencyRateHistory.currency_id.in_(currency_ids))
        .where(CurrencyRateHistory.rate_date == latest_date)
    ).all()
    return {row.currency_id: decimal_or_none(row.close_price) for row in rows}


def _value_series(positions, cash_value, first_trade_date, end_date):
    """Build the USD value series up to `end_date`.

    `cash_value` は期間中一定なので、全ての点に同じ額を足す。推移グラフは
    現金を評価額に含めないので 0 が渡るが、現金も含めた合計が要る
    `get_portfolio_summary` はここに残高を渡す。
    """

    # 価格を持つ保有が無いときは期間末の 1 点だけを返す。`asset_type=cash`
    # ならその点が残高、ポートフォリオが空なら 0 になる。
    if not positions:
        return [end_date], [cash_value]

    rows = db.session.execute(
        _value_series_statement(positions, first_trade_date, end_date)
    ).all()
    dates = [row.price_date for row in rows]
    values = [cash_value + decimal_or_zero(row.market_value) for row in rows]
    return dates, values


def _value_series_statement(positions, first_trade_date, end_date):
    """Return the statement that totals every position per date.

    日付ごとに保有数量・終値・FX を引き当てて合計する。数量は現在値から
    その日より後の取引を差し引いて復元し、終値と FX はその日以前で最も
    新しい行を使う（休場日は前営業日の値を横引きする）。
    """

    asset_ids = [position["asset_id"] for position in positions]
    holding_ids = [position["holding_id"] for position in positions]
    end_date_column = literal(end_date, Date).label("price_date")

    price_dates = (
        select(AssetDataHistory.price_date.label("price_date"))
        .where(AssetDataHistory.asset_id.in_(asset_ids))
        .where(AssetDataHistory.price_date <= end_date)
    )
    if first_trade_date is not None:
        price_dates = price_dates.where(AssetDataHistory.price_date >= first_trade_date)
    # 期間末の点は必ず 1 つ作る。終値がまだ無い日は直近の終値で評価する。
    date_point = price_dates.union(select(end_date_column)).cte("date_point")

    signed_quantity = case(
        (
            func.lower(Transactions.transaction_type) == TransactionType.SELL.value,
            -Transactions.quantity,
        ),
        else_=Transactions.quantity,
    )
    quantity_after = (
        select(func.coalesce(func.sum(signed_quantity), 0))
        .where(Transactions.holding_id == Holdings.id)
        .where(Transactions.trade_date > date_point.c.price_date)
        .scalar_subquery()
    )
    close_price = (
        select(AssetDataHistory.close_price)
        .where(AssetDataHistory.asset_id == Holdings.asset_id)
        .where(AssetDataHistory.price_date <= date_point.c.price_date)
        .order_by(AssetDataHistory.price_date.desc())
        .limit(1)
        .scalar_subquery()
    )
    rate_on_or_before = (
        select(CurrencyRateHistory.close_price)
        .where(CurrencyRateHistory.currency_id == AssetMaster.currency_id)
        .where(CurrencyRateHistory.rate_date <= date_point.c.price_date)
        .order_by(CurrencyRateHistory.rate_date.desc())
        .limit(1)
        .scalar_subquery()
    )
    earliest_rate = (
        select(CurrencyRateHistory.close_price)
        .where(CurrencyRateHistory.currency_id == AssetMaster.currency_id)
        .order_by(CurrencyRateHistory.rate_date)
        .limit(1)
        .scalar_subquery()
    )
    # 保存済みレートを優先する。その日以前に行が無ければ最も古い行まで遡り、
    # 履歴がまったく無い通貨だけ現在のレートで換算する。
    fx_rate = func.coalesce(rate_on_or_before, earliest_rate, _live_fx_case(positions))

    quantity = Holdings.quantity - quantity_after
    market_value = case(
        (quantity > 0, quantity * close_price * fx_rate),
        else_=literal(0),
    )
    return (
        select(
            date_point.c.price_date,
            func.coalesce(func.sum(market_value), 0).label("market_value"),
        )
        .select_from(date_point)
        .join(Holdings, Holdings.id.in_(holding_ids))
        .join(AssetMaster, AssetMaster.id == Holdings.asset_id)
        .group_by(date_point.c.price_date)
        .order_by(date_point.c.price_date)
    )


def _live_fx_case(positions):
    """Map each currency to the live rate, for currencies with no stored history."""

    branches = [
        (AssetMaster.currency_id == position["currency_id"], position["live_fx_rate"])
        for position in positions
        if position["currency_id"] is not None
        and position["live_fx_rate"] is not None
    ]
    if not branches:
        return literal(None)
    return case(*branches, else_=literal(None))


def _inception_date(first_trade_date, dates, end_date):
    """Return the first day the portfolio can be valued（運用開始日）."""

    if first_trade_date is not None:
        return min(first_trade_date, end_date)
    # 取引履歴がまだ無いときは、価格データのある最も古い日を起点にする。
    return min(dates[0], end_date) if dates else end_date


def _investment_flows(positions, as_of):
    """Return BUY and SELL amounts for the positions through ``as_of``."""

    holding_ids = [position["holding_id"] for position in positions]
    if not holding_ids:
        return []

    rate_on_or_before = (
        select(CurrencyRateHistory.close_price)
        .where(CurrencyRateHistory.currency_id == AssetMaster.currency_id)
        .where(CurrencyRateHistory.rate_date <= Transactions.trade_date)
        .order_by(CurrencyRateHistory.rate_date.desc())
        .limit(1)
        .scalar_subquery()
    )
    earliest_rate = (
        select(CurrencyRateHistory.close_price)
        .where(CurrencyRateHistory.currency_id == AssetMaster.currency_id)
        .order_by(CurrencyRateHistory.rate_date)
        .limit(1)
        .scalar_subquery()
    )
    fx_rate = func.coalesce(
        rate_on_or_before, earliest_rate, _live_fx_case(positions)
    )
    amount = (Transactions.quantity * Transactions.price * fx_rate).label("amount")

    rows = db.session.execute(
        select(
            Transactions.trade_date,
            Transactions.transaction_type,
            amount,
        )
        .select_from(Transactions)
        .join(Holdings, Holdings.id == Transactions.holding_id)
        .join(AssetMaster, AssetMaster.id == Holdings.asset_id)
        .where(Transactions.holding_id.in_(holding_ids))
        .where(Transactions.trade_date <= as_of)
        .where(
            Transactions.transaction_type.in_(
                (TransactionType.BUY.value, TransactionType.SELL.value)
            )
        )
        .order_by(Transactions.trade_date)
    ).all()

    return [
        (
            trade_date,
            transaction_type,
            decimal_or_zero(amount),
        )
        for trade_date, transaction_type, amount in rows
    ]


def _return_baseline(dates, values, target, as_of, investment_flows):
    """Return the historical baseline and BUY/SELL amounts after it."""

    index = max(bisect.bisect_right(dates, target) - 1, 0)
    baseline_date = dates[index]
    purchases = decimal.Decimal("0")
    sales = decimal.Decimal("0")
    for trade_date, transaction_type, amount in investment_flows:
        if not baseline_date < trade_date <= as_of:
            continue
        if transaction_type == TransactionType.BUY.value:
            purchases += decimal_or_zero(amount)
        elif transaction_type == TransactionType.SELL.value:
            sales += decimal_or_zero(amount)

    return values[index], purchases, sales


def _performance_returns(dates, values, as_of, investment_flows=()):
    """Compare the as-of value with each range's trade-adjusted baseline."""

    as_of_value = values[-1]

    def change(target):
        return _performance_change(
            as_of_value,
            *_return_baseline(dates, values, target, as_of, investment_flows),
        )

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
        "return_total": _performance_change(
            as_of_value,
            *_return_baseline(dates, values, dates[0], as_of, investment_flows),
        ),
    }


def _performance_change(
    as_of_value,
    baseline_value,
    purchases=decimal.Decimal("0"),
    sales=decimal.Decimal("0"),
):
    invested_amount = baseline_value + purchases
    amount = as_of_value + sales - invested_amount
    return {
        "amount": float(amount),
        "percent": float(percent_of(amount, invested_amount)),
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
