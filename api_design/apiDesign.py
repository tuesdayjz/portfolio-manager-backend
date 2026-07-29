"""Swagger/mock API design for the portfolio manager backend."""

import datetime as dt
from typing import Dict, List, Literal, Optional

from fastapi import FastAPI, Header, HTTPException, Path, Query
from pydantic import BaseModel, Field


app = FastAPI(
    title="Portfolio Manager API spec",
    version="1.0.0",
    openapi_tags=[
        {"name": "auth", "description": "認証関連"},
        {"name": "portfolio", "description": "ポートフォリオ関連"},
        {"name": "assets", "description": "資産関連（資産情報、Yahoo Finance価格）"},
        {"name": "transactions", "description": "取引履歴関連"},
    ],
)


class SignupRequest(BaseModel):
    email: str = Field(..., examples=["user@example.com"])
    password: str = Field(..., min_length=8, examples=["password123"])
    portfolio_name: str = Field(..., examples=["Main Portfolio"])
    base_currency: str = Field(..., examples=["JPY"])


class LoginRequest(BaseModel):
    email: str = Field(..., examples=["user@example.com"])
    password: str = Field(..., examples=["password123"])


class AuthUser(BaseModel):
    user_id: int = Field(..., examples=[101])
    email: str = Field(..., examples=["user@example.com"])


class AuthPortfolio(BaseModel):
    portfolio_id: int = Field(..., examples=[1])
    name: str = Field(..., examples=["Main Portfolio"])
    base_currency: str = Field(..., examples=["JPY"])


class AuthResponse(BaseModel):
    access_token: str = Field(..., examples=["mock-access-token-101"])
    token_type: str = Field(..., examples=["bearer"])
    user: AuthUser
    portfolio: AuthPortfolio


class LogoutResponse(BaseModel):
    message: str = Field(..., examples=["Logged out"])


class PortfolioSummary(BaseModel):
    portfolio_id: int = Field(..., examples=[1])
    user_id: int = Field(..., examples=[101])
    currency: str = Field(..., examples=["JPY"])
    cash_balance: float = Field(
        ...,
        ge=0,
        description="Mock-only cash value; current Supabase schema has no cash balance column",
        examples=[1250000],
    )
    total_purchase_value: float = Field(..., ge=0, examples=[3901250])
    total_market_value: float = Field(..., ge=0, examples=[4220000])
    total_asset_value: float = Field(..., ge=0, examples=[5470000])
    unrealized_gain_loss: float = Field(..., examples=[318750])


class PortfolioCreate(BaseModel):
    user_id: int = Field(..., ge=1, examples=[101])
    name: str = Field(..., examples=["Main Portfolio"])
    currency: str = Field(..., examples=["JPY"])
    cash_balance: float = Field(
        0,
        ge=0,
        description="Mock-only cash value; current Supabase schema has no cash balance column",
        examples=[1000000],
    )


class Portfolio(PortfolioCreate):
    portfolio_id: int = Field(..., ge=1, examples=[1])


class Asset(BaseModel):
    asset_id: int = Field(..., ge=1, description="Asset ID", examples=[1])
    user_id: int = Field(..., ge=1, examples=[101])
    portfolio_id: int = Field(..., ge=1, examples=[1])
    type: str = Field(..., max_length=20, description="Asset type", examples=["stock"])
    name: str = Field(..., description="Asset name", examples=["Toyota Motor Corp."])
    ticker: str = Field(
        ...,
        description="Yahoo Finance ticker; maps to Supabase asset_master.ticker",
        examples=["7203.T"],
    )
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
    ticker: str = Field(
        ...,
        description="Yahoo Finance ticker; maps to Supabase asset_master.ticker",
        examples=["7203.T"],
    )
    currency: str = Field(..., description="通貨", examples=["JPY"])


class Holding(BaseModel):
    user_id: int = Field(..., ge=1, examples=[101])
    portfolio_id: int = Field(..., ge=1, examples=[1])
    asset_id: int = Field(..., ge=1, description="Asset ID", examples=[1])
    ticker: str = Field(
        ...,
        description="Yahoo Finance ticker; maps to Supabase asset_master.ticker",
        examples=["7203.T"],
    )
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


