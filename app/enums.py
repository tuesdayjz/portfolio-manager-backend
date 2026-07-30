"""API で使う列挙型。OpenAPI の enum 定義の元になる。"""

import enum


class TransactionType(enum.Enum):
    """取引種別。

    - ``buy``  : 買い付け。保有数量を増やし、平均取得単価を再計算する。
    - ``sell`` : 売却。保有数量を減らす。保有数量を超える売却は 400。
    """

    BUY = "buy"
    SELL = "sell"


class TransactionStatus(enum.Enum):
    """取引の約定ステータス。

    - ``completed`` : 約定済み。保有残高に反映済み。
    - ``pending``   : 約定待ち。保有残高にはまだ反映しない。
    """

    COMPLETED = "completed"
    PENDING = "pending"


class Interval(enum.Enum):
    """推移グラフの粒度。Yahoo Finance の interval 表記に合わせる。"""

    DAILY = "1d"
    WEEKLY = "1wk"
    MONTHLY = "1mo"


class PerformanceRange(enum.Enum):
    """パフォーマンス画面の期間セレクタ（1D / 1W / 1M / 3M / 6M / 1Y / ALL）。

    `Interval` がグラフの「粒度」なのに対し、こちらは「どこまで遡るか」を表す。
    `all` は口座開設日（最初の取引日）からの全期間。
    """

    DAY = "1d"
    WEEK = "1w"
    MONTH = "1m"
    THREE_MONTHS = "3m"
    SIX_MONTHS = "6m"
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
