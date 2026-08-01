# Portfolio Manager API Design

## 目的

Portfolio Manager backend は、個人向けポートフォリオ管理 API の Flask
アプリケーションである。現時点では OpenAPI / Swagger UI と
Marshmallow schema による request / response validation を中心に実装している。

`POST /api/v1/portfolios/` は実装済みで、それ以外の portfolio / assets /
transactions の業務処理はまだ未実装。Supabase 接続設定、Supabase client helper、
database connection tests、RLS tests は実装済み。

この API は実際の証券発注を行わない。buy / sell は将来的に取引履歴の記録と
holdings の更新だけを行う。

## 現在の方針

### Frontend / Backend / Supabase

- React は Supabase Auth を直接使って signup / login する。
- React は Supabase access token を使って private table を直接 read できる。
- private table の read 制御は Supabase RLS で行う。
- React が Flask private API を呼ぶ場合は
  `Authorization: Bearer <access_token>` を header に付ける。
- この branch は Flask 側の Auth context を準備する。
- holdings / transactions などの業務 DB read/write と row ownership check は、
  後続の SQLAlchemy branch で `g.current_user_id` を使って実装する。

### Private Data Access

private portfolio data では client から owner identifier を受け取らない。

- `user_id` は path / query / request body に出さない。
- `portfolio_id` も private endpoint の path / query / request body に出さない。
- backend はログイン済み user context から対象 user / portfolio を解決する。
- response にも `portfolio_id` は返さない。
- public asset / Yahoo Finance market data は portfolio scope を持たない。

この設計により、client が他人の `portfolio_id` を指定して存在確認する経路を
作らない。

## Swagger Sections

| Tag | Japanese label | 内容 |
| --- | --- | --- |
| `portfolio` | ポートフォリオ関連 | portfolio 作成、summary、holdings、allocation、performance |
| `assets` | 資産関連 | asset master と market price |
| `transactions` | 取引履歴関連 | buy / sell transaction history |

すべての API path は `/api/v1` 配下。

## Current Endpoints

### Portfolio

| Method | Path | 状態 | 内容 |
| --- | --- | --- | --- |
| `POST` | `/api/v1/portfolios/` | 201 | portfolio を作成する |
| `GET` | `/api/v1/portfolios/summary` | 501 | cash balance、market value、return rate を返す |
| `GET` | `/api/v1/portfolios/holdings` | 501 | holdings list、totals、pagination を返す |
| `GET` | `/api/v1/portfolios/allocation` | 501 | `asset_type` / `currency` / `asset` / `sector` で配分を返す |
| `GET` | `/api/v1/portfolios/performance` | 501 | graph-ready performance points を返す |

`GET /portfolios/holdings` の filter:

- `asset_type`: optional, default `all`
- `page`
- `per_page`

`GET /portfolios/allocation` の filter:

- `group_by`: `asset_type`, `currency`, `asset`, `sector`

`GET /portfolios/performance` の filter:

- `start_date`
- `end_date`
- `interval`: `1d`, `1wk`, `1mo`

### Assets

| Method | Path | 状態 | 内容 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/assets/{asset_id}/` | 501 | asset master record を返す |
| `GET` | `/api/v1/assets/{asset_id}/price-history` | 501 | historical OHLCV / close price data を返す |

assets endpoint は public data を扱うため、`user_id` は不要。
保有数量や平均取得単価は holdings 側の private data として扱う。

### Transactions

| Method | Path | 状態 | 内容 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/portfolios/transactions` | 501 | transaction history、realized P/L、pagination を返す |
| `POST` | `/api/v1/transactions` | 501 | 1 件の buy / sell を登録し holdings を更新する |
| `POST` | `/api/v1/transactions/batch` | 501 | 複数 transaction をまとめて登録する |

`GET /portfolios/transactions` の filter:

- `transaction_type`
- `asset_type`
- `start_date`
- `end_date`
- `page`
- `per_page`

transaction write の将来挙動:

