"""Shared test configuration helpers."""

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_ENV_FILE = PROJECT_ROOT / "tests" / ".env"
ROOT_ENV_FILE = PROJECT_ROOT / ".env"


def load_test_env():
    """Load shared project env first, then test-specific overrides."""

    load_dotenv(ROOT_ENV_FILE, override=True)
    load_dotenv(TEST_ENV_FILE, override=True)
