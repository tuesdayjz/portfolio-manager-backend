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
| `GET` | `/api/v1/portfolios/summary` | 200 | USD の cash balance、market value、return rate を返す |
| `GET` | `/api/v1/portfolios/holdings` | 200 | USD の holdings list、totals、pagination を返す |
| `GET` | `/api/v1/portfolios/allocation` | 200 | `asset_type` / `currency` / `asset` / `sector` で配分を返す |
| `GET` | `/api/v1/portfolios/performance` | 200 | graph-ready performance points と期間別 return を返す |

`GET /portfolios/summary`:

- response currency は `USD` 固定。`currency_symbol` は USD の symbol、未設定なら `$`。
- `cash_balance` は cash holding の `average_cost * quantity` を USD 換算して合計する。
- `total_market_value` は cash 以外の holding だけを対象に、Yahoo Finance の現在価格、
  quantity、FX で USD 評価額を計算する。
- `total_return_percent` は cash 以外の holding の市場評価額と
  `average_cost * quantity` の USD 換算取得価額から計算する。
- Yahoo price / FX が取れない holding は集計から除外する。

`GET /portfolios/holdings` の filter:

- `asset_type`: optional, default `all`
- `page`
- `per_page`

`GET /portfolios/holdings` の response:

```json
{
  "items": [
    {
      "ticker": "7203.T",
      "name": "Toyota Motor Corp.",
      "asset_type": "stock",
      "quantity": 8.5,
      "average_purchase_price": 1095.8,
      "total_purchase_price": 9314.3,
      "current_price": 2980.5,
      "total_market_value": 25334.25,
      "today_return_percent": 1.8,
      "total_return_percent": 12.4,
      "currency": "USD"
    }
  ],
  "totals": {
    "market_value": 4220000,
    "day_change": 42150,
    "day_change_percent": 1.01,
    "currency": "USD"
  },
  "pagination": {
    "page": 1,
    "per_page": 5,
    "total_items": 24,
    "total_pages": 5
  }
}
```

holdings response の計算:

- cash holding は `items` と investment totals に含めない。`asset_type=cash` filter では
  空の list と zero totals を返す。
- 現在価格と FX は Yahoo Finance から取得し、USD に換算して返す。
- `average_purchase_price` は `average_cost * FX`。
- `total_purchase_price` は `average_cost * quantity * FX`。
- `total_market_value` は `quantity * current_price * FX`。
- `today_return_percent` は USD 換算 current price と前日終値の比較。
- 前日終値は `asset_data_history` の `price_date < today` の最新 `close_price`。
- `total_return_percent` は USD 換算 current price と USD 換算 average cost の比較。
- current price / FX / previous close が取れない holding は response から除外する。
- totals は pagination 後の items ではなく、filter に一致した全 valid holdings で集計する。

`GET /portfolios/allocation` の filter:

- `group_by`: `asset_type`, `currency`, `asset`, `sector`（required）

`GET /portfolios/allocation` の response:

```json
{
  "group_by": "asset_type",
  "currency": "USD",
  "total_value": 2350,
  "items": [
    { "category": "stock", "value": 1030, "weight": 0.4383, "holdings_count": 2 },
    { "category": "cash", "value": 1000, "weight": 0.4255, "holdings_count": 1 },
    { "category": "etf", "value": 320, "weight": 0.1362, "holdings_count": 1 }
  ],
  "as_of": "2026-08-02T14:25:00+00:00"
}
```

allocation response の計算:

- response currency は `USD` 固定。評価額は holdings と同じく
  `quantity * current_price * FX` で計算する。
- cash holding は `average_cost * quantity * FX` を評価額として集計に含める。
  cash を持たないのは `group_by=sector` のときだけ。
- `category` は集計基準ごとの区分名。`asset_type` は資産クラス名、`currency` は
  asset の元通貨コード、`asset` は銘柄名（無ければ ticker）、`sector` は
  Yahoo Finance の sector。
- `group_by=sector` は株式（`asset_type=stock`）だけを対象にし、sector が
  取れない銘柄は除外する。`total_value` も株式ぶんだけの合計になる。
- `weight` は `value / total_value` の 0〜1 の割合。`total_value` が 0 なら 0。
- `items` は `value` の降順。同額のときは `category` 名の昇順。
- `holdings_count` はその区分に含まれる holding 件数。
- current price / FX が取れない holding は集計から除外する。
- `as_of` は市場価格を取得した時刻（UTC）。

`GET /portfolios/performance` の filter:

- `start_date`
- `end_date`
- `range`: `1d`, `1w`, `1m`, `3m`, `YTD`, `1y`, `all`（既定値 `all`）
- `interval`: `1d`, `1wk`, `1mo`（既定値 `1d`）

`GET /portfolios/performance` の response:

