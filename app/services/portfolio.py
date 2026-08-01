"""Portfolio business logic backed by SQLAlchemy."""

import datetime
import decimal
import uuid

from flask import g
from flask_smorest import abort
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

from app.extensions import db
from app.models import AssetMaster, AssetType, Currency, Holdings, Portfolio, Users

PORTFOLIO_CREATED_MESSAGE = "Portfolio created"
PORTFOLIO_ALREADY_EXISTS_MESSAGE = "Portfolio already exists for this user."


def create_portfolio(payload):
    """Create the current user's only portfolio and optional initial cash holding."""

    user_id = _current_user_id()
    currency_code = payload.get("currency", "USD").upper()
    cash_balance = decimal.Decimal(str(payload.get("cash_balance", 0)))

    try:
        _ensure_user(user_id)
        # 現行仕様では 1 user = 1 portfolio。作成前に明示的に確認する。
        existing_portfolio = db.session.execute(
            select(Portfolio).where(Portfolio.user_id == user_id)
        ).scalar_one_or_none()
        if existing_portfolio:
            abort(409, message=PORTFOLIO_ALREADY_EXISTS_MESSAGE)

        now = datetime.datetime.now(datetime.timezone.utc)
        portfolio = Portfolio(
            id=uuid.uuid4(),
            user_id=user_id,
            name=payload["name"],
            created_at=now,
            updated_at=now,
        )
        db.session.add(portfolio)
        db.session.flush()

        if cash_balance > 0:
            cash_asset = _cash_asset(currency_code)
            # cash_balance は portfolio table ではなく cash holding に quantity=1 で保存する。
            db.session.add(
                Holdings(
                    id=uuid.uuid4(),
                    portfolio_id=portfolio.id,
                    asset_id=cash_asset.id,
                    quantity=decimal.Decimal("1"),
                    average_cost=cash_balance,
                    updated_at=now,
                )
            )

        db.session.commit()
    except HTTPException:
        db.session.rollback()
        raise
    except IntegrityError:
        db.session.rollback()
        abort(409, message=PORTFOLIO_ALREADY_EXISTS_MESSAGE)
    except SQLAlchemyError:
        db.session.rollback()
        abort(500, message="Could not create portfolio.")

    return {"message": PORTFOLIO_CREATED_MESSAGE}


def _current_user_id():
    try:
        return uuid.UUID(str(g.current_user_id))
    except (AttributeError, TypeError, ValueError):
        abort(401, message="Missing authenticated user context.")


def _ensure_user(user_id):
    user = db.session.get(Users, user_id)
    if user:
        return user

    email = getattr(g, "current_user_email", None)
    if not email:
        abort(400, message="Authenticated user email is required.")

    now = datetime.datetime.now(datetime.timezone.utc)
    user = Users(id=user_id, email=email, created_at=now, updated_at=now)
    db.session.add(user)
    db.session.flush()
    return user


def _cash_asset(currency_code):
    currency = db.session.execute(
        select(Currency).where(Currency.currency == currency_code)
    ).scalar_one_or_none()
    if not currency:
        abort(400, message=f"Currency {currency_code} does not exist.")

    cash_type = db.session.execute(
        select(AssetType).where(AssetType.asset_type == "cash")
    ).scalar_one_or_none()
    if not cash_type:
        abort(400, message="Cash asset type does not exist.")

    ticker = f"CASH-{currency_code}"
    asset = db.session.execute(
        select(AssetMaster).where(AssetMaster.ticker == ticker)
    ).scalar_one_or_none()
    if asset:
        return asset

    asset = AssetMaster(
        id=uuid.uuid4(),
        ticker=ticker,
        name=f"Cash {currency_code}",
        asset_type_id=cash_type.id,
        currency_id=currency.id,
    )
    db.session.add(asset)
    db.session.flush()
    return asset
