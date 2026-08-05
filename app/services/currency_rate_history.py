"""Currency USD rate history import helpers.

`currency` の各通貨について Yahoo Finance の `<CUR>USD=X` 日次終値を取得し、
`currency_rate_history` に upsert する。構成は `asset_history` と対になっていて、
日付レンジの解釈やバッチ処理はそちらの helper をそのまま使う。
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.extensions import db
from app.models import Currency, CurrencyRateHistory
from app.services.asset_history import chunks, date_from_index
from app.services.common import decimal_or_none

DEFAULT_RANGE = "2y"
#: 基準通貨。自分自身に対するレートは常に 1 なので row を作らない。
BASE_CURRENCY = "USD"


@dataclass(frozen=True)
class CurrencyRateImportResult:
    """Summary for one currency rate import attempt."""

    currency: str
    currency_id: uuid.UUID
    existing_rows_before: int
    existing_rows_after: int
    fetched_rows: int
    upserted_rows: int
    error: str | None = None

    @property
    def added_rows(self) -> int:
        return max(self.existing_rows_after - self.existing_rows_before, 0)


def import_recent_currency_rates(
    *,
    start_date: datetime.date,
    end_date: datetime.date,
    currencies: Iterable[str] | None = None,
    batch_size: int = 500,
    dry_run: bool = False,
) -> list[CurrencyRateImportResult]:
    """Fetch Yahoo Finance daily USD rates and upsert them for known currencies."""

    if start_date >= end_date:
        raise ValueError("start_date must be before end_date")
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")

    results: list[CurrencyRateImportResult] = []

    for currency in _currency_query(currencies):
        existing_rows_before = count_currency_rate_rows(
            currency.id,
            start_date=start_date,
            end_date=end_date,
        )
        try:
            rows = fetch_daily_rate_rows(
                currency,
                start_date=start_date,
                end_date=end_date,
            )
            rows_to_write = find_currency_rate_rows_to_write(rows)
            if not rows_to_write:
                print(f"{currency.currency}: no write needed")
                upserted_rows = 0
            elif dry_run:
                print(
                    f"{currency.currency}: dry-run, {len(rows_to_write)} rows need writing"
                )
                upserted_rows = 0
            else:
                print(
                    f"{currency.currency}: write started, {len(rows_to_write)} rows to write"
                )
                upserted_rows = upsert_currency_rate_rows(rows_to_write, batch_size)
                db.session.commit()
                print(
                    f"{currency.currency}: write finished, {upserted_rows} rows written"
                )
            existing_rows_after = (
                existing_rows_before
                if dry_run
                else count_currency_rate_rows(
                    currency.id,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            results.append(
                CurrencyRateImportResult(
                    currency=currency.currency,
                    currency_id=currency.id,
                    existing_rows_before=existing_rows_before,
                    existing_rows_after=existing_rows_after,
                    fetched_rows=len(rows),
                    upserted_rows=upserted_rows,
                )
            )
        except Exception as error:
            db.session.rollback()
            results.append(
                CurrencyRateImportResult(
                    currency=currency.currency,
                    currency_id=currency.id,
                    existing_rows_before=existing_rows_before,
                    existing_rows_after=existing_rows_before,
                    fetched_rows=0,
                    upserted_rows=0,
                    error=str(error),
                )
            )

    return results


def rate_ticker(currency_code: str) -> str:
    """Return the Yahoo Finance FX ticker for a currency's USD rate."""

    return f"{currency_code.strip().upper()}USD=X"


def fetch_daily_rate_rows(
    currency: Currency,
    *,
    start_date: datetime.date,
    end_date: datetime.date,
) -> list[dict]:
    """Return currency_rate_history rows built from Yahoo Finance daily closes."""

    import yfinance as yf

    history = yf.Ticker(rate_ticker(currency.currency)).history(
        start=start_date,
        end=end_date,
        interval="1d",
        auto_adjust=False,
    )

    if history is None or history.empty or "Close" not in history:
        return []

    rows = []
    closes = history["Close"].dropna()
    for index, close in closes.items():
        rate = decimal_or_none(close)
        if rate is None:
            continue

        rate_date = date_from_index(index)
        if rate_date is None:
            continue

        rows.append(
            {
                "id": uuid.uuid4(),
                "currency_id": currency.id,
                "rate_date": rate_date,
                "close_price": rate,
            }
        )
    return rows


