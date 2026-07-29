# Portfolio Manager API Design

## Purpose

This backend is currently a Swagger/mock API design for a portfolio management
application. It lets users create portfolios, view holdings, record buy/sell
transactions, inspect market prices, and review portfolio valuation.

This draft does not place real brokerage orders. Buy and sell actions only
record portfolio transactions and update current holdings.

## Data Source Plan

- Supabase stores private portfolio data:
  - `users`
  - `portfolio`
  - `asset_master`
  - `asset_data_history`
  - `holdings`
  - `transactions`
  - `currency`
  - `asset_type`
  - `transaction_type`
- Yahoo Finance provides market data by `asset_master.ticker`.
- `asset_data_history.close_price` can store historical market close prices.
- A background job can periodically refresh many tickers:
  - read active `asset_master.ticker` values from Supabase
  - fetch prices from Yahoo Finance
  - write refreshed prices to `asset_data_history` or a future market snapshot area
  - do not write current market prices into `holdings`

## Data Access Rules

- User-owned portfolio data must be filtered by `user_id`.
- During mock/development, private `GET` APIs require `user_id` as a query
  parameter.
- `portfolio_id` is required in the path for private portfolio data.
- In production, the backend can get `user_id` from login/auth instead of query
  parameters.
- Public asset/market data does not require `user_id`.

## Swagger Sections

| Tag | Japanese label | Purpose |
| --- | --- | --- |
| `auth` | 認証関連 | Signup, login, and logout |
| `portfolio` | ポートフォリオ関連 | Portfolio creation, summary, holdings, allocation, and performance |
| `assets` | 資産関連 | Asset master data and Yahoo Finance market prices |
| `transactions` | 取引履歴関連 | Buy/sell transaction history |

## Current Mock Endpoints

Paths below are shown without a prefix. The Flask app serves them under
`/api/v1`, so `GET /portfolios/1/summary` is
`GET /api/v1/portfolios/1/summary`.

### Auth

`POST /auth/signup`

Registers a user and creates one default portfolio. Future production behavior
uses Supabase Auth for the password and token.

Request:

```json
{
  "email": "user@example.com",
  "password": "password123",
  "portfolio_name": "Main Portfolio",
  "base_currency": "JPY"
}
```

Response:

```json
{
  "access_token": "mock-access-token-101",
  "token_type": "bearer",
  "user": {
    "user_id": 101,
    "email": "user@example.com"
  },
  "portfolio": {
    "portfolio_id": 1,
    "name": "Main Portfolio",
    "base_currency": "JPY"
  }
}
```

`POST /auth/login`

Logs in with email/password and returns a bearer token plus the user's default
portfolio.

`POST /auth/logout`

Logs out the current session. Future production behavior should clear the
Supabase session/token on the client side.

### Portfolio

`POST /portfolios/`

Creates a mock portfolio.

Request:

```json
{
  "user_id": 202,
  "name": "Main Portfolio",
  "currency": "JPY",
  "cash_balance": 500000
}
```

Response:

```json
{
  "user_id": 202,
  "name": "Main Portfolio",
  "currency": "JPY",
  "cash_balance": 500000,
  "portfolio_id": 2
}
```

`GET /portfolios/{portfolio_id}/summary`

Returns purchase value, market value, total asset value, and unrealized
gain/loss for one portfolio.

Request:

```text
GET /portfolios/1/summary?user_id=101
```

Notes:

- `user_id` is required for mock owner checking.
- Market value uses Yahoo Finance or `asset_data_history` prices, not
  `holdings`.
- `cash_balance` is mock-only because the current Supabase schema has no cash
  balance column/table.

`GET /portfolios/{portfolio_id}/holdings`

Returns current holdings for one portfolio. The response is an array because one
portfolio can contain multiple assets.

Request:

```text
GET /portfolios/1/holdings?user_id=101
```

Supports filters:

- `user_id` required
- `asset_id`

Important data boundary:

- Supabase `holdings` stores quantity and average cost.
- `current_price` is market data from Yahoo Finance or `asset_data_history`.
- Do not store `current_price` in `holdings`.

`GET /portfolios/{portfolio_id}/allocation`

Returns allocation by asset type, currency, and individual asset.

Request:

```text
GET /portfolios/1/allocation?user_id=101
```

