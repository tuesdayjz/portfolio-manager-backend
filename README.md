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

すべて `/api/v1` 配下。`POST /user/register` 以外は `X-API-Key` ヘッダーが必要な設計。

| メソッド | パス | 説明 |
| --- | --- | --- |
| GET / POST | `/assets/` | 銘柄の一覧・登録 |
| GET / PATCH / DELETE | `/assets/{asset_id}` | 銘柄の取得・更新・削除 |
| GET / POST | `/transactions/` | 取引の検索・登録 |
| GET / PATCH / DELETE | `/transactions/{transaction_id}` | 取引の取得・更新・削除 |
| GET | `/holdings/` | 保有状況（取引から算出） |
| GET | `/holdings/{asset_id}` | 特定銘柄の保有状況 |
| POST | `/user/register` | ユーザー登録（API キー払い出し） |
| GET / PATCH / DELETE | `/user/` | 認証中ユーザーのプロフィール |
| POST | `/user/api-key/rotate` | API キー再発行 |

`/transactions/` の絞り込み: `asset_id`, `start_date`, `end_date`,
`transaction_type`, `sort`, `page`, `page_size`。
日付は UTC 基準で、`start_date` / `end_date` はどちらも指定日を含む。

### 設計メモ

- **金額は文字列でやり取りする。** JSON の number は倍精度浮動小数点なので、
  金額を通すと丸め誤差が出る。入出力は文字列で、内部では `Decimal` を使う想定。
- **保有状況は保存しない。** `holdings` は取引履歴を時系列に再生して都度算出する設計
  （移動平均法、手数料は取得原価に算入）。`as_of=YYYY-MM-DD` で過去時点も出せる。
- **時価評価は対象外。** 価格取得の仕組みを前提にしないため、含み損益は返さない。
- **通貨は合算しない。** 為替レートを持たないため、`summary` は通貨ごとに分けて返す。
- **認証は API キー**（`X-API-Key` ヘッダー）。JWT / OAuth2 に差し替える場合は
  `app/config.py` の `securitySchemes` を変更する。

### 構成

```
app/
├── schemas/     Marshmallow スキーマ（= OpenAPI 定義。ここが本体）
├── api/         エンドポイント定義（パスと入出力の宣言のみ。処理は未実装）
├── enums.py     AssetType / TransactionType
└── config.py    設定（OpenAPI 設定を含む）
```

### 未実装

DB（モデル・マイグレーション）、認証処理、保有状況の算出ロジック、テスト。
