"""Create or prepare a Supabase test user for local API testing."""

from __future__ import annotations

import argparse
import datetime
import os
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_local_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    load_dotenv(PROJECT_ROOT / "tests" / ".env", override=True)


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a Supabase Auth test user and ensure public.users has the "
            "matching profile row."
        )
    )
    parser.add_argument(
        "--email",
        default=None,
        help=(
            "Test user email. If omitted, a unique plus-address is generated "
            "from SUPABASE_TEST_USER_EMAIL."
        ),
    )
    parser.add_argument(
        "--password",
        default=os.getenv("SUPABASE_TEST_USER_PASSWORD"),
        help="Test user password. Defaults to SUPABASE_TEST_USER_PASSWORD.",
    )
    return parser.parse_args()


def unique_email(base_email: str) -> str:
    local_part, separator, domain = base_email.partition("@")
    if not separator or not local_part or not domain:
        raise SystemExit(
            "SUPABASE_TEST_USER_EMAIL must be a valid email when --email is omitted."
        )

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = secrets.token_hex(3)
    return f"{local_part}+{timestamp}-{suffix}@{domain}"


def auth_user_id(service_client, anon_client, email: str, password: str) -> str:
    try:
        response = service_client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
            }
        )
        print(f"Created Supabase Auth user: {email}")
        return str(response.user.id)
    except Exception as error:
        message = str(error).lower()
        if "already" not in message and "registered" not in message:
            raise

    response = anon_client.auth.sign_in_with_password(
        {"email": email, "password": password}
    )
    user = response.user
    if not user or not user.id:
        raise SystemExit(f"Auth user already exists, but sign-in failed for {email}.")
    print(f"Supabase Auth user already exists: {email}")
    return str(user.id)


def ensure_public_user(service_client, user_id: str, email: str) -> None:
    rows = (
        service_client.table("users")
        .select("id,email")
        .eq("id", user_id)
        .limit(1)
        .execute()
        .data
    )
    if rows:
        print(f"public.users row already exists: {user_id}")
        return

    email_rows = (
        service_client.table("users")
        .select("id,email")
        .eq("email", email)
        .limit(1)
        .execute()
        .data
    )
    if email_rows:
        raise SystemExit(
            "public.users already has this email with a different id: "
            f"{email_rows[0]['id']}"
        )

    service_client.table("users").insert({"id": user_id, "email": email}).execute()
    print(f"Created public.users row: {user_id}")


def main() -> int:
    load_local_env()
    args = parse_args()

    email = args.email or unique_email(required_env("SUPABASE_TEST_USER_EMAIL"))
    if not args.password:
        raise SystemExit(
            "Missing password. Set SUPABASE_TEST_USER_PASSWORD or pass --password."
        )

    url = required_env("SUPABASE_URL")
    service_client = create_client(url, required_env("SUPABASE_SERVICE_ROLE_KEY"))
    anon_client = create_client(url, required_env("SUPABASE_ANON_KEY"))

    user_id = auth_user_id(service_client, anon_client, email, args.password)
    ensure_public_user(service_client, user_id, email)
    print(f"Ready for testing: {email} ({user_id})")
    print(
        "Generate token with: "
        f".venv/bin/python scripts/generate_token.py --email {email!r} --password {args.password!r}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
