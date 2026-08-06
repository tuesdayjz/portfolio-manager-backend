## Felix Portfolio Manager (Tokyo Team)

Backend repository for the Portfolio Management API. Built using Flask, flask-smorest, and SQLAlchemy with Supabase PostgreSQL as the primary database. The backend handles portfolio creation, cash balance management, asset transaction recording (buy/sell), holdings tracking, portfolio valuation summary, asset allocation breakdown, performance history charting, and automatic background import of historical asset prices and currency exchange rates.

Supabase connection setup, Supabase Auth token validation, Supabase client helpers, database connection tests, SQLAlchemy models, Flask-Migrate migrations, and Supabase RLS tests are implemented.

### User Story

1. As an investor, I want to register my assets so that I can manage my holdings in one place.
2. As an investor, I want to view the current value of my portfolio so that I can understand my overall financial position.
3. As an investor, I want to track my profits and losses so that I can make informed investment decisions.
4. As an investor, I want to record my transaction history so that I can review my investment performance over time.
5. As an investor, I want to visualize my asset allocation so that I can better control and manage risk.
6. As an investor, I want to monitor my investment performance over time so that I can track the growth of my portfolio.

### Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env

export FLASK_APP=wsgi.py
.venv/bin/flask run --port=5001
```

> **Use port 5001.** Because macOS AirPlay Receiver occupies `*:5000`, using port 5000 causes requests to `localhost` to be intercepted by AirPlay, returning `403 Forbidden` (`Server: AirTunes`). If port 5001 is unavailable, launching with `--port=5003` during development is fine.

### Supabase Configuration

Configure Supabase connection info in `.env`.

```env
SUPABASE_URL=https://gvtxkyimbroikdfjsacb.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
DEFAULT_BASE_CURRENCY=USD
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres?sslmode=require
TEST_DATABASE_URL=sqlite+pysqlite:///:memory:
```

- `SUPABASE_ANON_KEY`: Publishable / anon key from Supabase Dashboard.
- `SUPABASE_SERVICE_ROLE_KEY`: Secret / service role key from Supabase Dashboard.
- `SUPABASE_SERVICE_ROLE_KEY` is a backend secret used for connection testing and RLS verification. Do not expose to frontend or Git.
- `DEFAULT_BASE_CURRENCY`: Default currency when creating a portfolio. Both frontend and backend use `USD` as the default value.
- `DATABASE_URL`: SQLAlchemy URI for connecting to Supabase PostgreSQL from the backend.
- `TEST_DATABASE_URL`: DB URI for unit tests. Defaults to in-memory SQLite if unset.
- `.env` is listed in `.gitignore`, so keep it in local environments only.

Within the Flask app, do not read Supabase configuration directly via `os.getenv`; create clients via `app.config`.

```python
from app.services.supabase import get_supabase_anon_client

client = get_supabase_anon_client()
```

`get_supabase_anon_client()` uses `current_app.config["SUPABASE_URL"]` and `current_app.config["SUPABASE_ANON_KEY"]` for validating Supabase Auth tokens. `get_supabase_service_client()` remains as a helper for connection tests and RLS verification. `get_*_client()` functions are cached on the Flask app. If you need to separate sessions across multiple users in tests, use a non-cached client creator such as `create_supabase_anon_client()`.

### Authentication Policy

- React handles signup / login directly using Supabase Auth.
- When React reads private tables directly, access is protected by Supabase access tokens and RLS.
- When React calls Flask private APIs, include `Authorization: Bearer <access_token>` in the request header.
- Flask validates the token and sets the user context via `app.auth.require_auth()`.
- Business DB read/write operations and ownership checks for holdings, transactions, and cash balances are executed via SQLAlchemy using `g.current_user_id`.

On the Flask side, `app.auth.require_auth()` validates the Supabase access token and, upon success, saves the following to the request context:

```python
from flask import g

