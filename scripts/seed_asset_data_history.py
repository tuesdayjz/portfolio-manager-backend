"""Seed `asset_data_history` with daily closes fetched from Yahoo Finance.

Examples:
    # Backfill 1 year for every ticker already in asset_master
    .venv/bin/python scripts/seed_asset_data_history.py

    # Backfill specific tickers, registering them in asset_master if missing
    .venv/bin/python scripts/seed_asset_data_history.py \
        --ticker AAPL --ticker VOO --create-missing --period 2y

    # Explicit date range, without writing anything
    .venv/bin/python scripts/seed_asset_data_history.py \
        --ticker AAPL --start 2024-01-01 --end 2024-12-31 --dry-run
"""

from __future__ import annotations

import argparse
import datetime
import decimal
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import AssetDataHistory, AssetMaster, AssetType, Currency  # noqa: E402
from app.services.market_data import YahooFinanceMarketData  # noqa: E402
from app.services.transaction import QUOTE_TYPE_TO_ASSET_TYPE  # noqa: E402

# close_price は Numeric（精度指定なし）なので、桁があふれないようここで丸める。
PRICE_EXPONENT = decimal.Decimal("0.000001")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch daily closes from Yahoo Finance and upsert them into "
            "asset_data_history for local/test use."
        )
    )
    parser.add_argument(
        "--ticker",
        action="append",
        dest="tickers",
        default=None,
        help=(
            "Ticker to seed. Repeatable. Defaults to every ticker already "
            "present in asset_master."
        ),
    )
    parser.add_argument(
        "--period",
        default="1y",
        help="yfinance period when --start is omitted (1mo / 6mo / 1y / max ...).",
    )
    parser.add_argument(
        "--start",
        default=None,
        help="Inclusive start date (YYYY-MM-DD). Overrides --period.",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="Inclusive end date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--create-missing",
        action="store_true",
        help=(
            "Register unknown tickers in asset_master using Yahoo Finance "
            "metadata instead of skipping them."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and report, but roll back instead of committing.",
    )
    return parser.parse_args()


def parse_date(value: str | None, label: str) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise SystemExit(f"--{label} must be YYYY-MM-DD, got: {value!r}")


def existing_tickers() -> list[str]:
    return list(
        db.session.execute(select(AssetMaster.ticker).order_by(AssetMaster.ticker))
        .scalars()
        .all()
    )


def resolve_asset(ticker: str, create_missing: bool, market_data) -> AssetMaster | None:
    """Return the asset_master row for `ticker`, optionally creating it."""

    asset = db.session.execute(
        select(AssetMaster).where(AssetMaster.ticker == ticker)
    ).scalar_one_or_none()
    if asset or not create_missing:
        if not asset:
            print(f"  skip: {ticker} is not in asset_master (use --create-missing)")
        return asset

    meta = market_data.asset_meta(ticker)
    if not meta:
        print(f"  skip: {ticker} has no Yahoo Finance metadata")
        return None

    asset_type_value = QUOTE_TYPE_TO_ASSET_TYPE.get(meta["quote_type"])
    if not asset_type_value:
        print(f"  skip: {ticker} has unsupported quoteType {meta['quote_type']}")
        return None

    asset_type = db.session.execute(
        select(AssetType).where(AssetType.asset_type == asset_type_value)
    ).scalar_one_or_none()
    currency = db.session.execute(
        select(Currency).where(Currency.currency == meta["currency"])
    ).scalar_one_or_none()
    if not asset_type or not currency:
        print(
            f"  skip: {ticker} needs asset_type={asset_type_value!r} / "
            f"currency={meta['currency']!r} rows in the master tables"
        )
        return None

    asset = AssetMaster(
        id=uuid.uuid4(),
        ticker=ticker,
        name=ticker,
        asset_type_id=asset_type.id,
        currency_id=currency.id,
    )
    db.session.add(asset)
    db.session.flush()
    print(f"  created asset_master row for {ticker} ({asset.id})")
    return asset


def fetch_closes(
    ticker: str,
    period: str,
    start: datetime.date | None,
    end: datetime.date | None,
) -> list[tuple[datetime.date, decimal.Decimal]]:
    """Return `[(price_date, close_price), ...]` sorted by date."""

    import yfinance as yf

    kwargs: dict = {"interval": "1d", "auto_adjust": False}
    if start:
        kwargs["start"] = start.isoformat()
        # yfinance の end は排他なので、指定日を含めるために 1 日足す。
        last_day = (end or datetime.date.today()) + datetime.timedelta(days=1)
        kwargs["end"] = last_day.isoformat()
    else:
        kwargs["period"] = period

    try:
        history = yf.Ticker(ticker).history(**kwargs)
    except Exception as error:  # noqa: BLE001 - ネットワーク起因は握って次の銘柄へ
        print(f"  skip: {ticker} history fetch failed: {error}")
        return []

    if history is None or history.empty or "Close" not in history:
        print(f"  skip: {ticker} returned no history")
        return []

    rows: list[tuple[datetime.date, decimal.Decimal]] = []
    for index, value in history["Close"].dropna().items():
        price_date = index.date() if hasattr(index, "date") else index
        if end and price_date > end:
            continue
        try:
            price = decimal.Decimal(str(value)).quantize(
                PRICE_EXPONENT, rounding=decimal.ROUND_HALF_UP
            )
        except (decimal.InvalidOperation, TypeError, ValueError):
            continue
        if price <= 0:
            continue
        rows.append((price_date, price))

    rows.sort(key=lambda row: row[0])
    return rows


def upsert_history(
    asset: AssetMaster, rows: list[tuple[datetime.date, decimal.Decimal]]
) -> tuple[int, int]:
    """Insert new dates and refresh changed closes. Returns (inserted, updated)."""

    existing = {
        row.price_date: row
        for row in db.session.execute(
            select(AssetDataHistory).where(AssetDataHistory.asset_id == asset.id)
        ).scalars()
    }

    inserted = 0
    updated = 0
    for price_date, close_price in rows:
        current = existing.get(price_date)
        if current is None:
            db.session.add(
                AssetDataHistory(
                    id=uuid.uuid4(),
                    asset_id=asset.id,
                    price_date=price_date,
                    close_price=close_price,
                )
            )
            inserted += 1
        elif current.close_price != close_price:
            current.close_price = close_price
            updated += 1

    db.session.flush()
    return inserted, updated


def main() -> int:
    args = parse_args()
    start = parse_date(args.start, "start")
    end = parse_date(args.end, "end")
    if start and end and start > end:
        raise SystemExit("--start must not be after --end")

    app = create_app()
    market_data = YahooFinanceMarketData()

    with app.app_context():
        tickers = [t.strip() for t in (args.tickers or []) if t.strip()]
        if not tickers:
            tickers = existing_tickers()
            if not tickers:
                raise SystemExit(
                    "asset_master is empty. Pass --ticker ... --create-missing."
                )
            print(f"No --ticker given; seeding {len(tickers)} asset_master tickers.")

        total_inserted = 0
        total_updated = 0
        for ticker in tickers:
            print(f"{ticker}:")
            asset = resolve_asset(ticker, args.create_missing, market_data)
            if not asset:
                continue

            rows = fetch_closes(ticker, args.period, start, end)
            if not rows:
                continue

            inserted, updated = upsert_history(asset, rows)
            total_inserted += inserted
            total_updated += updated
            print(
                f"  {len(rows)} closes {rows[0][0]}..{rows[-1][0]} "
                f"-> inserted {inserted}, updated {updated}"
            )

        if args.dry_run:
            db.session.rollback()
            print(
                f"Dry run: rolled back (would insert {total_inserted}, "
                f"update {total_updated})."
            )
        else:
            db.session.commit()
            print(f"Committed: inserted {total_inserted}, updated {total_updated}.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
