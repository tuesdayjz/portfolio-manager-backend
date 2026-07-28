"""Swagger/mock API design for the portfolio manager backend."""

import datetime as dt
from typing import Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, Field


app = FastAPI(
    title="Portfolio Manager API spec",
    version="1.0.0",
    openapi_tags=[
        {"name": "accounts", "description": "口座関連（口座、保有残高、評価額、資産配分）"},
        {"name": "assets", "description": "資産関連（資産情報、Yahoo Finance価格）"},
        {"name": "transactions", "description": "取引履歴関連"},
    ],
)


class AccountSummary(BaseModel):
    portfolio_id: int = Field(..., examples=[1])
    user_id: int = Field(..., examples=[101])
    currency: str = Field(..., examples=["JPY"])
    cash_balance: float = Field(..., ge=0, examples=[1250000])
    total_purchase_value: float = Field(..., ge=0, examples=[3901250])
    total_market_value: float = Field(..., ge=0, examples=[4220000])
    total_asset_value: float = Field(..., ge=0, examples=[5470000])
    unrealized_gain_loss: float = Field(..., examples=[318750])


class AccountCreate(BaseModel):
    user_id: int = Field(..., ge=1, examples=[101])
    currency: str = Field(..., examples=["JPY"])
    cash_balance: float = Field(0, ge=0, examples=[1000000])


class Account(AccountCreate):
    portfolio_id: int = Field(..., ge=1, examples=[1])


class Asset(BaseModel):
    asset_id: int = Field(..., ge=1, description="Asset ID", examples=[1])
    user_id: int = Field(..., ge=1, examples=[101])
    portfolio_id: int = Field(..., ge=1, examples=[1])
    type: str = Field(..., max_length=20, description="Asset type", examples=["stock"])
    name: str = Field(..., description="Asset name", examples=["Toyota Motor Corp."])
    symbol: str = Field(..., description="Yahoo Finance symbol", examples=["7203.T"])
    quantity: float = Field(
        ...,
        ge=0,
        description="how many units of the asset the user has",
        examples=[8.5],
    )
    purchase_price: float = Field(..., ge=0, description="取得価額", examples=[1095.80])
    current_price: float = Field(
        ...,
        ge=0,
        description="Mock Yahoo Finance market price; not stored in Supabase holdings",
        examples=[2980.50],
    )
    currency: str = Field(..., description="通貨", examples=["JPY"])


class AssetInfo(BaseModel):
    asset_id: int = Field(..., ge=1, description="Asset ID", examples=[1])
    type: str = Field(..., max_length=20, description="Asset type", examples=["stock"])
    name: str = Field(..., description="Asset name", examples=["Toyota Motor Corp."])
    symbol: str = Field(..., description="Yahoo Finance symbol", examples=["7203.T"])
    currency: str = Field(..., description="通貨", examples=["JPY"])


class Holding(BaseModel):
    user_id: int = Field(..., ge=1, examples=[101])
    portfolio_id: int = Field(..., ge=1, examples=[1])
    asset_id: int = Field(..., ge=1, description="Asset ID", examples=[1])
    symbol: str = Field(..., description="Yahoo Finance symbol", examples=["7203.T"])
    name: str = Field(..., description="Asset name", examples=["Toyota Motor Corp."])
    quantity: float = Field(..., ge=0, description="Current holding quantity", examples=[8.5])
    average_purchase_price: float = Field(..., ge=0, description="平均取得単価", examples=[1095.80])
    current_price: float = Field(
        ...,
        ge=0,
        description="Yahoo Finance market price; not stored in Supabase holdings",
        examples=[2980.50],
    )
    currency: str = Field(..., description="通貨", examples=["JPY"])


class TransactionCreate(BaseModel):
    user_id: int = Field(..., ge=1, examples=[101])
    portfolio_id: int = Field(..., ge=1, examples=[1])
    asset_id: int = Field(..., ge=1, examples=[1])
    transaction_type: Literal["buy", "sell"] = Field(..., examples=["buy"])
    quantity: float = Field(..., gt=0, examples=[5.4])
    price: float = Field(..., ge=0, examples=[2980.5])
    fees: float = Field(0, ge=0, examples=[0.0])
    date: dt.datetime = Field(..., examples=["2026-05-26T18:00:00"])


