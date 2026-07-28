from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, Field


app = FastAPI(
    title="Portfolio Manager API spec",
    version="1.0.0",
    openapi_tags=[
        {
            "name": "accounts",
            "description": "口座関連",
        },
        {
            "name": "transactions",
            "description": "取引履歴関連",
        },
    ],
)


class Asset(BaseModel):
    asset_id: int = Field(
        ...,
        ge=1,
        description="Asset ID",
        examples=[1],
    )
    type: str = Field(
        ...,
        max_length=20,
        description="Asset type",
        examples=["stock, bond"],
    )
    quantity: float = Field(
        ...,
        ge=0,
        description="how many units of the asset the user has",
        examples=[8.5],
    )
    purchase_price: float = Field(
        ...,
        ge=0,
        description="取得価額",
        examples=[1095.80],
    )
    current_price: float = Field(
        ...,
        ge=0,
        description="現在価格",
        examples=[20.50],
    )
    currency: str = Field(
        ...,
        description="通貨",
        examples=["JPY"],
    )


class Transaction(BaseModel):
    transaction_type: str = Field(..., examples=["buy"])
    quantity: float = Field(..., ge=0, examples=[5.4])
    price: float = Field(..., ge=0, examples=[4.3])
    fees: float = Field(..., ge=0, examples=[0.0])
    date: datetime = Field(..., examples=["2026-05-26T18:00:00"])


assets = {
    1: Asset(
        asset_id=1,
        type="stock",
        quantity=8.5,
        purchase_price=1095.80,
        current_price=20.50,
        currency="JPY",
    ),
    2: Asset(
        asset_id=2,
        type="bond",
        quantity=3.0,
        purchase_price=10000.00,
        current_price=10150.00,
        currency="JPY",
    ),
}

transactions: List[Transaction] = [
    Transaction(
        transaction_type="buy",
        quantity=5.4,
        price=4.3,
        fees=0.0,
        date="2026-05-26T18:00:00",
    ),
    Transaction(
        transaction_type="sell",
        quantity=1.0,
        price=20.5,
        fees=0.0,
        date="2026-06-10T09:30:00",
    ),
]


@app.get(
    "/assets/{asset_id}/",
    response_model=Asset,
    responses={404: {"description": "The specified asset does not exist"}},
    tags=["accounts"],
    summary="API to fetch assets",
    description="資産の情報を取得する",
)
def fetch_asset(
    asset_id: int = Path(
        ...,
        ge=1,
        description="Asset ID",
        examples=[1],
    ),
):
    asset = assets.get(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="The specified asset does not exist")

    return asset


@app.get(
    "/transactions/",
    response_model=List[Transaction],
    tags=["transactions"],
    summary="API to fetch transactions",
    description="取引履歴を取得する",
)
def fetch_transactions(
    user_id: Optional[int] = Query(default=None),
    asset_id: Optional[int] = Query(default=None),
    start_date: Optional[int] = Query(default=None),
    end_date: Optional[int] = Query(default=None),
):
    return transactions


@app.get("/", include_in_schema=False)
def home():
    return {
        "message": "Portfolio Manager API is running",
        "swagger_ui": "/docs",
        "openapi_json": "/openapi.json",
    }
