## Portfolio Manager (Tokyo Team)

ポートフォリオ管理 API の**設計リポジトリ**。現時点では OpenAPI 仕様の定義のみで、
処理は未実装（全エンドポイントが `501 Not Implemented` を返す）。

API 設計は Flask + flask-smorest で管理し、OpenAPI 3 仕様は Marshmallow
スキーマから自動生成される。

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

### テスト

設定だけをテストする場合:

```bash
.venv/bin/python -m unittest tests.test_config
```

Supabase への接続と、全テーブルへの read 権限を確認する場合:

```bash
.venv/bin/python -W ignore::DeprecationWarning -m unittest tests.test_supabase_connection
```

この接続テストは `.env` の Supabase keys を使い、以下のテーブルに対して
`select("id").limit(1)` だけを実行する。データの作成・更新・削除は行わない。

```text
users
portfolio
asset_master
currency
asset_type
transaction_type
asset_data_history
holdings
transactions
```

すべてのテストを実行する場合:

```bash
.venv/bin/python -W ignore::DeprecationWarning -m unittest discover -s tests
```

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
| POST | `/auth/signup` | auth | ユーザー登録 |
| POST | `/auth/login` | auth | ログイン |
| POST | `/auth/logout` | auth | ログアウト |
| POST | `/portfolios/` | portfolio | ポートフォリオ作成 |
| GET | `/portfolios/{portfolio_id}/summary` | portfolio | サマリー（取得価額・評価額・総資産・含み損益） |
| GET | `/portfolios/{portfolio_id}/holdings` | portfolio | 保有残高一覧 |
| GET | `/portfolios/{portfolio_id}/allocation` | portfolio | 資産配分（種別・通貨・銘柄別） |
| GET | `/portfolios/{portfolio_id}/performance` | portfolio | 推移グラフ |
| GET | `/assets/{asset_id}/` | assets | 資産マスタ情報 |
| GET | `/assets/{asset_id}/price-history` | assets | 過去の市場価格（OHLCV） |
| GET | `/portfolios/{portfolio_id}/transactions` | transactions | 取引履歴の検索 |
| POST | `/portfolios/{portfolio_id}/transactions` | transactions | 取引の登録（単件） |
| POST | `/portfolios/{portfolio_id}/transactions/batch` | transactions | 取引の一括登録 |

`/transactions` の絞り込み: `user_id`（必須）, `asset_id`, `start_date`, `end_date`。
`start_date` / `end_date` はどちらも指定日を含む。
`/performance` は `start_date`, `end_date`, `interval`（`1d` / `1wk` / `1mo`）を取る。

### 設計メモ

- **実際の証券発注は行わない。** 売買は取引履歴の記録と保有残高の更新だけを行う。
- **所有者は `user_id` で絞り込む。** モック／開発中は private な GET API に
  `user_id` をクエリパラメータで渡す。本番ではログイン情報から解決する想定なので、
  その際は `app/schemas/common.py` の `UserIdQuerySchema` を外して認証に差し替える。
  公開の資産・市場データに `user_id` は不要。
- **`portfolio_id` はパスで受ける。** private なポートフォリオデータは必ずパスに含める。
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
│   ├── auth.py        登録 / ログイン / ログアウト
│   ├── portfolio.py   サマリー / 配分 / 推移グラフ
│   ├── asset.py       資産マスタ / 価格履歴
│   ├── holding.py     保有残高
│   ├── transaction.py 取引履歴
│   └── common.py      共通バリデーターと user_id クエリ
├── api/           エンドポイント定義（パスと入出力の宣言のみ。処理は未実装）
│   └── parameters.py  パスパラメータの OpenAPI 定義
├── enums.py       TransactionType / Interval
└── config.py      設定（OpenAPI 設定を含む）
```

### 未実装

DB（モデル・マイグレーション）、認証処理、評価額・配分・推移の算出ロジック、
Yahoo Finance 連携。