class TransactionItem(BaseModel):
    asset_id: int = Field(..., ge=1, examples=[1])
    transaction_type: Literal["buy", "sell"] = Field(..., examples=["buy"])
    quantity: float = Field(..., gt=0, examples=[5.4])
    price: float = Field(..., ge=0, examples=[2980.5])
    fees: float = Field(0, ge=0, examples=[0.0])
    date: dt.datetime = Field(..., examples=["2026-05-26T18:00:00"])


class TransactionCreate(TransactionItem):
    user_id: Optional[int] = Field(
        default=None,
        ge=1,
        description="Mock fallback user ID. Future production should use Authorization bearer token.",
        examples=[101],
    )


class Transaction(TransactionCreate):
    user_id: int = Field(..., ge=1, examples=[101])
    portfolio_id: int = Field(..., ge=1, examples=[1])
    transaction_id: int = Field(..., ge=1, examples=[1])


class TransactionBatchCreate(BaseModel):
    user_id: Optional[int] = Field(
        default=None,
        ge=1,
        description="Mock fallback user ID. Future production should use Authorization bearer token.",
        examples=[101],
    )
    transactions: List[TransactionItem] = Field(..., min_length=1)


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


class PerformanceGraphPoint(BaseModel):
    date: dt.date = Field(..., examples=["2026-07-28"])
    total_purchase_value: float = Field(..., ge=0, examples=[3901250])
    total_market_value: float = Field(..., ge=0, examples=[4220000])
    unrealized_gain_loss: float = Field(..., examples=[318750])


class PerformanceGraph(BaseModel):
    user_id: int = Field(..., ge=1, examples=[101])
    portfolio_id: int = Field(..., ge=1, examples=[1])
    currency: str = Field(..., examples=["JPY"])
    interval: Literal["1d", "1wk", "1mo"] = Field(..., examples=["1d"])
    points: List[PerformanceGraphPoint]


portfolios = {
    1: {
        "portfolio_id": 1,
        "user_id": 101,
        "name": "Main Portfolio",
        "currency": "JPY",
        "cash_balance": 1250000.0,
    }
}

mock_users = {
    101: {
        "user_id": 101,
        "email": "demo@example.com",
        "password": "password123",
    }
}

mock_tokens = {"mock-access-token-101": 101}

assets: Dict[int, Asset] = {
    1: Asset(
        asset_id=1,
        user_id=101,
        portfolio_id=1,
        type="stock",
        name="Toyota Motor Corp.",
        ticker="7203.T",
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
        ticker="AAPL",
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
    Transaction(
        transaction_id=3,
        user_id=101,
        portfolio_id=1,
        asset_id=1,
        transaction_type="buy",
        quantity=4.1,
        price=1095.80,
        fees=0.0,
        date="2026-06-20T10:00:00",
    ),
    Transaction(
        transaction_id=4,
        user_id=101,
        portfolio_id=1,
        asset_id=2,
        transaction_type="buy",
        quantity=3.0,
        price=28500.00,
        fees=0.0,
        date="2026-06-20T10:05:00",
    ),
]


def get_asset_or_404(asset_id: int) -> Asset:
    asset = assets.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="The specified asset does not exist")
    return asset


def token_for_user(user_id: int) -> str:
    token = f"mock-access-token-{user_id}"
    mock_tokens[token] = user_id
    return token


def resolve_user_id(
    authorization: Optional[str],
    user_id: Optional[int],
) -> int:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Invalid authorization header")
        token_user_id = mock_tokens.get(token)
        if token_user_id is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        if user_id is not None and user_id != token_user_id:
            raise HTTPException(status_code=403, detail="Token user does not match user_id")
        return token_user_id
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authorization token or user_id is required")
    return user_id


def find_user_by_email(email: str) -> Optional[Dict[str, object]]:
    normalized_email = email.lower()
    for user in mock_users.values():
        if str(user["email"]).lower() == normalized_email:
            return user
    return None


def find_primary_portfolio(user_id: int) -> Dict[str, object]:
    for portfolio in portfolios.values():
        if portfolio["user_id"] == user_id:
            return portfolio
    raise HTTPException(status_code=404, detail="The specified portfolio does not exist")


