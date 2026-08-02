## Portfolio Manager (Tokyo Team)

ポートフォリオ管理 API の backend リポジトリ。現時点では Flask +
flask-smorest で OpenAPI / Swagger UI とリクエスト・レスポンススキーマを
定義している。`POST /api/v1/portfolios/` は実装済みで、それ以外の
portfolio / assets / transactions の業務処理はまだ未実装。

Supabase 接続設定、Supabase client helper、database connection tests、
RLS tests は実装済み。

### User Story

1. As an investor, I want to register my assets so that I can manage my holdings in one place.
2. As an investor, I want to view the current value of my portfolio so that I can understand my overall finalcial position.
3. As an investor, I want to track my profits and losses so that I can make informed investment decisions.
4. As an investor, I want to record my transaction history so that I can review my investment performance over time.
5. As an investor, I want to visualize my asset allocation so that I can better control and manage risk.
6. As an investor, I want to monitor my investment performance over time so that I can track the growth of my portfolio.

### セットアップ

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env

export FLASK_APP=wsgi.py
.venv/bin/flask run --port=5001
```

> **ポートは 5001 を使う。** macOS の AirPlay レシーバーが `*:5000` を
> 掴んでいるため、5000 番だと `localhost` が AirPlay 側に吸われて
> `403 Forbidden`（`Server: AirTunes`）が返る。5001 が使えない場合は、
> 開発中は `--port=5003` で起動してよい。

### Supabase 設定

`.env` に Supabase の接続情報を設定する。

```env
SUPABASE_URL=https://gvtxkyimbroikdfjsacb.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
DEFAULT_BASE_CURRENCY=USD
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres?sslmode=require
TEST_DATABASE_URL=sqlite+pysqlite:///:memory:
```

- `SUPABASE_ANON_KEY`: Supabase Dashboard の publishable / anon key。
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase Dashboard の secret / service role key。
- `SUPABASE_SERVICE_ROLE_KEY` は接続確認・RLS 検証用の backend secret。frontend や Git には出さない。
- `DEFAULT_BASE_CURRENCY`: portfolio 作成時の既定通貨。frontend / backend ともに `USD` を既定値にする。
- `DATABASE_URL`: backend から Supabase PostgreSQL へ接続するための SQLAlchemy URI。
- `TEST_DATABASE_URL`: unit test 用 DB URI。未設定時は in-memory SQLite を使う。
- `.env` は `.gitignore` 対象なので、ローカル環境だけに置く。

Flask アプリ内では Supabase 設定を直接 `os.getenv` で読まず、`app.config`
経由で client を作成する。

```python
from app.services.supabase import get_supabase_anon_client

client = get_supabase_anon_client()
```

`get_supabase_anon_client()` は `current_app.config["SUPABASE_URL"]` と
`current_app.config["SUPABASE_ANON_KEY"]` を使い、Supabase Auth の token
検証に使う。`get_supabase_service_client()` は接続確認・RLS 検証用 helper として
残すが、portfolio / holdings / transactions の業務 CRUD の主線にはしない。
`get_*_client()` は Flask app に cache される。テストなどで複数ユーザーの
session を分けたい場合は `create_supabase_anon_client()` のような non-cached
client creator を使う。

### 認証方針

- React は Supabase Auth を直接使って signup / login する。
- React が private table を直接読む場合は Supabase access token と RLS で保護する。
- React が Flask の private API を呼ぶ場合は
  `Authorization: Bearer <access_token>` を header に付ける。
- この branch は Flask 側で Auth context を作るところまでを担当する。
- holdings / transactions などの業務 DB read/write と ownership check は、
  後続の SQLAlchemy branch で `g.current_user_id` を使って実装する。

Flask 側では `app.auth.require_auth()` が Supabase access token を検証し、
成功すると以下を request context に保存する。

```python
from flask import g

