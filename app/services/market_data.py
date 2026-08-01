"""Market data helpers backed by Yahoo Finance."""

from decimal import Decimal, InvalidOperation


class YahooFinanceMarketData:
    """Fetch latest prices and FX rates from Yahoo Finance with per-request cache."""

    def __init__(self):
        self._prices = {}
        self._fx_rates = {}

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


def _decimal_or_none(value):
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if price.is_nan() or price <= 0:
        return None
    return price
