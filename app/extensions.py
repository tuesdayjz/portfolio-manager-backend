"""Flask 拡張のインスタンス。循環 import を避けるため定義だけをここに置く。"""

from flask_smorest import Api

api = Api()
