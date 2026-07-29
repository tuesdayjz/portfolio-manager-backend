"""API で使う列挙型。OpenAPI の enum 定義の元になる。"""

import enum


class AssetType(enum.Enum):
    STOCK = "STOCK"
    ETF = "ETF"
    MUTUAL_FUND = "MUTUAL_FUND"
    BOND = "BOND"
    CRYPTO = "CRYPTO"
    CASH = "CASH"
    OTHER = "OTHER"


class TransactionType(enum.Enum):
    """取引種別。

    種別ごとに ``quantity`` / ``price`` の意味が変わる。

    - ``BUY``      : quantity=約定株数, price=単価
    - ``SELL``     : quantity=約定株数, price=単価
    - ``DIVIDEND`` : quantity=0,        price=配当総額（税引前）
    - ``SPLIT``    : quantity=分割比率, price=0   (例: 1→2 の分割なら 2)
    """

    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    SPLIT = "SPLIT"
