"""Generate a Supabase access token for Swagger UI testing."""

from __future__ import annotations

import argparse
import os
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
        description="Sign in a Supabase test user and print an access token."
    )
    parser.add_argument(
        "--email",
        default=os.getenv("SUPABASE_TEST_USER_EMAIL"),
        help="Test user email. Defaults to SUPABASE_TEST_USER_EMAIL.",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("SUPABASE_TEST_USER_PASSWORD"),
        help="Test user password. Defaults to SUPABASE_TEST_USER_PASSWORD.",
    )
    parser.add_argument(
        "--header",
        action="store_true",
        help="Print an Authorization header instead of the raw access token.",
    )
    return parser.parse_args()


def main() -> int:
    load_local_env()
    args = parse_args()

    if not args.email:
        raise SystemExit("Missing email. Set SUPABASE_TEST_USER_EMAIL or pass --email.")
    if not args.password:
        raise SystemExit(
            "Missing password. Set SUPABASE_TEST_USER_PASSWORD or pass --password."
        )

    client = create_client(required_env("SUPABASE_URL"), required_env("SUPABASE_ANON_KEY"))
    response = client.auth.sign_in_with_password(
        {"email": args.email, "password": args.password}
    )
    session = response.session
    if not session or not session.access_token:
        raise SystemExit("Supabase sign-in did not return an access token.")

    if args.header:
        print(f"Authorization: Bearer {session.access_token}")
    else:
        print(session.access_token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
