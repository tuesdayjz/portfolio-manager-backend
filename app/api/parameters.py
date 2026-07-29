"""パスパラメータの OpenAPI 定義。

Flask の `<int:...>` コンバーターからは `type: integer` しか導出されないため、
説明・例・下限はここで明示して `blp.route(..., parameters=[...])` に渡す。
"""

PORTFOLIO_ID = {
    "in": "path",
    "name": "portfolio_id",
    "required": True,
    "description": "Portfolio ID",
    "schema": {"type": "integer", "minimum": 1, "example": 1},
}

ASSET_ID = {
    "in": "path",
    "name": "asset_id",
    "required": True,
    "description": "Asset ID",
    "schema": {"type": "integer", "minimum": 1, "example": 1},
}
