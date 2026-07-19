from __future__ import annotations

import os
from pathlib import Path

import pytest

from als_intel.db import DEFAULT_TEST_DSN, ensure_database
from als_intel.store import EvidenceStore


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    """Isolated test database — never defaults to the app DB."""
    configured = str(os.getenv("ALS_TEST_DATABASE_URL") or "").strip()
    dsn = configured or DEFAULT_TEST_DSN
    ensure_database(dsn)
    return dsn


@pytest.fixture(scope="session", autouse=True)
def _configure_test_dsn(pg_dsn: str) -> None:
    # Bind both vars to the test DB for the pytest process so bare EvidenceStore()
    # calls cannot touch the developer app database.
    os.environ["ALS_TEST_DATABASE_URL"] = pg_dsn
    os.environ["ALS_DATABASE_URL"] = pg_dsn
    if not os.getenv("ALS_MIGRATIONS_DIR"):
        root = Path(__file__).resolve().parents[1] / "migrations" / "postgres"
        os.environ["ALS_MIGRATIONS_DIR"] = str(root)


@pytest.fixture(autouse=True)
def clean_postgres(pg_dsn: str) -> None:
    store = EvidenceStore(pg_dsn)
    store.reset_all_data()
    yield
