"""currency_rate_history import service and script tests."""

import datetime
import decimal
import io
import sys
import unittest
import uuid
from contextlib import redirect_stdout
from unittest.mock import patch

from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.models import Currency, CurrencyRateHistory
from app.services.currency_rate_history import (
    estimate_rate_rows,
    import_recent_currency_rates,
    rate_ticker,
    requested_currencies_not_matched,
    upsert_currency_rate_rows,
)


class CurrencyRateImportTest(unittest.TestCase):
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
            CREATE TABLE currency (
                id CHAR(32) PRIMARY KEY,
                currency TEXT NOT NULL,
                symbol TEXT
            )
            """,
            """
            CREATE TABLE currency_rate_history (
                id CHAR(32) PRIMARY KEY,
                currency_id CHAR(32) NOT NULL,
                rate_date DATE NOT NULL,
                close_price NUMERIC NOT NULL,
                UNIQUE (currency_id, rate_date)
            )
            """,
        ]
        for statement in statements:
            db.session.execute(text(statement))
        db.session.commit()

    def _drop_sqlite_schema(self):
        for table_name in ("currency_rate_history", "currency"):
            db.session.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        db.session.commit()

    def _currency(self, code, symbol=None):
        currency = Currency(id=uuid.uuid4(), currency=code, symbol=symbol)
        db.session.add(currency)
        db.session.commit()
        return currency

    def _fake_fetch(self, rate_date, close_price):
        def fetch(currency, *, start_date, end_date):
            return [
                {
                    "id": uuid.uuid4(),
                    "currency_id": currency.id,
                    "rate_date": rate_date,
                    "close_price": close_price,
                }
            ]

        return fetch

    def test_rate_ticker_uses_yahoo_fx_pair_format(self):
        self.assertEqual(rate_ticker("jpy"), "JPYUSD=X")
        self.assertEqual(rate_ticker(" eur "), "EURUSD=X")

    def test_upsert_currency_rate_rows_updates_duplicate_date(self):
        currency = self._currency("JPY")
        rate_date = datetime.date(2026, 8, 3)

        first_count = upsert_currency_rate_rows(
            [
                {
                    "id": uuid.uuid4(),
                    "currency_id": currency.id,
                    "rate_date": rate_date,
                    "close_price": decimal.Decimal("0.0068"),
                }
            ]
        )
        second_count = upsert_currency_rate_rows(
            [
                {
                    "id": uuid.uuid4(),
                    "currency_id": currency.id,
                    "rate_date": rate_date,
                    "close_price": decimal.Decimal("0.0071"),
                }
            ]
        )
        db.session.commit()

        rows = (
            db.session.query(CurrencyRateHistory)
            .filter_by(currency_id=currency.id)
            .all()
        )

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].close_price, decimal.Decimal("0.0071"))

    def test_dry_run_fetches_without_writing(self):
        self._currency("EUR")

        with patch(
            "app.services.currency_rate_history.fetch_daily_rate_rows",
            side_effect=self._fake_fetch(
                datetime.date(2026, 8, 3), decimal.Decimal("1.09")
            ),
        ):
            results = import_recent_currency_rates(
                start_date=datetime.date(2024, 8, 4),
                end_date=datetime.date(2026, 8, 4),
                dry_run=True,
            )

        count = db.session.execute(
            text("SELECT COUNT(*) FROM currency_rate_history")
        ).scalar()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].currency, "EUR")
        self.assertEqual(results[0].fetched_rows, 1)
        self.assertEqual(results[0].upserted_rows, 0)
        self.assertEqual(results[0].existing_rows_after, 0)
        self.assertEqual(count, 0)

    def test_import_reports_added_rows(self):
        self._currency("GBP")

        with patch(
            "app.services.currency_rate_history.fetch_daily_rate_rows",
            side_effect=self._fake_fetch(
                datetime.date(2026, 8, 3), decimal.Decimal("1.27")
            ),
        ):
            results = import_recent_currency_rates(
                start_date=datetime.date(2024, 8, 4),
                end_date=datetime.date(2026, 8, 4),
            )

        self.assertEqual(results[0].existing_rows_before, 0)
        self.assertEqual(results[0].existing_rows_after, 1)
        self.assertEqual(results[0].upserted_rows, 1)
        self.assertEqual(results[0].added_rows, 1)

    def test_base_currency_is_skipped(self):
        self._currency("USD", "$")
        self._currency("JPY", "¥")

        with patch(
            "app.services.currency_rate_history.fetch_daily_rate_rows",
            side_effect=self._fake_fetch(
                datetime.date(2026, 8, 3), decimal.Decimal("0.0068")
            ),
        ):
            results = import_recent_currency_rates(
                start_date=datetime.date(2024, 8, 4),
                end_date=datetime.date(2026, 8, 4),
                dry_run=True,
            )

        self.assertEqual([result.currency for result in results], ["JPY"])

    def test_currency_matching_is_case_insensitive(self):
        self._currency("JPY")
        self._currency("EUR")

        with patch(
            "app.services.currency_rate_history.fetch_daily_rate_rows",
            side_effect=self._fake_fetch(
                datetime.date(2026, 8, 3), decimal.Decimal("0.0068")
            ),
        ):
            results = import_recent_currency_rates(
                start_date=datetime.date(2024, 8, 4),
                end_date=datetime.date(2026, 8, 4),
                currencies=["jpy"],
                dry_run=True,
            )

        self.assertEqual([result.currency for result in results], ["JPY"])

    def test_import_prints_no_write_when_history_is_current(self):
        currency = self._currency("CHF")
        rate_date = datetime.date(2026, 8, 3)
        upsert_currency_rate_rows(
            [
                {
                    "id": uuid.uuid4(),
                    "currency_id": currency.id,
                    "rate_date": rate_date,
                    "close_price": decimal.Decimal("1.15"),
                }
            ]
        )
        db.session.commit()

        output = io.StringIO()
        with (
            patch(
                "app.services.currency_rate_history.fetch_daily_rate_rows",
                side_effect=self._fake_fetch(rate_date, decimal.Decimal("1.15")),
            ),
            redirect_stdout(output),
        ):
            results = import_recent_currency_rates(
                start_date=datetime.date(2024, 8, 4),
                end_date=datetime.date(2026, 8, 4),
            )

        self.assertIn("CHF: no write needed", output.getvalue())
        self.assertEqual(results[0].existing_rows_before, 1)
        self.assertEqual(results[0].existing_rows_after, 1)
        self.assertEqual(results[0].upserted_rows, 0)

    def test_import_rolls_back_and_records_error(self):
        self._currency("KRW")

        with patch(
            "app.services.currency_rate_history.fetch_daily_rate_rows",
            side_effect=RuntimeError("yahoo is down"),
        ):
            results = import_recent_currency_rates(
                start_date=datetime.date(2024, 8, 4),
                end_date=datetime.date(2026, 8, 4),
            )

        self.assertEqual(results[0].error, "yahoo is down")
        self.assertEqual(results[0].upserted_rows, 0)
        self.assertEqual(results[0].added_rows, 0)

    def test_requested_currencies_not_matched_ignores_base_currency(self):
        results = [
            type(
                "Result",
                (),
                {"currency": "JPY", "error": None},
            )()
        ]

        self.assertEqual(
            requested_currencies_not_matched(["jpy", "USD", "MXN"], results),
            ["MXN"],
        )

    def test_estimate_rate_rows_uses_weekdays(self):
        self.assertEqual(
            estimate_rate_rows(
                3,
                datetime.date(2026, 7, 14),
                datetime.date(2026, 8, 4),
            ),
            45,
        )

    def test_import_script_main_delegates_to_currency_rate_service(self):
        import scripts.import_currency_rate_history as script

        result = type(
            "Result",
            (),
            {
                "currency": "JPY",
                "currency_id": uuid.uuid4(),
                "fetched_rows": 1,
                "upserted_rows": 1,
                "existing_rows_before": 0,
                "existing_rows_after": 1,
                "added_rows": 1,
                "error": None,
            },
        )()

        with (
            patch.object(
                sys,
                "argv",
                [
                    "import_currency_rate_history.py",
                    "--currency",
                    "JPY",
                    "--start-date",
                    "2024-08-04",
                    "--end-date",
                    "2026-08-04",
                    "--dry-run",
                ],
            ),
            patch(
                "scripts.import_currency_rate_history.create_app",
                return_value=self.app,
            ),
            patch(
                "scripts.import_currency_rate_history.import_recent_currency_rates",
                return_value=[result],
            ) as importer,
            redirect_stdout(io.StringIO()),
        ):
            exit_code = script.main()

        self.assertEqual(exit_code, 0)
        importer.assert_called_once_with(
            start_date=datetime.date(2024, 8, 4),
            end_date=datetime.date(2026, 8, 4),
            currencies=["JPY"],
            batch_size=500,
            dry_run=True,
        )

    def test_script_default_range_covers_two_years(self):
        from app.services.asset_history import resolve_date_range
        from app.services.currency_rate_history import DEFAULT_RANGE

        start_date, end_date = resolve_date_range(
            range_value=DEFAULT_RANGE,
            start_date=None,
            end_date=datetime.date(2026, 8, 4),
        )

        self.assertEqual(DEFAULT_RANGE, "2y")
        # 2y は暦ではなく 365 * 2 日で解釈される（`parse_range_delta`）。
        self.assertEqual(start_date, datetime.date(2024, 8, 4))
        self.assertEqual(end_date, datetime.date(2026, 8, 4))


if __name__ == "__main__":
    unittest.main()