g.current_user_id
g.current_user_email
g.current_access_token
```

Private API implementations do not receive `user_id` from the client; instead, they resolve the target user using `g.current_user_id`. In Swagger UI, enter the Supabase access token via **Authorize** in the top right.

When manually testing private APIs in Swagger UI, set up Supabase configuration along with `SUPABASE_TEST_USER_EMAIL` / `SUPABASE_TEST_USER_PASSWORD` in your local `.env` and `tests/.env`, then run the following:

```bash
.venv/bin/python scripts/create_test_user.py
.venv/bin/python scripts/generate_token.py
```

`scripts/create_test_user.py` generates a unique email from `SUPABASE_TEST_USER_EMAIL` (e.g. `user001+20260802000000-abcdef@gmail.com`) to create a new test user. Pass `--email` only if you want to use a fixed email address.
After creation, run the displayed token generation command (`scripts/generate_token.py --email ...`) and paste the output into **Authorize** in Swagger UI. Add `--header` if you want to inspect HTTP header format output.

### Skipping Token During Debugging

If issuing a token and pasting it into Swagger UI each time is cumbersome, adding the following to your local `.env` causes `require_auth()` to skip token validation and treat `DEBUG_USER_ID` as the current user:

```bash
AUTH_DISABLED=true
DEBUG_USER_ID=<UUID of Supabase auth user>
DEBUG_USER_EMAIL=<email of that user>
```

Use the user ID displayed when created by `scripts/create_test_user.py` as `DEBUG_USER_ID`. Note that if you do not use an existing user ID, a new `users` row will be created with that ID.

When enabled, a warning log `AUTH_DISABLED=true: ...` will be output upon startup. In `FLASK_ENV=production`, it is forcibly disabled by configuration, so even if it remains in `.env`, it will have no effect in production. To revert, simply set `AUTH_DISABLED=false`.

### Supabase RLS

Read policy for private tables:

| Table | Read policy |
| --- | --- |
| `users` | Only rows matching `users.id = auth.uid()` can be read |
| `portfolio` | Only rows matching `portfolio.user_id = auth.uid()` can be read |
| `holdings` | Only rows matching `holdings -> portfolio.user_id = auth.uid()` can be read |
| `transactions` | Only rows matching `transactions -> holdings -> portfolio.user_id = auth.uid()` can be read |

Shared tables:

```text
currency
asset_type
asset_master
asset_data_history
currency_rate_history
```

Logged-in users can read shared tables. Private writes and table updates are handled through backend SQLAlchemy services authenticated with Supabase user context.

### Testing

To test configuration only:

```bash
.venv/bin/python -m unittest tests.test_config
```

To test Auth helper and configuration:

```bash
.venv/bin/python -m unittest tests.test_auth tests.test_config
```

To test portfolio creation API:

```bash
.venv/bin/python -m unittest tests.test_portfolio_create
```

To test cash deposits and withdrawals:

```bash
.venv/bin/python -m unittest tests.test_cash_transaction_create
```

To batch test portfolio read APIs:

```bash
.venv/bin/python -m unittest tests.test_portfolio_summary tests.test_portfolio_holdings \
    tests.test_portfolio_allocation tests.test_portfolio_performance
