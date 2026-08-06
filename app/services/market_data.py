import threading
import time
from decimal import Decimal, InvalidOperation


class YahooFinanceMarketData:
    """Fetch latest prices, FX rates and sectors from Yahoo Finance with server-side TTL cache."""

    DEFAULT_TTL_SECONDS = 3600  # Default 1h cache TTL
    _cache_lock = threading.Lock()
    _shared_prices = {}
    _shared_latest_closes = {}
    _shared_fx_rates = {}
    _shared_sectors = {}
    _shared_historical_fx_rates = {}
    _shared_asset_tradability = {}
    _shared_asset_meta = {}

    def __init__(self, ttl_seconds=DEFAULT_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        self._prices = {}
        self._latest_closes = {}
        self._fx_rates = {}
        self._historical_fx_rates = {}
        self._asset_tradability = {}
        self._sectors = {}
        self._asset_meta = {}

    @classmethod
    def clear_cache(cls):
        """Clear all server-side cached market data."""
        with cls._cache_lock:
            cls._shared_prices.clear()
            cls._shared_latest_closes.clear()
            cls._shared_fx_rates.clear()
            cls._shared_sectors.clear()
            cls._shared_historical_fx_rates.clear()
            cls._shared_asset_tradability.clear()
            cls._shared_asset_meta.clear()

    def latest_price(self, ticker):
        ticker = (ticker or "").strip()
        if not ticker:
            return None

        if ticker in self._prices:
            return self._prices[ticker]

        now = time.time()
        with self._cache_lock:
            if ticker in self._shared_prices:
                val, ts = self._shared_prices[ticker]
                if now - ts < self.ttl_seconds:
                    self._prices[ticker] = val
                    return val

        price = self._fetch_latest_price(ticker)

        with self._cache_lock:
            if price is not None:
                self._shared_prices[ticker] = (price, now)
            self._prices[ticker] = price

        return price

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

        if ticker in self._latest_closes:
            return self._latest_closes[ticker]

        now = time.time()
        with self._cache_lock:
            if ticker in self._shared_latest_closes:
                val, ts = self._shared_latest_closes[ticker]
                if now - ts < self.ttl_seconds:
                    self._latest_closes[ticker] = val
                    return val

        price = self._fetch_latest_close(ticker)

        with self._cache_lock:
            if price is not None:
                self._shared_latest_closes[ticker] = (price, now)
            self._latest_closes[ticker] = price

        return price

    def fx_to_usd(self, currency):
        currency = (currency or "USD").strip().upper()
        if currency == "USD":
            return Decimal("1")

        if currency in self._fx_rates:
            return self._fx_rates[currency]

        now = time.time()
        with self._cache_lock:
            if currency in self._shared_fx_rates:
                val, ts = self._shared_fx_rates[currency]
                if now - ts < self.ttl_seconds:
                    self._fx_rates[currency] = val
                    return val

        rate = self.latest_price(f"{currency}USD=X")

        with self._cache_lock:
            if rate is not None:
                self._shared_fx_rates[currency] = (rate, now)
            self._fx_rates[currency] = rate

        return rate

    def fx_to_usd_on(self, currency, date):
        currency = (currency or "USD").strip().upper()
        if currency == "USD":
            return Decimal("1")

        key = (currency, date)
        if key in self._historical_fx_rates:
            return self._historical_fx_rates[key]

        now = time.time()
        with self._cache_lock:
            if key in self._shared_historical_fx_rates:
                val, ts = self._shared_historical_fx_rates[key]
                if now - ts < self.ttl_seconds:
                    self._historical_fx_rates[key] = val
                    return val

        rate = self._fetch_historical_fx_rate(currency, date)

        with self._cache_lock:
            if rate is not None:
                self._shared_historical_fx_rates[key] = (rate, now)
            self._historical_fx_rates[key] = rate

        return rate

    def sector(self, ticker):
        ticker = (ticker or "").strip()
        if not ticker:
            return None

        if ticker in self._sectors:
            return self._sectors[ticker]

        now = time.time()
        with self._cache_lock:
            if ticker in self._shared_sectors:
                val, ts = self._shared_sectors[ticker]
                if now - ts < self.ttl_seconds:
                    self._sectors[ticker] = val
                    return val

        sec = self._fetch_sector(ticker)

        with self._cache_lock:
            if sec is not None:
                self._shared_sectors[ticker] = (sec, now)
            self._sectors[ticker] = sec

        return sec

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