- body の `ticker` + `name` とログイン user の portfolio から asset / holding を探す。
- `buy` は transaction を追加し、holding quantity を増やし、average cost を再計算する。
- `sell` は transaction を追加し、holding quantity を減らす。
- holding quantity を超える `sell` は `400`。
- batch は全件 validation 後にまとめて更新する。1 件でも不正なら何も更新しない。

## Supabase Database Design

現在の設計では、private data と shared data を分けて扱う。

### Private Tables

| Table | 主な owner relation |
| --- | --- |
| `users` | `users.id` が Supabase Auth user id と一致する |
| `portfolio` | `portfolio.user_id -> users.id` |
| `holdings` | `holdings.portfolio_id -> portfolio.id` |
| `transactions` | `transactions.holding_id -> holdings.id -> portfolio.id` |

private table の RLS:

| Table | RLS read rule |
| --- | --- |
| `users` | `users.id = auth.uid()` |
| `portfolio` | `portfolio.user_id = auth.uid()` |
| `holdings` | `holdings -> portfolio.user_id = auth.uid()` |
| `transactions` | `transactions -> holdings -> portfolio.user_id = auth.uid()` |

React user には通常の `INSERT` / `UPDATE` / `DELETE` policy を追加しない。
重要な write は Flask backend 経由にするが、実装主線は後続の SQLAlchemy branch に寄せる。

### Shared Tables

| Table | 内容 |
| --- | --- |
| `currency` | 通貨 code / symbol |
| `asset_type` | stock, bond, etf などの asset type |
| `asset_master` | ticker, name, asset_type_id, currency_id |
| `asset_data_history` | historical close price |

logged-in user は shared tables を read できる。write 方針は SQLAlchemy branch
で backend DB 実装と合わせて整理する。

### Table Notes

#### `users`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | Supabase Auth user id と一致させる |
| `email` | text | user email |
| `name` | varchar | optional display name |
| `created_at` | timestamptz | default `now()` |
| `updated_at` | timestamptz | default `now()` |

production では password を application table に保存しない。password は Supabase
Auth 側で管理する。

#### `portfolio`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | internal id。private API response では返さない |
| `user_id` | uuid | owner; `users.id` を参照 |
| `name` | text | default portfolio name |
| `created_at` | timestamptz | default `now()` |
| `updated_at` | timestamptz | default `now()` |

#### `asset_master`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | API response では `asset_id` として返す |
| `ticker` | text | Yahoo Finance ticker |
| `name` | text | asset name |
| `asset_type_id` | uuid | `asset_type.id` を参照 |
| `currency_id` | uuid | `currency.id` を参照 |

Review note: `asset_master.asset_type` の text column は削除済み。資産クラスは
`asset_type_id -> asset_type.id` で参照する。

#### `holdings`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | holding id |
| `portfolio_id` | uuid | `portfolio.id` を参照 |
| `asset_id` | uuid | `asset_master.id` を参照 |
| `quantity` | numeric | 現在の保有数量 |
| `average_cost` | numeric | 平均取得単価 |
| `updated_at` | timestamptz | default `now()` |

金額や数量は float ではなく `numeric` で保存する。`current_price` は holdings
に保存しない。market price は Yahoo Finance または `asset_data_history` から取る。

#### `transactions`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | transaction id |
| `holding_id` | uuid | `holdings.id` を参照 |
| `transaction_type` | text | `buy` / `sell` などの取引種別 |
| `trade_date` | date | trade date |
| `quantity` | numeric | transaction quantity |
| `price` | numeric | transaction price |
| `fees` | numeric | default `0` |
| `created_at` | timestamptz | default `now()` |

`transactions` に `user_id` / `portfolio_id` / `asset_id` は追加しない。
ownership は `transactions -> holdings -> portfolio -> users` で解決する。

#### `asset_data_history`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | history row id |
| `asset_id` | uuid | `asset_master.id` を参照 |
| `price_date` | date | market price date |
| `close_price` | numeric | historical close price |

## Supabase Client / Config

Flask app では Supabase 設定を直接 `os.getenv` で読まない。`app.config` を経由し、
`app.services.supabase` で Auth / test 用 client を作成する。