def make_auth_response(user: Dict[str, object], portfolio: Dict[str, object]) -> AuthResponse:
    user_id = int(user["user_id"])
    return AuthResponse(
        access_token=token_for_user(user_id),
        token_type="bearer",
        user=AuthUser(user_id=user_id, email=str(user["email"])),
        portfolio=AuthPortfolio(
            portfolio_id=int(portfolio["portfolio_id"]),
            name=str(portfolio["name"]),
            base_currency=str(portfolio["currency"]),
        ),
    )


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


def next_graph_date(current_date: dt.date, interval: str) -> dt.date:
    if interval == "1wk":
        return current_date + dt.timedelta(days=7)
    if interval == "1mo":
        month = current_date.month + 1
        year = current_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(current_date.day, 28)
        return dt.date(year, month, day)
    return current_date + dt.timedelta(days=1)


def mock_market_price(asset: Asset, graph_date: dt.date) -> float:
    base_date = dt.date(2026, 7, 28)
    days_from_base = (graph_date - base_date).days
    return round(asset.current_price * (1 + days_from_base * 0.002), 2)


def calculate_graph_values(
    user_id: int,
    portfolio_id: int,
    graph_date: dt.date,
) -> Dict[str, float]:
    holding_values: Dict[int, Dict[str, float]] = {}
    relevant_transactions = sorted(
        [
            transaction
            for transaction in transactions
            if transaction.user_id == user_id
            and transaction.portfolio_id == portfolio_id
            and transaction.date.date() <= graph_date
        ],
        key=lambda transaction: transaction.date,
    )

    for transaction in relevant_transactions:
        holding = holding_values.setdefault(
            transaction.asset_id,
            {"quantity": 0.0, "purchase_value": 0.0},
        )
        if transaction.transaction_type == "buy":
            holding["quantity"] += transaction.quantity
            holding["purchase_value"] += transaction.quantity * transaction.price + transaction.fees
        elif holding["quantity"] > 0:
            average_cost = holding["purchase_value"] / holding["quantity"]
            sell_quantity = min(transaction.quantity, holding["quantity"])
            holding["quantity"] -= sell_quantity
            holding["purchase_value"] -= average_cost * sell_quantity

    total_purchase_value = 0.0
    total_market_value = 0.0
    for asset_id, holding in holding_values.items():
        if holding["quantity"] <= 0:
            continue
        asset = assets.get(asset_id)
        if asset is None:
            continue
        total_purchase_value += holding["purchase_value"]
        total_market_value += holding["quantity"] * mock_market_price(asset, graph_date)

    return {
        "total_purchase_value": round(total_purchase_value, 2),
        "total_market_value": round(total_market_value, 2),
        "unrealized_gain_loss": round(total_market_value - total_purchase_value, 2),
    }


def calculate_post_transaction_asset(
    asset: Asset,
    portfolio_id: int,
    request: TransactionCreate,
) -> Asset:
    if request.user_id is None:
        raise HTTPException(status_code=401, detail="Authorization token or user_id is required")
    if asset.user_id != request.user_id or asset.portfolio_id != portfolio_id:
        raise HTTPException(
            status_code=400,
            detail="Asset does not belong to the specified user and portfolio",
        )
    if request.transaction_type == "sell" and request.quantity > asset.quantity:
        raise HTTPException(status_code=400, detail="Cannot sell more than current holding")

    updated_asset = asset.model_copy(deep=True)
    if request.transaction_type == "buy":
        new_quantity = updated_asset.quantity + request.quantity
        new_purchase_value = (
            updated_asset.quantity * updated_asset.purchase_price
            + request.quantity * request.price
            + request.fees
        )
        updated_asset.quantity = round(new_quantity, 6)
        updated_asset.purchase_price = round(new_purchase_value / new_quantity, 2)
    else:
        updated_asset.quantity = round(updated_asset.quantity - request.quantity, 6)
    return updated_asset


def build_transaction_request(user_id: int, transaction_item: TransactionItem) -> TransactionCreate:
    return TransactionCreate(user_id=user_id, **transaction_item.model_dump())


