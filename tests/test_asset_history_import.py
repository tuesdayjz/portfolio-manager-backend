"""asset_data_history import service and script tests."""

import datetime
import decimal
import io
import sys
import unittest
import uuid
from contextlib import redirect_stdout

from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.models import AssetDataHistory, AssetMaster
from app.services.asset_history import (
    AUTO_BACKFILL_RANGE,
    estimate_history_rows,
    import_recent_asset_history,
    parse_range_delta,
    requested_tickers_not_matched,
    resolve_date_range,
    schedule_asset_history_backfill,
    upsert_asset_history_rows,
)


class AssetHistoryImportTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.app_context = self.app.app_context()
        self.app_context.push()
        self._create_sqlite_schema()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        engine = db.engine
        db.session.remove()
        self._drop_sqlite_schema()
        engine.dispose()
        self.app_context.pop()

    def _create_sqlite_schema(self):
        statements = [
            """
            CREATE TABLE asset_master (
                id CHAR(32) PRIMARY KEY,
                ticker TEXT NOT NULL,
                name TEXT,
                asset_type_id CHAR(32),
                currency_id CHAR(32)
            )
            """,
            """
            CREATE TABLE asset_data_history (
                id CHAR(32) PRIMARY KEY,
                asset_id CHAR(32) NOT NULL,
                price_date DATE NOT NULL,
                close_price NUMERIC NOT NULL,
                UNIQUE (asset_id, price_date)
            )
            """,
        ]
        for statement in statements:
            db.session.execute(text(statement))
        db.session.commit()

    def _drop_sqlite_schema(self):
        for table_name in ("asset_data_history", "asset_master"):
            db.session.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        db.session.commit()

    def _asset(self, ticker):
        asset = AssetMaster(id=uuid.uuid4(), ticker=ticker, name=ticker)
        db.session.add(asset)
        db.session.commit()
        return asset

    def test_upsert_asset_history_rows_updates_duplicate_date(self):
        asset = self._asset("AAPL")
        price_date = datetime.date(2026, 8, 3)

        first_count = upsert_asset_history_rows(
            [
                {
                    "id": uuid.uuid4(),
                    "asset_id": asset.id,
                    "price_date": price_date,
                    "close_price": decimal.Decimal("100.50"),
                }
            ]
        )
        second_count = upsert_asset_history_rows(
            [
                {
                    "id": uuid.uuid4(),
                    "asset_id": asset.id,
                    "price_date": price_date,
                    "close_price": decimal.Decimal("101.75"),
                }
            ]
        )
        db.session.commit()

        rows = db.session.query(AssetDataHistory).filter_by(asset_id=asset.id).all()

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].close_price, decimal.Decimal("101.75"))

    def test_dry_run_fetches_without_writing(self):
        asset = self._asset("MSFT")

        def fake_fetch(asset, *, start_date, end_date):
            return [
                {
                    "id": uuid.uuid4(),
                    "asset_id": asset.id,
                    "price_date": datetime.date(2026, 8, 3),
                    "close_price": decimal.Decimal("10"),
                }
            ]

        from unittest.mock import patch

        with patch(
            "app.services.asset_history.fetch_daily_close_rows",
            side_effect=fake_fetch,
        ):
            results = import_recent_asset_history(
                start_date=datetime.date(2026, 7, 13),
                end_date=datetime.date(2026, 8, 4),
                dry_run=True,
            )

        count = db.session.execute(
            text("SELECT COUNT(*) FROM asset_data_history")
        ).scalar()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].ticker, "MSFT")
        self.assertEqual(results[0].existing_rows_before, 0)
        self.assertEqual(results[0].existing_rows_after, 0)
        self.assertEqual(results[0].fetched_rows, 1)
        self.assertEqual(results[0].upserted_rows, 0)
        self.assertEqual(count, 0)

    def test_import_reports_added_rows(self):
        asset = self._asset("TSLA")

        def fake_fetch(asset, *, start_date, end_date):
            return [
                {
                    "id": uuid.uuid4(),
                    "asset_id": asset.id,
                    "price_date": datetime.date(2026, 8, 3),
                    "close_price": decimal.Decimal("250"),
                }
            ]

        from unittest.mock import patch

        with patch(
            "app.services.asset_history.fetch_daily_close_rows",
            side_effect=fake_fetch,
        ):
            results = import_recent_asset_history(
                start_date=datetime.date(2026, 7, 13),
                end_date=datetime.date(2026, 8, 4),
            )

        self.assertEqual(results[0].existing_rows_before, 0)
        self.assertEqual(results[0].existing_rows_after, 1)
        self.assertEqual(results[0].upserted_rows, 1)
        self.assertEqual(results[0].added_rows, 1)

    def test_import_writes_only_available_rows_for_recently_listed_asset(self):
        asset = self._asset("IPO")
        available_dates = [
            datetime.date(2026, 7, 31),
            datetime.date(2026, 8, 3),
        ]

        def fake_fetch(asset, *, start_date, end_date):
            self.assertEqual(start_date, datetime.date(2023, 8, 4))
            self.assertEqual(end_date, datetime.date(2026, 8, 4))
            return [
                {
                    "id": uuid.uuid4(),
                    "asset_id": asset.id,
                    "price_date": price_date,
                    "close_price": decimal.Decimal("25"),
                }
                for price_date in available_dates
            ]

        from unittest.mock import patch

        with patch(
            "app.services.asset_history.fetch_daily_close_rows",
            side_effect=fake_fetch,
        ):
            results = import_recent_asset_history(
                start_date=datetime.date(2023, 8, 4),
                end_date=datetime.date(2026, 8, 4),
            )

        rows = (
            db.session.query(AssetDataHistory)
            .filter_by(asset_id=asset.id)
            .order_by(AssetDataHistory.price_date)
            .all()
        )

        self.assertEqual(results[0].fetched_rows, 2)
        self.assertEqual(results[0].upserted_rows, 2)
        self.assertEqual([row.price_date for row in rows], available_dates)

    def test_import_prints_no_write_when_history_is_current(self):
        asset = self._asset("NVDA")
        price_date = datetime.date(2026, 8, 3)
        upsert_asset_history_rows(
            [
                {
                    "id": uuid.uuid4(),
                    "asset_id": asset.id,
                    "price_date": price_date,
                    "close_price": decimal.Decimal("100.00"),
                }
            ]
        )
        db.session.commit()

        def fake_fetch(asset, *, start_date, end_date):
            return [
                {
                    "id": uuid.uuid4(),
                    "asset_id": asset.id,
                    "price_date": price_date,
                    "close_price": decimal.Decimal("100.00"),
                }
            ]

        from unittest.mock import patch

        output = io.StringIO()
        with (
            patch(
                "app.services.asset_history.fetch_daily_close_rows",
                side_effect=fake_fetch,
            ),
            redirect_stdout(output),
        ):
            results = import_recent_asset_history(
                start_date=datetime.date(2026, 7, 13),
                end_date=datetime.date(2026, 8, 4),
            )

        self.assertIn("NVDA: no write needed", output.getvalue())
        self.assertEqual(results[0].existing_rows_before, 1)
        self.assertEqual(results[0].existing_rows_after, 1)
        self.assertEqual(results[0].upserted_rows, 0)

    def test_import_prints_write_start_count_and_end(self):
        asset = self._asset("AMD")

        def fake_fetch(asset, *, start_date, end_date):
            return [
                {
                    "id": uuid.uuid4(),
                    "asset_id": asset.id,
                    "price_date": datetime.date(2026, 8, 3),
                    "close_price": decimal.Decimal("175.25"),
                }
            ]

        from unittest.mock import patch

        output = io.StringIO()
        with (
            patch(
                "app.services.asset_history.fetch_daily_close_rows",
                side_effect=fake_fetch,
            ),
            redirect_stdout(output),
        ):
            results = import_recent_asset_history(
                start_date=datetime.date(2026, 7, 13),
                end_date=datetime.date(2026, 8, 4),
            )

        printed = output.getvalue()
        self.assertIn("AMD: write started, 1 rows to write", printed)
        self.assertIn("AMD: write finished, 1 rows written", printed)
        self.assertEqual(results[0].upserted_rows, 1)
        self.assertEqual(results[0].added_rows, 1)

    def test_ticker_matching_is_case_insensitive(self):
        asset = self._asset("AAPL")
        row = {
            "id": uuid.uuid4(),
            "asset_id": asset.id,
            "price_date": datetime.date(2026, 8, 3),
            "close_price": decimal.Decimal("100"),
        }

        from unittest.mock import patch

        with patch(
            "app.services.asset_history.fetch_daily_close_rows",
            return_value=[row],
        ):
            results = import_recent_asset_history(
                start_date=datetime.date(2026, 7, 13),
                end_date=datetime.date(2026, 8, 4),
                tickers=["aapl"],
                dry_run=True,
            )

        self.assertEqual([result.ticker for result in results], ["AAPL"])

    def test_requested_tickers_not_matched_reports_missing_values(self):
        asset_id = uuid.uuid4()
        results = [
            type(
                "Result",
                (),
                {
                    "ticker": "AAPL",
                    "asset_id": asset_id,
                    "fetched_rows": 0,
                    "upserted_rows": 0,
                    "existing_rows_before": 0,
                    "existing_rows_after": 0,
                    "added_rows": 0,
                    "error": None,
                },
            )()
        ]

        self.assertEqual(
            requested_tickers_not_matched(["aapl", "MSFT"], results),
            ["MSFT"],
        )

    def test_default_range_is_three_weeks(self):
        start_date, end_date = resolve_date_range(
            range_value="3w",
            start_date=None,
            end_date=datetime.date(2026, 8, 4),
        )

        self.assertEqual(start_date, datetime.date(2026, 7, 14))
        self.assertEqual(end_date, datetime.date(2026, 8, 4))

    def test_parse_range_accepts_different_units(self):
        self.assertEqual(parse_range_delta("10d"), datetime.timedelta(days=10))
        self.assertEqual(parse_range_delta("3w"), datetime.timedelta(days=21))
        self.assertEqual(parse_range_delta("6mo"), datetime.timedelta(days=180))
        self.assertEqual(parse_range_delta("1y"), datetime.timedelta(days=365))

    def test_estimate_history_rows_uses_weekdays(self):
        self.assertEqual(
            estimate_history_rows(
                3,
                datetime.date(2026, 7, 14),
                datetime.date(2026, 8, 4),
            ),
            45,
        )

    def test_schedule_asset_history_backfill_starts_thread_with_default_range(self):
        from unittest.mock import patch

        asset_id = uuid.uuid4()
        self.app.config["RUN_ASSET_HISTORY_BACKFILL_IN_TESTS"] = True

        with patch("app.services.asset_history.threading.Thread") as thread_class:
            thread = schedule_asset_history_backfill(self.app, [asset_id, asset_id])

        self.assertIs(thread, thread_class.return_value)
        thread_class.assert_called_once()
        call_kwargs = thread_class.call_args.kwargs
        self.assertTrue(call_kwargs["daemon"])
        self.assertEqual(call_kwargs["name"], "asset-history-backfill")
        self.assertEqual(call_kwargs["args"], (self.app, [asset_id], AUTO_BACKFILL_RANGE))
        thread_class.return_value.start.assert_called_once_with()

    def test_import_script_main_delegates_to_asset_history_service(self):
        import scripts.import_asset_history as script

        result = type(
            "Result",
            (),
            {
                "ticker": "AAPL",
                "asset_id": uuid.uuid4(),
                "fetched_rows": 1,
                "upserted_rows": 1,
                "existing_rows_before": 0,
                "existing_rows_after": 1,
                "added_rows": 1,
                "error": None,
            },
        )()

        from unittest.mock import patch

        with (
            patch.object(
                sys,
                "argv",
                [
                    "import_asset_history.py",
                    "--ticker",
                    "AAPL",
                    "--start-date",
                    "2026-07-14",
                    "--end-date",
                    "2026-08-04",
                    "--dry-run",
                ],
            ),
            patch("scripts.import_asset_history.create_app", return_value=self.app),
            patch(
                "scripts.import_asset_history.import_recent_asset_history",
                return_value=[result],
            ) as importer,
            redirect_stdout(io.StringIO()),
        ):
            exit_code = script.main()

        self.assertEqual(exit_code, 0)
        importer.assert_called_once_with(
            start_date=datetime.date(2026, 7, 14),
            end_date=datetime.date(2026, 8, 4),
            tickers=["AAPL"],
            batch_size=500,
            dry_run=True,
        )


if __name__ == "__main__":
    unittest.main()
