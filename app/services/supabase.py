"""Supabase client helpers backed by Flask app configuration.

この branch では Supabase client を Auth / connection test 用に限定する。
portfolio / holdings / transactions の業務 CRUD は後続の SQLAlchemy 実装に寄せる。
"""

from flask import current_app
from supabase import create_client

SUPABASE_CLIENTS_EXTENSION_KEY = "supabase_clients"


def get_supabase_anon_client():
    """Return a Supabase client for Supabase Auth token validation."""

    return get_supabase_client("SUPABASE_ANON_KEY")


def get_supabase_service_client():
    """Return a service role client for legacy/helper tests, not business CRUD."""

    return get_supabase_client("SUPABASE_SERVICE_ROLE_KEY")


def create_supabase_anon_client():
    """Create a non-cached anon client for Auth/RLS test sessions."""

    return create_supabase_client("SUPABASE_ANON_KEY")


def create_supabase_service_client():
    """Create a non-cached service role client for tests and diagnostics."""

    return create_supabase_client("SUPABASE_SERVICE_ROLE_KEY")


def get_supabase_client(key_name):
    """Return a cached Supabase client using values from current_app.config."""

    clients = current_app.extensions.setdefault(SUPABASE_CLIENTS_EXTENSION_KEY, {})
    if key_name not in clients:
        clients[key_name] = create_supabase_client(key_name)
    return clients[key_name]


def create_supabase_client(key_name):
    """Create a new Supabase client using values from current_app.config."""

    return create_client(
        _required_config("SUPABASE_URL"),
        _required_config(key_name),
    )


def close_supabase_clients(app=None):
    """Best-effort release for cached Supabase HTTP resources."""

    flask_app = app or current_app
    clients = flask_app.extensions.pop(SUPABASE_CLIENTS_EXTENSION_KEY, {})
    released = False
    for client in clients.values():
        released = close_supabase_client(client) or released
    return released


def _required_config(key):
    value = current_app.config.get(key)
    if not value:
        raise RuntimeError(f"{key} is required to create a Supabase client.")
    return value


def close_supabase_client(client):
    """Best-effort release for one Supabase client's HTTP resources."""

    released = False

    auth_close = getattr(getattr(client, "auth", None), "close", None)
    if callable(auth_close):
        auth_close()
        released = True

    for resource_name in ("postgrest", "storage"):
        session = getattr(getattr(client, resource_name, None), "session", None)
        session_close = getattr(session, "close", None)
        if callable(session_close) and not getattr(session, "is_closed", False):
            session_close()
            released = True

    return released
