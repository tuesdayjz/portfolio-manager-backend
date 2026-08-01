## Portfolio Manager (Tokyo Team)

ポートフォリオ管理 API の backend リポジトリ。現時点では Flask +
flask-smorest で OpenAPI / Swagger UI とリクエスト・レスポンススキーマを
定義している。portfolio / assets / transactions の業務処理はまだ未実装で、
該当エンドポイントは `501 Not Implemented` を返す。

API 設計は Flask + flask-smorest で管理し、OpenAPI 3 仕様は Marshmallow
スキーマから自動生成される。Supabase 接続設定と RLS / database connection
tests は実装済み。

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
> `403 Forbidden`（`Server: AirTunes`）が返る。`.env` に
> `FLASK_RUN_PORT=5001` を入れておけば `flask run` だけで済む。
> 5001 が使えない場合は、開発中は `--port=5003` で起動してよい。

### Supabase 設定

`.env` に Supabase の接続情報を設定する。

```env
SUPABASE_URL=https://gvtxkyimbroikdfjsacb.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
DEFAULT_BASE_CURRENCY=JPY
```

- `SUPABASE_ANON_KEY`: Supabase Dashboard の publishable / anon key。
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase Dashboard の secret / service role key。
- `SUPABASE_SERVICE_ROLE_KEY` は backend 専用。frontend や Git には出さない。
- `.env` は `.gitignore` 対象なので、ローカル環境だけに置く。

Flask アプリ内では Supabase 設定を直接 `os.getenv` で読まず、`app.config`
経由で client を作成する:

```python
from app.services.supabase import get_supabase_service_client

client = get_supabase_service_client()
```

`app.services.supabase.get_supabase_service_client()` は
`current_app.config["SUPABASE_URL"]` と
`current_app.config["SUPABASE_SERVICE_ROLE_KEY"]` を使う。frontend/user session
相当の client が必要な場合は `get_supabase_anon_client()` を使う。
`get_*_client()` は Flask app に cache される。テストなどで複数ユーザーの
session を分けたい場合は `create_supabase_anon_client()` のような non-cached
client creator を使う。

認証の方針:

- React は Supabase Auth を直接使って signup / login する。
- React が private table を直接読む場合は Supabase access token と RLS で保護する。
- holdings / transactions など重要な write は Flask backend から
  `SUPABASE_SERVICE_ROLE_KEY` を使って実行する。
- `SUPABASE_SERVICE_ROLE_KEY` は RLS を bypass できるため、backend local env のみに置く。

private table の RLS:

| Table | Read policy |
| --- | --- |
| `users` | `users.id = auth.uid()` の row だけ読める |
| `portfolio` | `portfolio.user_id = auth.uid()` の row だけ読める |
| `holdings` | `holdings -> portfolio.user_id = auth.uid()` の row だけ読める |
| `transactions` | `transactions -> holdings -> portfolio.user_id = auth.uid()` の row だけ読める |

shared table の方針:

```text
currency
asset_type
transaction_type
asset_master
asset_data_history
```

logged-in user は read 可能。write は backend/service role 側に寄せる。

### テスト

設定だけをテストする場合:

```bash
.venv/bin/python -m unittest tests.test_config
```

Supabase への接続と、全テーブルへの read 権限を確認する場合:

```bash
.venv/bin/python -W ignore::DeprecationWarning -m unittest tests.database_connection.test_supabase_connection
```

この接続テストは `.env` と `tests/.env` の Supabase keys を使う。
GitHub に共有するテンプレートは `tests/.env.example` に置き、実際の
テストユーザーとパスワードはローカルの `tests/.env` にだけ置く。

接続テストを有効にするには `tests/.env` で以下を設定する:

```text
RUN_SUPABASE_CONNECTION_TESTS=true
```

接続テストでは以下を確認する:

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
| `test_supabase_user_rls.py` | `RUN_SUPABASE_REAL_USER=false` のとき mock users で private/shared RLS を確認し、`true` のとき real users `user001` / `user002` の holdings isolation を確認する。 |

RLS テストは `RUN_SUPABASE_REAL_USER` で mock user / real user を切り替える:

```text
RUN_SUPABASE_REAL_USER=false  # mock user で private/public RLS tests を実行
RUN_SUPABASE_REAL_USER=true   # real user001/user002 で RLS tests を実行
```

Real-user RLS で 2 人のユーザーのデータ分離を確認する場合は、ローカルの
`tests/.env` に以下を設定する:

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

### ドキュメント

| URL | 内容 |
| --- | --- |
| http://localhost:5001/docs | Swagger UI |
| http://localhost:5001/redoc | ReDoc |
| http://localhost:5001/openapi.json | OpenAPI 3.0.3 仕様 |

リポジトリには生成済みの [`openapi.yaml`](openapi.yaml) をコミットしてある。
スキーマを変更したら再生成すること:

```bash
.venv/bin/flask export-openapi                  # → openapi.yaml
.venv/bin/flask export-openapi -f json          # → openapi.json
```

> 組み込みの `flask openapi write -f yaml` でも出力できるが、日本語が
> `\uXXXX` にエスケープされて差分が読めないため、上のコマンドを使う。

**API 設計はスキーマが単一の情報源。** `app/schemas/` を直せば仕様書・
バリデーション・Swagger UI がまとめて追従する。仕様書だけ手で書き換える運用はしない。

処理は未実装だが**リクエストのバリデーションは動く**ので、
Swagger UI の Try it out で入力仕様の検証はできる（通れば 501、通らなければ 422）。

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

`/holdings` の絞り込みは `asset_type`（既定値 `all`）のみ。`asset_id` と
`search` は受け取らず、検索はフロントエンド側で行う。`/allocation` の
`items` は分類名を `category` として返す。

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
- **React から直接読む private data は Supabase RLS で守る。** 重要な write は
  Flask 経由にする。
- **`current_price` は保存しない。** 市場価格は Yahoo Finance または
  `asset_data_history` 由来で、Supabase `holdings` には書かない。
- **`cash_balance` はモック専用。** 現行の Supabase スキーマに現金残高のカラムがない。
- **一括登録は全件検証してから更新する。** 1 件でも不正なら何も更新しない。

Supabase のテーブル定義と将来の実装方針は
[`API_DESIGN.md`](API_DESIGN.md) にまとめてある。

### 構成

```
app/
├── schemas/       Marshmallow スキーマ（= OpenAPI 定義。ここが本体）
│   ├── portfolio.py   サマリー / 配分 / 推移グラフ
│   ├── asset.py       資産マスタ / 価格履歴
│   ├── holding.py     保有残高
│   ├── transaction.py 取引履歴
│   └── common.py      共通バリデーターと pagination / date range
├── api/           エンドポイント定義（パスと入出力の宣言のみ。処理は未実装）
│   └── parameters.py  パスパラメータの OpenAPI 定義
├── enums.py       TransactionType / Interval
├── services/
│   └── supabase.py    Flask app.config から Supabase client を作成する
└── config.py      設定（OpenAPI / Supabase 設定を含む）

tests/
├── config.py
├── test_config.py
└── database_connection/
    ├── helpers.py
    ├── test_supabase_connection.py
    └── test_supabase_user_rls.py
```

### 未実装

portfolio / assets / transactions の実 API 処理、Flask 側の token 検証 middleware、
評価額・配分・推移の算出ロジック、Yahoo Finance 連携、DB migration 管理。