class Transaction(TransactionCreate):
    transaction_id: int = Field(..., ge=1, examples=[1])


class PriceHistoryItem(BaseModel):
    date: dt.date = Field(..., examples=["2026-07-28"])
    open: float = Field(..., ge=0, examples=[2950.0])
    high: float = Field(..., ge=0, examples=[3000.0])
    low: float = Field(..., ge=0, examples=[2920.0])
    close: float = Field(..., ge=0, examples=[2980.5])
    volume: int = Field(..., ge=0, examples=[1200000])


class AllocationItem(BaseModel):
    name: str = Field(..., examples=["stock"])
    value: float = Field(..., ge=0, examples=[4220000])
    weight: float = Field(..., ge=0, le=1, examples=[0.72])


class PortfolioAllocation(BaseModel):
    by_asset_type: List[AllocationItem]
    by_currency: List[AllocationItem]
    by_asset: List[AllocationItem]


accounts = {
    1: {
        "portfolio_id": 1,
        "user_id": 101,
        "currency": "JPY",
        "cash_balance": 1250000.0,
    }
}

assets: Dict[int, Asset] = {
    1: Asset(
        asset_id=1,
        user_id=101,
        portfolio_id=1,
        type="stock",
        name="Toyota Motor Corp.",
        symbol="7203.T",
        quantity=8.5,
        purchase_price=1095.80,
        current_price=2980.50,
        currency="JPY",
    ),
    2: Asset(
        asset_id=2,
        user_id=101,
        portfolio_id=1,
        type="stock",
        name="Apple Inc.",
        symbol="AAPL",
        quantity=3.0,
        purchase_price=28500.00,
        current_price=33200.00,
        currency="JPY",
    ),
}

transactions: List[Transaction] = [
    Transaction(
        transaction_id=1,
        user_id=101,
        portfolio_id=1,
        asset_id=1,
        transaction_type="buy",
        quantity=5.4,
        price=1095.80,
        fees=0.0,
        date="2026-05-26T18:00:00",
    ),
    Transaction(
        transaction_id=2,
        user_id=101,
        portfolio_id=1,
        asset_id=1,
        transaction_type="sell",
        quantity=1.0,
        price=2980.50,
        fees=0.0,
        date="2026-06-10T09:30:00",
    ),
]


def get_asset_or_404(asset_id: int) -> Asset:
    asset = assets.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="The specified asset does not exist")
    return asset


def portfolio_assets(portfolio_id: Optional[int] = None) -> List[Asset]:
    filtered_assets = list(assets.values())
    if portfolio_id is not None:
        filtered_assets = [asset for asset in filtered_assets if asset.portfolio_id == portfolio_id]
    return filtered_assets


def calculate_values(filtered_assets: List[Asset]) -> Dict[str, float]:
    total_purchase_value = sum(
        asset.quantity * asset.purchase_price for asset in filtered_assets
    )
    total_market_value = sum(asset.quantity * asset.current_price for asset in filtered_assets)
    return {
        "total_purchase_value": round(total_purchase_value, 2),
        "total_market_value": round(total_market_value, 2),
        "unrealized_gain_loss": round(total_market_value - total_purchase_value, 2),
    }


def make_allocation(items: Dict[str, float], total: float) -> List[AllocationItem]:
    return [
        AllocationItem(
            name=name,
            value=round(value, 2),
            weight=round(value / total, 4) if total else 0,
        )
        for name, value in items.items()
    ]


