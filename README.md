## Portfolio Manager (Tokyo Team)

Backend repository for the Portfolio Management API. Currently, OpenAPI / Swagger UI and request/response schemas are defined using Flask + flask-smorest. `POST /api/v1/portfolios/` is implemented, while business logic for other portfolio / assets / transactions operations is not yet implemented.

Supabase connection setup, Supabase client helpers, database connection tests, and RLS tests are implemented.

### User Story

1. As an investor, I want to register my assets so that I can manage my holdings in one place.
2. As an investor, I want to view the current value of my portfolio so that I can understand my overall finalcial position.
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

`get_supabase_anon_client()` uses `current_app.config["SUPABASE_URL"]` and `current_app.config["SUPABASE_ANON_KEY"]` for validating Supabase Auth tokens. `get_supabase_service_client()` remains as a helper for connection tests and RLS verification, but is not used for primary business CRUD operations on portfolios / holdings / transactions. `get_*_client()` functions are cached on the Flask app. If you need to separate sessions across multiple users in tests, use a non-cached client creator such as `create_supabase_anon_client()`.

### Authentication Policy

- React handles signup / login directly using Supabase Auth.
- When React reads private tables directly, access is protected by Supabase access tokens and RLS.
- When React calls Flask private APIs, include `Authorization: Bearer <access_token>` in the request header.
- This branch is responsible for creating the Auth context on the Flask side.
- Business DB read/write operations and ownership checks for holdings / transactions will be implemented using `g.current_user_id` in subsequent SQLAlchemy branches.

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

> Review note: This branch only prepares authentication; authorization checks and business DB writes will be implemented after merging with the SQLAlchemy branch.

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

Logged-in users can read shared tables. Write policies will be organized along with backend DB implementation in the SQLAlchemy branch.

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

To batch test portfolio read APIs:

```bash
.venv/bin/python -m unittest tests.test_portfolio_summary tests.test_portfolio_holdings \
    tests.test_portfolio_allocation tests.test_portfolio_performance
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

To run all tests:

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

The DB connects to Supabase PostgreSQL using Flask-SQLAlchemy. Connection information uses only `DATABASE_URL` in `.env`, taking the Connection string directly from Supabase Dashboard > Project Settings > Database (driver is psycopg v3, `sslmode=require` is required). Refer to [`.env.example`](.env.example) for format.

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

**Request validation functions** even for unimplemented endpoints, allowing verification of input specs in Swagger UI's Try it out (501 if unimplemented, 422 if validation fails).

### Endpoints

All under `/api/v1`. Refer to [`API_DESIGN.md`](API_DESIGN.md) for design background.

| Method | Path | Tag | Description |
| --- | --- | --- | --- |
| POST | `/portfolios/` | portfolio | Create portfolio |
| GET | `/portfolios/summary` | portfolio | Summary (acquisition value, market value, total assets, unrealized P&L) |
| GET | `/portfolios/holdings` | portfolio | Holdings list |
| GET | `/portfolios/allocation` | portfolio | Asset allocation (by category, currency, ticker) |
| GET | `/portfolios/performance` | portfolio | Performance history chart |
| GET | `/assets/{asset_id}/` | assets | Asset master info (deprecated) |
| GET | `/assets/{asset_id}/price-history` | assets | Historical market prices (deprecated) |
| GET | `/portfolios/transactions` | transactions | Search transaction history |
| POST | `/transactions` | transactions | Register transaction (single) |
| POST | `/transactions/batch` | transactions | Register transactions (batch) |

`POST /portfolios/` accepts any `currency` (frontend default is `USD`) and optional `cash_balance`, returning only `message` on success. Returns `409 Conflict` if the user already has a portfolio. `cash_balance` is registered as a cash holding upon portfolio creation, treated with a quantity of `1`. Portfolios do not have a name property.

```json
{
  "currency": "USD",
  "cash_balance": 1000000
}
```

`GET /portfolios/summary` returns a USD-denominated summary from the logged-in user's portfolio. `cash_balance` converts cash holding into USD for aggregation, while `total_market_value` and `total_return_percent` are calculated using non-cash holdings only. Market prices and FX rates are fetched from Yahoo Finance and not stored in the DB.

`GET /portfolios/holdings` returns a list of non-cash holdings denominated in USD. Accepts `asset_type` (default `all`), `page`, and `per_page`. Does not accept `asset_id` or `search`; search is performed on the frontend. `items` returns current price, acquisition price, market value, daily gain/loss rate, and cumulative return rate. Current price and FX rates are retrieved from Yahoo Finance, and previous close price uses the latest `close_price` from `asset_data_history` where `price_date < today`. Holdings lacking required market data are excluded from the list and totals. `totals` aggregates across all matching holdings rather than paginated `items`.

`GET /portfolios/allocation` returns asset allocations aggregated in USD by required parameter `group_by` (`asset_type` / `currency` / `asset` / `sector`). `items` returns category name as `category`, USD valuation as `value`, component ratio (0–1) as `weight`, and count of holdings in the classification as `holdings_count`, sorted in descending order of `value`. Cash holdings are included as a category, but `group_by=sector` is restricted to stocks (`asset_type=stock`), excluding tickers whose Yahoo Finance sector cannot be retrieved. Holdings whose market price or FX cannot be obtained are also excluded. `as_of` represents the timestamp when prices were retrieved.

`GET /portfolios/performance` returns performance charts in USD. Accepts `start_date`, `end_date`, `range`, and `interval`. `range` accepts `1d` / `1w` / `1m` / `3m` / `YTD` / `1y` / `all` (default `all`), and `interval` accepts `1d` / `1wk` / `1mo` (default `1d`). If explicit dates are provided, they take precedence and response `range` becomes `null`. Daily valuation is constructed from close prices in `asset_data_history`, and daily holding quantities are reconstructed by tracing transactions back from current holdings. Cash holdings are treated as constant throughout the period, and past FX rates are converted using current rates since historical FX rates are not stored. Returns `return_1d`, `return_1w`, `return_1m`, `return_3m`, `return_YTD`, `return_1y`, and `return_total`, each formatted as `{ amount, percent }`. `today` is calculated as the difference between today's close price and previous day's close price, and return for each period is calculated as the difference between today's close price and the starting close price of the period (e.g. 1 week ago for `1w`). Valuation series are constructed from inception (first transaction date) regardless of `range`, so narrowing display range does not change `return_total`.

Filtering for `/transactions` includes `transaction_type`, `asset_type` (default `all`), `start_date`, and `end_date`. `asset_id` and `search` are not accepted. History retrieval returns `date`, `symbol`, `name`, `asset_type`, `quantity`, `transaction_type`, `executed_price`, `executed_unit_price`, and `realized_pl` in `items`. `realized_pl` is calculated for `sell` only (`null` for `buy`). `totals` returns `realized_pl`, `realized_pl_percent`, and `currency` for all records matching filters prior to pagination. Single and batch creation items accept `ticker`, `name`, `position`, `order_type`, `transaction_type`, and `quantity`, returning execution summary of `date`, `symbol`, `name`, `executed_price`, `executed_unit_price`, and `asset_type` as confirmation of created transactions on success. When adding a new asset, information fetched from Yahoo Finance API is registered into `asset_master` before creating transactions. Transaction registration always updates the `CASH-USD` holding. Non-USD tickers have execution amounts converted to USD, subtracting for `buy` and adding for `sell`.

### Design Notes

- **No actual brokerage order execution.** Buying/selling only records transaction history and updates holdings balance and cash holding.
- **Owner is resolved from login information.** Private APIs do not receive `user_id` or `portfolio_id` from client. Internally, backend resolves target data using Supabase Auth user id and `portfolio.user_id`.
- **`portfolio_id` is not returned in responses.** Private portfolio data is assumed to be resolved from login context and is not exposed to client.
- **Private data read directly from React is protected by Supabase RLS.** Critical writes and ownership checks are deferred to upcoming SQLAlchemy implementation.
- **`current_price` is not stored.** Market prices originate from Yahoo Finance or `asset_data_history` and are not written to Supabase `holdings`.
- **`cash_balance` is handled as a cash holding.** Not stored in portfolio table; registered in holdings with quantity `1` using asset of `asset_type=cash`.
- **`holdings` list returns investment holdings only.** Cash is handled in summary `cash_balance` and not included in holdings list.
- **Batch registration validates all items before updating.** If even 1 item is invalid, nothing is updated.

Supabase table definitions and future implementation policies are summarized in [`API_DESIGN.md`](API_DESIGN.md).

### Project Structure

```text
app/
├── schemas/       Marshmallow schemas (= OpenAPI definitions. Main source of truth)
│   ├── portfolio.py   Summary / Allocation / Performance chart
│   ├── asset.py       Asset master / Price history
│   ├── holding.py     Holdings balance
│   ├── transaction.py Transaction history
│   └── common.py      Common validators, pagination / date range
├── api/           Endpoint definitions (Paths, I/O, service calls)
│   └── parameters.py  OpenAPI definitions for path parameters
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
│   ├── common.py      Service constants, authenticated user resolution, Decimal conversions
│   ├── market_data.py Fetches prices, FX, and sector from Yahoo Finance
│   ├── performance.py Business logic for performance charts (valuation series and period returns)
│   ├── portfolio.py   Business logic for portfolio / summary / holdings / allocation
│   └── supabase.py    Creates Supabase client from Flask app.config
└── config.py      Configuration (Includes OpenAPI / Supabase settings)

tests/
├── config.py
├── test_auth.py
├── test_config.py
├── test_portfolio_allocation.py
├── test_portfolio_create.py
├── test_portfolio_holdings.py
├── test_portfolio_performance.py
├── test_portfolio_summary.py
└── database_connection/
    ├── helpers.py
    ├── test_sqlalchemy_connection.py
    ├── test_supabase_connection.py
    └── test_supabase_user_rls.py

scripts/
├── create_test_user.py  Prepares Supabase Auth test user and public.users row
└── generate_token.py    Generates access token for manual Swagger UI testing
```

### Unimplemented Features

Actual API business logic for assets and transactions.
Read APIs for summary / holdings / allocation / performance, Supabase Auth token validation, Yahoo Finance price/FX/sector fetching, SQLAlchemy connection, and DB migration management are already implemented.
