"""Flask 拡張のインスタンス。循環 import を避けるため定義だけをここに置く。"""

from flask_migrate import Migrate
from flask_smorest import Api
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

api = Api()


class Base(DeclarativeBase):
    """全モデルの基底クラス（SQLAlchemy 2.0 スタイル）。"""


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