```json
{
  "currency": "USD",
  "interval": "1d",
  "range": "all",
  "start_date": "2026-07-24",
  "end_date": "2026-08-03",
  "metrics": {
    "portfolio_value": 2000,
    "today": { "amount": 50, "percent": 2.56 },
    "return": { "amount": 200, "percent": 11.11 },
    "total_return": { "amount": 200, "percent": 11.11 }
  },
  "return_1d": { "amount": 50, "percent": 2.56 },
  "return_1w": { "amount": 100, "percent": 5.26 },
  "return_1m": { "amount": 200, "percent": 11.11 },
  "return_3m": { "amount": 200, "percent": 11.11 },
  "return_YTD": { "amount": 200, "percent": 11.11 },
  "return_1y": { "amount": 200, "percent": 11.11 },
  "return_total": { "amount": 200, "percent": 11.11 },
  "points": [
    { "date": "2026-07-24", "total_market_value": 1800 },
    { "date": "2026-08-03", "total_market_value": 2000 }
  ]
}
```

performance response の計算:

- response currency は `USD` 固定。評価額は現金を含む総資産額。
- 日次の評価額は `asset_data_history` の `close_price` から組み立てる。終値の無い日は
  直近の終値で評価する。summary / holdings と違い、Yahoo Finance の現在価格は使わない。
- 各日の保有数量は、現在の `holdings.quantity` から `trade_date` がその日より後の
  transaction を差し戻して復元する（`buy` は減算、`sell` は加算）。
- 期間の起点（運用開始日）は最初の `trade_date`。transaction がまだ無い場合は
  価格データのある最も古い日。評価額の系列は必ずこの日から作るので、
  `range` を絞っても `return_total` は変わらない。
- cash holding は取引履歴を持たないため、期間中は一定額として扱う。
- 過去の FX レートは保存していないため、全期間を通して現在のレートで換算する。
- `range` と `start_date` / `end_date` の両方が来た場合は日付を優先し、
  response の `range` は `null` になる。未来の `end_date` は今日に丸める。
- `return_*` は as-of（= `end_date`）時点の評価額と、各期間の起点日以前で
  最も新しい評価額との差分。`return_YTD` の起点は前年最終営業日の終値。
  起点より前のデータが無い期間は、記録のある最も古い評価額を起点にする。
- `metrics.today` は `return_1d`、`metrics.total_return` は `return_total` と一致する。
  `metrics.return` は `range`（または `start_date`）で指定した期間の損益。
- `points` は `interval` ごとに間引く。`1wk` は各 ISO 週、`1mo` は各月の最後の点を残す。
- FX が取れない holding と、価格データがまだ無い holding は集計から除外する。

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
| `GET` | `/api/v1/portfolios/transactions` | 200 | transaction history、realized P/L、pagination を返す |
| `POST` | `/api/v1/transactions` | 501 | 1 件の buy / sell を登録し holdings を更新する |
| `POST` | `/api/v1/transactions/batch` | 501 | 複数 transaction をまとめて登録する |

`GET /portfolios/transactions` の filter:

- `transaction_type`
- `asset_type`
- `start_date`
- `end_date`
- `page`
- `per_page`

response は `items` に `transaction_id`, `date`, `symbol`, `name`, `asset_type`,
`quantity`, `transaction_type`, `executed_price`, `executed_unit_price`,
`realized_pl` を返す。`realized_pl` は sell のみ計算し、buy は `null`。`totals`
はページング前のフィルタ適用後全件を対象にする。

transaction write の将来挙動:

- body の `ticker` + `name` とログイン user の portfolio から asset / holding を探す。
- `buy` は transaction を追加し、holding quantity を増やし、average cost を再計算し、
  約定金額を USD 換算して `CASH-USD` holding から差し引く。
- `sell` は transaction を追加し、holding quantity を減らし、約定金額を USD 換算して
  `CASH-USD` holding に加える。
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
| `currency_rate_history` | 通貨ごとの USD 建て historical close rate |

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
| `average_cost_before` | numeric | 取引前の平均取得単価 |
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

#### `currency_rate_history`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid | history row id |
| `currency_id` | uuid | `currency.id` を参照 |
| `rate_date` | date | rate date |
| `close_price` | numeric | 1 通貨単位あたりの USD 建て終値 |

`close_price` の向きは Yahoo Finance の `<CUR>USD=X` と同じ（例: `JPYUSD=X`）。
USD 自身のレートは常に 1 なので row を持たない。`(currency_id, rate_date)` が
unique。

## Supabase Client / Config

Flask app では Supabase 設定を直接 `os.getenv` で読まない。`app.config` を経由し、
`app.services.supabase` で Auth / test 用 client を作成する。

```python
from app.services.supabase import get_supabase_anon_client

client = get_supabase_anon_client()
```

Review note: Supabase client は Auth context と接続検証に限定する。
portfolio summary / holdings read は SQLAlchemy で実装済み。transactions write など
残りの業務 CRUD は後続実装に残す。

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

```bash
.venv/bin/python -m unittest tests.test_portfolio_create tests.test_portfolio_summary tests.test_portfolio_holdings
```

portfolio API tests は以下を確認する。

- portfolio 作成、cash holding 登録、重複作成の `409`。
- summary の cash / market value / return の USD 集計。
- holdings list の Yahoo price / FX 換算、前日終値比較、asset_type filter、
  pagination、cash 除外、missing market data skip。

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