```

To test transaction creation and transaction history search:

```bash
.venv/bin/python -m unittest tests.test_transaction_create tests.test_transaction_history
```

To test asset historical price and currency rate import services:

```bash
.venv/bin/python -m unittest tests.test_asset_history_import tests.test_currency_rate_import
```

To verify Supabase connection and read permissions on all tables:

```bash
.venv/bin/python -W ignore::DeprecationWarning -m unittest tests.database_connection.test_supabase_connection
```

To verify that backend SQLAlchemy engine can connect to PostgreSQL using `DATABASE_URL`:

```bash
.venv/bin/python -m unittest tests.database_connection.test_sqlalchemy_connection
```

This connection test uses Supabase keys from `.env` and `tests/.env`. The template shared on GitHub is located at `tests/.env.example`, while actual test user credentials should be placed only in local `tests/.env`.

To enable connection tests, set the following in `tests/.env`:

```text
RUN_SUPABASE_CONNECTION_TESTS=true
```

Connection tests verify the following:

```text
Connection Setup: Create client with configured URL/key and verify active status via lightweight read
Basic Operations: Execute select limit 1 on reference tables and verify results can be received
Exception & Teardown: Verify exception is raised on invalid keys and HTTP client resources can be closed
```

For service role core table read checks, only `select("id").limit(1)` is executed against the following tables. No data creation, modification, or deletion is performed.

```text
users
portfolio
asset_master
currency
asset_type
asset_data_history
holdings
transactions
```

To run all unit tests:

```bash
.venv/bin/python -W ignore::DeprecationWarning -m unittest discover -s tests
```

To run only Database connection / Supabase-related tests:

```bash
.venv/bin/python -W ignore::DeprecationWarning -m unittest discover -s tests/database_connection -t .
```

Database connection / Supabase test details:

| Test file | Details |
| --- | --- |
| `test_supabase_connection.py` | Creates a client with Supabase config to verify basic read, invalid key exception, and client close/release. |
| `test_supabase_user_rls.py` | Verifies private/shared RLS with mock users when `RUN_SUPABASE_REAL_USER=false`, and verifies holdings isolation for real users when `true`. |

RLS tests toggle between mock user / real user via `RUN_SUPABASE_REAL_USER`:

```text
RUN_SUPABASE_REAL_USER=false  # Run private/public RLS tests using mock user
RUN_SUPABASE_REAL_USER=true   # Run RLS tests using real user
```

To verify data isolation between two users in Real-user RLS, configure the following in local `tests/.env`:

```text
RUN_SUPABASE_REAL_USER=true
RUN_SUPABASE_REAL_USER_BOOTSTRAP_DATA=true
SUPABASE_TEST_USER_EMAIL=
SUPABASE_TEST_USER_PASSWORD=
SUPABASE_SECOND_TEST_USER_EMAIL=
SUPABASE_SECOND_TEST_USER_PASSWORD=
```

When `RUN_SUPABASE_REAL_USER_BOOTSTRAP_DATA=true`, temporary mock holdings are created for test users who do not have holdings, and the created holdings / assets / portfolios are deleted after testing finishes.

### Database (Supabase)

The DB connects to Supabase PostgreSQL using Flask-SQLAlchemy. Connection information uses `DATABASE_URL` in `.env`, taking the Connection string directly from Supabase Dashboard > Project Settings > Database (driver is psycopg v3, `sslmode=require` is required). Refer to [`.env.example`](.env.example) for format.

Schema changes are managed via Flask-Migrate (Alembic):

```bash
.venv/bin/flask db migrate -m "add holdings table"   # Generate migration
.venv/bin/flask db upgrade                           # Apply migration
.venv/bin/flask db downgrade                         # Rollback migration
```

Place models in `app/models/` and **import them in `app/models/__init__.py`**. `flask db migrate` only inspects models registered in `db.metadata`; forgetting to import them will generate empty migrations.

### Documentation

| URL | Content |
| --- | --- |
| http://localhost:5001/docs | Swagger UI |
| http://localhost:5001/redoc | ReDoc |
| http://localhost:5001/openapi.json | OpenAPI 3.0.3 Specification |

The generated [`openapi.yaml`](openapi.yaml) has been committed to the repository. Regenerate it whenever schemas are updated:

```bash
.venv/bin/flask export-openapi                  # -> openapi.yaml
.venv/bin/flask export-openapi -f json          # -> openapi.json
```

**Schemas are the single source of truth for API design.** Updating `app/schemas/` will update specifications, validation, and Swagger UI altogether. Avoid manually editing specifications alone.

**Request validation functions** for all active endpoints. Input specifications can be tested directly in Swagger UI's Try it out (422 if validation fails).

### Endpoints

All under `/api/v1`. Refer to [`API_DESIGN.md`](API_DESIGN.md) for design background.

| Method | Path | Tag | Description |
| --- | --- | --- | --- |
| POST | `/portfolios/` | portfolio | Create portfolio |
| GET | `/portfolios/summary` | portfolio | Summary (cash balance, market value, total assets, unrealized P&L) |
| POST | `/portfolios/capital` | portfolio | Cash deposit & withdrawal (updates cash balance) |
| GET | `/portfolios/holdings` | portfolio | Holdings list |
| GET | `/portfolios/allocation` | portfolio | Asset allocation (by category, currency, ticker, sector) |
| GET | `/portfolios/performance` | portfolio | Performance history chart |
| GET | `/assets/{asset_id}/` | assets | Asset master info (deprecated, 501) |
| GET | `/assets/{asset_id}/price-history` | assets | Historical market prices (deprecated, 501) |
| GET | `/portfolios/transactions` | transactions | Search transaction history |
| POST | `/transactions` | transactions | Register transaction (single) |
| POST | `/transactions/batch` | transactions | Register transactions (batch) |

`POST /portfolios/` accepts any `currency` (frontend default is `USD`) and optional `cash_balance`, returning only `message` on success. Returns `409 Conflict` if the user already has a portfolio. `cash_balance` is registered as a cash holding (`CASH-USD`) upon portfolio creation, treated with a quantity equal to `cash_balance` and average cost of `1.0`.

```json
{
  "currency": "USD",
  "cash_balance": 1000000
}
```

`GET /portfolios/summary` はログイン user の portfolio から USD 建ての
サマリーを返す。`cash_balance` は cash holding を USD に換算して集計し、
`total_market_value` に含める。`total_return_percent` は cash balance を含む
資産総額から計算し、外部キャッシュフローは deposit/withdrawal で調整する。
buy/sell は内部の資産移動なので外部キャッシュフローには含めない。
市場価格と FX は Yahoo Finance から取得する。

`GET /portfolios/holdings` は cash を除いた保有残高一覧を USD 建てで返す。
`asset_type`（既定値 `all`）、`page`、`per_page` を受け取る。`asset_id` と
`search` は受け取らず、検索はフロントエンド側で行う。`items` は現在価格・取得単価・
評価額・当日騰落率・累計損益率を返す。現在価格と FX は Yahoo Finance から取得し、
前日終値は `asset_data_history` の `price_date < today` の最新 `close_price` を使う。
必要な market data が足りない holding は一覧と totals から除外する。`totals` は
ページング後の `items` ではなく、条件に一致した全 holding で集計する。

`GET /portfolios/allocation` は必須の `group_by`（`asset_type` / `currency` /
`asset` / `sector`）で集計した配分を USD 建てで返す。`items` は分類名を
`category`、USD 評価額を `value`、0〜1 の構成比を `weight`、区分に含まれる
holding 件数を `holdings_count` として `value` の降順で返す。cash holding も
1 区分として含めるが、`group_by=sector` だけは株式（`asset_type=stock`）に
限定し、Yahoo Finance の sector が取れない銘柄は集計から除く。市場価格と FX が
取れない holding も除外する。`as_of` は価格を取得した時刻。

`GET /portfolios/performance` は推移グラフを USD 建てで返す。`start_date`,
`end_date`, `range`, `interval` を取る。`range` は `1d` / `1w` / `1m` / `3m` /
`YTD` / `1y` / `all`（既定値 `all`）、`interval` は `1d` / `1wk` / `1mo`
（既定値 `1d`）。日付を指定した場合はそちらが優先され、レスポンスの `range` は
`null` になる。日次の評価額は `asset_data_history` の close price から組み立て、
各日の保有数量は取引履歴を現在の holdings から差し戻して復元する。cash holding は
グラフ上では期間中一定額として扱い、過去の FX は保存していないため現在のレートで換算する。
レスポンスは `return_1d`, `return_1w`, `return_1m`, `return_3m`, `return_YTD`,
`return_1y`, `return_total` をそれぞれ `{ amount, percent }` で返す。各期間の
return は対象期間の起点（例: `1w` なら 1 週間前）以降の買付・売却を調整して計算する。
各 return の損益額は `(現在資産総額 + 期間中の売却額) - (初期資産総額 +
期間中の買付額)`、比率は `損益額 / (初期資産総額 + 期間中の買付額)` とする。
評価額の系列は `range` に関わらず運用開始日（最初の取引日）から作るので、
表示期間を絞っても `return_total` は変わらない。

`/transactions` の絞り込みは `transaction_type`, `asset_type`（既定値
`all`）, `start_date`, `end_date`。`asset_id` と `search` は受け取らない。
履歴取得は `items` に `date`, `symbol`, `name`, `asset_type`, `quantity`,
`transaction_type`, `executed_price`, `executed_unit_price`, `realized_pl` を返す。
金額項目は USD 換算後の値で、`realized_pl` は sell のみ計算し、buy は `null`。
`totals` はページング前の
フィルタ適用後全件を対象に、`realized_pl`, `realized_pl_percent`, `currency`
を返す。単件作成と一括作成の各 item は `ticker`, `name`, `position`,
`order_type`, `transaction_type`, `quantity` を受け取り、成功時は作成された
取引の確認として `date`, `symbol`, `name`, `executed_price`,
`executed_unit_price`, `asset_type` の取引通貨建て約定サマリーを返す。新しい asset を
追加する場合は、Yahoo Finance API から取得した情報を `asset_master` に登録してから
取引を作成する。取引登録時は常に `CASH-USD` holding を更新する。USD 以外の銘柄は
約定金額を USD 換算し、`buy` は差し引き、`sell` は加える。

### 設計メモ

- **実際の証券発注は行わない。** 売買は取引履歴の記録、保有残高、cash holding
  の更新だけを行う。
- **所有者はログイン情報から解決する。** private API では client から
  `user_id` も `portfolio_id` も受け取らない。backend 内部では
  Supabase Auth user id と `portfolio.user_id` で対象データを解決する。
- **`portfolio_id` はレスポンスで返さない。** private なポートフォリオデータは
  ログイン情報から解決する想定で、クライアントには公開しない。
- **React から直接読む private data は Supabase RLS で守る。** 重要な write と
  ownership check は後続の SQLAlchemy 実装に寄せる。
- **`current_price` は保存しない。** 市場価格は Yahoo Finance または
  `asset_data_history` 由来で、Supabase `holdings` には書かない。
- **`cash_balance` は cash holding として扱う。** portfolio table には保存せず、
  `asset_type=cash` の asset を使って holdings に quantity `1` で登録する。
- **`holdings` 一覧は investment holding だけを返す。** cash は summary の
  `cash_balance` で扱い、holdings list には含めない。
- **一括登録は全件検証してから更新する。** 1 件でも不正なら何も更新しない。

Supabase のテーブル定義と将来の実装方針は
[`API_DESIGN.md`](API_DESIGN.md) にまとめてある。

### 構成
`POST /portfolios/capital` registers cash deposits (`deposit`) and withdrawals (`withdrawal`), updating the user's cash balance. Returns `400 Bad Request` if withdrawal exceeds available cash balance.

```json
{
  "transaction_type": "deposit",
  "amount": 5000,
  "currency": "USD"
}
```

`GET /portfolios/summary` returns a USD-denominated summary from the logged-in user's portfolio. `cash_balance` converts cash holdings into USD and is included in `total_market_value`. `total_return_percent` adjusts the cash-inclusive asset value for external deposits and withdrawals; buys and sells are internal transfers and are not treated as external cash flows.

`GET /portfolios/holdings` returns a list of non-cash holdings denominated in USD. Accepts `asset_type` (default `all`), `page`, and `per_page`. Does not accept `asset_id` or `search`; search is performed on the frontend. `items` returns current price, acquisition price, market value, daily gain/loss rate, and cumulative return rate. Current price and FX rates are retrieved from Yahoo Finance, and previous close price uses the latest `close_price` from `asset_data_history` where `price_date < today`. Holdings lacking required market data are excluded from the list and totals. `totals` aggregates across all matching holdings rather than paginated `items`.

`GET /portfolios/allocation` returns asset allocations aggregated in USD by required parameter `group_by` (`asset_type` / `currency` / `asset` / `sector`). `items` returns category name as `category`, USD valuation as `value`, component ratio (0–1) as `weight`, and count of holdings in the classification as `holdings_count`, sorted in descending order of `value`. Cash holdings are included as a category, but `group_by=sector` is restricted to stocks (`asset_type=stock`), excluding tickers whose Yahoo Finance sector cannot be retrieved. Holdings whose market price or FX cannot be obtained are also excluded. `as_of` represents the timestamp when prices were retrieved.

`GET /portfolios/performance` returns performance charts in USD. Accepts `start_date`, `end_date`, `range`, and `interval`. `range` accepts `1d` / `1w` / `1m` / `3m` / `YTD` / `1y` / `all` (default `all`), and `interval` accepts `1d` / `1wk` / `1mo` (default `1d`). If explicit dates are provided, they take precedence and response `range` becomes `null`. Daily valuation is constructed from close prices in `asset_data_history`, and daily holding quantities are reconstructed by tracing transactions back from current holdings. Cash holdings are treated as constant throughout the period, and past FX rates are converted using current rates since historical FX rates are not stored. Returns `return_1d`, `return_1w`, `return_1m`, `return_3m`, `return_YTD`, `return_1y`, and `return_total`, each formatted as `{ amount, percent }`. `today` is calculated as the difference between today's close price and previous day's close price, and return for each period is calculated as the difference between today's close price and the starting close price of the period (e.g. 1 week ago for `1w`). Valuation series are constructed from inception (first transaction date) regardless of `range`, so narrowing display range does not change `return_total`.

`GET /portfolios/transactions` filters transaction history by `transaction_type`, `asset_type` (default `all`), `start_date`, and `end_date`. Returns `date`, `symbol`, `name`, `asset_type`, `quantity`, `transaction_type`, `executed_price`, `executed_unit_price`, and `realized_pl` in `items`. Monetary fields are USD-denominated in the response. `realized_pl` is calculated for `sell` only (`null` for `buy`). `totals` returns `realized_pl`, `realized_pl_percent`, and `currency` for all records matching filters prior to pagination.

`POST /transactions` and `POST /transactions/batch` register single or multiple buy/sell transactions. Request items accept `ticker`, `name`, `transaction_type` (`buy`/`sell`), `trade_date`, `quantity`, and `executed_price` (or `price`). When adding a new asset, ticker information fetched from Yahoo Finance API is automatically registered into `asset_master` before creating transactions. Executing a `buy` transaction validates available cash balance, updates average cost and quantity for the holding, and automatically deducts the USD-converted purchase cost from `CASH-USD`. Executing a `sell` transaction validates that current holding quantity is sufficient, updates quantity, calculates realized P&L, and automatically adds the USD-converted proceeds to `CASH-USD`.

### Design Notes

- **No actual brokerage order execution.** Buying/selling only records transaction history, updates holdings balance, and adjusts cash balance (`CASH-USD`).
- **Owner is resolved from login context.** Private APIs do not receive `user_id` or `portfolio_id` from client. Internally, backend resolves target data using Supabase Auth user id (`g.current_user_id`) and `portfolio.user_id`.
- **`portfolio_id` is not returned in responses.** Private portfolio data is resolved from login context and is not exposed to client.
- **Private data access and writes.** Protected by Supabase Auth token validation in Flask (`require_auth()`) and Supabase RLS on direct database reads. Backend performs DB reads/writes via SQLAlchemy.
- **`current_price` is not stored.** Market prices originate from Yahoo Finance or `asset_data_history` and are not written to Supabase `holdings`.
- **`cash_balance` is handled as a cash holding.** Stored in `holdings` with asset `CASH-USD` (`asset_type=cash`). Deposits and withdrawals are processed via `POST /portfolios/capital`.
- **`holdings` list returns investment holdings only.** Cash is handled in summary `cash_balance` and not included in holdings list.
- **Batch registration validates all items before updating.** If even 1 item is invalid, nothing is updated.
- **Automatic historical price and FX backfills.** Registering a transaction automatically schedules or imports missing historical close prices (`asset_data_history`) and exchange rates (`currency_rate_history`) needed for performance calculation.

Supabase table definitions and detailed API design policies are summarized in [`API_DESIGN.md`](API_DESIGN.md).

### Project Structure

```text
app/
├── schemas/       Marshmallow schemas (= OpenAPI definitions. Main source of truth)
│   ├── portfolio.py   Summary / Allocation / Performance chart
│   ├── asset.py       Asset master / Price history
│   ├── holding.py     Holdings balance
│   ├── transaction.py Transaction history & creation schemas
│   ├── user.py        User schema
│   └── common.py      Common validators, pagination / date range
├── api/           Endpoint definitions (Paths, I/O, service calls)
│   ├── assets.py      Asset master endpoints (deprecated)
│   ├── parameters.py  OpenAPI definitions for path parameters
│   ├── portfolios.py  Portfolio endpoints (Summary, Holdings, Allocation, Performance, Capital)
│   └── transactions.py Transaction endpoints (History, Single Create, Batch Create)
├── models/        SQLAlchemy models (Supabase public schema)
│   ├── user.py        public.users
│   ├── portfolio.py   portfolio
│   ├── holding.py     holdings
│   ├── asset.py       currency / asset_type / asset_master / asset_data_history
│   │                  / currency_rate_history
│   └── transaction.py transactions
├── auth.py        Validates Supabase access token and sets g.current_user_id
├── enums.py       TransactionType / Interval
├── services/
│   ├── asset_history.py           Backfills & imports historical asset close prices
│   ├── common.py                  Service constants, authenticated user resolution, Decimal conversions
│   ├── currency_rate_history.py   Backfills & imports historical currency rates
│   ├── market_data.py             Fetches prices, FX, and sector from Yahoo Finance
│   ├── performance.py             Business logic for performance charts (valuation series and period returns)
│   ├── portfolio.py               Business logic for portfolio / summary / holdings / allocation
│   ├── supabase.py                Creates Supabase client from Flask app.config
│   └── transaction.py             Business logic for transaction search, buy/sell creation, cash deposit/withdrawal
└── config.py      Configuration (Includes OpenAPI / Supabase settings)

