# Portfolio Manager API Design

## Purpose

This backend is currently a Swagger/mock API design for a portfolio management
application. It lets users create accounts, view assets, record buy/sell
transactions, inspect mock market prices, and review portfolio valuation.

This draft does not place real brokerage orders. Buy and sell actions record
portfolio transactions and update holdings only.

## Data Source Plan

- Supabase will store user portfolio data:
  - accounts
  - assets
  - holdings
  - transactions
  - cash balances
- The API can calculate return/gain values from stored transactions and assets:
  - realized gain
  - unrealized gain
  - total return
  - return rate
- Yahoo Finance will provide market data:
  - latest price
  - historical open/high/low/close/volume data
- Each asset should store a Yahoo-compatible `symbol`.
  - Examples: `AAPL`, `MSFT`, `7203.T`

## Data Access Rules

- User-owned portfolio data must be filtered by `user_id`.
  - Examples: holdings, transactions, portfolio-specific summaries.
- `portfolio_id` is the Supabase portfolio identifier. It replaces the earlier
  draft wording of `account_id`.
- Market price data is public market data.
  - Asset price endpoints use `asset_id` to find the asset `symbol`.
  - Yahoo Finance uses that `symbol` to fetch latest and historical prices.
  - They do not require `user_id` because Yahoo Finance prices are not private
    user data.

## Swagger Sections

| Tag | Japanese label | Purpose |
| --- | --- | --- |
| `accounts` | 口座関連 | Account creation, account summary, holdings, valuation, and allocation |
| `assets` | 資産関連 | Asset master data and Yahoo Finance market prices |
| `transactions` | 取引履歴関連 | Buy/sell transaction history |

## Current Mock Endpoints

### Accounts

`POST /accounts/`

Creates a mock account.

Request:

```json
{
  "user_id": 202,
  "currency": "JPY",
  "cash_balance": 500000
}
```

Response:

```json
{
  "user_id": 202,
  "currency": "JPY",
  "cash_balance": 500000,
  "portfolio_id": 2
}
```

`GET /accounts/{portfolio_id}/summary`

Returns cash balance, purchase value, market value, total asset value, and
unrealized gain/loss. This is the merged account and portfolio valuation
endpoint.

Market value uses Yahoo Finance prices, not Supabase holdings columns.

### Assets

`GET /assets/{asset_id}/`

Returns one asset master record. The response includes `symbol`, which connects
the asset to Yahoo Finance market data.

This endpoint does not return user-owned values like quantity or purchase
price. Those values belong to `GET /portfolio/holdings`.

`GET /assets/{asset_id}/price-history`

Returns mock historical OHLCV price data. Future behavior uses the asset
`symbol` to fetch Yahoo Finance history.

### Accounts Portfolio APIs

`GET /portfolio/holdings`

Returns user-owned holdings from the existing Supabase `public.holdings` table
concept. The response is an array because one portfolio can contain multiple
assets. `user_id` is required because holdings are private user data and users
should only see their own holdings. Supports filters:

- `user_id` required
- `portfolio_id` required
- `asset_id`

Important data boundary:

- Supabase `public.holdings` stores user-owned values like quantity and average
  purchase price.
- `current_price` is market data from Yahoo Finance, using the asset `symbol`.
- In this mock API, `current_price` is sample data only. In the future version,
  the API should fetch it from Yahoo Finance at request time or from a separate
  market price cache, not from the holdings table.

`GET /portfolio/allocation`

Returns allocation by:

- asset type
- currency
- individual asset

Requires:

- `portfolio_id` required

### Transactions

`GET /transactions/`

Returns one user's transaction history. `user_id` is required so the API returns
the transaction log for that user only. Supports filters:

- `user_id` required
- `portfolio_id` required
- `asset_id`
- `start_date`
- `end_date`

`POST /transactions/`

Records a buy or sell transaction and updates the user's holding.

Request:

```json
{
  "user_id": 101,
  "portfolio_id": 1,
  "asset_id": 1,
  "transaction_type": "buy",
  "quantity": 2,
  "price": 3000,
  "fees": 10,
  "date": "2026-07-28T18:00:00"
}
```

Behavior:

- `buy` inserts one transaction and increases the matching holding quantity.
- `buy` recalculates the holding average purchase price.
- `sell` inserts one transaction and decreases the matching holding quantity.
- Selling more than the current holding returns `400`.

Future Supabase behavior:

1. Insert the request into the existing `transactions` table.
2. Find the matching row in the existing `public.holdings` table by
   `user_id`, `portfolio_id`, and `asset_id`.
3. For `buy`, increase quantity and update average purchase price.
4. For `sell`, decrease quantity.
5. Reject the request if a sell quantity is larger than the current holding.

## Supabase Table Assumptions

Do not change the existing Supabase schema just for this mock API. The tables
below describe the fields the API expects to read if they already exist or can
be mapped from the current design.

### `accounts`

| Column | Type | Notes |
| --- | --- | --- |
| `portfolio_id` | integer | Primary key |
| `user_id` | integer | Owner |
| `currency` | text | Example: `JPY` |
| `cash_balance` | numeric | Portfolio cash |

### `assets`

| Column | Type | Notes |
| --- | --- | --- |
| `asset_id` | integer | Primary key |
| `type` | text | Example: `stock` |
| `name` | text | Asset name |
| `symbol` | text | Yahoo Finance symbol |
| `currency` | text | Example: `JPY` |

### `public.holdings`

Use the existing Supabase `public.holdings` table. The API design assumes it can map to
these concepts without requiring a schema redesign:

| Concept | Notes |
| --- | --- |
| user | Holding owner; required for private data access |
| portfolio | Supabase portfolio ID |
| asset | Related stock/asset; connects to `assets.asset_id` |
| quantity | Current holding quantity |
| average purchase price | Updated after buys |

Do not store `current_price` in `public.holdings`. Current market prices should
come from Yahoo Finance by using the asset `symbol`.

### `transactions`

| Column | Type | Notes |
| --- | --- | --- |
| `transaction_id` | integer | Primary key |
| `user_id` | integer | Owner |
| `portfolio_id` | integer | Portfolio |
| `asset_id` | integer | Related asset |
| `transaction_type` | text | `buy` or `sell` |
| `quantity` | numeric | Transaction quantity |
| `price` | numeric | Transaction price |
| `fees` | numeric | Transaction fees |
| `date` | timestamp | Transaction timestamp |

## Future Calculated Values

The API can calculate these values later without adding Supabase columns or a
separate Swagger section:

- `realized_gain`: profit/loss from completed sell transactions
- `unrealized_gain`: current market value minus purchase value for held assets
- `total_return`: realized gain plus unrealized gain
- `return_rate`: total return divided by purchase value

## Run Locally

```bash
python3 -m uvicorn api_design.apiDesign:app --host 127.0.0.1 --port 8000
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```
