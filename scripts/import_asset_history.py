"""CLI wrapper for importing recent Yahoo Finance close prices."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.services.asset_history import (
    DEFAULT_RANGE,
    estimate_history_rows,
    import_recent_asset_history,
    parse_iso_date,
    requested_tickers_not_matched,
    resolve_date_range,
)


def load_local_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    load_dotenv(PROJECT_ROOT / "tests" / ".env", override=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch recent Yahoo Finance daily close prices for asset_master rows "
            "and upsert them into asset_data_history."
        )
    )
    parser.add_argument(
        "--range",
        default=DEFAULT_RANGE,
        help=(
            "Recent time range to import, such as 10d, 3w, 6mo, or 1y. "
            f"Defaults to {DEFAULT_RANGE}."
        ),
    )
    parser.add_argument(
        "--start-date",
        type=parse_iso_date,
        default=None,
        help="Inclusive start date in YYYY-MM-DD format. Overrides --range start.",
    )
    parser.add_argument(
        "--end-date",
        type=parse_iso_date,
        default=None,
        help=(
            "Exclusive end date in YYYY-MM-DD format. Defaults to tomorrow so "
            "today's completed Yahoo data can be included when available."
        ),
    )
    parser.add_argument(
        "--ticker",
        action="append",
        default=[],
        help="Ticker to import. Repeat for multiple tickers. Defaults to all assets.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Rows per database upsert batch. Defaults to 500.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data and print counts without writing to the database.",
    )
    return parser.parse_args()


def main() -> int:
    load_local_env()
    args = parse_args()
    try:
        start_date, end_date = resolve_date_range(
            range_value=args.range,
            start_date=args.start_date,
            end_date=args.end_date,
        )
    except argparse.ArgumentTypeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    app = create_app()
    with app.app_context():
        results = import_recent_asset_history(
            start_date=start_date,
            end_date=end_date,
            tickers=args.ticker,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )

    asset_count = len(results)
    fetched_total = sum(result.fetched_rows for result in results)
    upserted_total = sum(result.upserted_rows for result in results)
    added_total = sum(result.added_rows for result in results)
    estimated_rows = estimate_history_rows(asset_count, start_date, end_date)

    mode = "dry run" if args.dry_run else "import"
    print(
        f"Asset history {mode} complete: assets={asset_count}, "
        f"range={start_date.isoformat()}..{end_date.isoformat()}, "
        f"estimated_rows={estimated_rows}, fetched_rows={fetched_total}, "
        f"upserted_rows={upserted_total}, added_rows={added_total}"
    )

    unmatched_tickers = requested_tickers_not_matched(args.ticker, results)
    if unmatched_tickers:
        print(
            "No matching asset_master row for: "
            f"{', '.join(unmatched_tickers)}",
            file=sys.stderr,
        )

    failures = [result for result in results if result.error]
    for result in results:
        status = f"error={result.error}" if result.error else "ok"
        print(
            f"- {result.ticker}: before={result.existing_rows_before}, "
            f"after={result.existing_rows_after}, fetched={result.fetched_rows}, "
            f"upserted={result.upserted_rows}, added={result.added_rows}, {status}"
        )

    if failures or unmatched_tickers:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
