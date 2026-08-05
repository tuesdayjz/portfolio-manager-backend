"""Market data helpers backed by Yahoo Finance."""

from decimal import Decimal, InvalidOperation


class YahooFinanceMarketData:
    """Fetch latest prices, FX rates and sectors from Yahoo Finance with per-request cache."""

    def __init__(self):
        self._prices = {}
        self._latest_closes = {}
        self._fx_rates = {}
        self._historical_fx_rates = {}
        self._asset_tradability = {}
        self._sectors = {}
        self._asset_meta = {}

    def latest_price(self, ticker):
        ticker = (ticker or "").strip()
        if not ticker:
            return None
        if ticker not in self._prices:
            self._prices[ticker] = self._fetch_latest_price(ticker)
        return self._prices[ticker]

    def latest_prices(self, tickers):
        """Fetch uncached ticker prices in one Yahoo Finance request."""

        normalized = list(
            dict.fromkeys(
                ticker.strip()
                for ticker in tickers
                if isinstance(ticker, str) and ticker.strip()
            )
        )
        missing = [ticker for ticker in normalized if ticker not in self._prices]
        if missing:
            self._prices.update(self._fetch_latest_prices(missing))
        return {ticker: self._prices.get(ticker) for ticker in normalized}

    def today_order_price(self, ticker):
        """Return live price when available, otherwise the latest available close."""

        price = self.latest_price(ticker)
        if price is not None:
            return price
        return self.latest_close(ticker)

    def latest_close(self, ticker):
        ticker = (ticker or "").strip()
        if not ticker:
            return None
        if ticker not in self._latest_closes:
            self._latest_closes[ticker] = self._fetch_latest_close(ticker)
        return self._latest_closes[ticker]

    def fx_to_usd(self, currency):
        currency = (currency or "USD").strip().upper()
        if currency == "USD":
            return Decimal("1")
        if currency not in self._fx_rates:
            self._fx_rates[currency] = self.latest_price(f"{currency}USD=X")
        return self._fx_rates[currency]

    def fx_to_usd_on(self, currency, date):
        currency = (currency or "USD").strip().upper()
        if currency == "USD":
            return Decimal("1")

        key = (currency, date)
        if key not in self._historical_fx_rates:
            self._historical_fx_rates[key] = self._fetch_historical_fx_rate(
                currency, date
            )
        return self._historical_fx_rates[key]

    def sector(self, ticker):
        ticker = (ticker or "").strip()
        if not ticker:
            return None
        if ticker not in self._sectors:
            self._sectors[ticker] = self._fetch_sector(ticker)
        return self._sectors[ticker]

    def asset_meta(self, ticker):
        """Return `{"quote_type": ..., "currency": ...}` for a new ticker, or None."""

        ticker = (ticker or "").strip()
        if not ticker:
            return None
        if ticker not in self._asset_meta:
            self._asset_meta[ticker] = self._fetch_asset_meta(ticker)
        return self._asset_meta[ticker]

    def asset_tradable_on(self, ticker, date):
        """Return whether Yahoo has a close for this ticker on `date`."""

        ticker = (ticker or "").strip()
        if not ticker:
            return False
        key = (ticker, date)
        if key not in self._asset_tradability:
            self._asset_tradability[key] = self._fetch_asset_tradable_on(ticker, date)
        return self._asset_tradability[key]

    def _fetch_asset_meta(self, ticker):
        try:
            import yfinance as yf

            info = yf.Ticker(ticker).info or {}
        except Exception:
            return None

        quote_type = info.get("quoteType")
        currency = info.get("currency")
        if not isinstance(quote_type, str) or not quote_type.strip():
            return None
        if not isinstance(currency, str) or not currency.strip():
            return None
        return {
            "quote_type": quote_type.strip().upper(),
            "currency": currency.strip().upper(),
        }

    def _fetch_latest_price(self, ticker):
        try:
            import yfinance as yf

            history = yf.Ticker(ticker).history(period="5d")
        except Exception:
            return None

        try:
            closes = history["Close"].dropna()
        except Exception:
            return None

        if closes.empty:
            return None
        return _decimal_or_none(closes.iloc[-1])

    def _fetch_latest_prices(self, tickers):
        prices = {ticker: None for ticker in tickers}
        try:
            import yfinance as yf

            history = yf.download(
                tickers=tickers,
                period="5d",
                group_by="column",
                auto_adjust=True,
                progress=False,
                threads=True,
                multi_level_index=True,
            )
            closes = history["Close"]
        except Exception:
            return prices

        # With multi_level_index=True, multiple symbols produce a DataFrame.
        # Keep support for a Series as well in case Yahoo/yfinance collapses a
        # single-symbol response.
        if hasattr(closes, "columns"):
            columns = {str(column).upper(): column for column in closes.columns}
            for ticker in tickers:
                column = columns.get(ticker.upper())
                if column is None:
                    continue
                values = closes[column].dropna()
                if not values.empty:
                    prices[ticker] = _decimal_or_none(values.iloc[-1])
        elif len(tickers) == 1:
            values = closes.dropna()
            if not values.empty:
                prices[tickers[0]] = _decimal_or_none(values.iloc[-1])

        return prices

    def _fetch_latest_close(self, ticker):
        try:
            import yfinance as yf

            history = yf.Ticker(ticker).history(period="10d", interval="1d")
        except Exception:
            return None

        try:
            closes = history["Close"].dropna()
        except Exception:
            return None

        if closes.empty:
            return None
        return _decimal_or_none(closes.iloc[-1])

    def _fetch_historical_fx_rate(self, currency, date):
        try:
            import datetime
            import yfinance as yf

            end = date + datetime.timedelta(days=1)
            start = date - datetime.timedelta(days=10)
            history = yf.Ticker(f"{currency}USD=X").history(
                start=start,
                end=end,
                interval="1d",
                auto_adjust=False,
            )
        except Exception:
            return None

        try:
            closes = history["Close"].dropna()
            closes = closes[closes.index.date <= date]
        except Exception:
            return None

        if closes.empty:
            return None
        return _decimal_or_none(closes.iloc[-1])

    def _fetch_asset_tradable_on(self, ticker, date):
        try:
            import datetime
            import yfinance as yf

            end = date + datetime.timedelta(days=1)
            history = yf.Ticker(ticker).history(
                start=date,
                end=end,
                interval="1d",
                auto_adjust=False,
            )
        except Exception:
            return False

        try:
            closes = history["Close"].dropna()
            closes = closes[closes.index.date == date]
        except Exception:
            return False

        return not closes.empty

    def _fetch_sector(self, ticker):
        try:
            import yfinance as yf

            info = yf.Ticker(ticker).info or {}
        except Exception:
            return None

        sector = info.get("sector")
        return sector.strip() if isinstance(sector, str) and sector.strip() else None


def _decimal_or_none(value):
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if price.is_nan() or price <= 0:
        return None
    return price