@app.get(
    "/accounts/{portfolio_id}/summary",
    response_model=AccountSummary,
    responses={404: {"description": "The specified account does not exist"}},
    tags=["accounts"],
    summary="API to fetch account summary",
    description="口座サマリーを取得する",
)
def fetch_account_summary(
    portfolio_id: int = Path(..., ge=1, description="Portfolio ID", examples=[1]),
):
    account = accounts.get(portfolio_id)
    if account is None:
        raise HTTPException(status_code=404, detail="The specified account does not exist")

    values = calculate_values(portfolio_assets(portfolio_id=portfolio_id))
    return AccountSummary(
        **account,
        **values,
        total_asset_value=round(account["cash_balance"] + values["total_market_value"], 2),
    )


@app.post(
    "/accounts/",
    response_model=Account,
    status_code=201,
    tags=["accounts"],
    summary="API to create account",
    description="口座を作成する",
)
def create_account(request: AccountCreate):
    portfolio_id = max(accounts.keys(), default=0) + 1
    account = {
        "portfolio_id": portfolio_id,
        "user_id": request.user_id,
        "currency": request.currency,
        "cash_balance": request.cash_balance,
    }
    accounts[portfolio_id] = account
    return account


@app.get(
    "/assets/{asset_id}/",
    response_model=AssetInfo,
    responses={404: {"description": "The specified asset does not exist"}},
    tags=["assets"],
    summary="API to fetch asset",
    description="資産マスタ情報を取得する。保有数量や取得価額はportfolio holdingsで取得する。",
)
def fetch_asset(
    asset_id: int = Path(..., ge=1, description="Asset ID", examples=[1]),
):
    asset = get_asset_or_404(asset_id)
    return AssetInfo(
        asset_id=asset.asset_id,
        type=asset.type,
        name=asset.name,
        symbol=asset.symbol,
        currency=asset.currency,
    )


@app.get(
    "/portfolio/holdings",
    response_model=List[Holding],
    tags=["accounts"],
    summary="API to fetch holdings",
    description=(
        "保有残高一覧を取得する。1つのポートフォリオに含まれる複数の資産を返す。"
        "current_priceはYahoo Finance由来の市場価格で、Supabase holdingsには保存しない。"
    ),
)
def fetch_holdings(
    user_id: int = Query(..., ge=1, description="User ID", examples=[101]),
    portfolio_id: int = Query(..., ge=1, description="Portfolio ID", examples=[1]),
    asset_id: Optional[int] = Query(default=None),
):
    filtered_assets = list(assets.values())
    filtered_assets = [asset for asset in filtered_assets if asset.user_id == user_id]
    filtered_assets = [asset for asset in filtered_assets if asset.portfolio_id == portfolio_id]
    if asset_id is not None:
        filtered_assets = [asset for asset in filtered_assets if asset.asset_id == asset_id]

    return [
        Holding(
            user_id=asset.user_id,
            portfolio_id=asset.portfolio_id,
            asset_id=asset.asset_id,
            symbol=asset.symbol,
            name=asset.name,
            quantity=asset.quantity,
            average_purchase_price=asset.purchase_price,
            current_price=asset.current_price,
            currency=asset.currency,
        )
        for asset in filtered_assets
    ]


@app.get(
    "/transactions/",
    response_model=List[Transaction],
    tags=["transactions"],
    summary="API to fetch transactions",
    description="取引履歴を取得する",
)
def fetch_transactions(
    user_id: int = Query(..., ge=1, description="User ID", examples=[101]),
    portfolio_id: int = Query(..., ge=1, description="Portfolio ID", examples=[1]),
    asset_id: Optional[int] = Query(default=None),
    start_date: Optional[dt.date] = Query(default=None),
    end_date: Optional[dt.date] = Query(default=None),
):
    filtered_transactions = transactions
    filtered_transactions = [
        transaction
        for transaction in filtered_transactions
        if transaction.user_id == user_id
    ]
    filtered_transactions = [
        transaction
        for transaction in filtered_transactions
        if transaction.portfolio_id == portfolio_id
    ]
    if asset_id is not None:
        filtered_transactions = [
            transaction
            for transaction in filtered_transactions
            if transaction.asset_id == asset_id
        ]
    if start_date is not None:
        filtered_transactions = [
            transaction
            for transaction in filtered_transactions
            if transaction.date.date() >= start_date
        ]
    if end_date is not None:
        filtered_transactions = [
            transaction
            for transaction in filtered_transactions
            if transaction.date.date() <= end_date
        ]
    return filtered_transactions


