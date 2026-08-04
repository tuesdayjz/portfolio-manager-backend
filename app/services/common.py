"""Portfolio service で共有する小さな部品。

`portfolio.py` と `performance.py` の両方が使う定数・認証ユーザー解決・
Decimal 変換だけを置く。個々の endpoint 固有の計算はそれぞれのモジュールに残す。
"""

import decimal
import uuid

from flask import g
from flask_smorest import abort
from sqlalchemy import select

from app.extensions import db
from app.models import Portfolio

#: レスポンスの基準通貨。現行仕様では USD 固定。
SUMMARY_CURRENCY = "USD"

PORTFOLIO_NOT_FOUND_MESSAGE = "The specified portfolio does not exist"


def current_user_id():
    """Return the authenticated user id set by `require_auth()`."""

    try:
        return uuid.UUID(str(g.current_user_id))
    except (AttributeError, TypeError, ValueError):
        abort(401, message="Missing authenticated user context.")


def current_portfolio():
    """Return the current user's only portfolio, or abort with 404."""

    portfolio = db.session.execute(
        select(Portfolio).where(Portfolio.user_id == current_user_id())
    ).scalar_one_or_none()
    if not portfolio:
        abort(404, message=PORTFOLIO_NOT_FOUND_MESSAGE)
    return portfolio


def decimal_or_zero(value):
    if value is None:
        return decimal.Decimal("0")
    return decimal.Decimal(str(value))


def decimal_or_none(value):
    """Return a positive Decimal, or None when the value is unusable as a price."""

    if value is None:
        return None
    try:
        result = decimal.Decimal(str(value))
    except (decimal.InvalidOperation, TypeError, ValueError):
        return None
    if result.is_nan() or result <= 0:
        return None
    return result


def asset_currency(asset):
    return (
        getattr(getattr(asset, "currency", None), "currency", None) or SUMMARY_CURRENCY
    ).upper()


def percent_of(amount, base):
    if base == 0:
        return decimal.Decimal("0")
    return amount / base * 100