tests/
├── config.py
├── test_asset_history_import.py
├── test_auth.py
├── test_cash_transaction_create.py
├── test_config.py
├── test_currency_rate_import.py
├── test_portfolio_allocation.py
├── test_portfolio_create.py
├── test_portfolio_holdings.py
├── test_portfolio_performance.py
├── test_portfolio_summary.py
├── test_transaction_create.py
├── test_transaction_history.py
└── database_connection/
    ├── helpers.py
    ├── test_sqlalchemy_connection.py
    ├── test_supabase_connection.py
    └── test_supabase_user_rls.py

scripts/
├── create_test_user.py               Prepares Supabase Auth test user and public.users row
├── generate_token.py                 Generates access token for manual Swagger UI testing
├── import_asset_history.py           Imports asset historical prices from Yahoo Finance
├── import_currency_rate_history.py   Imports currency rate history from Yahoo Finance
└── seed_asset_data_history.py        Seeds asset price history data for local testing
```

### Unimplemented Features

Only the deprecated legacy asset endpoints (`GET /api/v1/assets/{asset_id}/` and `GET /api/v1/assets/{asset_id}/price-history`) return `501 Not Implemented`.

All core business logic for portfolio summary, holdings list, asset allocation, performance charting, cash deposit/withdrawal, single and batch buy/sell transaction creation, transaction history search, and background asset/FX history synchronization are fully implemented.
