import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd

from app.services.market_data import YahooFinanceMarketData


class YahooFinanceMarketDataTest(unittest.TestCase):
    def setUp(self):
        YahooFinanceMarketData.clear_cache()

    def tearDown(self):
        YahooFinanceMarketData.clear_cache()

    def test_latest_prices_fetches_uncached_symbols_in_one_request(self):
        columns = pd.MultiIndex.from_tuples(
            [("Close", "AAPL"), ("Close", "MSFT")]
        )
        history = pd.DataFrame(
            [[100, 200], [110, 210]],
            columns=columns,
        )
        market_data = YahooFinanceMarketData()

        with patch("yfinance.download", return_value=history) as download:
            prices = market_data.latest_prices(["AAPL", "MSFT", "AAPL"])
            cached_prices = market_data.latest_prices(["MSFT"])

        self.assertEqual(
            prices, {"AAPL": Decimal("110"), "MSFT": Decimal("210")}
        )
        self.assertEqual(cached_prices, {"MSFT": Decimal("210")})
        download.assert_called_once_with(
            tickers=["AAPL", "MSFT"],
            period="5d",
            group_by="column",
            auto_adjust=True,
            progress=False,
            threads=True,
            multi_level_index=True,
        )

    def test_latest_prices_caches_missing_symbols(self):
        columns = pd.MultiIndex.from_tuples([("Close", "AAPL")])
        history = pd.DataFrame([[100]], columns=columns)
        market_data = YahooFinanceMarketData()

        with patch("yfinance.download", return_value=history) as download:
            prices = market_data.latest_prices(["AAPL", "UNKNOWN"])
            missing = market_data.latest_price("UNKNOWN")

        self.assertEqual(prices["AAPL"], Decimal("100"))
        self.assertIsNone(prices["UNKNOWN"])
        self.assertIsNone(missing)
        download.assert_called_once()

    def test_latest_price_ttl_cache_hit_and_expiry(self):
        md1 = YahooFinanceMarketData(ttl_seconds=3600)
        md2 = YahooFinanceMarketData(ttl_seconds=3600)

        with patch("time.time", return_value=1000.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_latest_price", return_value=Decimal("150.0")
            ) as mock_fetch:
                price1 = md1.latest_price("AAPL")
                self.assertEqual(price1, Decimal("150.0"))
                self.assertEqual(mock_fetch.call_count, 1)

        # Within TTL (1800s later), md2 should hit the shared cache without re-fetching
        with patch("time.time", return_value=2800.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_latest_price", return_value=Decimal("160.0")
            ) as mock_fetch:
                price2 = md2.latest_price("AAPL")
                self.assertEqual(price2, Decimal("150.0"))
                mock_fetch.assert_not_called()

        # After TTL (3601s later), md2 should expire cache and re-fetch new price
        md3 = YahooFinanceMarketData(ttl_seconds=3600)
        with patch("time.time", return_value=4601.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_latest_price", return_value=Decimal("160.0")
            ) as mock_fetch:
                price3 = md3.latest_price("AAPL")
                self.assertEqual(price3, Decimal("160.0"))
                self.assertEqual(mock_fetch.call_count, 1)

    def test_latest_close_ttl_cache_hit_and_expiry(self):
        md1 = YahooFinanceMarketData(ttl_seconds=3600)
        md2 = YahooFinanceMarketData(ttl_seconds=3600)

        with patch("time.time", return_value=1000.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_latest_close", return_value=Decimal("148.0")
            ) as mock_fetch:
                close1 = md1.latest_close("AAPL")
                self.assertEqual(close1, Decimal("148.0"))
                self.assertEqual(mock_fetch.call_count, 1)

        # Within TTL, md2 hits shared cache
        with patch("time.time", return_value=2500.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_latest_close", return_value=Decimal("158.0")
            ) as mock_fetch:
                close2 = md2.latest_close("AAPL")
                self.assertEqual(close2, Decimal("148.0"))
                mock_fetch.assert_not_called()

        # Expired TTL re-fetches
        md3 = YahooFinanceMarketData(ttl_seconds=3600)
        with patch("time.time", return_value=4601.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_latest_close", return_value=Decimal("158.0")
            ) as mock_fetch:
                close3 = md3.latest_close("AAPL")
                self.assertEqual(close3, Decimal("158.0"))
                self.assertEqual(mock_fetch.call_count, 1)

    def test_fx_to_usd_ttl_cache_hit_and_expiry(self):
        md1 = YahooFinanceMarketData(ttl_seconds=3600)
        md2 = YahooFinanceMarketData(ttl_seconds=3600)

        # USD should always return 1 without calling latest_price
        self.assertEqual(md1.fx_to_usd("USD"), Decimal("1"))

        with patch("time.time", return_value=1000.0):
            with patch.object(
                YahooFinanceMarketData, "latest_price", return_value=Decimal("1.08")
            ) as mock_latest_price:
                rate1 = md1.fx_to_usd("EUR")
                self.assertEqual(rate1, Decimal("1.08"))
                mock_latest_price.assert_called_once_with("EURUSD=X")

        # Within TTL, md2 hits shared fx cache
        with patch("time.time", return_value=2000.0):
            with patch.object(
                YahooFinanceMarketData, "latest_price", return_value=Decimal("1.12")
            ) as mock_latest_price:
                rate2 = md2.fx_to_usd("EUR")
                self.assertEqual(rate2, Decimal("1.08"))
                mock_latest_price.assert_not_called()

        # After TTL expiry, md3 re-fetches
        md3 = YahooFinanceMarketData(ttl_seconds=3600)
        with patch("time.time", return_value=4601.0):
            with patch.object(
                YahooFinanceMarketData, "latest_price", return_value=Decimal("1.12")
            ) as mock_latest_price:
                rate3 = md3.fx_to_usd("EUR")
                self.assertEqual(rate3, Decimal("1.12"))
                mock_latest_price.assert_called_once_with("EURUSD=X")

    def test_fx_to_usd_on_historical_ttl_cache_hit_and_expiry(self):
        target_date = date(2026, 1, 15)
        md1 = YahooFinanceMarketData(ttl_seconds=3600)
        md2 = YahooFinanceMarketData(ttl_seconds=3600)

        # USD should return 1 immediately
        self.assertEqual(md1.fx_to_usd_on("USD", target_date), Decimal("1"))

        with patch("time.time", return_value=1000.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_historical_fx_rate", return_value=Decimal("1.05")
            ) as mock_fetch:
                rate1 = md1.fx_to_usd_on("EUR", target_date)
                self.assertEqual(rate1, Decimal("1.05"))
                mock_fetch.assert_called_once_with("EUR", target_date)

        # Within TTL, md2 hits shared cache
        with patch("time.time", return_value=2000.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_historical_fx_rate", return_value=Decimal("1.10")
            ) as mock_fetch:
                rate2 = md2.fx_to_usd_on("EUR", target_date)
                self.assertEqual(rate2, Decimal("1.05"))
                mock_fetch.assert_not_called()

        # Expired TTL re-fetches
        md3 = YahooFinanceMarketData(ttl_seconds=3600)
        with patch("time.time", return_value=4601.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_historical_fx_rate", return_value=Decimal("1.10")
            ) as mock_fetch:
                rate3 = md3.fx_to_usd_on("EUR", target_date)
                self.assertEqual(rate3, Decimal("1.10"))
                mock_fetch.assert_called_once_with("EUR", target_date)

    def test_sector_ttl_cache_hit_and_expiry(self):
        md1 = YahooFinanceMarketData(ttl_seconds=3600)
        md2 = YahooFinanceMarketData(ttl_seconds=3600)

        with patch("time.time", return_value=1000.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_sector", return_value="Technology"
            ) as mock_fetch:
                sec1 = md1.sector("AAPL")
                self.assertEqual(sec1, "Technology")
                mock_fetch.assert_called_once_with("AAPL")

        # Within TTL, md2 hits shared cache
        with patch("time.time", return_value=2000.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_sector", return_value="Consumer Electronics"
            ) as mock_fetch:
                sec2 = md2.sector("AAPL")
                self.assertEqual(sec2, "Technology")
                mock_fetch.assert_not_called()

        # Expired TTL re-fetches
        md3 = YahooFinanceMarketData(ttl_seconds=3600)
        with patch("time.time", return_value=4601.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_sector", return_value="Consumer Electronics"
            ) as mock_fetch:
                sec3 = md3.sector("AAPL")
                self.assertEqual(sec3, "Consumer Electronics")
                mock_fetch.assert_called_once_with("AAPL")

    def test_custom_ttl_seconds_setting(self):
        md1 = YahooFinanceMarketData(ttl_seconds=60)

        with patch("time.time", return_value=1000.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_latest_price", return_value=Decimal("100.0")
            ):
                md1.latest_price("GOOG")

        # md2 with 60s TTL checked at t=1030s (within 60s)
        md2 = YahooFinanceMarketData(ttl_seconds=60)
        with patch("time.time", return_value=1030.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_latest_price", return_value=Decimal("105.0")
            ) as mock_fetch:
                price = md2.latest_price("GOOG")
                self.assertEqual(price, Decimal("100.0"))
                mock_fetch.assert_not_called()

        # md3 with 60s TTL checked at t=1061s (expired past 60s)
        md3 = YahooFinanceMarketData(ttl_seconds=60)
        with patch("time.time", return_value=1061.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_latest_price", return_value=Decimal("105.0")
            ) as mock_fetch:
                price = md3.latest_price("GOOG")
                self.assertEqual(price, Decimal("105.0"))
                mock_fetch.assert_called_once()

    def test_clear_cache_clears_all_shared_caches(self):
        md = YahooFinanceMarketData()
        target_date = date(2026, 1, 15)

        with patch("time.time", return_value=1000.0):
            with patch.object(YahooFinanceMarketData, "_fetch_latest_price", return_value=Decimal("100.0")):
                md.latest_price("AAPL")
            with patch.object(YahooFinanceMarketData, "_fetch_latest_close", return_value=Decimal("98.0")):
                md.latest_close("AAPL")
            with patch.object(YahooFinanceMarketData, "latest_price", return_value=Decimal("1.08")):
                md.fx_to_usd("EUR")
            with patch.object(YahooFinanceMarketData, "_fetch_historical_fx_rate", return_value=Decimal("1.05")):
                md.fx_to_usd_on("EUR", target_date)
            with patch.object(YahooFinanceMarketData, "_fetch_sector", return_value="Technology"):
                md.sector("AAPL")

        # Verify shared cache populated
        self.assertIn("AAPL", YahooFinanceMarketData._shared_prices)
        self.assertIn("AAPL", YahooFinanceMarketData._shared_latest_closes)
        self.assertIn("EUR", YahooFinanceMarketData._shared_fx_rates)
        self.assertIn(("EUR", target_date), YahooFinanceMarketData._shared_historical_fx_rates)
        self.assertIn("AAPL", YahooFinanceMarketData._shared_sectors)

        # Clear cache
        YahooFinanceMarketData.clear_cache()

        # Verify shared cache cleared
        self.assertEqual(len(YahooFinanceMarketData._shared_prices), 0)
        self.assertEqual(len(YahooFinanceMarketData._shared_latest_closes), 0)
        self.assertEqual(len(YahooFinanceMarketData._shared_fx_rates), 0)
        self.assertEqual(len(YahooFinanceMarketData._shared_historical_fx_rates), 0)
        self.assertEqual(len(YahooFinanceMarketData._shared_sectors), 0)

        # Subsequent fetch on new instance re-fetches
        md_new = YahooFinanceMarketData()
        with patch("time.time", return_value=1000.0):
            with patch.object(
                YahooFinanceMarketData, "_fetch_latest_price", return_value=Decimal("200.0")
            ) as mock_fetch:
                price = md_new.latest_price("AAPL")
                self.assertEqual(price, Decimal("200.0"))
                mock_fetch.assert_called_once()

    def test_instance_cache_hit(self):
        md = YahooFinanceMarketData()
        with patch.object(
            YahooFinanceMarketData, "_fetch_latest_price", return_value=Decimal("100.0")
        ) as mock_fetch:
            price1 = md.latest_price("TSLA")
            price2 = md.latest_price("TSLA")

            self.assertEqual(price1, Decimal("100.0"))
            self.assertEqual(price2, Decimal("100.0"))
            # Internal fetch called only once because second call hit instance cache self._prices
            mock_fetch.assert_called_once()


if __name__ == "__main__":
    unittest.main()

