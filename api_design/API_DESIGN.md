# Portfolio Manager API Design

## Purpose

This backend is currently a Swagger/mock API design for a portfolio management
application. It lets users create portfolios, view holdings, record buy/sell
transactions, inspect market prices, and review portfolio valuation.

This draft does not place real brokerage orders. Buy and sell actions only
record portfolio transactions and update current holdings.

Login/signup is also a mock API design. Future production behavior should use
Supabase Auth for password storage and token issuing.

## Data Source Plan

- Supabase stores private portfolio data:
  - `users`
  - `portfolio`
  - `asset_master`
  - `asset_data_history`
  - `holdings`
  - `transactions`
- Supabase Auth stores login credentials and issues access tokens.
- Do not store passwords in `public.users`.
- Yahoo Finance uses the API field `ticker`.
- Supabase stores ticker values in `asset_master.ticker`.
- `asset_data_history.close_price` can store historical market close prices.
- A background job can periodically refresh many tickers:
  - read active ticker values from `asset_master.ticker` in Supabase
  - fetch prices from Yahoo Finance
  - write refreshed prices to `asset_data_history` or a future market snapshot area
  - do not write current market prices into `holdings`

## Data Access Rules

- User-owned portfolio data must be filtered by the authenticated user.
- During mock/development, private APIs support either:
  - `Authorization: Bearer mock-access-token-...`
  - explicit `user_id` as a Swagger fallback
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

### Auth

`POST /auth/signup`

Creates a mock user and one default mock portfolio.

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

Behavior:

- Returns `409` when the email already exists.
- Mock token is only for Swagger/API design.
- Future production should call Supabase Auth `signUp()`.

`POST /auth/login`

Checks email/password and returns a mock bearer token plus the user's primary
portfolio.

Request:

```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

Behavior:

- Returns `401` for wrong email or password.
- Future production should call Supabase Auth `signInWithPassword()`.

`POST /auth/logout`

Logs out the mock user. In production, the frontend should discard the access
token and Supabase session.

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

- Use `Authorization: Bearer ...` when available.
- `user_id` is still accepted for simple Swagger mock testing.
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

Token version:

```text
GET /portfolios/1/holdings
Authorization: Bearer mock-access-token-101
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
- Uses API field `ticker` as the Yahoo Finance ticker.
- Maps `ticker` to Supabase `asset_master.ticker`.
- Does not require any Supabase schema change.

### Assets

`GET /assets/{asset_id}/`

Returns one asset master record. The response includes `ticker`, which connects
the asset to Yahoo Finance market data. In Supabase this value is stored in
`asset_master.ticker`.

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

Token version:

```text
GET /portfolios/1/transactions
Authorization: Bearer mock-access-token-101
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
- Uses `Authorization` token when available; `user_id` remains as mock fallback.
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

The current Supabase schema should stay unchanged.

Supabase Auth should be enabled separately for email/password login. Auth owns
passwords and session tokens. The public `users` table is the app profile table.

### `users`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key |
| `email` | text | User email |
| `created_at` | timestamp with time zone | Created timestamp |
| `updated_at` | timestamp with time zone | Updated timestamp |

Auth notes:

- `public.users.id` should match the Supabase Auth user UUID.
- `public.users.email` should match the Supabase Auth user email.
- Do not add a password column.
- A future database trigger can insert `public.users` automatically when
  Supabase creates an Auth user.

### `portfolio`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key; API name is `portfolio_id` |
| `user_id` | uuid | Owner; references `users.id` |
| `name` | text | Portfolio name |
| `base_currency` | character | Portfolio base currency |
| `created_at` | timestamp with time zone | Created timestamp |
| `updated_at` | timestamp with time zone | Updated timestamp |

### `asset_master`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key; API name is `asset_id` |
| `ticker` | text | Yahoo Finance ticker, such as `AAPL` or `7203.T` |
| `name` | text | Asset name |
| `asset_type` | text | Example: `stock` |
| `currency` | character | Asset currency |
| `created_at` | timestamp with time zone | Created timestamp |

### `asset_data_history`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key |
| `asset_id` | uuid | References `asset_master.id` |
| `price_date` | date | Market price date |
| `close_price` | numeric | Historical close price |

### `holdings`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key |
| `portfolio_id` | uuid | References `portfolio.id` |
| `asset_id` | uuid | References `asset_master.id` |
| `quantity` | numeric | Current holding quantity |
| `average_cost` | numeric | Average purchase cost |
| `updated_at` | timestamp with time zone | Updated timestamp |

### `transactions`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Primary key |
| `asset_id` | uuid | References `asset_master.id` |
| `holding_id` | uuid | References `holdings.id` |
| `transaction_type` | text | `buy` or `sell` |
| `trade_date` | date | Trade date |
| `quantity` | numeric | Transaction quantity |
| `price` | numeric | Transaction price |
| `fees` | numeric | Transaction fees |
| `created_at` | timestamp with time zone | Created timestamp |

Foreign keys:

- `portfolio.user_id` -> `users.id`
- `holdings.portfolio_id` -> `portfolio.id`
- `holdings.asset_id` -> `asset_master.id`
- `transactions.holding_id` -> `holdings.id`
- `transactions.asset_id` -> `asset_master.id`
- `asset_data_history.asset_id` -> `asset_master.id`

Database behavior notes:

- Do not add `user_id` to `holdings`; get ownership through
  `holdings -> portfolio -> users`.
- Do not add `portfolio_id` or `user_id` to `transactions`; get ownership
  through `transactions -> holdings -> portfolio`.
- API and Supabase both use `ticker`.
- Do not store `current_price` in `holdings`.
- Portfolio summary should not claim `cash_balance` comes from Supabase because
  the current schema has no cash balance column/table.

## Future Supabase Behavior

Auth flow:

1. Enable Supabase Email/Password provider.
2. On signup, call Supabase Auth `signUp()`.
3. Add a trigger/function so new `auth.users` rows create matching
   `public.users` rows.
4. Create one default `public.portfolio` row for the new user.
5. On login, call Supabase Auth `signInWithPassword()` and use the access token
   for private portfolio APIs.

1. For transaction create, use path `portfolio_id` and body `asset_id` to find
   or create a matching `holdings` row.
2. Insert the transaction row with `asset_id`, `holding_id`,
   `transaction_type`, `trade_date`, `quantity`, `price`, and `fees`.
3. For `buy`, increase `holdings.quantity` and update `holdings.average_cost`.
4. For `sell`, decrease `holdings.quantity`.
5. Reject a sell request if the requested quantity is larger than the current
   holding.

## Run Locally

```bash
python3 -m uvicorn api_design.apiDesign:app --host 127.0.0.1 --port 8000
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```
