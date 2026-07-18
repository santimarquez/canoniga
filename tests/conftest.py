from __future__ import annotations

import os

import pytest

from als_intel.store import EvidenceStore

DEFAULT_TEST_DSN = "postgresql://als:als@localhost:5432/als_intel"


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    return str(os.getenv("ALS_TEST_DATABASE_URL") or os.getenv("ALS_DATABASE_URL") or DEFAULT_TEST_DSN)


@pytest.fixture(scope="session", autouse=True)
def _configure_test_dsn(pg_dsn: str) -> None:
    os.environ["ALS_DATABASE_URL"] = pg_dsn
    os.environ["ALS_TEST_DATABASE_URL"] = pg_dsn
    # Ensure migrations are discoverable from repo root in editable installs.
    if not os.getenv("ALS_MIGRATIONS_DIR"):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "migrations" / "postgres"
        os.environ["ALS_MIGRATIONS_DIR"] = str(root)


@pytest.fixture(autouse=True)
def clean_postgres(pg_dsn: str) -> None:
    store = EvidenceStore(pg_dsn)
    store.reset_all_data()
    yield
