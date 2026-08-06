"""Yahoo Finance market data batching tests."""

import unittest
from decimal import Decimal
from unittest.mock import patch

import pandas as pd

from app.services.market_data import YahooFinanceMarketData


class YahooFinanceMarketDataTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