def apply_transaction(portfolio_id: int, request: TransactionCreate) -> Transaction:
    if request.user_id is None:
        raise HTTPException(status_code=401, detail="Authorization token or user_id is required")
    asset = get_asset_or_404(request.asset_id)
    assets[request.asset_id] = calculate_post_transaction_asset(asset, portfolio_id, request)
    transaction = Transaction(
        transaction_id=len(transactions) + 1,
        portfolio_id=portfolio_id,
        **request.model_dump(),
    )
    transactions.append(transaction)
    return transaction


@app.post(
    "/auth/signup",
    response_model=AuthResponse,
    status_code=201,
    responses={409: {"description": "Email already exists"}},
    tags=["auth"],
    summary="API to sign up",
    description=(
        "ユーザー登録を行う。Mock版ではメモリ上にユーザーとデフォルトポートフォリオを作成する。"
        "本番ではSupabase AuthのsignUpを使用する想定。"
    ),
)
def signup(request: SignupRequest):
    if find_user_by_email(request.email) is not None:
        raise HTTPException(status_code=409, detail="Email already exists")

    user_id = max(mock_users.keys(), default=100) + 1
    portfolio_id = max(portfolios.keys(), default=0) + 1
    user = {
        "user_id": user_id,
        "email": request.email,
        "password": request.password,
    }
    portfolio = {
        "portfolio_id": portfolio_id,
        "user_id": user_id,
        "name": request.portfolio_name,
        "currency": request.base_currency,
        "cash_balance": 0.0,
    }
    mock_users[user_id] = user
    portfolios[portfolio_id] = portfolio
    return make_auth_response(user, portfolio)


@app.post(
    "/auth/login",
    response_model=AuthResponse,
    responses={401: {"description": "Invalid email or password"}},
    tags=["auth"],
    summary="API to log in",
    description="ログインを行う。Mock版ではメールアドレスとパスワードを確認し、mock bearer tokenを返す。",
)
def login(request: LoginRequest):
    user = find_user_by_email(request.email)
    if user is None or user["password"] != request.password:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    portfolio = find_primary_portfolio(int(user["user_id"]))
    return make_auth_response(user, portfolio)


@app.post(
    "/auth/logout",
    response_model=LogoutResponse,
    tags=["auth"],
    summary="API to log out",
    description="ログアウトを行う。Mock版ではクライアント側でtokenを破棄する想定。",
)
def logout(authorization: Optional[str] = Header(default=None, alias="Authorization")):
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token in mock_tokens:
            mock_tokens.pop(token)
    return LogoutResponse(message="Logged out")