g.current_user_id
g.current_user_email
g.current_access_token
```

private API の実装では client から `user_id` を受け取らず、
`g.current_user_id` を使って対象ユーザーを解決する。Swagger UI では右上の
**Authorize** から Supabase access token を入力する。

Swagger UI で private API を手動テストする場合は、ローカルの `.env` と
`tests/.env` に Supabase 設定と `SUPABASE_TEST_USER_EMAIL` /
`SUPABASE_TEST_USER_PASSWORD` を置いたうえで、以下を使う。

```bash
.venv/bin/python scripts/create_test_user.py
.venv/bin/python scripts/generate_token.py
```

`scripts/create_test_user.py` は、`SUPABASE_TEST_USER_EMAIL` から
`user001+20260802000000-abcdef@gmail.com` のような一意の email を生成して
新しい test user を作る。固定 email を使いたい場合だけ `--email` を渡す。
作成後に表示される `scripts/generate_token.py --email ...` の token 生成コマンドを
実行し、出力を Swagger UI の **Authorize** に貼り付ける。HTTP header 形式で
確認したい場合は `--header` を付ける。

### デバッグ時に token を省略する

毎回 token を発行して Swagger UI に貼り直すのが面倒な場合は、ローカルの
`.env` に以下を置くと `require_auth()` が token 検証を飛ばし、
`DEBUG_USER_ID` を現在のユーザーとして扱う。

```bash
AUTH_DISABLED=true
DEBUG_USER_ID=<Supabase auth user の UUID>
DEBUG_USER_EMAIL=<その user の email>
```

`DEBUG_USER_ID` は `scripts/create_test_user.py` が作成時に表示する user id を使う。
実在する user の id にしておかないと、その id で新しい `users` row が作られる点に注意。

有効にすると起動時に `AUTH_DISABLED=true: ...` の warning log が出る。
`FLASK_ENV=production` では config 側で強制的に無効化されるため、
env に残っていても本番では効かない。切り戻しは `AUTH_DISABLED=false` に戻すだけでよい。

> Review note: この branch では authentication だけを準備し、authorization
> check と業務 DB write は SQLAlchemy branch との merge 後に実装する。

### Supabase RLS

private table の read policy:

| Table | Read policy |
| --- | --- |
| `users` | `users.id = auth.uid()` の row だけ読める |
| `portfolio` | `portfolio.user_id = auth.uid()` の row だけ読める |
| `holdings` | `holdings -> portfolio.user_id = auth.uid()` の row だけ読める |
| `transactions` | `transactions -> holdings -> portfolio.user_id = auth.uid()` の row だけ読める |

shared table:

```text
currency
asset_type
asset_master
asset_data_history
```

logged-in user は shared table を read できる。write 方針は SQLAlchemy branch
で backend DB 実装と合わせて整理する。

### テスト

設定だけをテストする場合:

```bash
.venv/bin/python -m unittest tests.test_config
```

Auth helper と設定をテストする場合:

```bash
.venv/bin/python -m unittest tests.test_auth tests.test_config
```

portfolio 作成 API をテストする場合:

```bash
.venv/bin/python -m unittest tests.test_portfolio_create
```

Supabase への接続と、全テーブルへの read 権限を確認する場合:

```bash
.venv/bin/python -W ignore::DeprecationWarning -m unittest tests.database_connection.test_supabase_connection
```

backend の SQLAlchemy engine が `DATABASE_URL` で PostgreSQL に接続できることを
確認する場合:

```bash
.venv/bin/python -m unittest tests.database_connection.test_sqlalchemy_connection
```

この接続テストは `.env` と `tests/.env` の Supabase keys を使う。
GitHub に共有するテンプレートは `tests/.env.example` に置き、実際の
テストユーザーとパスワードはローカルの `tests/.env` にだけ置く。

接続テストを有効にするには `tests/.env` で以下を設定する。

```text
RUN_SUPABASE_CONNECTION_TESTS=true
```

接続テストでは以下を確認する。

```text
Connection Setup: configured URL/key で client を作成し、軽量 read で active 状態を確認する
Basic Operations: reference table に対して select limit 1 を実行し、結果を受け取れることを確認する
Exception & Teardown: 不正 key で例外が出ること、HTTP client resource を close できることを確認する
```

service role の core table read では以下のテーブルに対して
`select("id").limit(1)` だけを実行する。データの作成・更新・削除は行わない。

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

すべてのテストを実行する場合:

```bash
.venv/bin/python -W ignore::DeprecationWarning -m unittest discover -s tests
```

Database connection / Supabase 関連のテストだけを実行する場合:

```bash
.venv/bin/python -W ignore::DeprecationWarning -m unittest discover -s tests/database_connection -t .
```

Database connection / Supabase tests の内容:

| Test file | 内容 |
| --- | --- |
| `test_supabase_connection.py` | Supabase config で client を作成し、basic read、invalid key exception、client close/release を確認する。 |
| `test_supabase_user_rls.py` | `RUN_SUPABASE_REAL_USER=false` のとき mock users で private/shared RLS を確認し、`true` のとき real users の holdings isolation を確認する。 |

RLS テストは `RUN_SUPABASE_REAL_USER` で mock user / real user を切り替える。

```text
RUN_SUPABASE_REAL_USER=false  # mock user で private/public RLS tests を実行
RUN_SUPABASE_REAL_USER=true   # real user で RLS tests を実行
```

Real-user RLS で 2 人のユーザーのデータ分離を確認する場合は、ローカルの
`tests/.env` に以下を設定する。

```text
RUN_SUPABASE_REAL_USER=true
RUN_SUPABASE_REAL_USER_BOOTSTRAP_DATA=true
SUPABASE_TEST_USER_EMAIL=
SUPABASE_TEST_USER_PASSWORD=
SUPABASE_SECOND_TEST_USER_EMAIL=
SUPABASE_SECOND_TEST_USER_PASSWORD=
```

`RUN_SUPABASE_REAL_USER_BOOTSTRAP_DATA=true` の場合、holding がないテストユーザーには
一時 mock holding を作成し、テスト終了後に作成した holding / asset / portfolio を削除する。

### データベース (Supabase)

DB は Supabase の PostgreSQL に Flask-SQLAlchemy で接続する。接続情報は
`.env` の `DATABASE_URL` だけで、Supabase Dashboard > Project Settings >
Database の Connection string をそのまま使う（ドライバは psycopg v3、
`sslmode=require` 必須）。書式は [`.env.example`](.env.example) を参照。

スキーマ変更は Flask-Migrate (Alembic) で管理する:

```bash
.venv/bin/flask db migrate -m "add holdings table"   # マイグレーション生成
.venv/bin/flask db upgrade                           # 適用
.venv/bin/flask db downgrade                         # 巻き戻し
```

モデルは `app/models/` に置き、**`app/models/__init__.py` で import する**。
`flask db migrate` は `db.metadata` に登録されたモデルしか見ないため、
import し忘れると差分が空のマイグレーションが生成される。

### ドキュメント

| URL | 内容 |
| --- | --- |
| http://localhost:5001/docs | Swagger UI |
| http://localhost:5001/redoc | ReDoc |
| http://localhost:5001/openapi.json | OpenAPI 3.0.3 仕様 |

リポジトリには生成済みの [`openapi.yaml`](openapi.yaml) をコミットしてある。
スキーマを変更したら再生成すること。

```bash
.venv/bin/flask export-openapi                  # -> openapi.yaml
.venv/bin/flask export-openapi -f json          # -> openapi.json
```

**API 設計はスキーマが単一の情報源。** `app/schemas/` を直せば仕様書・
バリデーション・Swagger UI がまとめて追従する。仕様書だけ手で書き換える運用はしない。

未実装 endpoint でも**リクエストのバリデーションは動く**ので、Swagger UI の
Try it out で入力仕様の検証はできる（未実装なら 501、通らなければ 422）。

### エンドポイント

すべて `/api/v1` 配下。設計の背景は [`API_DESIGN.md`](API_DESIGN.md) を参照。

| メソッド | パス | タグ | 説明 |
| --- | --- | --- | --- |
| POST | `/portfolios/` | portfolio | ポートフォリオ作成 |
| GET | `/portfolios/summary` | portfolio | サマリー（取得価額・評価額・総資産・含み損益） |
| GET | `/portfolios/holdings` | portfolio | 保有残高一覧 |
| GET | `/portfolios/allocation` | portfolio | 資産配分（種別・通貨・銘柄別） |
| GET | `/portfolios/performance` | portfolio | 推移グラフ |
| GET | `/assets/{asset_id}/` | assets | 資産マスタ情報（deprecated） |
| GET | `/assets/{asset_id}/price-history` | assets | 過去の市場価格（deprecated） |
| GET | `/portfolios/transactions` | transactions | 取引履歴の検索 |
| POST | `/transactions` | transactions | 取引の登録（単件） |
| POST | `/transactions/batch` | transactions | 取引の一括登録 |

`POST /portfolios/` は `name`、任意の `currency`（フロントエンド既定値は
`USD`）、任意の `cash_balance` を受け取り、成功時は `message` だけを返す。
すでに portfolio があるユーザーの場合は `409 Conflict` を返す。
`cash_balance` は portfolio 作成時に cash holding として登録し、quantity は
`1` として扱う。

```json
{
  "name": "Main Portfolio",
  "currency": "USD",
  "cash_balance": 1000000
}
```

`GET /portfolios/summary` はログイン user の portfolio から USD 建ての
サマリーを返す。`cash_balance` は cash holding を USD に換算して集計し、
`total_market_value` と `total_return_percent` は cash 以外の holding だけで
計算する。市場価格と FX は Yahoo Finance から取得し、DB には保存しない。

`GET /portfolios/holdings` は cash を除いた保有残高一覧を USD 建てで返す。
`asset_type`（既定値 `all`）、`page`、`per_page` を受け取る。`asset_id` と
`search` は受け取らず、検索はフロントエンド側で行う。`items` は現在価格・取得単価・
評価額・当日騰落率・累計損益率を返す。現在価格と FX は Yahoo Finance から取得し、
前日終値は `asset_data_history` の `price_date < today` の最新 `close_price` を使う。
必要な market data が足りない holding は一覧と totals から除外する。`totals` は
ページング後の `items` ではなく、条件に一致した全 holding で集計する。

`/allocation` の `items` は分類名を `category` として返す。

`/performance` は `start_date`, `end_date`, `range`, `interval` を取る。
`range` は `1d` / `1w` / `1m` / `3m` / `YTD` / `1y` / `all`、
`interval` の既定値は `1d`。レスポンスは `return_1d`, `return_1w`,
`return_1m`, `return_3m`, `return_YTD`, `return_1y`, `return_total` を
それぞれ `{ amount, percent }` で返す。`today` は今日の close price と
前日の close price の差分で計算し、各期間の return は今日の close price と
対象期間の起点 close price（例: `1w` なら 1 週間前）の差分で計算する。

`/transactions` の絞り込みは `transaction_type`, `asset_type`（既定値
`all`）, `start_date`, `end_date`。`asset_id` と `search` は受け取らない。
単件作成と一括作成の各 item は `ticker`, `name`, `position`, `order_type`,
`transaction_type`, `quantity` を受け取り、成功時は作成された取引の確認として
`date`, `symbol`, `name`, `executed_price`, `executed_unit_price`,
`asset_type` の約定サマリーを返す。新しい asset を追加する場合は、Yahoo
Finance API から取得した情報を `asset_master` に登録してから取引を作成する。

### 設計メモ

- **実際の証券発注は行わない。** 売買は取引履歴の記録と保有残高の更新だけを行う。
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

```text
app/
├── schemas/       Marshmallow スキーマ（= OpenAPI 定義。ここが本体）
│   ├── portfolio.py   サマリー / 配分 / 推移グラフ
│   ├── asset.py       資産マスタ / 価格履歴
│   ├── holding.py     保有残高
│   ├── transaction.py 取引履歴
│   └── common.py      共通バリデーターと pagination / date range
├── api/           エンドポイント定義（パス・入出力・service 呼び出し）
│   └── parameters.py  パスパラメータの OpenAPI 定義
├── models/        SQLAlchemy モデル（Supabase public schema）
│   ├── user.py        public.users
│   ├── portfolio.py   portfolio
│   ├── holding.py     holdings
│   ├── asset.py       currency / asset_type / asset_master / asset_data_history
│   └── transaction.py transactions
├── auth.py        Supabase access token を検証し g.current_user_id を設定する
├── enums.py       TransactionType / Interval
├── services/
│   ├── market_data.py Yahoo Finance から価格・FX を取得する
│   ├── portfolio.py   portfolio / summary / holdings の business logic
│   └── supabase.py    Flask app.config から Supabase client を作成する
└── config.py      設定（OpenAPI / Supabase 設定を含む）

tests/
├── config.py
├── test_auth.py
├── test_config.py
├── test_portfolio_create.py
├── test_portfolio_holdings.py
├── test_portfolio_summary.py
└── database_connection/
    ├── helpers.py
    ├── test_sqlalchemy_connection.py
    ├── test_supabase_connection.py
    └── test_supabase_user_rls.py

scripts/
├── create_test_user.py  Supabase Auth test user と public.users row を準備する
└── generate_token.py    Swagger UI 手動テスト用の access token を生成する
```

### 未実装

portfolio allocation / performance、assets、transactions の実 API 処理。
summary / holdings の read API、Supabase Auth token 検証、Yahoo Finance 価格・FX 取得、
SQLAlchemy 接続、DB migration 管理は実装済み。
