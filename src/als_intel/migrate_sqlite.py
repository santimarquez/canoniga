from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from als_intel.db import connect, resolve_dsn, table_names
from als_intel.store import EvidenceStore

# FK-safe import order (parents before children).
IMPORT_TABLE_ORDER = [
    "users",
    "sync_runs",
    "evidence",
    "evidence_history",
    "sync_state",
    "sync_stage_state",
    "evidence_source_metadata",
    "evidence_change_log",
    "review_decisions",
    "investigator_sessions",
    "auth_magic_links",
    "auth_sessions",
    "user_activity",
    "investigation_runs",
    "investigation_templates",
    "automation_experiments",
    "automation_exports",
    "model_registry",
    "model_evaluations",
    "kg_nodes",
    "kg_edges",
    "manual_sync_cooldowns",
    "manual_sync_source_durations",
    "manual_sync_events",
]


def _sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _table_columns_pg(conn, table: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ?
        ORDER BY ordinal_position
        """,
        (table,),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _table_columns_sqlite(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def migrate_sqlite_to_postgres(
    *,
    sqlite_path: str | Path,
    dsn: str | None = None,
    truncate_first: bool = True,
) -> dict[str, object]:
    sqlite_file = Path(sqlite_path)
    if not sqlite_file.is_file():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_file}")

    store = EvidenceStore(dsn)
    store.init_db()
    target_dsn = resolve_dsn(dsn)

    src = sqlite3.connect(str(sqlite_file))
    src.row_factory = sqlite3.Row
    try:
        available = _sqlite_tables(src)
        report: dict[str, object] = {
            "sqlite_path": str(sqlite_file),
            "dsn": target_dsn,
            "tables": {},
            "ok": True,
        }
        with connect(target_dsn) as dst:
            if truncate_first:
                names = table_names(dst)
                if names:
                    joined = ", ".join(f'"{name}"' for name in names)
                    dst.execute(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE")

            dst.execute("SET session_replication_role = replica")
            try:
                for table in IMPORT_TABLE_ORDER:
                    if table not in available:
                        continue
                    sqlite_cols = _table_columns_sqlite(src, table)
                    pg_cols = _table_columns_pg(dst, table)
                    shared = [col for col in sqlite_cols if col in pg_cols]
                    if not shared:
                        continue
                    rows = src.execute(
                        f"SELECT {', '.join(shared)} FROM {table}"
                    ).fetchall()
                    inserted = 0
                    if rows:
                        placeholders = ", ".join(["?"] * len(shared))
                        col_list = ", ".join(shared)
                        sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
                        for row in rows:
                            values = [row[col] for col in shared]
                            dst.execute(sql, tuple(values))
                            inserted += 1
                    src_count = int(
                        src.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    )
                    pg_count = int(
                        dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    )
                    report["tables"][table] = {
                        "sqlite_count": src_count,
                        "postgres_count": pg_count,
                        "inserted": inserted,
                        "parity": src_count == pg_count,
                    }
                    if src_count != pg_count:
                        report["ok"] = False
            finally:
                dst.execute("SET session_replication_role = DEFAULT")
            dst.commit()

        # Sample claim_id checksum for evidence
        if "evidence" in available:
            src_ids = {
                str(row[0])
                for row in src.execute("SELECT claim_id FROM evidence").fetchall()
            }
            with connect(target_dsn) as dst:
                pg_ids = {
                    str(row[0])
                    for row in dst.execute("SELECT claim_id FROM evidence").fetchall()
                }
            report["evidence_claim_id_parity"] = src_ids == pg_ids
            if src_ids != pg_ids:
                report["ok"] = False
        return report
    finally:
        src.close()


def format_migration_report(report: dict[str, object]) -> str:
    return json.dumps(report, indent=2, sort_keys=True)