`GET /portfolios/{portfolio_id}/performance`

Returns graph-ready portfolio performance points.

Request:

```text
GET /portfolios/1/performance?user_id=101&start_date=2026-07-26&end_date=2026-07-28&interval=1d
```

Response:

```json
{
  "user_id": 101,
  "portfolio_id": 1,
  "currency": "JPY",
  "interval": "1d",
  "points": [
    {
      "date": "2026-07-26",
      "total_purchase_value": 94814.3,
      "total_market_value": 124434.53,
      "unrealized_gain_loss": 29620.23
    }
  ]
}
```

Behavior:

- Reconstructs historical holding quantity from `transactions`.
- Uses `asset_data_history.close_price` by date for market value.
- Uses `asset_master.ticker` as the Yahoo Finance ticker.
- Does not require any Supabase schema change.

### Assets

`GET /assets/{asset_id}/`

Returns one asset master record. The response includes `ticker`, which connects
the asset to Yahoo Finance market data.

This endpoint does not return private user-owned values like quantity or
average cost. Those values belong to `GET /portfolios/{portfolio_id}/holdings`.

`GET /assets/{asset_id}/price-history`

Returns mock historical OHLCV price data. Future behavior uses the asset
`ticker` to fetch Yahoo Finance history or reads cached close prices from
`asset_data_history`.

### Transactions

`GET /portfolios/{portfolio_id}/transactions`

Returns one user's transaction history for one portfolio.

Request:

```text
GET /portfolios/1/transactions?user_id=101
```

Supports filters:

- `user_id` required
- `asset_id`
- `start_date`
- `end_date`

Future extensible query options:

- `transaction_type`: filter by `buy` or `sell`
- `ticker`: filter transactions after joining `asset_master`
- `limit` and `offset`: support pagination
- `sort_by` and `sort_order`: support sorting by date, quantity, price, or fees

`POST /portfolios/{portfolio_id}/transactions`

Records one buy or sell transaction and updates the user's holding.

Request:

```json
{
  "user_id": 101,
  "asset_id": 1,
  "transaction_type": "buy",
  "quantity": 2,
  "price": 3000,
  "fees": 10,
  "date": "2026-07-28T18:00:00"
}
```

Behavior:

- Uses `portfolio_id` from the path.
- `buy` inserts one transaction and increases the matching holding quantity.
- `buy` recalculates holding average cost.
- `sell` inserts one transaction and decreases the matching holding quantity.
- Selling more than the current holding returns `400`.

`POST /portfolios/{portfolio_id}/transactions/batch`

Records multiple buy/sell transactions in one request and updates holdings for
each transaction.

Request:

```json
{
  "user_id": 101,
  "transactions": [
    {
      "asset_id": 1,
      "transaction_type": "buy",
      "quantity": 2,
      "price": 3000,
      "fees": 10,
      "date": "2026-07-28T18:00:00"
    },
    {
      "asset_id": 2,
      "transaction_type": "sell",
      "quantity": 1,
      "price": 33200,
      "fees": 0,
      "date": "2026-07-28T18:05:00"
    }
  ]
}
```

Purpose:

- Reduces network overhead by sending many transactions in one request.
- Improves database batch insert/update efficiency.
- Lets the backend validate the whole batch before updating holdings.

## Supabase Database Design

This section reflects the current Supabase `public` schema checked on
2026-07-29. The API can still use readable request/response fields, but the
database now normalizes currency, asset type, and transaction type through
lookup tables.

### `users`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key |
| `email` | text | Required user email |
| `created_at` | timestamp with time zone | Required; default `now()` |
| `updated_at` | timestamp with time zone | Required; default `now()` |
| `name` | character varying | Optional display name |
| `password` | text | Optional current schema column; future production should use Supabase Auth instead |

### `portfolio`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key; default `gen_random_uuid()`; API name is `portfolio_id` |
| `user_id` | uuid | Required owner; references `users.id` |
| `name` | text | Required portfolio name; default `Default Portfolio` |
| `created_at` | timestamp with time zone | Required; default `now()` |
| `updated_at` | timestamp with time zone | Required; default `now()` |