```python
from app.services.supabase import get_supabase_anon_client

client = get_supabase_anon_client()
```

Review note: この branch では Supabase client を Auth context と接続検証に限定し、
portfolio / holdings / transactions の業務 CRUD は SQLAlchemy branch に残す。

主な helper:

| Function | 用途 |
| --- | --- |
| `get_supabase_anon_client()` | Auth token 検証用の cached anon client を返す |
| `get_supabase_service_client()` | 接続確認・RLS 検証用の cached service role client を返す |
| `create_supabase_anon_client()` | session を分けたい test 用の non-cached anon client |
| `create_supabase_service_client()` | 接続確認・diagnostics 用の non-cached service role client |
| `close_supabase_client(client)` | HTTP resources を解放する |
| `close_supabase_clients(app=None)` | Flask app に cached された clients を解放する |

## Flask Auth Context

`app.auth.require_auth()` は Supabase Auth の access token を検証し、Flask の
request context に current user を保存する。

Request:

```http
Authorization: Bearer <supabase_access_token>
```

Backend context:

```python
from flask import g

g.current_user_id
g.current_user_email
g.current_access_token
```

private API 実装では `user_id` を request body / query から受け取らず、
`g.current_user_id` を使う。Swagger UI では OpenAPI security scheme
`bearerAuth` を使うため、右上の Authorize button から token を入力できる。

## Test Design

### Unit Tests

```bash
.venv/bin/python -m unittest tests.test_config
```

`tests.test_config` は以下を確認する。

- `app/config.py` が Supabase env を `TestingConfig` に反映する。
- secrets 未設定時は safe local defaults になる。
- Supabase client helper が Flask `app.config` を使う。
- 必要な config key がない場合は明確に失敗する。

```bash
.venv/bin/python -m unittest tests.test_auth
```

`tests.test_auth` は以下を確認する。

- Bearer token から Supabase Auth user を取得し、`g.current_user_id` を設定する。
- token がない場合は `401`。
- token が不正または期限切れの場合は `401`。

### Database Connection Tests

```bash
.venv/bin/python -W ignore::DeprecationWarning -m unittest tests.database_connection.test_supabase_connection
```

有効化:

```text
RUN_SUPABASE_CONNECTION_TESTS=true
```

確認内容:

- Connection Setup: 正しい URL / key で client を作成できる。
- Basic Operations: reference table に軽量 read を実行できる。
- Exception: 不正 key では例外を捕捉できる。
- Teardown: client resource を close / release できる。

### RLS Tests

```bash
.venv/bin/python -W ignore::DeprecationWarning -m unittest tests.database_connection.test_supabase_user_rls
```

`RUN_SUPABASE_REAL_USER` で mock user / real user を切り替える。

```text
RUN_SUPABASE_REAL_USER=false
```

mock user mode:

- temporary Auth users を作成する。
- users / portfolio / holdings / transactions が自分の rows だけ見えることを確認する。
- shared tables を read できることを確認する。
- shared/private table への direct write が拒否されることを確認する。
- 作成した test data は teardown で削除する。

```text
RUN_SUPABASE_REAL_USER=true
SUPABASE_TEST_USER_EMAIL=
SUPABASE_TEST_USER_PASSWORD=
SUPABASE_SECOND_TEST_USER_EMAIL=
SUPABASE_SECOND_TEST_USER_PASSWORD=
```

real user mode:

- 実在 user で login する。
- user A / user B の holdings が互いに見えないことを確認する。
- direct insert が拒否されることを確認する。
- `RUN_SUPABASE_REAL_USER_BOOTSTRAP_DATA=true` の場合、holding がない user に
  temporary mock holding を作成し、test 後に削除する。

## Run Locally

```bash
export FLASK_APP=wsgi.py
.venv/bin/flask run --port=5001
```

5001 が使えない場合:

```bash
.venv/bin/flask run --port=5003
```

Swagger UI:

```text
http://localhost:5001/docs
http://localhost:5003/docs
```

OpenAPI export:

```bash
.venv/bin/flask export-openapi
.venv/bin/flask export-openapi -f json
```
