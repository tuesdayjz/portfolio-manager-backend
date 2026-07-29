"""API ブループリントの登録。ここに並べた順序が Swagger UI のタグ順になる。"""

from flask_smorest import Api

from app.api import assets, holdings, transactions, user


def register_blueprints(api: Api) -> None:
    api.register_blueprint(assets.blp)
    api.register_blueprint(transactions.blp)
    api.register_blueprint(holdings.blp)
    api.register_blueprint(user.blp)