@app.get(
    "/portfolios/{portfolio_id}/summary",
    response_model=PortfolioSummary,
    responses={404: {"description": "The specified portfolio does not exist"}},
    tags=["portfolio"],
    summary="API to fetch portfolio summary",
    description="ポートフォリオサマリーを取得する",
)
def fetch_portfolio_summary(
    portfolio_id: int = Path(..., ge=1, description="Portfolio ID", examples=[1]),
    user_id: Optional[int] = Query(default=None, ge=1, description="Mock fallback User ID", examples=[101]),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    resolved_user_id = resolve_user_id(authorization, user_id)
    portfolio = portfolios.get(portfolio_id)
    if portfolio is None or portfolio["user_id"] != resolved_user_id:
        raise HTTPException(status_code=404, detail="The specified portfolio does not exist")

    values = calculate_values(portfolio_assets(portfolio_id=portfolio_id))
    return PortfolioSummary(
        **portfolio,
        **values,
        total_asset_value=round(portfolio["cash_balance"] + values["total_market_value"], 2),
    )


@app.get(
    "/portfolios/{portfolio_id}/performance",
    response_model=PerformanceGraph,
    responses={404: {"description": "The specified portfolio does not exist"}},
    tags=["portfolio"],
    summary="API to fetch portfolio performance",
    description=(
        "ポートフォリオ推移グラフを取得する。"
        "取引履歴から日付ごとの保有残高を復元し、asset_data_historyまたはYahoo Financeの価格データで評価額と含み損益を計算する想定。"
    ),
)
def fetch_portfolio_performance(
    portfolio_id: int = Path(..., ge=1, description="Portfolio ID", examples=[1]),
    user_id: Optional[int] = Query(default=None, ge=1, description="Mock fallback User ID", examples=[101]),
    start_date: Optional[dt.date] = Query(default=None, examples=["2026-07-26"]),
    end_date: Optional[dt.date] = Query(default=None, examples=["2026-07-28"]),
    interval: Literal["1d", "1wk", "1mo"] = Query(default="1d", examples=["1d"]),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    resolved_user_id = resolve_user_id(authorization, user_id)
    portfolio = portfolios.get(portfolio_id)
    if portfolio is None or portfolio["user_id"] != resolved_user_id:
        raise HTTPException(status_code=404, detail="The specified portfolio does not exist")

    graph_start_date = start_date or dt.date(2026, 7, 26)
    graph_end_date = end_date or dt.date(2026, 7, 28)
    if graph_start_date > graph_end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")

    points = []
    current_date = graph_start_date
    while current_date <= graph_end_date:
        points.append(
            PerformanceGraphPoint(
                date=current_date,
                **calculate_graph_values(resolved_user_id, portfolio_id, current_date),
            )
        )
        current_date = next_graph_date(current_date, interval)

    return PerformanceGraph(
        user_id=resolved_user_id,
        portfolio_id=portfolio_id,
        currency=portfolio["currency"],
        interval=interval,
        points=points,
    )


@app.post(
    "/portfolios/",
    response_model=Portfolio,
    status_code=201,
    tags=["portfolio"],
    summary="API to create portfolio",
    description="ポートフォリオを作成する",
)
def create_portfolio(request: PortfolioCreate):
    portfolio_id = max(portfolios.keys(), default=0) + 1
    portfolio = {
        "portfolio_id": portfolio_id,
        "user_id": request.user_id,
        "name": request.name,
        "currency": request.currency,
        "cash_balance": request.cash_balance,
    }
    portfolios[portfolio_id] = portfolio
    return portfolio


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
        ticker=asset.ticker,
        currency=asset.currency,
    )


@app.get(
    "/portfolios/{portfolio_id}/holdings",
    response_model=List[Holding],
    tags=["portfolio"],
    summary="API to fetch holdings",
    description=(
        "保有残高一覧を取得する。1つのポートフォリオに含まれる複数の資産を返す。"
        "current_priceはYahoo Finance由来の市場価格で、Supabase holdingsには保存しない。"
    ),
)
def fetch_holdings(
    portfolio_id: int = Path(..., ge=1, description="Portfolio ID", examples=[1]),
    user_id: Optional[int] = Query(default=None, ge=1, description="Mock fallback User ID", examples=[101]),
    asset_id: Optional[int] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    resolved_user_id = resolve_user_id(authorization, user_id)
    portfolio = portfolios.get(portfolio_id)
    if portfolio is None or portfolio["user_id"] != resolved_user_id:
        raise HTTPException(status_code=404, detail="The specified portfolio does not exist")

    filtered_assets = list(assets.values())
    filtered_assets = [asset for asset in filtered_assets if asset.user_id == resolved_user_id]
    filtered_assets = [asset for asset in filtered_assets if asset.portfolio_id == portfolio_id]
    if asset_id is not None:
        filtered_assets = [asset for asset in filtered_assets if asset.asset_id == asset_id]

    return [
        Holding(
            user_id=asset.user_id,
            portfolio_id=asset.portfolio_id,
            asset_id=asset.asset_id,
            ticker=asset.ticker,
            name=asset.name,
            quantity=asset.quantity,
            average_purchase_price=asset.purchase_price,
            current_price=asset.current_price,
            currency=asset.currency,
        )
        for asset in filtered_assets
    ]


@app.get(
    "/portfolios/{portfolio_id}/transactions",
    response_model=List[Transaction],
    tags=["transactions"],
    summary="API to fetch transactions",
    description="取引履歴を取得する",
)
def fetch_transactions(
    portfolio_id: int = Path(..., ge=1, description="Portfolio ID", examples=[1]),
    user_id: Optional[int] = Query(default=None, ge=1, description="Mock fallback User ID", examples=[101]),
    asset_id: Optional[int] = Query(default=None),
    start_date: Optional[dt.date] = Query(default=None),
    end_date: Optional[dt.date] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    resolved_user_id = resolve_user_id(authorization, user_id)
    portfolio = portfolios.get(portfolio_id)
    if portfolio is None or portfolio["user_id"] != resolved_user_id:
        raise HTTPException(status_code=404, detail="The specified portfolio does not exist")

    filtered_transactions = transactions
    filtered_transactions = [
        transaction
        for transaction in filtered_transactions
        if transaction.user_id == resolved_user_id
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
    "/portfolios/{portfolio_id}/transactions",
    response_model=Transaction,
    status_code=201,
    responses={400: {"description": "Cannot sell more than current holding"}},
    tags=["transactions"],
    summary="API to record transaction",
    description="取引を登録し、保有残高（holdings）を更新する",
)
def record_transaction(
    portfolio_id: int = Path(..., ge=1, description="Portfolio ID", examples=[1]),
    request: TransactionCreate = ...,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    resolved_user_id = resolve_user_id(authorization, request.user_id)
    portfolio = portfolios.get(portfolio_id)
    if portfolio is None or portfolio["user_id"] != resolved_user_id:
        raise HTTPException(status_code=404, detail="The specified portfolio does not exist")
    request_with_user = request.model_copy(update={"user_id": resolved_user_id})
    return apply_transaction(portfolio_id, request_with_user)


@app.post(
    "/portfolios/{portfolio_id}/transactions/batch",
    response_model=List[Transaction],
    status_code=201,
    responses={400: {"description": "One or more transactions are invalid"}},
    tags=["transactions"],
    summary="API to record multiple transactions",
    description=(
        "複数の取引を一括登録し、各取引ごとに保有残高（holdings）を更新する。"
        "ネットワーク通信回数を減らし、データベースの一括登録・一括更新効率を高める。"
    ),
)
def record_transaction_batch(
    portfolio_id: int = Path(..., ge=1, description="Portfolio ID", examples=[1]),
    request: TransactionBatchCreate = ...,
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    resolved_user_id = resolve_user_id(authorization, request.user_id)
    portfolio = portfolios.get(portfolio_id)
    if portfolio is None or portfolio["user_id"] != resolved_user_id:
        raise HTTPException(status_code=404, detail="The specified portfolio does not exist")

    simulated_assets = {asset_id: asset.model_copy(deep=True) for asset_id, asset in assets.items()}
    transaction_requests = [
        build_transaction_request(resolved_user_id, transaction_item)
        for transaction_item in request.transactions
    ]
    for transaction_request in transaction_requests:
        asset = simulated_assets.get(transaction_request.asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="The specified asset does not exist")
        simulated_assets[transaction_request.asset_id] = calculate_post_transaction_asset(
            asset,
            portfolio_id,
            transaction_request,
        )

    created_transactions = []
    for transaction_request in transaction_requests:
        created_transactions.append(apply_transaction(portfolio_id, transaction_request))
    return created_transactions


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
    "/portfolios/{portfolio_id}/allocation",
    response_model=PortfolioAllocation,
    tags=["portfolio"],
    summary="API to fetch portfolio allocation",
    description="資産配分を取得する。評価額計算の市場価格はYahoo Financeから取得する想定。",
)
def fetch_portfolio_allocation(
    portfolio_id: int = Path(..., ge=1, description="Portfolio ID", examples=[1]),
    user_id: Optional[int] = Query(default=None, ge=1, description="Mock fallback User ID", examples=[101]),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    resolved_user_id = resolve_user_id(authorization, user_id)
    portfolio = portfolios.get(portfolio_id)
    if portfolio is None or portfolio["user_id"] != resolved_user_id:
        raise HTTPException(status_code=404, detail="The specified portfolio does not exist")

    filtered_assets = [
        asset
        for asset in portfolio_assets(portfolio_id=portfolio_id)
        if asset.user_id == resolved_user_id
    ]
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
