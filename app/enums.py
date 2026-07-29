"""API で使う列挙型。OpenAPI の enum 定義の元になる。"""

import enum


class TransactionType(enum.Enum):
    """取引種別。

    - ``buy``  : 買い付け。保有数量を増やし、平均取得単価を再計算する。
    - ``sell`` : 売却。保有数量を減らす。保有数量を超える売却は 400。
    """

    BUY = "buy"
    SELL = "sell"


class Interval(enum.Enum):
    """推移グラフの粒度。Yahoo Finance の interval 表記に合わせる。"""

    DAILY = "1d"
    WEEKLY = "1wk"
    MONTHLY = "1mo"
