"""API で使う列挙型。OpenAPI の enum 定義の元になる。"""

import enum


class TransactionType(enum.Enum):
    """取引種別。

    - ``buy``        : 買い付け。保有数量を増やし、平均取得単価を再計算する。
    - ``sell``       : 売却。保有数量を減らす。保有数量を超える売却は 400。
    - ``deposit``    : 入金。現金残高を増やすだけで、他の holding には影響しない。
    - ``withdrawal`` : 出金。現金残高を減らす。残高を超える出金は 400。
    """

    BUY = "buy"
    SELL = "sell"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"


class Interval(enum.Enum):
    """推移グラフの粒度。現時点では 1 日粒度を標準として扱う。"""

    DAILY = "1d"
    WEEKLY = "1wk"
    MONTHLY = "1mo"


class PerformanceRange(enum.Enum):
    """パフォーマンス画面の期間セレクタ（1D / 1W / 1M / 3M / YTD / 1Y / ALL）。

    `Interval` がグラフの「粒度」なのに対し、こちらは「どこまで遡るか」を表す。
    `all` は口座開設日（最初の取引日）からの全期間。
    """

    DAY = "1d"
    WEEK = "1w"
    MONTH = "1m"
    THREE_MONTHS = "3m"
    YEAR_TO_DATE = "YTD"
    YEAR = "1y"
    ALL = "all"


class AllocationGroupBy(enum.Enum):
    """資産配分の集計基準。

    - ``asset_type`` : 資産クラス別。目標比率と乖離もあわせて返す。
    - ``currency``   : 通貨別。
    - ``asset``      : 個別銘柄別。
    - ``sector``     : 株式のセクター別。セクターを持たない資産は集計から除く。
    """

    ASSET_TYPE = "asset_type"
    CURRENCY = "currency"
    ASSET = "asset"
    SECTOR = "sector"


class Theme(enum.Enum):
    """UI のカラーテーマ。"""

    LIGHT = "light"
    DARK = "dark"


class ExportFormat(enum.Enum):
    """明細・レポートのエクスポート形式。"""

    CSV = "csv"
    PDF = "pdf"
