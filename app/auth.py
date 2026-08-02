"""Supabase Auth token を Flask request context に変換する helper。"""

import types

from flask import current_app, g, request
from flask_smorest import abort

from app.services.supabase import get_supabase_anon_client


def require_auth():
    """Authorization header の Supabase access token を検証する。

    成功した場合は `g.current_user_id` / `g.current_user_email` に現在の
    Supabase Auth user を保存する。private API は client から `user_id` を
    受け取らず、この値を server-side caller context として使う。
    ここでは authentication だけを行い、row ownership の authorization は
    後続の SQLAlchemy 実装で `g.current_user_id` を使って判定する。

    `AUTH_DISABLED` が有効なときは token 検証を飛ばし、固定の debug user を
    caller context に入れる（Swagger UI から token なしで叩くため）。
    """

    if current_app.config.get("AUTH_DISABLED"):
        return _debug_user()

    token = _bearer_token()
    try:
        response = get_supabase_anon_client().auth.get_user(token)
    except Exception:
        abort(401, message="Invalid or expired access token.")

    user = getattr(response, "user", None)
    user_id = getattr(user, "id", None)
    if not user or not user_id:
        abort(401, message="Invalid or expired access token.")

    g.current_user_id = str(user_id)
    g.current_user_email = getattr(user, "email", None)
    g.current_access_token = token
    return user


def _debug_user():
    """AUTH_DISABLED 時に使う固定 user。DB 上の実在 user と揃えておく。"""

    user_id = current_app.config.get("DEBUG_USER_ID")
    if not user_id:
        raise RuntimeError(
            "AUTH_DISABLED=true のときは DEBUG_USER_ID (Supabase auth user の UUID) が必要。"
        )

    email = current_app.config.get("DEBUG_USER_EMAIL")
    g.current_user_id = str(user_id)
    g.current_user_email = email
    # RLS 越しの client を使う経路のために、token は明示的に未設定にしておく。
    g.current_access_token = None
    return types.SimpleNamespace(id=str(user_id), email=email)


def _bearer_token():
    auth_header = request.headers.get("Authorization", "").strip()
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        abort(401, message="Missing bearer access token.")
    return token.strip()