@app.post(
    "/transactions/",
    response_model=Transaction,
    status_code=201,
    responses={400: {"description": "Cannot sell more than current holding"}},
    tags=["transactions"],
    summary="API to record transaction",
    description="取引を登録し、保有残高（holdings）を更新する",
)
def record_transaction(request: TransactionCreate):
    asset = get_asset_or_404(request.asset_id)
    if request.transaction_type == "sell" and request.quantity > asset.quantity:
        raise HTTPException(status_code=400, detail="Cannot sell more than current holding")

    if request.transaction_type == "buy":
        new_quantity = asset.quantity + request.quantity
        new_purchase_value = (
            asset.quantity * asset.purchase_price
            + request.quantity * request.price
            + request.fees
        )
        asset.quantity = round(new_quantity, 6)
        asset.purchase_price = round(new_purchase_value / new_quantity, 2)
    else:
        asset.quantity = round(asset.quantity - request.quantity, 6)

    transaction = Transaction(
        transaction_id=len(transactions) + 1,
        **request.model_dump(),
    )
    transactions.append(transaction)
    return transaction


@app.get(
    "/assets/{asset_id}/price-history",
    response_model=List[PriceHistoryItem],
    responses={404: {"description": "The specified asset does not exist"}},
    tags=["assets"],
    summary="API to fetch historical market prices",
    description="過去の市場価格を取得する。価格データはYahoo Financeから取得する想定。",
)
def fetch_price_history(
    asset_id: int = Path(..., ge=1, description="Asset ID", examples=[1]),
    start_date: Optional[dt.date] = Query(default=None, examples=["2026-01-01"]),
    end_date: Optional[dt.date] = Query(default=None, examples=["2026-07-28"]),
    interval: str = Query(default="1d", examples=["1d"]),
):
    get_asset_or_404(asset_id)
    return [
        PriceHistoryItem(
            date="2026-07-26",
            open=2920.0,
            high=2965.0,
            low=2900.0,
            close=2950.0,
            volume=980000,
        ),
        PriceHistoryItem(
            date="2026-07-27",
            open=2950.0,
            high=2995.0,
            low=2935.0,
            close=2972.5,
            volume=1110000,
        ),
        PriceHistoryItem(
            date="2026-07-28",
            open=2950.0,
            high=3000.0,
            low=2920.0,
            close=2980.5,
            volume=1200000,
        ),
    ]


@app.get(
    "/portfolio/allocation",
    response_model=PortfolioAllocation,
    tags=["accounts"],
    summary="API to fetch portfolio allocation",
    description="資産配分を取得する。評価額計算の市場価格はYahoo Financeから取得する想定。",
)
def fetch_portfolio_allocation(
    portfolio_id: int = Query(..., ge=1, description="Portfolio ID", examples=[1]),
):
    filtered_assets = portfolio_assets(portfolio_id=portfolio_id)
    market_values = {
        asset.asset_id: asset.quantity * asset.current_price for asset in filtered_assets
    }
    total_market_value = sum(market_values.values())

    by_asset_type: Dict[str, float] = {}
    by_currency: Dict[str, float] = {}
    by_asset: Dict[str, float] = {}
    for asset in filtered_assets:
        value = market_values[asset.asset_id]
        by_asset_type[asset.type] = by_asset_type.get(asset.type, 0) + value
        by_currency[asset.currency] = by_currency.get(asset.currency, 0) + value
        by_asset[asset.name] = value

    return PortfolioAllocation(
        by_asset_type=make_allocation(by_asset_type, total_market_value),
        by_currency=make_allocation(by_currency, total_market_value),
        by_asset=make_allocation(by_asset, total_market_value),
    )


@app.get("/", include_in_schema=False)
def home():
    return {
        "message": "Portfolio Manager API is running",
        "swagger_ui": "/docs",
        "openapi_json": "/openapi.json",
    }