def upsert_currency_rate_rows(rows: list[dict], batch_size: int = 500) -> int:
    """Upsert rows by the currency/date uniqueness constraint."""

    if not rows:
        return 0

    upserted = 0
    table = CurrencyRateHistory.__table__
    dialect_name = db.engine.dialect.name

    for batch in chunks(rows, batch_size):
        if dialect_name == "postgresql":
            statement = postgresql_insert(table).values(batch)
        elif dialect_name == "sqlite":
            statement = sqlite_insert(table).values(batch)
        else:
            raise RuntimeError(f"Unsupported database dialect: {dialect_name}")

        statement = statement.on_conflict_do_update(
            index_elements=["currency_id", "rate_date"],
            set_={"close_price": statement.excluded.close_price},
        )
        result = db.session.execute(statement)
        # psycopg は行数を返せないとき rowcount に -1 を入れる。負値も
        # 「取得できなかった」扱いにしてバッチ長で代用する。
        rowcount = result.rowcount
        upserted += rowcount if rowcount is not None and rowcount >= 0 else len(batch)

    return upserted


def find_currency_rate_rows_to_write(rows: list[dict]) -> list[dict]:
    """Return rows that are missing or have a changed close rate."""

    if not rows:
        return []

    requested_keys = {
        (uuid.UUID(str(row["currency_id"])), row["rate_date"]) for row in rows
    }
    currency_ids = sorted({currency_id for currency_id, _ in requested_keys}, key=str)
    rate_dates = sorted({rate_date for _, rate_date in requested_keys})

    statement = (
        select(
            CurrencyRateHistory.currency_id,
            CurrencyRateHistory.rate_date,
            CurrencyRateHistory.close_price,
        )
        .where(CurrencyRateHistory.currency_id.in_(currency_ids))
        .where(CurrencyRateHistory.rate_date.in_(rate_dates))
    )
    existing = {
        (uuid.UUID(str(currency_id)), rate_date): close_price
        for currency_id, rate_date, close_price in db.session.execute(statement)
    }

    rows_to_write = []
    for row in rows:
        key = (uuid.UUID(str(row["currency_id"])), row["rate_date"])
        existing_close = existing.get(key)
        if existing_close is None or existing_close != row["close_price"]:
            rows_to_write.append(row)
    return rows_to_write


def count_currency_rate_rows(
    currency_id: uuid.UUID,
    *,
    start_date: datetime.date,
    end_date: datetime.date,
) -> int:
    statement = (
        select(func.count())
        .select_from(CurrencyRateHistory)
        .where(CurrencyRateHistory.currency_id == currency_id)
        .where(CurrencyRateHistory.rate_date >= start_date)
        .where(CurrencyRateHistory.rate_date < end_date)
    )
    return db.session.execute(statement).scalar_one()


def estimate_rate_rows(
    currency_count: int,
    start_date: datetime.date,
    end_date: datetime.date,
) -> int:
    """Estimate weekday daily-rate rows before hitting Yahoo Finance."""

    days = max((end_date - start_date).days, 0)
    return int(currency_count * days * 5 / 7)


def requested_currencies_not_matched(
    requested_currencies: Iterable[str],
    results: Iterable[CurrencyRateImportResult],
) -> list[str]:
    """Return requested codes with no `currency` row, ignoring the base currency."""

    requested = {
        currency.strip().upper()
        for currency in requested_currencies
        if currency and currency.strip()
    }
    requested.discard(BASE_CURRENCY)
    matched = {result.currency.upper() for result in results}
    return sorted(requested - matched)


def _currency_query(currencies: Iterable[str] | None = None) -> list[Currency]:
    statement = (
        select(Currency)
        .where(func.upper(Currency.currency) != BASE_CURRENCY)
        .order_by(Currency.currency)
    )

    normalized_currencies = sorted(
        {
            currency.strip().upper()
            for currency in currencies or []
            if currency.strip()
        }
    )
    if normalized_currencies:
        statement = statement.where(
            func.upper(Currency.currency).in_(normalized_currencies)
        )

    return list(db.session.execute(statement).scalars())
