"""Market data helpers backed by Yahoo Finance."""

from decimal import Decimal, InvalidOperation


class YahooFinanceMarketData:
    """Fetch latest prices, FX rates and sectors from Yahoo Finance with per-request cache."""

    def __init__(self):
        self._prices = {}
        self._fx_rates = {}
        self._historical_fx_rates = {}
        self._sectors = {}
        self._asset_meta = {}

    def latest_price(self, ticker):
        ticker = (ticker or "").strip()
        if not ticker:
            return None
        if ticker not in self._prices:
            self._prices[ticker] = self._fetch_latest_price(ticker)
        return self._prices[ticker]

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
