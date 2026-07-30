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

- Clients send no owner identifier at all for private portfolio data: neither
  `portfolio_id` nor `user_id` appears in any path, query string, or request
  body.
- The backend resolves both the user and the target portfolio from login/auth,
  so every private endpoint acts on the caller's own portfolio. Since a client
  cannot name someone else's portfolio, the API cannot leak which portfolio ids
  exist.
- User-owned portfolio data is still filtered by `user_id` internally; that is a
  server-side concern backed by the `portfolio.user_id` column.
- Responses still report `portfolio_id` so a client knows which portfolio the
  data came from.
- Public asset/market data is not scoped to a portfolio at all.

## Swagger Sections

| Tag | Japanese label | Purpose |
| --- | --- | --- |
| `auth` | 認証関連 | Signup, login, and logout |
| `portfolio` | ポートフォリオ関連 | Portfolio creation, summary, holdings, allocation, and performance |
| `assets` | 資産関連 | Asset master data and Yahoo Finance market prices |
| `transactions` | 取引履歴関連 | Buy/sell transaction history |

## Current Mock Endpoints

Paths below are shown without a prefix. The Flask app serves them under
`/api/v1`, so `GET /portfolios/summary` is
`GET /api/v1/portfolios/summary`.

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

Creates a mock portfolio. The owner comes from login/auth, not the body.

Request:

```json
{
  "name": "Main Portfolio",
  "currency": "JPY",
  "cash_balance": 500000
}
```

Response:

```json
{
  "name": "Main Portfolio",
  "currency": "JPY",
  "cash_balance": 500000,
  "portfolio_id": 2
}
```

`GET /portfolios/summary`

Returns cash balance, market value, and total return rate for one portfolio.

Request:

```text
GET /portfolios/summary
```

Notes:

- Market value uses Yahoo Finance or `asset_data_history` prices, not
  `holdings`.
- `cash_balance` is mock-only because the current Supabase schema has no cash
  balance column/table.

`GET /portfolios/holdings`

Returns current holdings for one portfolio as `items`, plus a `totals` row
aggregated over every holding that matches the filters and a `pagination` block.
`totals` reports today's change only, not all-time return.

Request:

```text
GET /portfolios/holdings
```

Supports filters:

- `asset_id`

Important data boundary:

- Supabase `holdings` stores quantity and average cost.
- `current_price` is market data from Yahoo Finance or `asset_data_history`.
- Do not store `current_price` in `holdings`.

`GET /portfolios/allocation`

Returns allocation for one grouping. `group_by` is required and takes one of
`asset_type`, `currency`, `asset`, or `sector`. There is no combined response;
a screen that shows more than one grouping calls this endpoint once per
grouping.

`group_by=sector` covers equities only, so its `total_value` is smaller than the
portfolio total whenever non-equity assets are held.

Request:

```text
GET /portfolios/allocation?group_by=asset_type
```

Response:

```json
{
  "portfolio_id": 1,
  "group_by": "asset_type",
  "currency": "JPY",
  "total_value": 5860000,
  "items": [
    {
      "name": "stock",
      "value": 4220000,
      "weight": 0.72,
      "holdings_count": 12
    }
  ],
  "as_of": "2026-07-30T14:25:00"
}
```

`GET /portfolios/performance`

Returns graph-ready portfolio performance points.

Request:

```text
GET /portfolios/performance?start_date=2026-07-26&end_date=2026-07-28&interval=1d
```

Response:

```json
{
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
average cost. Those values belong to `GET /portfolios/holdings`.

`GET /assets/{asset_id}/price-history`

Returns mock historical OHLCV price data. Future behavior uses the asset
`ticker` to fetch Yahoo Finance history or reads cached close prices from
`asset_data_history`.

### Transactions

`GET /portfolios/transactions`

Returns one user's transaction history for one portfolio, with realized profit
and loss per transaction and for the filtered set as a whole.

Request:

```text
GET /portfolios/transactions?page=1&per_page=20
```

Response:

```json
{
  "items": [
    {
      "transaction_id": 12,
      "portfolio_id": 1,
      "asset_id": 2,
      "transaction_type": "sell",
      "quantity": 20,
      "price": 178.5,
      "date": "2026-06-11T18:00:00",
      "total_amount": 3570.0,
      "symbol": "TSLA",
      "name": "Tesla Inc.",
      "asset_type": "stock",
      "cost_basis": 3710.0,
      "realized_pl": -140.0,
      "realized_pl_percent": -3.77,
      "currency": "JPY"
    }
  ],
  "totals": {
    "cost_basis": 3710.0,
    "realized_pl": -140.0,
    "realized_pl_percent": -3.77,
    "sell_count": 1,
    "currency": "JPY"
  },
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total_items": 1,
    "total_pages": 1
  }
}
```

Profit and loss rules:

- `realized_pl` is `total_amount - cost_basis`, where `cost_basis` is the
  average cost at the moment of the sale times the sold quantity.
- A `buy` does not settle profit or loss, so `cost_basis`, `realized_pl` and
  `realized_pl_percent` are all null on buy rows.
- `totals` covers every row matching the filters, not just the current page, and
  counts `sell` rows only. `sell_count` says how many rows fed the total.
- Unrealized gain on positions still held is not part of this endpoint; it lives
  on holdings and the portfolio summary.

Supports filters:

- `asset_id`
- `search`
- `transaction_type`
- `asset_type`
- `start_date`
- `end_date`
- `page` and `per_page`

Future extensible query options:

- `ticker`: filter transactions after joining `asset_master`
- `sort_by` and `sort_order`: support sorting by date, quantity, or price

`POST /transactions`

Records one buy or sell transaction and updates the user's holding. The target
portfolio is resolved from login/auth, not sent by the client.

Request:

```json
{
  "asset_id": 1,
  "transaction_type": "buy",
  "quantity": 2
}
```

Response:

```json
{
  "transaction_id": 12,
  "portfolio_id": 1,
  "asset_id": 1,
  "transaction_type": "buy",
  "quantity": 2,
  "price": 2980.5,
  "date": "2026-07-28T18:00:00",
  "total_amount": 5961.0,
  "symbol": "7203.T",
  "name": "Toyota Motor Corp.",
  "asset_type": "stock",
  "currency": "JPY"
}
```

`price` and `date` are settled server-side, so they are response-only.

Behavior:

- Resolves the target portfolio from login/auth.
- `buy` inserts one transaction and increases the matching holding quantity.
- `buy` recalculates holding average cost.
- `sell` inserts one transaction and decreases the matching holding quantity.
- Selling more than the current holding returns `400`.

`POST /transactions/batch`

Records multiple buy/sell transactions in one request and updates holdings for
each transaction.

Request:

```json
{
  "transactions": [
    {
      "asset_id": 1,
      "transaction_type": "buy",
      "quantity": 2
    },
    {
      "asset_id": 2,
      "transaction_type": "sell",
      "quantity": 1
    }
  ]
}
```

Purpose:

- Reduces network overhead by sending many transactions in one request.
- Improves database batch insert/update efficiency.
- Lets the backend validate the whole batch before updating holdings.
- Every element applies to the one portfolio resolved from login/auth, so a
  batch cannot span several portfolios.

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

1. For transaction create, use the portfolio resolved from login/auth and body
   `asset_id` to find or create a matching `holdings` row.
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
