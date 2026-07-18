from __future__ import annotations

import os
import re
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import tuple_row

DEFAULT_DSN = "postgresql://als:als@localhost:5432/als_intel"
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations" / "postgres"

_PLACEHOLDER_RE = re.compile(r"\?")


def resolve_dsn(explicit: str | None = None) -> str:
    """Resolve Postgres DSN from explicit arg or environment."""
    if explicit:
        value = str(explicit).strip()
        if value and ("://" in value or value.startswith("postgresql")):
            return value

    url = str(os.getenv("ALS_DATABASE_URL") or os.getenv("ALS_TEST_DATABASE_URL") or "").strip()
    if url:
        return url

    host = str(os.getenv("ALS_PG_HOST") or "localhost").strip() or "localhost"
    port = str(os.getenv("ALS_PG_PORT") or "5432").strip() or "5432"
    dbname = str(os.getenv("ALS_PG_DB") or "als_intel").strip() or "als_intel"
    user = str(os.getenv("ALS_PG_USER") or "als").strip() or "als"
    password = str(os.getenv("ALS_PG_PASSWORD") or "als")
    sslmode = str(os.getenv("ALS_PG_SSLMODE") or "prefer").strip() or "prefer"
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode={sslmode}"


def qmark_to_pyformat(sql: str) -> str:
    """Translate SQLite-style ``?`` placeholders to psycopg ``%s``.

    Literal ``%`` in SQL (e.g. ``LIKE 'PUBMED_%'``) must be escaped as ``%%``
    before introducing ``%s`` placeholders, or psycopg rejects the query.
    """
    escaped = sql.replace("%", "%%")
    return _PLACEHOLDER_RE.sub("%s", escaped)


class PgCursor:
    """sqlite3-like cursor wrapper over psycopg."""

    def __init__(self, conn: PgConnection, raw: Any) -> None:
        self._conn = conn
        self._raw = raw
        self.lastrowid: int | None = None
        self.rowcount = int(getattr(raw, "rowcount", -1) or -1)

    def fetchone(self) -> tuple[Any, ...] | None:
        row = self._raw.fetchone()
        return tuple(row) if row is not None else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return [tuple(row) for row in self._raw.fetchall()]

    def fetchmany(self, size: int | None = None) -> list[tuple[Any, ...]]:
        rows = self._raw.fetchmany(size) if size is not None else self._raw.fetchmany()
        return [tuple(row) for row in rows]

    def __iter__(self) -> Iterator[tuple[Any, ...]]:
        for row in self._raw:
            yield tuple(row)


class PgConnection:
    """sqlite3-compatible connection facade for EvidenceStore."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = psycopg.connect(dsn, row_factory=tuple_row, autocommit=False)

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> PgCursor:
        translated = qmark_to_pyformat(sql)
        cur = self._conn.execute(translated, params)
        wrapped = PgCursor(self, cur)
        wrapped.rowcount = int(getattr(cur, "rowcount", -1) or -1)
        return wrapped

    def executescript(self, script: str) -> None:
        # Split on semicolons outside of quotes is enough for our migration SQL.
        statements = [part.strip() for part in script.split(";") if part.strip()]
        for statement in statements:
            self._conn.execute(statement)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> PgConnection:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any) -> None:
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()


def connect(dsn: str | None = None) -> PgConnection:
    return PgConnection(resolve_dsn(dsn))


def migrations_dir() -> Path:
    configured = str(os.getenv("ALS_MIGRATIONS_DIR") or "").strip()
    if configured:
        return Path(configured)
    return MIGRATIONS_DIR


def list_migration_files() -> list[Path]:
    root = migrations_dir()
    if not root.is_dir():
        return []
    return sorted(path for path in root.glob("*.sql") if path.is_file())


def apply_migrations(conn: PgConnection) -> list[str]:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    applied_rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    applied = {str(row[0]) for row in applied_rows}
    newly: list[str] = []
    from datetime import datetime, timezone

    now_iso = datetime.now(timezone.utc).isoformat()
    for path in list_migration_files():
        version = path.name
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, now_iso),
        )
        newly.append(version)
    conn.commit()
    return newly


def table_names(conn: PgConnection) -> list[str]:
    rows = conn.execute(
        """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename <> 'schema_migrations'
        ORDER BY tablename
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def truncate_all_tables(conn: PgConnection) -> None:
    names = table_names(conn)
    if not names:
        return
    joined = ", ".join(f'"{name}"' for name in names)
    conn.execute(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE")
    conn.commit()