### `asset_master`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key; default `gen_random_uuid()`; API name is `asset_id` |
| `ticker` | text | Required Yahoo Finance ticker, such as `AAPL` or `7203.T` |
| `name` | text | Optional asset name |
| `asset_type` | text | Optional legacy readable asset type |
| `asset_type_id` | uuid | Optional; references `asset_type.id` |
| `currency_id` | uuid | Optional; references `currency.id` |

### `currency`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key; default `gen_random_uuid()` |
| `currency` | text | Required currency code, such as `JPY` or `USD` |
| `symbol` | text | Optional currency symbol |

Current allowed rows:

- `AUD`
- `CAD`
- `CHF`
- `CNY`
- `EUR`
- `GBP`
- `HKD`
- `JPY`
- `KRW`
- `SGD`
- `USD`

### `asset_type`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key; default `gen_random_uuid()` |
| `asset_type` | text | Required asset type |

Current allowed rows:

- `bond`
- `cash`
- `crypto`
- `etf`
- `fund`
- `reit`
- `stock`

### `transaction_type`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key; default `gen_random_uuid()` |
| `transaction_type` | character varying | Required transaction type |

Current allowed rows:

- `buy`
- `sell`

### `asset_data_history`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key; default `gen_random_uuid()` |
| `asset_id` | uuid | Required; references `asset_master.id` |
| `price_date` | date | Required market price date |
| `close_price` | numeric | Required historical close price |

### `holdings`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key; default `gen_random_uuid()` |
| `portfolio_id` | uuid | Required; references `portfolio.id` |
| `asset_id` | uuid | Required; references `asset_master.id` |
| `quantity` | numeric | Required current holding quantity; default `0` |
| `average_cost` | numeric | Optional average purchase cost |
| `updated_at` | timestamp with time zone | Required; default `now()` |

### `transactions`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key; default `gen_random_uuid()` |
| `holding_id` | uuid | Required; references `holdings.id` |
| `transaction_type_id` | uuid | Required; references `transaction_type.id` |
| `trade_date` | date | Required trade date |
| `quantity` | numeric | Required transaction quantity |
| `price` | numeric | Required transaction price |
| `fees` | numeric | Required transaction fees; default `0` |
| `created_at` | timestamp with time zone | Required; default `now()` |

Foreign keys:

- `portfolio.user_id` -> `users.id`
- `asset_master.asset_type_id` -> `asset_type.id`
- `asset_master.currency_id` -> `currency.id`
- `holdings.portfolio_id` -> `portfolio.id`
- `holdings.asset_id` -> `asset_master.id`
- `transactions.holding_id` -> `holdings.id`
- `transactions.transaction_type_id` -> `transaction_type.id`
- `asset_data_history.asset_id` -> `asset_master.id`

Database behavior notes:

- Do not add `user_id` to `holdings`; get ownership through
  `holdings -> portfolio -> users`.
- Do not add `portfolio_id` or `user_id` to `transactions`; get ownership
  through `transactions -> holdings -> portfolio`.
- Do not add `asset_id` to `transactions`; get the asset through
  `transactions -> holdings -> asset_master`.
- Use `asset_master.ticker` for Yahoo Finance lookup.
- Use `asset_master.currency_id -> currency.id` for currency validation.
- Use `asset_master.asset_type_id -> asset_type.id` for asset type validation.
- Use `transactions.transaction_type_id -> transaction_type.id` for buy/sell
  validation.
- Do not store `current_price` in `holdings`.
- Portfolio summary should not claim `cash_balance` comes from Supabase because
  the current schema has no cash balance column/table.

## Future Supabase Behavior

1. For transaction create, use path `portfolio_id` and body `asset_id` to find
   or create a matching `holdings` row.
2. Resolve body `transaction_type` (`buy` / `sell`) to
   `transaction_type.id`.
3. Insert the transaction row with `holding_id`, `transaction_type_id`,
   `trade_date`, `quantity`, `price`, and `fees`.
4. For `buy`, increase `holdings.quantity` and update `holdings.average_cost`.
5. For `sell`, decrease `holdings.quantity`.
6. Reject a sell request if the requested quantity is larger than the current
   holding.

## Run Locally

The API is implemented as a Flask + flask-smorest design under `app/`. See the
[README](README.md) for setup.

```bash
export FLASK_APP=wsgi.py
.venv/bin/flask run --port=5001
```

Swagger UI:

```text
http://localhost:5001/docs
```
