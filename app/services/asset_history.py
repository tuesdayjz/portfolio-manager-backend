"""Asset price history import and asynchronous backfill helpers."""

from __future__ import annotations

import argparse
import datetime
import decimal
import logging
import re
import threading
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from flask import Flask
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.extensions import db
from app.models import AssetDataHistory, AssetMaster

DEFAULT_RANGE = "3y"
AUTO_BACKFILL_RANGE = "3y"
RANGE_PATTERN = re.compile(
    r"^(?P<count>\d+)\s*"
    r"(?P<unit>d|day|days|w|wk|week|weeks|mo|month|months|y|yr|year|years)$",
    re.IGNORECASE,
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssetHistoryImportResult:
    """Summary for one asset history import attempt."""

    ticker: str
    asset_id: uuid.UUID
    existing_rows_before: int
    existing_rows_after: int
    fetched_rows: int
    upserted_rows: int
    error: str | None = None

    @property
    def added_rows(self) -> int:
        return max(self.existing_rows_after - self.existing_rows_before, 0)


def schedule_asset_history_backfill(
    app: Flask,
    asset_ids: Iterable[uuid.UUID],
    *,
    range_value: str = AUTO_BACKFILL_RANGE,
) -> threading.Thread | None:
    """Start a best-effort background history backfill for asset ids."""

    if app.config.get("TESTING") and not app.config.get(
        "RUN_ASSET_HISTORY_BACKFILL_IN_TESTS"
    ):
        return None

    unique_asset_ids = sorted(
        {uuid.UUID(str(asset_id)) for asset_id in asset_ids},
        key=str,
    )
    if not unique_asset_ids:
        return None

    # This is only a demo, so an in-process thread is the most convenient way
    # to keep the transaction response fast without adding a job table/worker.
    thread = threading.Thread(
        target=_run_asset_history_backfill,
        args=(app, unique_asset_ids, range_value),
        daemon=True,
        name="asset-history-backfill",
    )
    thread.start()
    return thread


def backfill_asset_history_if_incomplete(
    asset_ids: Iterable[uuid.UUID],
    *,
    range_value: str = AUTO_BACKFILL_RANGE,
    batch_size: int = 500,
) -> list[AssetHistoryImportResult]:
    """Fetch and upsert history for selected assets."""

    start_date, end_date = resolve_date_range(
        range_value=range_value,
        start_date=None,
        end_date=None,
    )
    return import_recent_asset_history(
        start_date=start_date,
        end_date=end_date,
        asset_ids=asset_ids,
        batch_size=batch_size,
    )


def import_recent_asset_history(
    *,
    start_date: datetime.date,
    end_date: datetime.date,
    tickers: Iterable[str] | None = None,
    asset_ids: Iterable[uuid.UUID] | None = None,
    batch_size: int = 500,
    dry_run: bool = False,
) -> list[AssetHistoryImportResult]:
    """Fetch Yahoo Finance daily closes and upsert them for known assets."""

    if start_date >= end_date:
        raise ValueError("start_date must be before end_date")
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")

    assets = _asset_query(tickers=tickers, asset_ids=asset_ids)
    results: list[AssetHistoryImportResult] = []

    for asset in assets:
        existing_rows_before = count_asset_history_rows(
            asset.id,
            start_date=start_date,
            end_date=end_date,
        )
        try:
            rows = fetch_daily_close_rows(
                asset,
                start_date=start_date,
                end_date=end_date,
            )
            rows_to_write = find_asset_history_rows_to_write(rows)
            if not rows_to_write:
                print(f"{asset.ticker}: no write needed")
                upserted_rows = 0
            elif dry_run:
                print(f"{asset.ticker}: dry-run, {len(rows_to_write)} rows need writing")
                upserted_rows = 0
            else:
                print(f"{asset.ticker}: write started, {len(rows_to_write)} rows to write")
                upserted_rows = upsert_asset_history_rows(rows_to_write, batch_size)
                db.session.commit()
                print(f"{asset.ticker}: write finished, {upserted_rows} rows written")
            existing_rows_after = (
                existing_rows_before
                if dry_run
                else count_asset_history_rows(
                    asset.id,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            results.append(
                AssetHistoryImportResult(
                    ticker=asset.ticker,
                    asset_id=asset.id,
                    existing_rows_before=existing_rows_before,
                    existing_rows_after=existing_rows_after,
                    fetched_rows=len(rows),
                    upserted_rows=upserted_rows,
                )
            )
        except Exception as error:
            db.session.rollback()
            results.append(
                AssetHistoryImportResult(
                    ticker=asset.ticker,
                    asset_id=asset.id,
                    existing_rows_before=existing_rows_before,
                    existing_rows_after=existing_rows_before,
                    fetched_rows=0,
                    upserted_rows=0,
                    error=str(error),
                )
            )

    return results


def fetch_daily_close_rows(
    asset: AssetMaster,
    *,
    start_date: datetime.date,
    end_date: datetime.date,
) -> list[dict]:
    """Return asset_data_history rows built from Yahoo Finance daily closes."""

    import yfinance as yf

    history = yf.Ticker(asset.ticker).history(
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
        price = _decimal_or_none(close)
        if price is None:
            continue

        price_date = _date_from_index(index)
        if price_date is None:
            continue

        rows.append(
            {
                "id": uuid.uuid4(),
                "asset_id": asset.id,
                "price_date": price_date,
                "close_price": price,
            }
        )
    return rows


def upsert_asset_history_rows(rows: list[dict], batch_size: int = 500) -> int:
    """Upsert rows by the asset/date uniqueness constraint."""

    if not rows:
        return 0

    upserted = 0
    table = AssetDataHistory.__table__
    dialect_name = db.engine.dialect.name

    for batch in _chunks(rows, batch_size):
        if dialect_name == "postgresql":
            statement = postgresql_insert(table).values(batch)
        elif dialect_name == "sqlite":
            statement = sqlite_insert(table).values(batch)
        else:
            raise RuntimeError(f"Unsupported database dialect: {dialect_name}")

        statement = statement.on_conflict_do_update(
            index_elements=["asset_id", "price_date"],
            set_={"close_price": statement.excluded.close_price},
        )
        result = db.session.execute(statement)
        upserted += result.rowcount or len(batch)

    return upserted


def find_asset_history_rows_to_write(rows: list[dict]) -> list[dict]:
    """Return rows that are missing or have a changed close price."""

    if not rows:
        return []

    requested_keys = {
        (uuid.UUID(str(row["asset_id"])), row["price_date"])
        for row in rows
    }
    asset_ids = sorted({asset_id for asset_id, _ in requested_keys}, key=str)
    price_dates = sorted({price_date for _, price_date in requested_keys})

    statement = (
        select(
            AssetDataHistory.asset_id,
            AssetDataHistory.price_date,
            AssetDataHistory.close_price,
        )
        .where(AssetDataHistory.asset_id.in_(asset_ids))
        .where(AssetDataHistory.price_date.in_(price_dates))
    )
    existing = {
        (uuid.UUID(str(asset_id)), price_date): close_price
        for asset_id, price_date, close_price in db.session.execute(statement)
    }

    rows_to_write = []
    for row in rows:
        key = (uuid.UUID(str(row["asset_id"])), row["price_date"])
        existing_close = existing.get(key)
        if existing_close is None or existing_close != row["close_price"]:
            rows_to_write.append(row)
    return rows_to_write


def resolve_date_range(
    *,
    range_value: str,
    start_date: datetime.date | None,
    end_date: datetime.date | None,
) -> tuple[datetime.date, datetime.date]:
    """Resolve date arguments into Yahoo Finance's start/end dates."""

    resolved_end = end_date or datetime.date.today() + datetime.timedelta(days=1)
    resolved_start = start_date or resolved_end - parse_range_delta(range_value)
    if resolved_start >= resolved_end:
        raise argparse.ArgumentTypeError("start date must be before end date")
    return resolved_start, resolved_end


def parse_range_delta(value: str) -> datetime.timedelta:
    """Parse a compact range string like 10d, 3w, 6mo, or 1y."""

    match = RANGE_PATTERN.match(value.strip())
    if not match:
        raise argparse.ArgumentTypeError(
            "range must look like 10d, 3w, 6mo, or 1y"
        )

    count = int(match.group("count"))
    unit = match.group("unit").lower()
    if count <= 0:
        raise argparse.ArgumentTypeError("range count must be greater than 0")
    if unit in {"d", "day", "days"}:
        return datetime.timedelta(days=count)
    if unit in {"w", "wk", "week", "weeks"}:
        return datetime.timedelta(weeks=count)
    if unit in {"mo", "month", "months"}:
        return datetime.timedelta(days=count * 30)
    return datetime.timedelta(days=count * 365)


def parse_iso_date(value: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a valid YYYY-MM-DD date"
        ) from error


def estimate_history_rows(
    asset_count: int,
    start_date: datetime.date,
    end_date: datetime.date,
) -> int:
    """Estimate weekday daily-price rows before hitting Yahoo Finance."""

    days = max((end_date - start_date).days, 0)
    return int(asset_count * days * 5 / 7)


def count_asset_history_rows(
    asset_id: uuid.UUID,
    *,
    start_date: datetime.date,
    end_date: datetime.date,
) -> int:
    statement = (
        select(func.count())
        .select_from(AssetDataHistory)
        .where(AssetDataHistory.asset_id == asset_id)
        .where(AssetDataHistory.price_date >= start_date)
        .where(AssetDataHistory.price_date < end_date)
    )
    return db.session.execute(statement).scalar_one()


def requested_tickers_not_matched(
    requested_tickers: Iterable[str],
    results: Iterable[AssetHistoryImportResult],
) -> list[str]:
    requested = {
        ticker.strip().upper()
        for ticker in requested_tickers
        if ticker and ticker.strip()
    }
    matched = {result.ticker.upper() for result in results}
    return sorted(requested - matched)


def _run_asset_history_backfill(
    app: Flask,
    asset_ids: list[uuid.UUID],
    range_value: str,
) -> None:
    with app.app_context():
        try:
            results = backfill_asset_history_if_incomplete(
                asset_ids,
                range_value=range_value,
            )
            failures = [result for result in results if result.error]
            if failures:
                logger.warning(
                    "Asset history backfill finished with failures: %s", failures
                )
        except Exception:
            logger.exception("Asset history backfill failed")
        finally:
            db.session.remove()


def _asset_query(
    *,
    tickers: Iterable[str] | None = None,
    asset_ids: Iterable[uuid.UUID] | None = None,
) -> list[AssetMaster]:
    statement = select(AssetMaster).order_by(AssetMaster.ticker)

    normalized_tickers = sorted(
        {ticker.strip().upper() for ticker in tickers or [] if ticker.strip()}
    )
    normalized_asset_ids = sorted(
        {uuid.UUID(str(asset_id)) for asset_id in asset_ids or []},
        key=str,
    )
    if normalized_tickers:
        statement = statement.where(
            func.upper(AssetMaster.ticker).in_(normalized_tickers)
        )
    if normalized_asset_ids:
        statement = statement.where(AssetMaster.id.in_(normalized_asset_ids))

    return list(db.session.execute(statement).scalars())


def _chunks(rows: list[dict], batch_size: int):
    for index in range(0, len(rows), batch_size):
        yield rows[index : index + batch_size]


def _date_from_index(value) -> datetime.date | None:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    date_method = getattr(value, "date", None)
    if callable(date_method):
        result = date_method()
        if isinstance(result, datetime.date):
            return result
    return None


def _decimal_or_none(value) -> decimal.Decimal | None:
    try:
        price = decimal.Decimal(str(value))
    except (decimal.InvalidOperation, TypeError, ValueError):
        return None
    if price.is_nan() or price <= 0:
        return None
    return price
