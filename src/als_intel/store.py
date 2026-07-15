from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from als_intel.models import EvidenceRecord


SOURCE_DISPLAY_NAMES = {
    "pubmed": "PubMed",
    "ctgov": "ClinicalTrials.gov",
    "pmc": "PubMed Central (PMC)",
    "ncbi_gene": "NCBI Gene",
    "uniprot": "UniProt",
    "go": "Gene Ontology (GO)",
    "reactome": "Reactome",
    "geo": "GEO (Gene Expression Omnibus)",
    "arrayexpress": "ArrayExpress",
    "kegg": "KEGG",
    "pride": "Proteomics databases (PRIDE as first concrete target)",
    "metabolomics_workbench": "Metabolomics Workbench",
    "chembl": "ChEMBL",
    "open_targets": "Open Targets",
    "fda_labels": "FDA Drug Labels",
}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL UNIQUE,
    claim_text TEXT NOT NULL,
    disease TEXT NOT NULL,
    entity TEXT NOT NULL,
    relation TEXT NOT NULL,
    outcome TEXT NOT NULL,
    effect_direction TEXT NOT NULL,
    study_type TEXT NOT NULL,
    sample_size INTEGER NOT NULL,
    endpoint_validity REAL NOT NULL,
    replication_count INTEGER NOT NULL,
    peer_reviewed INTEGER NOT NULL,
    year INTEGER NOT NULL,
    source_title TEXT NOT NULL,
    source_doi TEXT NOT NULL,
    cohort TEXT NOT NULL DEFAULT 'unknown',
    model_system TEXT NOT NULL DEFAULT 'unspecified',
    source_type TEXT NOT NULL DEFAULT 'journal',
    extraction_confidence REAL NOT NULL DEFAULT 1.0,
    causal_evidence_type TEXT NOT NULL DEFAULT 'observational',
    ingested_at TEXT NOT NULL DEFAULT '',
    source_reliability_score REAL NOT NULL DEFAULT 0.0,
    reliability_score REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    event_time TEXT NOT NULL,
    reliability_score REAL NOT NULL,
    study_component REAL NOT NULL,
    sample_component REAL NOT NULL,
    replication_component REAL NOT NULL,
    peer_component REAL NOT NULL,
    endpoint_component REAL NOT NULL,
    source_component REAL NOT NULL,
    extraction_component REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    query TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    records_seen INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    unchanged_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sync_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL UNIQUE,
    last_sync_run_id INTEGER,
    last_sync_timestamp TEXT,
    last_successful_timestamp TEXT,
    failure_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(last_sync_run_id) REFERENCES sync_runs(id)
);

CREATE TABLE IF NOT EXISTS sync_stage_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    last_sync_run_id INTEGER,
    last_sync_timestamp TEXT,
    last_successful_timestamp TEXT,
    failure_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(last_sync_run_id) REFERENCES sync_runs(id),
    UNIQUE(source_name, stage_name)
);

CREATE TABLE IF NOT EXISTS evidence_source_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL UNIQUE,
    source_name TEXT NOT NULL,
    source_id TEXT NOT NULL,
    abstract_text TEXT NOT NULL DEFAULT '',
    journal TEXT NOT NULL DEFAULT '',
    pubdate TEXT NOT NULL DEFAULT '',
    authors_json TEXT NOT NULL DEFAULT '[]',
    mesh_terms_json TEXT NOT NULL DEFAULT '[]',
    affiliations_json TEXT NOT NULL DEFAULT '[]',
    references_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    enriched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    claim_id TEXT NOT NULL,
    change_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES sync_runs(id)
);

CREATE TABLE IF NOT EXISTS review_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS investigator_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    question TEXT NOT NULL DEFAULT '',
    messages_json TEXT NOT NULL DEFAULT '[]',
    report_json TEXT NOT NULL DEFAULT '{}',
    filters_json TEXT NOT NULL DEFAULT '{}',
    evidence_claim_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS auth_magic_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    requested_ip TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT,
    revoked_at TEXT,
    user_agent TEXT NOT NULL DEFAULT '',
    ip_address TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS user_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS investigation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL DEFAULT '',
    objective TEXT NOT NULL,
    filters_json TEXT NOT NULL DEFAULT '{}',
    require_review_signoff INTEGER NOT NULL DEFAULT 0,
    scheduled_for TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    replay_of_run_id TEXT NOT NULL DEFAULT '',
    report_json TEXT NOT NULL DEFAULT '{}',
    quality_gate_json TEXT NOT NULL DEFAULT '{}',
    replay_diff_json TEXT NOT NULL DEFAULT '{}',
    approval_status TEXT NOT NULL DEFAULT 'pending',
    approved_by TEXT NOT NULL DEFAULT '',
    approved_at TEXT,
    rollback_run_id TEXT NOT NULL DEFAULT '',
    rolled_back_at TEXT,
    export_status TEXT NOT NULL DEFAULT 'not_exported',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    error_text TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS investigation_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    objective TEXT NOT NULL,
    filters_json TEXT NOT NULL DEFAULT '{}',
    require_review_signoff INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_used_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS automation_experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    objective TEXT NOT NULL,
    filters_json TEXT NOT NULL DEFAULT '{}',
    variant_a_json TEXT NOT NULL DEFAULT '{}',
    variant_b_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    winner_variant TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS automation_exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    error_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    delivered_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS model_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    base_model TEXT NOT NULL,
    adapter_path TEXT NOT NULL,
    dataset_manifest_path TEXT NOT NULL,
    training_config_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS model_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    candidate_model_id TEXT NOT NULL,
    baseline_model_id TEXT NOT NULL DEFAULT '',
    benchmark_manifest_path TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    gate_json TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS kg_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_key TEXT NOT NULL UNIQUE,
    node_type TEXT NOT NULL,
    label TEXT NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kg_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL,
    target_key TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    polarity TEXT NOT NULL,
    weight REAL NOT NULL,
    relation TEXT NOT NULL DEFAULT '',
    evidence_claim_id TEXT NOT NULL,
    event_time TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS manual_sync_cooldowns (
    scope TEXT NOT NULL PRIMARY KEY,
    last_successful_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS manual_sync_source_durations (
    source_name TEXT NOT NULL PRIMARY KEY,
    sample_count INTEGER NOT NULL DEFAULT 0,
    avg_duration_seconds REAL NOT NULL DEFAULT 0,
    last_duration_seconds REAL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_manual_sync_source_durations_source
ON manual_sync_source_durations (source_name);

CREATE INDEX IF NOT EXISTS idx_evidence_entity_direction_claim_reliability
ON evidence (entity, effect_direction, claim_id, reliability_score DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_history_claim_time
ON evidence_history (claim_id, event_time);

CREATE INDEX IF NOT EXISTS idx_change_log_run
ON evidence_change_log (run_id, claim_id);

CREATE INDEX IF NOT EXISTS idx_sync_state_source
ON sync_state (source_name);

CREATE INDEX IF NOT EXISTS idx_sync_stage_state_source_stage
ON sync_stage_state (source_name, stage_name);

CREATE INDEX IF NOT EXISTS idx_evidence_source_metadata_source
ON evidence_source_metadata (source_name, source_id, enriched_at DESC);

CREATE INDEX IF NOT EXISTS idx_review_decisions_claim
ON review_decisions (claim_id, decided_at);

CREATE INDEX IF NOT EXISTS idx_investigator_sessions_updated
ON investigator_sessions (updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_users_email
ON users (email);

CREATE INDEX IF NOT EXISTS idx_auth_magic_links_email_expires
ON auth_magic_links (email, expires_at DESC);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_expires
ON auth_sessions (user_id, expires_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_activity_user_created
ON user_activity (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_investigation_runs_user_created
ON investigation_runs (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_investigation_runs_status
ON investigation_runs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_investigation_templates_user_updated
ON investigation_templates (user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_automation_experiments_user_created
ON automation_experiments (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_automation_exports_user_created
ON automation_exports (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_model_registry_created_at
ON model_registry (created_at);

CREATE INDEX IF NOT EXISTS idx_model_evaluations_candidate
ON model_evaluations (candidate_model_id, created_at);

CREATE INDEX IF NOT EXISTS idx_kg_nodes_key
ON kg_nodes (node_key, node_type);

CREATE INDEX IF NOT EXISTS idx_kg_edges_source_target
ON kg_edges (source_key, target_key, edge_type);
"""


MIGRATION_COLUMNS = {
    "cohort": "TEXT NOT NULL DEFAULT 'unknown'",
    "model_system": "TEXT NOT NULL DEFAULT 'unspecified'",
    "source_type": "TEXT NOT NULL DEFAULT 'journal'",
    "extraction_confidence": "REAL NOT NULL DEFAULT 1.0",
    "causal_evidence_type": "TEXT NOT NULL DEFAULT 'observational'",
    "ingested_at": "TEXT NOT NULL DEFAULT ''",
    "source_reliability_score": "REAL NOT NULL DEFAULT 0.0",
}

INVESTIGATOR_SESSION_MIGRATION_COLUMNS = {
    "user_id": "TEXT NOT NULL DEFAULT ''",
}

INVESTIGATION_RUN_MIGRATION_COLUMNS = {
    "idempotency_key": "TEXT NOT NULL DEFAULT ''",
    "require_review_signoff": "INTEGER NOT NULL DEFAULT 0",
    "scheduled_for": "TEXT",
    "attempt_count": "INTEGER NOT NULL DEFAULT 0",
    "max_attempts": "INTEGER NOT NULL DEFAULT 1",
    "approval_status": "TEXT NOT NULL DEFAULT 'pending'",
    "approved_by": "TEXT NOT NULL DEFAULT ''",
    "approved_at": "TEXT",
    "rollback_run_id": "TEXT NOT NULL DEFAULT ''",
    "rolled_back_at": "TEXT",
    "export_status": "TEXT NOT NULL DEFAULT 'not_exported'",
}

USER_PROFILE_MIGRATION_COLUMNS = {
    "display_name": "TEXT NOT NULL DEFAULT ''",
    "title": "TEXT NOT NULL DEFAULT ''",
    "institution": "TEXT NOT NULL DEFAULT ''",
    "avatar_data": "BLOB",
    "avatar_mime_type": "TEXT NOT NULL DEFAULT ''",
    "profile_updated_at": "TEXT",
}


class EvidenceStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        timeout_seconds = max(1.0, float(os.getenv("ALS_SQLITE_TIMEOUT_SECONDS", "30")))
        busy_timeout_ms = max(1000, int(os.getenv("ALS_SQLITE_BUSY_TIMEOUT_MS", "30000")))
        conn = sqlite3.connect(self.db_path, timeout=timeout_seconds)
        conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _map_evidence_rows(self, rows: list[tuple[object, ...]]) -> list[dict[str, str | int | float | bool]]:
        output: list[dict[str, str | int | float | bool]] = []
        for row in rows:
            output.append(
                {
                    "claim_id": str(row[0] or ""),
                    "claim_text": str(row[1] or ""),
                    "disease": str(row[2] or ""),
                    "entity": str(row[3] or ""),
                    "relation": str(row[4] or ""),
                    "outcome": str(row[5] or ""),
                    "effect_direction": str(row[6] or ""),
                    "study_type": str(row[7] or ""),
                    "sample_size": int(row[8] or 0),
                    "endpoint_validity": float(row[9] or 0.0),
                    "replication_count": int(row[10] or 0),
                    "peer_reviewed": bool(row[11]),
                    "year": int(row[12] or 0),
                    "source_title": str(row[13] or ""),
                    "source_doi": str(row[14] or ""),
                    "cohort": str(row[15] or ""),
                    "model_system": str(row[16] or ""),
                    "source_type": str(row[17] or ""),
                    "extraction_confidence": float(row[18] or 0.0),
                    "causal_evidence_type": str(row[19] or ""),
                    "source_reliability_score": float(row[20] or 0.0),
                    "reliability_score": float(row[21] or 0.0),
                }
            )
        return output

    def attach_extraction_provenance(
        self,
        rows: list[dict[str, str | int | float | bool]],
    ) -> list[dict[str, object]]:
        if not rows:
            return rows
        claim_ids = [str(row.get("claim_id", "")).strip() for row in rows if str(row.get("claim_id", "")).strip()]
        if not claim_ids:
            return rows
        placeholders = ", ".join(["?"] * len(claim_ids))
        query = f"""
            SELECT claim_id, metadata_json
            FROM evidence_source_metadata
            WHERE claim_id IN ({placeholders})
        """
        provenance_by_claim: dict[str, dict[str, object]] = {}
        with self._connect() as conn:
            fetched = conn.execute(query, tuple(claim_ids)).fetchall()
        for claim_id, metadata_json in fetched:
            try:
                metadata = json.loads(str(metadata_json or "{}"))
            except json.JSONDecodeError:
                metadata = {}
            extracted = metadata.get("extracted_claim")
            if isinstance(extracted, dict):
                provenance_by_claim[str(claim_id)] = extracted

        enriched: list[dict[str, object]] = []
        for row in rows:
            updated = dict(row)
            claim_id = str(row.get("claim_id", "")).strip()
            if claim_id in provenance_by_claim:
                updated["extraction_provenance"] = provenance_by_claim[claim_id]
            enriched.append(updated)
        return enriched

    def all_evidence_with_provenance(self) -> list[dict[str, object]]:
        return self.attach_extraction_provenance(self.all_evidence())

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            self._migrate_evidence_table(conn)
            self._migrate_investigator_sessions_table(conn)
            self._migrate_investigation_runs_table(conn)
            self._migrate_users_table(conn)
            conn.commit()

    def _migrate_evidence_table(self, conn: sqlite3.Connection) -> None:
        existing_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(evidence)").fetchall()
        }
        for col_name, col_def in MIGRATION_COLUMNS.items():
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE evidence ADD COLUMN {col_name} {col_def}")

    def _migrate_investigator_sessions_table(self, conn: sqlite3.Connection) -> None:
        existing_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(investigator_sessions)").fetchall()
        }
        for col_name, col_def in INVESTIGATOR_SESSION_MIGRATION_COLUMNS.items():
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE investigator_sessions ADD COLUMN {col_name} {col_def}")
        refreshed_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(investigator_sessions)").fetchall()
        }
        if "user_id" in refreshed_cols:
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_investigator_sessions_user
                ON investigator_sessions (user_id, updated_at DESC)
                """
            )

    def _migrate_investigation_runs_table(self, conn: sqlite3.Connection) -> None:
        existing_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(investigation_runs)").fetchall()
        }
        for col_name, col_def in INVESTIGATION_RUN_MIGRATION_COLUMNS.items():
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE investigation_runs ADD COLUMN {col_name} {col_def}")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_investigation_runs_user_idempotency
            ON investigation_runs (user_id, idempotency_key)
            """
        )

    def _migrate_users_table(self, conn: sqlite3.Connection) -> None:
        existing_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        for col_name, col_def in USER_PROFILE_MIGRATION_COLUMNS.items():
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")

    def _row_to_user_profile(
        self,
        row: tuple[object, ...],
        *,
        include_avatar_bytes: bool,
    ) -> dict[str, object]:
        avatar_bytes = row[5] if row[5] is not None else b""
        if not isinstance(avatar_bytes, (bytes, bytearray)):
            avatar_bytes = bytes(avatar_bytes)
        profile = {
            "user_id": str(row[0] or ""),
            "email": str(row[1] or ""),
            "display_name": str(row[2] or ""),
            "title": str(row[3] or ""),
            "institution": str(row[4] or ""),
            "avatar_mime_type": str(row[6] or ""),
            "profile_updated_at": str(row[7] or "") if row[7] is not None else "",
            "has_avatar": bool(avatar_bytes),
        }
        if include_avatar_bytes:
            profile["avatar_data"] = bytes(avatar_bytes)
        return profile

    def get_user_profile(self, *, user_id: str, include_avatar_bytes: bool = False) -> dict[str, object] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id, email, display_name, title, institution,
                       avatar_data, avatar_mime_type, profile_updated_at
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_user_profile(row, include_avatar_bytes=include_avatar_bytes)

    def upsert_user_profile(
        self,
        *,
        user_id: str,
        display_name: str,
        title: str,
        institution: str,
        avatar_bytes: bytes | None = None,
        avatar_mime_type: str | None = None,
        clear_avatar: bool = False,
    ) -> dict[str, object]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT avatar_data, avatar_mime_type
                FROM users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                raise ValueError("User not found")
            next_avatar = row[0] if row[0] is not None else b""
            next_mime = str(row[1] or "")
            if clear_avatar:
                next_avatar = b""
                next_mime = ""
            elif avatar_bytes is not None:
                next_avatar = avatar_bytes
                next_mime = str(avatar_mime_type or "")
            conn.execute(
                """
                UPDATE users
                SET display_name = ?,
                    title = ?,
                    institution = ?,
                    avatar_data = ?,
                    avatar_mime_type = ?,
                    profile_updated_at = ?
                WHERE user_id = ?
                """,
                (
                    display_name,
                    title,
                    institution,
                    next_avatar,
                    next_mime,
                    now_iso,
                    user_id,
                ),
            )
            conn.commit()
        profile = self.get_user_profile(user_id=user_id, include_avatar_bytes=False)
        if profile is None:
            raise ValueError("Failed to load updated profile")
        return profile

    def upsert_evidence(
        self,
        record: EvidenceRecord,
        score_breakdown: dict[str, float],
        source_score: float,
        run_id: int | None = None,
        source_name: str = "manual",
    ) -> str:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            before = conn.execute(
                """
                SELECT claim_text, disease, entity, relation, outcome, effect_direction,
                       study_type, sample_size, endpoint_validity, replication_count,
                       peer_reviewed, year, source_title, source_doi, cohort,
                       model_system, source_type, extraction_confidence, causal_evidence_type,
                       source_reliability_score, reliability_score
                FROM evidence
                WHERE claim_id = ?
                """,
                (record.claim_id,),
            ).fetchone()

            conn.execute(
                """
                INSERT INTO evidence (
                    claim_id, claim_text, disease, entity, relation, outcome,
                    effect_direction, study_type, sample_size, endpoint_validity,
                    replication_count, peer_reviewed, year, source_title, source_doi,
                     cohort, model_system, source_type, extraction_confidence, causal_evidence_type,
                     ingested_at, source_reliability_score, reliability_score
                 ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(claim_id) DO UPDATE SET
                    claim_text=excluded.claim_text,
                    disease=excluded.disease,
                    entity=excluded.entity,
                    relation=excluded.relation,
                    outcome=excluded.outcome,
                    effect_direction=excluded.effect_direction,
                    study_type=excluded.study_type,
                    sample_size=excluded.sample_size,
                    endpoint_validity=excluded.endpoint_validity,
                    replication_count=excluded.replication_count,
                    peer_reviewed=excluded.peer_reviewed,
                    year=excluded.year,
                    source_title=excluded.source_title,
                    source_doi=excluded.source_doi,
                    cohort=excluded.cohort,
                    model_system=excluded.model_system,
                    source_type=excluded.source_type,
                    extraction_confidence=excluded.extraction_confidence,
                     causal_evidence_type=excluded.causal_evidence_type,
                    ingested_at=excluded.ingested_at,
                    source_reliability_score=excluded.source_reliability_score,
                    reliability_score=excluded.reliability_score
                """,
                (
                    record.claim_id,
                    record.claim_text,
                    record.disease,
                    record.entity,
                    record.relation,
                    record.outcome,
                    record.effect_direction,
                    record.study_type,
                    record.sample_size,
                    record.endpoint_validity,
                    record.replication_count,
                    1 if record.peer_reviewed else 0,
                    record.year,
                    record.source_title,
                    record.source_doi,
                    record.cohort,
                    record.model_system,
                    record.source_type,
                    record.extraction_confidence,
                     record.causal_evidence_type,
                    now_iso,
                    source_score,
                    score_breakdown["total"],
                ),
            )
            conn.execute(
                """
                INSERT INTO evidence_history (
                    claim_id, event_time, reliability_score,
                    study_component, sample_component, replication_component,
                    peer_component, endpoint_component, source_component, extraction_component
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.claim_id,
                    now_iso,
                    score_breakdown["total"],
                    score_breakdown["study"],
                    score_breakdown["sample"],
                    score_breakdown["replication"],
                    score_breakdown["peer_review"],
                    score_breakdown["endpoint"],
                    score_breakdown["source"],
                    score_breakdown["extraction"],
                ),
            )

            if before is None:
                change_type = "inserted"
            else:
                current_payload = (
                    record.claim_text,
                    record.disease,
                    record.entity,
                    record.relation,
                    record.outcome,
                    record.effect_direction,
                    record.study_type,
                    record.sample_size,
                    record.endpoint_validity,
                    record.replication_count,
                    1 if record.peer_reviewed else 0,
                    record.year,
                    record.source_title,
                    record.source_doi,
                    record.cohort,
                    record.model_system,
                    record.source_type,
                    record.extraction_confidence,
                     record.causal_evidence_type,
                    source_score,
                    score_breakdown["total"],
                )
                change_type = "unchanged" if tuple(before) == current_payload else "updated"

            if run_id is not None and change_type != "unchanged":
                conn.execute(
                    """
                    INSERT INTO evidence_change_log (
                        run_id, claim_id, change_type, source_name, changed_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (run_id, record.claim_id, change_type, source_name, now_iso),
                )
            conn.commit()
        return change_type

    def start_sync_run(self, source_name: str, query: str) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO sync_runs (source_name, query, started_at, status)
                VALUES (?, ?, ?, 'running')
                """,
                (source_name, query, now_iso),
            )
            conn.commit()
            return int(cur.lastrowid)

    def finish_sync_run(
        self,
        run_id: int,
        records_seen: int,
        inserted_count: int,
        updated_count: int,
        unchanged_count: int,
        status: str,
        notes: str = "",
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET ended_at = ?, records_seen = ?, inserted_count = ?, updated_count = ?,
                    unchanged_count = ?, status = ?, notes = ?
                WHERE id = ?
                """,
                (now_iso, records_seen, inserted_count, updated_count, unchanged_count, status, notes, run_id),
            )
            conn.commit()

    def recent_changes(self, run_id: int | None = None, limit: int = 50) -> list[dict[str, object]]:
        if run_id is None:
            query = """
            SELECT c.run_id, c.claim_id, c.change_type, c.source_name, c.changed_at
            FROM evidence_change_log c
            ORDER BY c.id DESC
            LIMIT ?
            """
            params: tuple[object, ...] = (limit,)
        else:
            query = """
            SELECT c.run_id, c.claim_id, c.change_type, c.source_name, c.changed_at
            FROM evidence_change_log c
            WHERE c.run_id = ?
            ORDER BY c.id DESC
            LIMIT ?
            """
            params = (run_id, limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            {
                "run_id": int(r[0]),
                "claim_id": r[1],
                "change_type": r[2],
                "source_name": r[3],
                "changed_at": r[4],
            }
            for r in rows
        ]

    def get_sync_state(self, source_name: str) -> dict[str, object] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT source_name, last_sync_run_id, last_sync_timestamp,
                       last_successful_timestamp, failure_count, updated_at
                FROM sync_state
                WHERE source_name = ?
                """,
                (source_name,),
            ).fetchone()
        if row is None:
            return None
        return {
            "source_name": str(row[0]),
            "last_sync_run_id": int(row[1]) if row[1] is not None else None,
            "last_sync_timestamp": row[2],
            "last_successful_timestamp": row[3],
            "failure_count": int(row[4] or 0),
            "updated_at": row[5],
        }

    def get_stage_sync_state(self, source_name: str, stage_name: str) -> dict[str, object] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT source_name, stage_name, last_sync_run_id, last_sync_timestamp,
                       last_successful_timestamp, failure_count, updated_at
                FROM sync_stage_state
                WHERE source_name = ? AND stage_name = ?
                """,
                (source_name, stage_name),
            ).fetchone()
        if row is None:
            return None
        return {
            "source_name": str(row[0]),
            "stage_name": str(row[1]),
            "last_sync_run_id": int(row[2]) if row[2] is not None else None,
            "last_sync_timestamp": row[3],
            "last_successful_timestamp": row[4],
            "failure_count": int(row[5] or 0),
            "updated_at": row[6],
        }

    def update_sync_state(
        self,
        *,
        source_name: str,
        run_id: int,
        status: str,
        sync_timestamp: str | None = None,
    ) -> dict[str, object]:
        now_iso = sync_timestamp or datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            valid_run_row = conn.execute(
                "SELECT id FROM sync_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            persisted_run_id = int(run_id) if valid_run_row is not None else None

            existing = conn.execute(
                """
                SELECT last_successful_timestamp, failure_count
                FROM sync_state
                WHERE source_name = ?
                """,
                (source_name,),
            ).fetchone()

            previous_success = existing[0] if existing is not None else None
            previous_failures = int(existing[1] or 0) if existing is not None else 0

            if status == "ok":
                next_success = now_iso
                next_failure_count = 0
            else:
                next_success = previous_success
                next_failure_count = previous_failures + 1

            conn.execute(
                """
                INSERT INTO sync_state (
                    source_name,
                    last_sync_run_id,
                    last_sync_timestamp,
                    last_successful_timestamp,
                    failure_count,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                    last_sync_run_id=excluded.last_sync_run_id,
                    last_sync_timestamp=excluded.last_sync_timestamp,
                    last_successful_timestamp=excluded.last_successful_timestamp,
                    failure_count=excluded.failure_count,
                    updated_at=excluded.updated_at
                """,
                (
                    source_name,
                    persisted_run_id,
                    now_iso,
                    next_success,
                    next_failure_count,
                    now_iso,
                ),
            )
            conn.commit()

        return self.get_sync_state(source_name) or {
            "source_name": source_name,
            "last_sync_run_id": persisted_run_id,
            "last_sync_timestamp": now_iso,
            "last_successful_timestamp": now_iso if status == "ok" else None,
            "failure_count": 0 if status == "ok" else 1,
            "updated_at": now_iso,
        }

    def update_stage_sync_state(
        self,
        *,
        source_name: str,
        stage_name: str,
        run_id: int,
        status: str,
        sync_timestamp: str | None = None,
    ) -> dict[str, object]:
        now_iso = sync_timestamp or datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            valid_run_row = conn.execute(
                "SELECT id FROM sync_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            persisted_run_id = int(run_id) if valid_run_row is not None else None

            existing = conn.execute(
                """
                SELECT last_successful_timestamp, failure_count
                FROM sync_stage_state
                WHERE source_name = ? AND stage_name = ?
                """,
                (source_name, stage_name),
            ).fetchone()

            previous_success = existing[0] if existing is not None else None
            previous_failures = int(existing[1] or 0) if existing is not None else 0

            if status == "ok":
                next_success = now_iso
                next_failure_count = 0
            else:
                next_success = previous_success
                next_failure_count = previous_failures + 1

            conn.execute(
                """
                INSERT INTO sync_stage_state (
                    source_name,
                    stage_name,
                    last_sync_run_id,
                    last_sync_timestamp,
                    last_successful_timestamp,
                    failure_count,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_name, stage_name) DO UPDATE SET
                    last_sync_run_id=excluded.last_sync_run_id,
                    last_sync_timestamp=excluded.last_sync_timestamp,
                    last_successful_timestamp=excluded.last_successful_timestamp,
                    failure_count=excluded.failure_count,
                    updated_at=excluded.updated_at
                """,
                (
                    source_name,
                    stage_name,
                    persisted_run_id,
                    now_iso,
                    next_success,
                    next_failure_count,
                    now_iso,
                ),
            )
            conn.commit()

        return self.get_stage_sync_state(source_name, stage_name) or {
            "source_name": source_name,
            "stage_name": stage_name,
            "last_sync_run_id": persisted_run_id,
            "last_sync_timestamp": now_iso,
            "last_successful_timestamp": now_iso if status == "ok" else None,
            "failure_count": 0 if status == "ok" else 1,
            "updated_at": now_iso,
        }

    def list_pubmed_ids_for_enrichment(
        self,
        *,
        since_timestamp: str | None,
        limit: int = 200,
    ) -> list[dict[str, str]]:
        with self._connect() as conn:
            if since_timestamp:
                rows = conn.execute(
                    """
                    SELECT e.claim_id, e.source_doi
                    FROM evidence e
                    LEFT JOIN evidence_source_metadata m ON m.claim_id = e.claim_id
                    WHERE e.claim_id LIKE 'PUBMED_%'
                      AND (
                        e.ingested_at > ?
                        OR m.claim_id IS NULL
                      )
                    ORDER BY e.ingested_at ASC, e.claim_id ASC
                    LIMIT ?
                    """,
                    (since_timestamp, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT e.claim_id, e.source_doi
                    FROM evidence e
                    WHERE e.claim_id LIKE 'PUBMED_%'
                    ORDER BY e.ingested_at ASC, e.claim_id ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        return [
            {
                "claim_id": str(row[0]),
                "source_id": str(row[1]),
            }
            for row in rows
            if str(row[1]).strip()
        ]

    def upsert_evidence_source_metadata(
        self,
        *,
        claim_id: str,
        source_name: str,
        source_id: str,
        abstract_text: str,
        journal: str,
        pubdate: str,
        authors: list[str],
        mesh_terms: list[str],
        affiliations: list[str],
        references: list[str],
        metadata: dict[str, object],
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO evidence_source_metadata (
                    claim_id,
                    source_name,
                    source_id,
                    abstract_text,
                    journal,
                    pubdate,
                    authors_json,
                    mesh_terms_json,
                    affiliations_json,
                    references_json,
                    metadata_json,
                    enriched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(claim_id) DO UPDATE SET
                    source_name=excluded.source_name,
                    source_id=excluded.source_id,
                    abstract_text=excluded.abstract_text,
                    journal=excluded.journal,
                    pubdate=excluded.pubdate,
                    authors_json=excluded.authors_json,
                    mesh_terms_json=excluded.mesh_terms_json,
                    affiliations_json=excluded.affiliations_json,
                    references_json=excluded.references_json,
                    metadata_json=excluded.metadata_json,
                    enriched_at=excluded.enriched_at
                """,
                (
                    claim_id,
                    source_name,
                    source_id,
                    abstract_text,
                    journal,
                    pubdate,
                    json.dumps(authors),
                    json.dumps(mesh_terms),
                    json.dumps(affiliations),
                    json.dumps(references),
                    json.dumps(metadata),
                    now_iso,
                ),
            )
            conn.commit()

    def get_evidence_source_metadata(self, claim_id: str) -> dict[str, object] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT claim_id, source_name, source_id, abstract_text, journal, pubdate,
                       authors_json, mesh_terms_json, affiliations_json,
                       references_json, metadata_json, enriched_at
                FROM evidence_source_metadata
                WHERE claim_id = ?
                """,
                (claim_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "claim_id": str(row[0]),
            "source_name": str(row[1]),
            "source_id": str(row[2]),
            "abstract_text": str(row[3]),
            "journal": str(row[4]),
            "pubdate": str(row[5]),
            "authors": json.loads(str(row[6] or "[]")),
            "mesh_terms": json.loads(str(row[7] or "[]")),
            "affiliations": json.loads(str(row[8] or "[]")),
            "references": json.loads(str(row[9] or "[]")),
            "metadata": json.loads(str(row[10] or "{}")),
            "enriched_at": str(row[11]),
        }

    def summary(self) -> dict[str, float | int]:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            avg_score = conn.execute("SELECT COALESCE(AVG(reliability_score), 0.0) FROM evidence").fetchone()[0]
            avg_source_score = conn.execute(
                "SELECT COALESCE(AVG(source_reliability_score), 0.0) FROM evidence"
            ).fetchone()[0]
            supports = conn.execute(
                "SELECT COUNT(*) FROM evidence WHERE effect_direction='supports'"
            ).fetchone()[0]
            contradicts = conn.execute(
                "SELECT COUNT(*) FROM evidence WHERE effect_direction='contradicts'"
            ).fetchone()[0]
        return {
            "records": int(count),
            "avg_reliability": round(float(avg_score), 4),
            "avg_source_reliability": round(float(avg_source_score), 4),
            "supports": int(supports),
            "contradicts": int(contradicts),
        }

    def contradiction_pairs(self) -> list[dict[str, str | float]]:
        query = """
        SELECT a.claim_id, b.claim_id, a.entity, a.outcome, b.outcome,
               a.reliability_score, b.reliability_score,
               a.cohort, b.cohort, a.model_system, b.model_system
        FROM evidence a
        JOIN evidence b
          ON a.entity = b.entity
         AND a.claim_id < b.claim_id
        WHERE (
            (a.effect_direction='supports' AND b.effect_direction='contradicts')
            OR (a.effect_direction='contradicts' AND b.effect_direction='supports')
        )
        ORDER BY (a.reliability_score + b.reliability_score) DESC
        """

        with self._connect() as conn:
            rows = conn.execute(query).fetchall()

        output: list[dict[str, str | float]] = []
        for (
            claim_a,
            claim_b,
            entity,
            outcome_a,
            outcome_b,
            score_a,
            score_b,
            cohort_a,
            cohort_b,
            model_a,
            model_b,
        ) in rows:
            contradiction_type = "direction_conflict"
            follow_up = "Run replication study with matched endpoint definitions and harmonized analysis plan."
            if outcome_a != outcome_b:
                contradiction_type = "endpoint_mismatch"
                follow_up = "Design an endpoint-alignment study with both outcomes measured in the same cohort."
            elif cohort_a != cohort_b and cohort_a != "unknown" and cohort_b != "unknown":
                contradiction_type = "cohort_mismatch"
                follow_up = "Perform stratified analysis across harmonized cohorts and pre-registered covariates."
            elif model_a != model_b and model_a != "unspecified" and model_b != "unspecified":
                contradiction_type = "model_system_mismatch"
                follow_up = "Bridge findings using translational model-to-human validation pipeline."

            output.append(
                {
                    "claim_a": claim_a,
                    "claim_b": claim_b,
                    "entity": entity,
                    "outcome_a": outcome_a,
                    "outcome_b": outcome_b,
                    "score_a": float(score_a),
                    "score_b": float(score_b),
                    "contradiction_type": contradiction_type,
                    "follow_up_experiment": follow_up,
                }
            )
        return output

    def confidence_drift(self, claim_id: str | None = None) -> list[dict[str, str | float | int]]:
        query = """
        SELECT claim_id,
               MIN(event_time) AS first_seen,
               MAX(event_time) AS last_seen,
               COUNT(*) AS points,
               MIN(id) AS min_id,
               MAX(id) AS max_id
        FROM evidence_history
        {where_clause}
        GROUP BY claim_id
        ORDER BY claim_id
        """
        params: tuple[str, ...] = ()
        where_clause = ""
        if claim_id:
            where_clause = "WHERE claim_id = ?"
            params = (claim_id,)

        with self._connect() as conn:
            groups = conn.execute(query.format(where_clause=where_clause), params).fetchall()
            output: list[dict[str, str | float | int]] = []
            for cid, first_seen, last_seen, points, min_id, max_id in groups:
                start = conn.execute(
                    "SELECT reliability_score FROM evidence_history WHERE id = ?",
                    (min_id,),
                ).fetchone()[0]
                end = conn.execute(
                    "SELECT reliability_score FROM evidence_history WHERE id = ?",
                    (max_id,),
                ).fetchone()[0]
                output.append(
                    {
                        "claim_id": cid,
                        "first_seen": str(first_seen),
                        "last_seen": str(last_seen),
                        "points": int(points),
                        "start_score": float(start),
                        "end_score": float(end),
                        "delta": round(float(end) - float(start), 4),
                    }
                )
        return output

    def all_evidence(self) -> list[dict[str, str | int | float | bool]]:
        query = """
        SELECT claim_id, claim_text, disease, entity, relation, outcome, effect_direction,
               study_type, sample_size, endpoint_validity, replication_count, peer_reviewed,
               year, source_title, source_doi, cohort, model_system, source_type,
              extraction_confidence, causal_evidence_type, source_reliability_score, reliability_score
        FROM evidence
        ORDER BY claim_id
        """
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()

        return self._map_evidence_rows(rows)

    def filter_evidence(
        self,
        *,
        filters: dict[str, object],
        limit: int | None = None,
    ) -> list[dict[str, str | int | float | bool]]:
        safe_limit: int | None = None
        if limit is not None:
            safe_limit = max(1, min(int(limit), 20000))

        evidence_types = {
            str(x).strip().lower()
            for x in (filters.get("evidence_types") or [])
            if str(x).strip()
        } if isinstance(filters, dict) else set()
        date_window = str((filters or {}).get("date_window", "all")).strip().lower() if isinstance(filters, dict) else "all"
        highlight_contradictions = bool((filters or {}).get("highlight_contradictions", False)) if isinstance(filters, dict) else False
        try:
            min_reliability = float((filters or {}).get("min_reliability", 0.0)) if isinstance(filters, dict) else 0.0
        except (TypeError, ValueError):
            min_reliability = 0.0

        where_clauses: list[str] = ["reliability_score >= ?"]
        params: list[object] = [min_reliability]

        if evidence_types:
            placeholders = ", ".join(["?"] * len(evidence_types))
            where_clauses.append(f"LOWER(causal_evidence_type) IN ({placeholders})")
            params.extend(sorted(evidence_types))

        current_year = datetime.now(timezone.utc).year
        if date_window == "last5":
            where_clauses.append("year >= ?")
            params.append(current_year - 5)
        elif date_window == "last10":
            where_clauses.append("year >= ?")
            params.append(current_year - 10)

        order_clause = "reliability_score DESC, claim_id ASC"
        if highlight_contradictions:
            order_clause = (
                "CASE WHEN LOWER(effect_direction) = 'contradicts' THEN 0 ELSE 1 END ASC, "
                "reliability_score DESC, claim_id ASC"
            )

        query = f"""
        SELECT claim_id, claim_text, disease, entity, relation, outcome, effect_direction,
               study_type, sample_size, endpoint_validity, replication_count, peer_reviewed,
               year, source_title, source_doi, cohort, model_system, source_type,
               extraction_confidence, causal_evidence_type, source_reliability_score, reliability_score
        FROM evidence
        WHERE {' AND '.join(where_clauses)}
        ORDER BY {order_clause}
        """

        if safe_limit is not None:
            query = query + "\nLIMIT ?"
            params.append(safe_limit)

        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        return self._map_evidence_rows(rows)

    def claim_lineage(self, claim_id: str) -> dict[str, object]:
        with self._connect() as conn:
            target = conn.execute(
                """
                SELECT claim_id, claim_text, entity, relation, outcome, effect_direction,
                       source_doi, reliability_score
                FROM evidence
                WHERE claim_id = ?
                """,
                (claim_id,),
            ).fetchone()

            if target is None:
                raise ValueError(f"Unknown claim_id: {claim_id}")

            t_claim_id, t_text, t_entity, t_relation, t_outcome, t_dir, t_doi, t_score = target

            related = conn.execute(
                """
                SELECT claim_id, source_doi, effect_direction, reliability_score
                FROM evidence
                WHERE claim_id != ?
                  AND entity = ?
                  AND relation = ?
                  AND outcome = ?
                ORDER BY reliability_score DESC
                """,
                (claim_id, t_entity, t_relation, t_outcome),
            ).fetchall()

        supporting: list[dict[str, object]] = []
        contradicting: list[dict[str, object]] = []
        neutral: list[dict[str, object]] = []
        for r_claim_id, r_doi, r_dir, r_score in related:
            row = {
                "claim_id": r_claim_id,
                "source_doi": r_doi,
                "effect_direction": r_dir,
                "reliability_score": float(r_score),
            }
            if r_dir == t_dir:
                supporting.append(row)
            elif r_dir == "neutral":
                neutral.append(row)
            else:
                contradicting.append(row)

        return {
            "claim": {
                "claim_id": t_claim_id,
                "claim_text": t_text,
                "entity": t_entity,
                "relation": t_relation,
                "outcome": t_outcome,
                "effect_direction": t_dir,
                "source_doi": t_doi,
                "reliability_score": float(t_score),
            },
            "lineage": {
                "supporting_citations": supporting,
                "contradicting_citations": contradicting,
                "neutral_citations": neutral,
            },
            "lineage_counts": {
                "supporting": len(supporting),
                "contradicting": len(contradicting),
                "neutral": len(neutral),
            },
        }

    def review_flags(
        self,
        delta_threshold: float = 0.15,
        contradiction_density_threshold: float = 0.34,
    ) -> list[dict[str, object]]:
        evidence = self.all_evidence()
        contradictions = self.contradiction_pairs()
        drift_rows = self.confidence_drift()

        by_entity_count: dict[str, int] = {}
        for row in evidence:
            entity = str(row["entity"])
            by_entity_count[entity] = by_entity_count.get(entity, 0) + 1

        contradiction_by_entity: dict[str, int] = {}
        contradiction_claims: set[str] = set()
        for row in contradictions:
            entity = str(row["entity"])
            contradiction_by_entity[entity] = contradiction_by_entity.get(entity, 0) + 1
            contradiction_claims.add(str(row["claim_a"]))
            contradiction_claims.add(str(row["claim_b"]))

        drift_by_claim = {
            str(r["claim_id"]): {
                "delta": float(r["delta"]),
                "points": int(r["points"]),
            }
            for r in drift_rows
        }

        flags: list[dict[str, object]] = []
        for row in evidence:
            claim_id = str(row["claim_id"])
            entity = str(row["entity"])
            density = contradiction_by_entity.get(entity, 0) / max(by_entity_count.get(entity, 1), 1)

            drift = drift_by_claim.get(claim_id, {"delta": 0.0, "points": 1})
            abs_delta = abs(float(drift["delta"]))
            has_high_delta = int(drift["points"]) >= 2 and abs_delta >= delta_threshold
            has_high_density = density >= contradiction_density_threshold and claim_id in contradiction_claims

            if not (has_high_delta or has_high_density):
                continue

            reasons: list[str] = []
            if has_high_delta:
                reasons.append(
                    f"confidence_delta_exceeds_threshold({abs_delta:.4f} >= {delta_threshold:.4f})"
                )
            if has_high_density:
                reasons.append(
                    f"contradiction_density_exceeds_threshold({density:.4f} >= {contradiction_density_threshold:.4f})"
                )

            risk_score = min(1.0, 0.6 * min(abs_delta / max(delta_threshold, 0.0001), 1.0) + 0.4 * min(density, 1.0))
            flags.append(
                {
                    "claim_id": claim_id,
                    "entity": entity,
                    "reliability_score": float(row["reliability_score"]),
                    "confidence_delta": round(float(drift["delta"]), 4),
                    "contradiction_density": round(float(density), 4),
                    "risk_score": round(float(risk_score), 4),
                    "requires_human_review": True,
                    "reasons": reasons,
                }
            )

        flags.sort(key=lambda x: x["risk_score"], reverse=True)
        return flags

    def consensus_timeline(
        self,
        entity: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        with self._connect() as conn:
            if entity:
                query = """
                SELECT h.event_time, e.entity, e.claim_id, e.effect_direction, h.reliability_score,
                       c.change_type, c.source_name
                FROM evidence_history h
                JOIN evidence e ON e.claim_id = h.claim_id
                LEFT JOIN evidence_change_log c
                  ON c.claim_id = e.claim_id
                 AND c.changed_at = h.event_time
                WHERE e.entity = ?
                ORDER BY h.event_time DESC
                LIMIT ?
                """
                rows = conn.execute(query, (entity, limit)).fetchall()
            else:
                query = """
                SELECT h.event_time, e.entity, e.claim_id, e.effect_direction, h.reliability_score,
                       c.change_type, c.source_name
                FROM evidence_history h
                JOIN evidence e ON e.claim_id = h.claim_id
                LEFT JOIN evidence_change_log c
                  ON c.claim_id = e.claim_id
                 AND c.changed_at = h.event_time
                ORDER BY h.event_time DESC
                LIMIT ?
                """
                rows = conn.execute(query, (limit,)).fetchall()

        timeline: list[dict[str, object]] = []
        for event_time, evt_entity, claim_id, effect_direction, reliability, change_type, source_name in rows:
            if effect_direction == "supports":
                consensus_state = "supporting_signal"
            elif effect_direction == "contradicts":
                consensus_state = "contradicting_signal"
            else:
                consensus_state = "neutral_signal"

            rationale_parts: list[str] = []
            if change_type:
                rationale_parts.append(f"change_type={change_type}")
            if source_name:
                rationale_parts.append(f"source={source_name}")
            rationale_parts.append(f"effect_direction={effect_direction}")
            rationale = ", ".join(rationale_parts)

            timeline.append(
                {
                    "event_time": event_time,
                    "entity": evt_entity,
                    "claim_id": claim_id,
                    "reliability_score": float(reliability),
                    "consensus_state": consensus_state,
                    "change_rationale": rationale,
                }
            )
        return timeline

    def record_review_decision(
        self,
        claim_id: str,
        decision: str,
        reviewer: str,
        notes: str = "",
    ) -> None:
        valid = {"approve", "reject", "needs_more_evidence"}
        if decision not in valid:
            raise ValueError(f"decision must be one of: {sorted(valid)}")

        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM evidence WHERE claim_id = ?",
                (claim_id,),
            ).fetchone()
            if exists is None:
                raise ValueError(f"Unknown claim_id: {claim_id}")

            conn.execute(
                """
                INSERT INTO review_decisions (claim_id, decision, reviewer, notes, decided_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (claim_id, decision, reviewer, notes, now_iso),
            )
            conn.commit()

    def approved_claim_ids(self) -> set[str]:
        query = """
        SELECT claim_id, decision
        FROM review_decisions
        ORDER BY id DESC
        """
        with self._connect() as conn:
            rows = conn.execute(query).fetchall()

        latest: dict[str, str] = {}
        for claim_id, decision in rows:
            if claim_id not in latest:
                latest[claim_id] = decision

        return {cid for cid, decision in latest.items() if decision == "approve"}

    def list_review_decisions(
        self,
        claim_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        if claim_id:
            query = """
            SELECT claim_id, decision, reviewer, notes, decided_at
            FROM review_decisions
            WHERE claim_id = ?
            ORDER BY id DESC
            LIMIT ?
            """
            params: tuple[object, ...] = (claim_id, limit)
        else:
            query = """
            SELECT claim_id, decision, reviewer, notes, decided_at
            FROM review_decisions
            ORDER BY id DESC
            LIMIT ?
            """
            params = (limit,)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            {
                "claim_id": row[0],
                "decision": row[1],
                "reviewer": row[2],
                "notes": row[3],
                "decided_at": row[4],
            }
            for row in rows
        ]

    def save_investigator_session(
        self,
        *,
        user_id: str,
        session_id: str,
        title: str,
        question: str,
        messages: list[dict[str, object]],
        report: dict[str, object],
        filters: dict[str, object],
        evidence_claim_ids: list[str],
    ) -> dict[str, object]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT user_id
                FROM investigator_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if existing is not None and str(existing[0]) != str(user_id):
                raise ValueError("session_id belongs to another user")
            conn.execute(
                """
                INSERT INTO investigator_sessions (
                    user_id, session_id, title, question, messages_json, report_json,
                    filters_json, evidence_claim_ids_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    title=excluded.title,
                    question=excluded.question,
                    messages_json=excluded.messages_json,
                    report_json=excluded.report_json,
                    filters_json=excluded.filters_json,
                    evidence_claim_ids_json=excluded.evidence_claim_ids_json,
                    updated_at=excluded.updated_at
                """,
                (
                    user_id,
                    session_id,
                    title,
                    question,
                    json.dumps(messages, ensure_ascii=True),
                    json.dumps(report, ensure_ascii=True),
                    json.dumps(filters, ensure_ascii=True),
                    json.dumps(evidence_claim_ids, ensure_ascii=True),
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()

        return {
            "user_id": user_id,
            "session_id": session_id,
            "updated_at": now_iso,
        }

    def list_investigator_sessions(self, *, user_id: str, limit: int = 50) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, title, question, created_at, updated_at
                FROM investigator_sessions
                WHERE user_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

        return [
            {
                "session_id": row[0],
                "title": row[1],
                "question": row[2],
                "created_at": row[3],
                "updated_at": row[4],
            }
            for row in rows
        ]

    def get_investigator_session(self, *, user_id: str, session_id: str) -> dict[str, object]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id, session_id, title, question, messages_json, report_json,
                       filters_json, evidence_claim_ids_json, created_at, updated_at
                FROM investigator_sessions
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id),
            ).fetchone()

        if row is None:
            raise ValueError(f"Unknown session_id: {session_id}")

        return {
            "user_id": row[0],
            "session_id": row[1],
            "title": row[2],
            "question": row[3],
            "messages": json.loads(row[4]),
            "report": json.loads(row[5]),
            "filters": json.loads(row[6]),
            "evidence_claim_ids": json.loads(row[7]),
            "created_at": row[8],
            "updated_at": row[9],
        }

    def get_or_create_user(self, *, user_id: str, email: str) -> dict[str, str]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (user_id, email, created_at, last_login_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    last_login_at=excluded.last_login_at
                """,
                (user_id, email, now_iso, now_iso),
            )
            row = conn.execute(
                """
                SELECT user_id, email
                FROM users
                WHERE email = ?
                """,
                (email,),
            ).fetchone()
            conn.commit()
        if row is None:
            raise ValueError("Failed to upsert user")
        return {"user_id": str(row[0]), "email": str(row[1])}

    def get_user_by_email(self, email: str) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_id, email
                FROM users
                WHERE email = ?
                """,
                (email,),
            ).fetchone()
        if row is None:
            return None
        return {"user_id": str(row[0]), "email": str(row[1])}

    def create_magic_link(
        self,
        *,
        email: str,
        token_hash: str,
        expires_at: str,
        requested_ip: str,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO auth_magic_links (email, token_hash, created_at, expires_at, requested_ip)
                VALUES (?, ?, ?, ?, ?)
                """,
                (email, token_hash, now_iso, expires_at, requested_ip),
            )
            conn.commit()

    def count_recent_magic_link_requests(self, *, email: str, since_iso: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM auth_magic_links
                WHERE email = ? AND created_at >= ?
                """,
                (email, since_iso),
            ).fetchone()
        return int(row[0] if row is not None else 0)

    def count_recent_magic_link_requests_by_ip(self, *, requested_ip: str, since_iso: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM auth_magic_links
                WHERE requested_ip = ? AND created_at >= ?
                """,
                (requested_ip, since_iso),
            ).fetchone()
        return int(row[0] if row is not None else 0)

    def consume_magic_link(self, *, token_hash: str, now_iso: str) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, email, expires_at, consumed_at
                FROM auth_magic_links
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            if row[3] is not None:
                return {"email": str(row[1]), "status": "replayed"}
            if str(row[2]) <= now_iso:
                return {"email": str(row[1]), "status": "expired"}
            conn.execute(
                """
                UPDATE auth_magic_links
                SET consumed_at = ?
                WHERE id = ?
                """,
                (now_iso, row[0]),
            )
            conn.commit()
        return {"email": str(row[1]), "status": "ok"}

    def create_auth_session(
        self,
        *,
        user_id: str,
        token_hash: str,
        expires_at: str,
        user_agent: str,
        ip_address: str,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO auth_sessions (
                    user_id, token_hash, created_at, expires_at, last_seen_at,
                    user_agent, ip_address
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, token_hash, now_iso, expires_at, now_iso, user_agent, ip_address),
            )
            conn.commit()

    def resolve_auth_session(self, *, token_hash: str, now_iso: str) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT s.user_id, u.email, s.expires_at, s.revoked_at
                FROM auth_sessions s
                JOIN users u ON u.user_id = s.user_id
                WHERE s.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            if row[3] is not None:
                return None
            if str(row[2]) <= now_iso:
                return None
            conn.execute(
                """
                UPDATE auth_sessions
                SET last_seen_at = ?
                WHERE token_hash = ?
                """,
                (now_iso, token_hash),
            )
            conn.commit()
        return {"user_id": str(row[0]), "email": str(row[1])}

    def get_auth_session_expiry(self, *, token_hash: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT expires_at
                FROM auth_sessions
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def revoke_auth_session(self, *, token_hash: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE token_hash = ?
                """,
                (now_iso, token_hash),
            )
            conn.commit()

    def log_user_activity(
        self,
        *,
        user_id: str,
        activity_type: str,
        endpoint: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_activity (user_id, activity_type, endpoint, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    activity_type,
                    endpoint,
                    json.dumps(payload or {}, ensure_ascii=True),
                    now_iso,
                ),
            )
            conn.commit()

    def list_user_activity(
        self,
        *,
        user_id: str,
        limit: int = 100,
        activity_type: str | None = None,
    ) -> list[dict[str, object]]:
        safe_limit = max(1, min(int(limit or 100), 500))
        with self._connect() as conn:
            if activity_type:
                rows = conn.execute(
                    """
                    SELECT activity_type, endpoint, payload_json, created_at
                    FROM user_activity
                    WHERE user_id = ? AND activity_type = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, activity_type, safe_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT activity_type, endpoint, payload_json, created_at
                    FROM user_activity
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, safe_limit),
                ).fetchall()
        output: list[dict[str, object]] = []
        for row in rows:
            payload_raw = str(row[2] or "{}")
            try:
                payload_obj = json.loads(payload_raw)
            except json.JSONDecodeError:
                payload_obj = {}
            output.append(
                {
                    "activity_type": str(row[0]),
                    "endpoint": str(row[1]),
                    "payload": payload_obj,
                    "created_at": str(row[3]),
                }
            )
        return output

    def create_investigation_run(
        self,
        *,
        run_id: str,
        user_id: str,
        objective: str,
        filters: dict[str, object],
        require_review_signoff: bool = False,
        idempotency_key: str = "",
        scheduled_for: str | None = None,
        max_attempts: int = 1,
        replay_of_run_id: str = "",
    ) -> dict[str, object]:
        now_iso = datetime.now(timezone.utc).isoformat()
        approval_status = "pending" if bool(require_review_signoff) else "auto_approved"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO investigation_runs (
                    run_id, user_id, idempotency_key, objective, filters_json,
                    require_review_signoff, scheduled_for, attempt_count, max_attempts,
                    status, replay_of_run_id, approval_status, approved_by, approved_at,
                    rollback_run_id, rolled_back_at, export_status, created_at, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    user_id,
                    str(idempotency_key or ""),
                    objective,
                    json.dumps(filters, ensure_ascii=True),
                    1 if bool(require_review_signoff) else 0,
                    str(scheduled_for) if scheduled_for else None,
                    1,
                    max(1, int(max_attempts or 1)),
                    "running",
                    replay_of_run_id,
                    approval_status,
                    "",
                    now_iso if approval_status == "auto_approved" else None,
                    "",
                    None,
                    "not_exported",
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
        return self.get_investigation_run(user_id=user_id, run_id=run_id)

    def find_investigation_run_by_idempotency(
        self,
        *,
        user_id: str,
        idempotency_key: str,
    ) -> dict[str, object] | None:
        key = str(idempotency_key or "").strip()
        if not key:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT run_id
                FROM investigation_runs
                WHERE user_id = ? AND idempotency_key = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, key),
            ).fetchone()
        if row is None:
            return None
        return self.get_investigation_run(user_id=user_id, run_id=str(row[0]))

    def queue_investigation_run(
        self,
        *,
        run_id: str,
        user_id: str,
        objective: str,
        filters: dict[str, object],
        require_review_signoff: bool,
        idempotency_key: str = "",
        scheduled_for: str | None = None,
        max_attempts: int = 3,
    ) -> dict[str, object]:
        now_iso = datetime.now(timezone.utc).isoformat()
        scheduled_iso = str(scheduled_for).strip() if str(scheduled_for or "").strip() else now_iso
        approval_status = "pending" if bool(require_review_signoff) else "auto_approved"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO investigation_runs (
                    run_id, user_id, idempotency_key, objective, filters_json,
                    require_review_signoff, scheduled_for, attempt_count, max_attempts,
                    status, replay_of_run_id, approval_status, approved_by, approved_at,
                    rollback_run_id, rolled_back_at, export_status, created_at, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    user_id,
                    str(idempotency_key or ""),
                    objective,
                    json.dumps(filters, ensure_ascii=True),
                    1 if bool(require_review_signoff) else 0,
                    scheduled_iso,
                    0,
                    max(1, int(max_attempts or 3)),
                    "queued",
                    "",
                    approval_status,
                    "",
                    now_iso if approval_status == "auto_approved" else None,
                    "",
                    None,
                    "not_exported",
                    now_iso,
                    None,
                ),
            )
            conn.commit()
        return self.get_investigation_run(user_id=user_id, run_id=run_id)

    def claim_due_queued_runs(self, *, now_iso: str, limit: int = 10) -> list[dict[str, object]]:
        safe_limit = max(1, min(int(limit or 10), 100))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, user_id, objective, filters_json, require_review_signoff,
                       attempt_count, max_attempts, scheduled_for
                FROM investigation_runs
                WHERE status = 'queued'
                  AND COALESCE(scheduled_for, created_at) <= ?
                ORDER BY COALESCE(scheduled_for, created_at) ASC
                LIMIT ?
                """,
                (now_iso, safe_limit),
            ).fetchall()

            claimed: list[dict[str, object]] = []
            for row in rows:
                run_id = str(row[0])
                current_attempts = int(row[5] or 0)
                next_attempts = current_attempts + 1
                updated = conn.execute(
                    """
                    UPDATE investigation_runs
                    SET status = 'running',
                        started_at = ?,
                        attempt_count = ?
                    WHERE run_id = ? AND status = 'queued'
                    """,
                    (now_iso, next_attempts, run_id),
                )
                if int(updated.rowcount or 0) <= 0:
                    continue
                claimed.append(
                    {
                        "run_id": run_id,
                        "user_id": str(row[1]),
                        "objective": str(row[2]),
                        "filters": json.loads(str(row[3] or "{}")),
                        "require_review_signoff": bool(int(row[4] or 0)),
                        "attempt_count": next_attempts,
                        "max_attempts": int(row[6] or 1),
                        "scheduled_for": str(row[7] or ""),
                    }
                )
            conn.commit()
        return claimed

    def retry_or_fail_investigation_run(
        self,
        *,
        user_id: str,
        run_id: str,
        error_text: str,
        backoff_seconds: int,
    ) -> dict[str, object]:
        now_iso = datetime.now(timezone.utc)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT attempt_count, max_attempts
                FROM investigation_runs
                WHERE user_id = ? AND run_id = ?
                """,
                (user_id, run_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown run_id: {run_id}")
            attempt_count = int(row[0] or 0)
            max_attempts = max(1, int(row[1] or 1))

            if attempt_count < max_attempts:
                next_schedule = (now_iso + timedelta(seconds=max(0, int(backoff_seconds or 0)))).isoformat()
                conn.execute(
                    """
                    UPDATE investigation_runs
                    SET status = 'queued',
                        scheduled_for = ?,
                        completed_at = NULL,
                        error_text = ?
                    WHERE user_id = ? AND run_id = ?
                    """,
                    (next_schedule, str(error_text or ""), user_id, run_id),
                )
                conn.commit()
                return {
                    "requeued": True,
                    "attempt_count": attempt_count,
                    "max_attempts": max_attempts,
                    "scheduled_for": next_schedule,
                }

            conn.execute(
                """
                UPDATE investigation_runs
                SET status = 'failed',
                    completed_at = ?,
                    error_text = ?
                WHERE user_id = ? AND run_id = ?
                """,
                (now_iso.isoformat(), str(error_text or ""), user_id, run_id),
            )
            conn.commit()
            return {
                "requeued": False,
                "attempt_count": attempt_count,
                "max_attempts": max_attempts,
            }

    def complete_investigation_run(
        self,
        *,
        user_id: str,
        run_id: str,
        status: str,
        report: dict[str, object] | None = None,
        quality_gate: dict[str, object] | None = None,
        replay_diff: dict[str, object] | None = None,
        error_text: str = "",
        approval_status: str | None = None,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        normalized_approval_status = str(approval_status or "").strip().lower()
        with self._connect() as conn:
            if normalized_approval_status:
                approved_at = now_iso if normalized_approval_status in {"approved", "auto_approved"} else None
                conn.execute(
                    """
                    UPDATE investigation_runs
                    SET status = ?,
                        report_json = ?,
                        quality_gate_json = ?,
                        replay_diff_json = ?,
                        completed_at = ?,
                        error_text = ?,
                        approval_status = ?,
                        approved_at = ?
                    WHERE user_id = ? AND run_id = ?
                    """,
                    (
                        status,
                        json.dumps(report or {}, ensure_ascii=True),
                        json.dumps(quality_gate or {}, ensure_ascii=True),
                        json.dumps(replay_diff or {}, ensure_ascii=True),
                        now_iso,
                        str(error_text or ""),
                        normalized_approval_status,
                        approved_at,
                        user_id,
                        run_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE investigation_runs
                    SET status = ?,
                        report_json = ?,
                        quality_gate_json = ?,
                        replay_diff_json = ?,
                        completed_at = ?,
                        error_text = ?
                    WHERE user_id = ? AND run_id = ?
                    """,
                    (
                        status,
                        json.dumps(report or {}, ensure_ascii=True),
                        json.dumps(quality_gate or {}, ensure_ascii=True),
                        json.dumps(replay_diff or {}, ensure_ascii=True),
                        now_iso,
                        str(error_text or ""),
                        user_id,
                        run_id,
                    ),
                )
            conn.commit()

    def list_investigation_runs(self, *, user_id: str, limit: int = 20) -> list[dict[str, object]]:
        safe_limit = max(1, min(int(limit or 20), 200))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, user_id, idempotency_key, objective, filters_json,
                       require_review_signoff, scheduled_for, attempt_count, max_attempts,
                       status, replay_of_run_id, report_json, quality_gate_json,
                       replay_diff_json, approval_status, approved_by, approved_at,
                       rollback_run_id, rolled_back_at, export_status,
                       created_at, started_at, completed_at, error_text
                FROM investigation_runs
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, safe_limit),
            ).fetchall()
        return [
            {
                "run_id": str(row[0]),
                "user_id": str(row[1]),
                "idempotency_key": str(row[2] or ""),
                "objective": str(row[3]),
                "filters": json.loads(str(row[4] or "{}")),
                "require_review_signoff": bool(int(row[5] or 0)),
                "scheduled_for": str(row[6] or ""),
                "attempt_count": int(row[7] or 0),
                "max_attempts": int(row[8] or 1),
                "status": str(row[9]),
                "replay_of_run_id": str(row[10] or ""),
                "report": json.loads(str(row[11] or "{}")),
                "quality_gate": json.loads(str(row[12] or "{}")),
                "replay_diff": json.loads(str(row[13] or "{}")),
                "approval_status": str(row[14] or "pending"),
                "approved_by": str(row[15] or ""),
                "approved_at": str(row[16] or ""),
                "rollback_run_id": str(row[17] or ""),
                "rolled_back_at": str(row[18] or ""),
                "export_status": str(row[19] or "not_exported"),
                "created_at": str(row[20]),
                "started_at": str(row[21] or ""),
                "completed_at": str(row[22] or ""),
                "error_text": str(row[23] or ""),
            }
            for row in rows
        ]

    def get_investigation_run(self, *, user_id: str, run_id: str) -> dict[str, object]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT run_id, user_id, idempotency_key, objective, filters_json,
                       require_review_signoff, scheduled_for, attempt_count, max_attempts,
                       status, replay_of_run_id, report_json, quality_gate_json,
                       replay_diff_json, approval_status, approved_by, approved_at,
                       rollback_run_id, rolled_back_at, export_status,
                       created_at, started_at, completed_at, error_text
                FROM investigation_runs
                WHERE user_id = ? AND run_id = ?
                """,
                (user_id, run_id),
            ).fetchone()
        if row is None:
            raise ValueError(f"Unknown run_id: {run_id}")
        return {
            "run_id": str(row[0]),
            "user_id": str(row[1]),
            "idempotency_key": str(row[2] or ""),
            "objective": str(row[3]),
            "filters": json.loads(str(row[4] or "{}")),
            "require_review_signoff": bool(int(row[5] or 0)),
            "scheduled_for": str(row[6] or ""),
            "attempt_count": int(row[7] or 0),
            "max_attempts": int(row[8] or 1),
            "status": str(row[9]),
            "replay_of_run_id": str(row[10] or ""),
            "report": json.loads(str(row[11] or "{}")),
            "quality_gate": json.loads(str(row[12] or "{}")),
            "replay_diff": json.loads(str(row[13] or "{}")),
            "approval_status": str(row[14] or "pending"),
            "approved_by": str(row[15] or ""),
            "approved_at": str(row[16] or ""),
            "rollback_run_id": str(row[17] or ""),
            "rolled_back_at": str(row[18] or ""),
            "export_status": str(row[19] or "not_exported"),
            "created_at": str(row[20]),
            "started_at": str(row[21] or ""),
            "completed_at": str(row[22] or ""),
            "error_text": str(row[23] or ""),
        }

    def set_investigation_run_approval(
        self,
        *,
        user_id: str,
        run_id: str,
        status: str,
        reviewer: str,
    ) -> dict[str, object]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"approved", "rejected", "pending", "auto_approved"}:
            raise ValueError("status must be one of approved, rejected, pending, auto_approved")
        now_iso = datetime.now(timezone.utc).isoformat()
        approved_at = now_iso if normalized_status in {"approved", "auto_approved"} else None
        with self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE investigation_runs
                SET approval_status = ?,
                    approved_by = ?,
                    approved_at = ?
                WHERE user_id = ? AND run_id = ?
                """,
                (normalized_status, str(reviewer or ""), approved_at, user_id, run_id),
            )
            conn.commit()
        if int(updated.rowcount or 0) <= 0:
            raise ValueError(f"Unknown run_id: {run_id}")
        return self.get_investigation_run(user_id=user_id, run_id=run_id)

    def mark_investigation_run_rolled_back(
        self,
        *,
        user_id: str,
        run_id: str,
        rollback_run_id: str,
    ) -> dict[str, object]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE investigation_runs
                SET rollback_run_id = ?,
                    rolled_back_at = ?
                WHERE user_id = ? AND run_id = ?
                """,
                (rollback_run_id, now_iso, user_id, run_id),
            )
            conn.commit()
        if int(updated.rowcount or 0) <= 0:
            raise ValueError(f"Unknown run_id: {run_id}")
        return self.get_investigation_run(user_id=user_id, run_id=run_id)

    def set_investigation_run_export_status(
        self,
        *,
        user_id: str,
        run_id: str,
        export_status: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE investigation_runs
                SET export_status = ?
                WHERE user_id = ? AND run_id = ?
                """,
                (str(export_status or "not_exported"), user_id, run_id),
            )
            conn.commit()

    def save_investigation_template(
        self,
        *,
        template_id: str,
        user_id: str,
        name: str,
        objective: str,
        filters: dict[str, object],
        require_review_signoff: bool,
    ) -> dict[str, object]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO investigation_templates (
                    template_id, user_id, name, objective, filters_json,
                    require_review_signoff, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(template_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    name=excluded.name,
                    objective=excluded.objective,
                    filters_json=excluded.filters_json,
                    require_review_signoff=excluded.require_review_signoff,
                    updated_at=excluded.updated_at
                """,
                (
                    template_id,
                    user_id,
                    name,
                    objective,
                    json.dumps(filters, ensure_ascii=True),
                    1 if bool(require_review_signoff) else 0,
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
        return self.get_investigation_template(user_id=user_id, template_id=template_id)

    def get_investigation_template(self, *, user_id: str, template_id: str) -> dict[str, object]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT template_id, user_id, name, objective, filters_json,
                       require_review_signoff, created_at, updated_at, last_used_at
                FROM investigation_templates
                WHERE user_id = ? AND template_id = ?
                """,
                (user_id, template_id),
            ).fetchone()
        if row is None:
            raise ValueError(f"Unknown template_id: {template_id}")
        return {
            "template_id": str(row[0]),
            "user_id": str(row[1]),
            "name": str(row[2]),
            "objective": str(row[3]),
            "filters": json.loads(str(row[4] or "{}")),
            "require_review_signoff": bool(int(row[5] or 0)),
            "created_at": str(row[6]),
            "updated_at": str(row[7]),
            "last_used_at": str(row[8] or ""),
        }

    def list_investigation_templates(self, *, user_id: str, limit: int = 50) -> list[dict[str, object]]:
        safe_limit = max(1, min(int(limit or 50), 200))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT template_id, user_id, name, objective, filters_json,
                       require_review_signoff, created_at, updated_at, last_used_at
                FROM investigation_templates
                WHERE user_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (user_id, safe_limit),
            ).fetchall()
        return [
            {
                "template_id": str(row[0]),
                "user_id": str(row[1]),
                "name": str(row[2]),
                "objective": str(row[3]),
                "filters": json.loads(str(row[4] or "{}")),
                "require_review_signoff": bool(int(row[5] or 0)),
                "created_at": str(row[6]),
                "updated_at": str(row[7]),
                "last_used_at": str(row[8] or ""),
            }
            for row in rows
        ]

    def touch_investigation_template(self, *, user_id: str, template_id: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE investigation_templates
                SET last_used_at = ?, updated_at = ?
                WHERE user_id = ? AND template_id = ?
                """,
                (now_iso, now_iso, user_id, template_id),
            )
            conn.commit()

    def create_automation_experiment(
        self,
        *,
        experiment_id: str,
        user_id: str,
        name: str,
        objective: str,
        filters: dict[str, object],
        variant_a: dict[str, object],
        variant_b: dict[str, object],
        result: dict[str, object],
        winner_variant: str,
    ) -> dict[str, object]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO automation_experiments (
                    experiment_id, user_id, name, objective, filters_json,
                    variant_a_json, variant_b_json, result_json,
                    winner_variant, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    user_id,
                    name,
                    objective,
                    json.dumps(filters, ensure_ascii=True),
                    json.dumps(variant_a, ensure_ascii=True),
                    json.dumps(variant_b, ensure_ascii=True),
                    json.dumps(result, ensure_ascii=True),
                    winner_variant,
                    "completed",
                    now_iso,
                ),
            )
            conn.commit()
        return self.get_automation_experiment(user_id=user_id, experiment_id=experiment_id)

    def get_automation_experiment(self, *, user_id: str, experiment_id: str) -> dict[str, object]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT experiment_id, user_id, name, objective, filters_json,
                       variant_a_json, variant_b_json, result_json,
                       winner_variant, status, created_at
                FROM automation_experiments
                WHERE user_id = ? AND experiment_id = ?
                """,
                (user_id, experiment_id),
            ).fetchone()
        if row is None:
            raise ValueError(f"Unknown experiment_id: {experiment_id}")
        return {
            "experiment_id": str(row[0]),
            "user_id": str(row[1]),
            "name": str(row[2]),
            "objective": str(row[3]),
            "filters": json.loads(str(row[4] or "{}")),
            "variant_a": json.loads(str(row[5] or "{}")),
            "variant_b": json.loads(str(row[6] or "{}")),
            "result": json.loads(str(row[7] or "{}")),
            "winner_variant": str(row[8] or ""),
            "status": str(row[9] or "completed"),
            "created_at": str(row[10]),
        }

    def list_automation_experiments(self, *, user_id: str, limit: int = 20) -> list[dict[str, object]]:
        safe_limit = max(1, min(int(limit or 20), 200))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT experiment_id, user_id, name, objective, filters_json,
                       variant_a_json, variant_b_json, result_json,
                       winner_variant, status, created_at
                FROM automation_experiments
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, safe_limit),
            ).fetchall()
        return [
            {
                "experiment_id": str(row[0]),
                "user_id": str(row[1]),
                "name": str(row[2]),
                "objective": str(row[3]),
                "filters": json.loads(str(row[4] or "{}")),
                "variant_a": json.loads(str(row[5] or "{}")),
                "variant_b": json.loads(str(row[6] or "{}")),
                "result": json.loads(str(row[7] or "{}")),
                "winner_variant": str(row[8] or ""),
                "status": str(row[9] or "completed"),
                "created_at": str(row[10]),
            }
            for row in rows
        ]

    def record_automation_export(
        self,
        *,
        delivery_id: str,
        user_id: str,
        run_id: str,
        channel: str,
        payload: dict[str, object],
        result: dict[str, object],
        status: str,
        error_text: str = "",
    ) -> dict[str, object]:
        now_iso = datetime.now(timezone.utc).isoformat()
        delivered_at = now_iso if str(status or "").lower() == "delivered" else None
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO automation_exports (
                    delivery_id, user_id, run_id, channel, payload_json, result_json,
                    status, error_text, created_at, delivered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery_id,
                    user_id,
                    run_id,
                    channel,
                    json.dumps(payload, ensure_ascii=True),
                    json.dumps(result, ensure_ascii=True),
                    status,
                    str(error_text or ""),
                    now_iso,
                    delivered_at,
                ),
            )
            conn.commit()
        return self.get_automation_export(user_id=user_id, delivery_id=delivery_id)

    def get_automation_export(self, *, user_id: str, delivery_id: str) -> dict[str, object]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT delivery_id, user_id, run_id, channel, payload_json, result_json,
                       status, error_text, created_at, delivered_at
                FROM automation_exports
                WHERE user_id = ? AND delivery_id = ?
                """,
                (user_id, delivery_id),
            ).fetchone()
        if row is None:
            raise ValueError(f"Unknown delivery_id: {delivery_id}")
        return {
            "delivery_id": str(row[0]),
            "user_id": str(row[1]),
            "run_id": str(row[2]),
            "channel": str(row[3]),
            "payload": json.loads(str(row[4] or "{}")),
            "result": json.loads(str(row[5] or "{}")),
            "status": str(row[6]),
            "error_text": str(row[7] or ""),
            "created_at": str(row[8]),
            "delivered_at": str(row[9] or ""),
        }

    def list_automation_exports(self, *, user_id: str, limit: int = 20) -> list[dict[str, object]]:
        safe_limit = max(1, min(int(limit or 20), 200))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT delivery_id, user_id, run_id, channel, payload_json, result_json,
                       status, error_text, created_at, delivered_at
                FROM automation_exports
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, safe_limit),
            ).fetchall()
        return [
            {
                "delivery_id": str(row[0]),
                "user_id": str(row[1]),
                "run_id": str(row[2]),
                "channel": str(row[3]),
                "payload": json.loads(str(row[4] or "{}")),
                "result": json.loads(str(row[5] or "{}")),
                "status": str(row[6]),
                "error_text": str(row[7] or ""),
                "created_at": str(row[8]),
                "delivered_at": str(row[9] or ""),
            }
            for row in rows
        ]

    def investigation_dashboard_metrics(self, *, user_id: str, days: int = 30) -> dict[str, object]:
        safe_days = max(1, min(int(days or 30), 365))
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=safe_days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, status, attempt_count, quality_gate_json,
                       approval_status, export_status, created_at,
                       completed_at, replay_of_run_id, replay_diff_json
                FROM investigation_runs
                WHERE user_id = ? AND created_at >= ?
                ORDER BY created_at DESC
                """,
                (user_id, cutoff_iso),
            ).fetchall()

        total = len(rows)
        status_counts: dict[str, int] = {}
        gate_passes = 0
        freshness_passes = 0
        citation_integrity_passes = 0
        retries = 0
        manual_approvals = 0
        exports_delivered = 0
        report_durations_seconds: list[float] = []
        replay_total = 0
        replay_stable = 0
        for row in rows:
            status = str(row[1] or "unknown")
            status_counts[status] = int(status_counts.get(status, 0)) + 1
            if int(row[2] or 0) > 1:
                retries += 1
            gate_raw = str(row[3] or "{}")
            try:
                gate = json.loads(gate_raw)
            except json.JSONDecodeError:
                gate = {}
            if bool(gate.get("passed", False)):
                gate_passes += 1

            checks = gate.get("checks") if isinstance(gate.get("checks"), dict) else {}
            freshness_check = checks.get("freshness") if isinstance(checks.get("freshness"), dict) else {}
            citation_check = checks.get("citation_integrity") if isinstance(checks.get("citation_integrity"), dict) else {}
            if bool(freshness_check.get("passed", False)):
                freshness_passes += 1
            if bool(citation_check.get("passed", False)):
                citation_integrity_passes += 1

            approval_status = str(row[4] or "")
            if approval_status == "approved":
                manual_approvals += 1
            if str(row[5] or "") == "delivered":
                exports_delivered += 1

            created_at_raw = str(row[6] or "").strip()
            completed_at_raw = str(row[7] or "").strip()
            if created_at_raw and completed_at_raw:
                try:
                    created_at = datetime.fromisoformat(created_at_raw)
                    completed_at = datetime.fromisoformat(completed_at_raw)
                    report_durations_seconds.append(max(0.0, (completed_at - created_at).total_seconds()))
                except ValueError:
                    pass

            replay_of_run_id = str(row[8] or "").strip()
            if replay_of_run_id:
                replay_total += 1
                replay_diff_raw = str(row[9] or "{}")
                try:
                    replay_diff = json.loads(replay_diff_raw)
                except json.JSONDecodeError:
                    replay_diff = {}
                if not bool(replay_diff.get("quality_gate_changed", True)):
                    replay_stable += 1

        success_count = int(status_counts.get("completed", 0))
        median_time_to_report_seconds = 0.0
        if report_durations_seconds:
            sorted_durations = sorted(report_durations_seconds)
            mid = len(sorted_durations) // 2
            if len(sorted_durations) % 2 == 1:
                median_time_to_report_seconds = float(sorted_durations[mid])
            else:
                median_time_to_report_seconds = (float(sorted_durations[mid - 1]) + float(sorted_durations[mid])) / 2.0
        return {
            "window_days": safe_days,
            "total_runs": total,
            "status_counts": status_counts,
            "success_rate": round((success_count / total), 4) if total else 0.0,
            "quality_gate_pass_rate": round((gate_passes / total), 4) if total else 0.0,
            "replay_stability_rate": round((replay_stable / replay_total), 4) if replay_total else 1.0,
            "weekly_replay_stability_7d": self._weekly_replay_stability(user_id=user_id, days=7),
            "median_time_to_report_seconds": round(median_time_to_report_seconds, 2),
            "retry_rate": round((retries / total), 4) if total else 0.0,
            "manual_intervention_rate": round((manual_approvals / total), 4) if total else 0.0,
            "citation_integrity_pass_rate": round((citation_integrity_passes / total), 4) if total else 0.0,
            "evidence_freshness_compliance": round((freshness_passes / total), 4) if total else 0.0,
            "export_delivery_rate": round((exports_delivered / total), 4) if total else 0.0,
        }

    def _weekly_replay_stability(self, *, user_id: str, days: int = 7) -> float:
        safe_days = max(1, min(int(days or 7), 30))
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=safe_days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT replay_of_run_id, replay_diff_json
                FROM investigation_runs
                WHERE user_id = ? AND created_at >= ? AND replay_of_run_id IS NOT NULL AND replay_of_run_id != ''
                """,
                (user_id, cutoff_iso),
            ).fetchall()
        if not rows:
            return 1.0
        stable = 0
        for replay_of_run_id, replay_diff_json in rows:
            if not str(replay_of_run_id or "").strip():
                continue
            try:
                replay_diff = json.loads(str(replay_diff_json or "{}"))
            except json.JSONDecodeError:
                replay_diff = {}
            if not bool(replay_diff.get("quality_gate_changed", True)):
                stable += 1
        return round(stable / len(rows), 4)

    def list_investigation_review_queue(
        self,
        *,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        status: str = "",
        risk_level: str = "",
        sort: str = "created_desc",
    ) -> tuple[list[dict[str, object]], int, bool]:
        safe_limit = max(1, min(int(limit or 50), 200))
        safe_offset = max(0, int(offset or 0))
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"", "any", "completed", "failed"}:
            normalized_status = ""
        normalized_risk_level = str(risk_level or "").strip().lower()
        if normalized_risk_level not in {"", "high", "medium"}:
            normalized_risk_level = ""
        normalized_sort = str(sort or "created_desc").strip().lower()
        if normalized_sort not in {"created_desc", "created_asc", "risk_desc", "attempts_desc"}:
            normalized_sort = "created_desc"

        query = (
            """
            SELECT run_id, objective, quality_gate_json, created_at, status,
                   require_review_signoff, approval_status, attempt_count
            FROM investigation_runs
            WHERE user_id = ?
              AND approval_status = 'pending'
              AND status IN ('completed', 'failed')
            """
        )
        params: tuple[object, ...] = (user_id,)
        if normalized_status in {"completed", "failed"}:
            query += " AND status = ?"
            params = (user_id, normalized_status)

        with self._connect() as conn:
            rows = conn.execute(
                query,
                params,
            ).fetchall()

        queue_rows: list[dict[str, object]] = []
        for row in rows:
            quality_gate_raw = str(row[2] or "{}")
            try:
                quality_gate = json.loads(quality_gate_raw)
            except json.JSONDecodeError:
                quality_gate = {}
            checks = quality_gate.get("checks") if isinstance(quality_gate.get("checks"), dict) else {}
            failed_checks = [
                str(name)
                for name, value in checks.items()
                if isinstance(value, dict) and not bool(value.get("passed", False))
            ]
            queue_rows.append(
                {
                    "run_id": str(row[0]),
                    "objective": str(row[1]),
                    "quality_gate": quality_gate,
                    "created_at": str(row[3]),
                    "status": str(row[4]),
                    "require_review_signoff": bool(int(row[5] or 0)),
                    "approval_status": str(row[6] or "pending"),
                    "attempt_count": int(row[7] or 0),
                    "failed_checks": failed_checks,
                    "risk_level": "high" if failed_checks else "medium",
                }
            )

        if normalized_risk_level:
            queue_rows = [row for row in queue_rows if str(row.get("risk_level") or "") == normalized_risk_level]

        if normalized_sort == "created_asc":
            queue_rows.sort(key=lambda row: str(row.get("created_at") or ""))
        elif normalized_sort == "risk_desc":
            queue_rows.sort(
                key=lambda row: (
                    1 if str(row.get("risk_level") or "") == "high" else 0,
                    str(row.get("created_at") or ""),
                ),
                reverse=True,
            )
        elif normalized_sort == "attempts_desc":
            queue_rows.sort(
                key=lambda row: (
                    int(row.get("attempt_count") or 0),
                    str(row.get("created_at") or ""),
                ),
                reverse=True,
            )
        else:
            queue_rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)

        total = len(queue_rows)
        start = min(safe_offset, total)
        end = min(start + safe_limit, total)
        page_rows = queue_rows[start:end]
        has_more = end < total
        return page_rows, total, has_more

    def investigation_review_queue_summary(self, *, user_id: str) -> dict[str, object]:
        with self._connect() as conn:
            db_rows = conn.execute(
                """
                SELECT run_id, objective, quality_gate_json, created_at, status,
                       require_review_signoff, approval_status, attempt_count
                FROM investigation_runs
                WHERE user_id = ?
                  AND approval_status = 'pending'
                  AND status IN ('completed', 'failed')
                """,
                (user_id,),
            ).fetchall()

        rows: list[dict[str, object]] = []
        for row in db_rows:
            quality_gate_raw = str(row[2] or "{}")
            try:
                quality_gate = json.loads(quality_gate_raw)
            except json.JSONDecodeError:
                quality_gate = {}
            checks = quality_gate.get("checks") if isinstance(quality_gate.get("checks"), dict) else {}
            failed_checks = [
                str(name)
                for name, value in checks.items()
                if isinstance(value, dict) and not bool(value.get("passed", False))
            ]
            rows.append(
                {
                    "run_id": str(row[0]),
                    "status": str(row[4]),
                    "risk_level": "high" if failed_checks else "medium",
                    "failed_checks": failed_checks,
                }
            )

        by_status: dict[str, int] = {"completed": 0, "failed": 0}
        by_risk: dict[str, int] = {"high": 0, "medium": 0}
        failed_checks_counts: dict[str, int] = {}

        for row in rows:
            status_value = str(row.get("status") or "").strip().lower()
            if status_value in by_status:
                by_status[status_value] += 1

            risk_value = str(row.get("risk_level") or "").strip().lower()
            if risk_value in by_risk:
                by_risk[risk_value] += 1

            failed_checks = row.get("failed_checks") if isinstance(row.get("failed_checks"), list) else []
            for check_name in failed_checks:
                key = str(check_name or "").strip()
                if not key:
                    continue
                failed_checks_counts[key] = int(failed_checks_counts.get(key, 0)) + 1

        top_failed_checks = sorted(
            [
                {"check": name, "count": count}
                for name, count in failed_checks_counts.items()
            ],
            key=lambda item: (-int(item["count"]), str(item["check"])),
        )

        return {
            "pending_total": len(rows),
            "by_status": by_status,
            "by_risk": by_risk,
            "top_failed_checks": top_failed_checks,
        }

    def freshness_alarms(self, *, stale_after_hours: int = 24, failure_threshold: int = 2) -> list[dict[str, object]]:
        safe_hours = max(1, min(int(stale_after_hours or 24), 24 * 365))
        safe_failure_threshold = max(0, min(int(failure_threshold or 2), 100))
        now_utc = datetime.now(timezone.utc)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_name, last_successful_timestamp, failure_count, updated_at
                FROM sync_state
                ORDER BY source_name ASC
                """
            ).fetchall()

        alarms: list[dict[str, object]] = []
        for row in rows:
            source_name = str(row[0])
            last_successful_timestamp = str(row[1] or "")
            failure_count = int(row[2] or 0)
            updated_at = str(row[3] or "")

            stale = False
            age_hours = None
            if last_successful_timestamp:
                try:
                    parsed = datetime.fromisoformat(last_successful_timestamp)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    age_hours = (now_utc - parsed).total_seconds() / 3600.0
                    stale = bool(age_hours > safe_hours)
                except ValueError:
                    stale = True
            else:
                stale = True

            failing = failure_count >= safe_failure_threshold
            if stale or failing:
                alarms.append(
                    {
                        "source_name": source_name,
                        "last_successful_timestamp": last_successful_timestamp,
                        "updated_at": updated_at,
                        "age_hours": round(float(age_hours), 2) if age_hours is not None else None,
                        "stale": stale,
                        "failure_count": failure_count,
                        "failing": failing,
                        "severity": "high" if (failing and stale) else "medium",
                    }
                )
        return alarms

    def source_article_breakdown(self) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT COALESCE(source_name, 'unknown') AS source_name, COUNT(*)
                FROM evidence_source_metadata
                GROUP BY source_name
                ORDER BY COUNT(*) DESC, source_name ASC
                """
            ).fetchall()
            total_rows = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
        seen_total = sum(int(row[1]) for row in rows)
        output = [
            {
                "source": SOURCE_DISPLAY_NAMES.get(str(row[0]), str(row[0])),
                "articles": int(row[1]),
            }
            for row in rows
        ]
        if int(total_rows) > seen_total:
            output.append({"source": "unmapped", "articles": int(total_rows) - seen_total})
        output.sort(key=lambda row: (-int(row["articles"]), str(row["source"]).lower()))
        if len(output) <= 4:
            return output
        top_sources = output[:4]
        others_total = sum(int(row["articles"]) for row in output[4:])
        if others_total > 0:
            top_sources.append({"source": "Others", "articles": others_total})
        return top_sources

    def latest_sync_timestamp(self) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT ended_at
                FROM sync_runs
                WHERE ended_at IS NOT NULL
                ORDER BY ended_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def has_running_sync_run(self, *, max_age_minutes: int = 120) -> bool:
        safe_minutes = max(1, min(int(max_age_minutes or 120), 24 * 60))
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=safe_minutes)).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM sync_runs
                WHERE status = 'running' AND started_at >= ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (cutoff,),
            ).fetchone()
        return row is not None

    def reconcile_stale_sync_runs(self, *, worker_active: bool = False) -> int:
        """Mark orphaned running sync_runs as failed when no worker is active."""
        if worker_active:
            return 0
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE sync_runs
                SET status = 'failed',
                    ended_at = ?,
                    notes = CASE
                        WHEN notes IS NULL OR TRIM(notes) = '' THEN 'interrupted (no active sync worker)'
                        ELSE notes || ' [interrupted: no active sync worker]'
                    END
                WHERE status = 'running'
                """,
                (now_iso,),
            )
            conn.commit()
            return int(cur.rowcount or 0)

    def record_manual_sync_success(self, scope: str, *, completed_at: str | None = None) -> None:
        normalized_scope = str(scope).strip().lower()
        if not normalized_scope:
            return
        now_iso = completed_at or datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO manual_sync_cooldowns (scope, last_successful_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(scope) DO UPDATE SET
                    last_successful_at = excluded.last_successful_at,
                    updated_at = excluded.updated_at
                """,
                (normalized_scope, now_iso, now_iso),
            )
            conn.commit()

    def manual_sync_last_successful_at(self, scope: str) -> str | None:
        normalized_scope = str(scope).strip().lower()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT last_successful_at
                FROM manual_sync_cooldowns
                WHERE scope = ?
                """,
                (normalized_scope,),
            ).fetchone()
        if row is None:
            return None
        value = str(row[0] or "").strip()
        return value or None

    def record_manual_sync_source_duration(self, source_name: str, duration_seconds: float) -> None:
        normalized_source = str(source_name).strip().lower()
        if not normalized_source:
            return
        duration = max(1.0, float(duration_seconds))
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT sample_count, avg_duration_seconds
                FROM manual_sync_source_durations
                WHERE source_name = ?
                """,
                (normalized_source,),
            ).fetchone()
            if row is None:
                sample_count = 1
                avg_duration = duration
            else:
                sample_count = int(row[0] or 0) + 1
                previous_avg = float(row[1] or 0.0)
                avg_duration = ((previous_avg * (sample_count - 1)) + duration) / sample_count
            conn.execute(
                """
                INSERT INTO manual_sync_source_durations (
                    source_name, sample_count, avg_duration_seconds, last_duration_seconds, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                    sample_count = excluded.sample_count,
                    avg_duration_seconds = excluded.avg_duration_seconds,
                    last_duration_seconds = excluded.last_duration_seconds,
                    updated_at = excluded.updated_at
                """,
                (normalized_source, sample_count, avg_duration, duration, now_iso),
            )
            conn.commit()

    def get_source_duration_estimate(self, source_name: str, *, default_seconds: float = 120.0) -> float:
        normalized_source = str(source_name).strip().lower()
        if not normalized_source:
            return max(1.0, float(default_seconds))
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT avg_duration_seconds
                FROM manual_sync_source_durations
                WHERE source_name = ?
                """,
                (normalized_source,),
            ).fetchone()
            if row is not None and float(row[0] or 0.0) > 0:
                return float(row[0])
            history = conn.execute(
                """
                SELECT AVG(
                    (julianday(ended_at) - julianday(started_at)) * 86400.0
                )
                FROM sync_runs
                WHERE source_name = ?
                  AND status = 'ok'
                  AND ended_at IS NOT NULL
                  AND started_at IS NOT NULL
                """,
                (normalized_source,),
            ).fetchone()
        if history is not None and history[0] is not None and float(history[0]) > 0:
            return float(history[0])
        return max(1.0, float(default_seconds))

    def get_source_sync_activity(self, source_name: str) -> dict[str, object]:
        normalized_source = str(source_name).strip().lower()
        sync_state = self.get_sync_state(normalized_source) or {}
        last_successful_at = str(sync_state.get("last_successful_timestamp", "") or "").strip()
        last_attempt_at = ""
        last_attempt_status = ""
        last_attempt_notes = ""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT status, ended_at, started_at, notes
                FROM sync_runs
                WHERE source_name = ?
                ORDER BY COALESCE(ended_at, started_at) DESC, id DESC
                LIMIT 1
                """,
                (normalized_source,),
            ).fetchone()
            duration_row = conn.execute(
                """
                SELECT updated_at
                FROM manual_sync_source_durations
                WHERE source_name = ?
                """,
                (normalized_source,),
            ).fetchone()
        if row is not None:
            last_attempt_status = str(row[0] or "").strip()
            last_attempt_at = str(row[1] or row[2] or "").strip()
            last_attempt_notes = str(row[3] or "").strip()
        manual_updated_at = ""
        if duration_row is not None:
            manual_updated_at = str(duration_row[0] or "").strip()
        return {
            "last_successful_at": last_successful_at,
            "last_attempt_at": last_attempt_at,
            "last_attempt_status": last_attempt_status,
            "last_attempt_notes": last_attempt_notes,
            "last_manual_sync_at": manual_updated_at,
        }

    def list_sync_states(self) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_name, last_successful_timestamp, failure_count, updated_at
                FROM sync_state
                ORDER BY source_name ASC
                """
            ).fetchall()
        return [
            {
                "source_name": str(row[0]),
                "last_successful_timestamp": str(row[1] or ""),
                "failure_count": int(row[2] or 0),
                "updated_at": str(row[3] or ""),
            }
            for row in rows
        ]

    def register_model(
        self,
        *,
        model_id: str,
        base_model: str,
        adapter_path: str,
        dataset_manifest_path: str,
        training_config: dict[str, object],
        metrics: dict[str, object],
        status: str,
        notes: str = "",
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_registry (
                    model_id, created_at, base_model, adapter_path,
                    dataset_manifest_path, training_config_json, metrics_json,
                    status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_id,
                    now_iso,
                    base_model,
                    adapter_path,
                    dataset_manifest_path,
                    json.dumps(training_config, ensure_ascii=True),
                    json.dumps(metrics, ensure_ascii=True),
                    status,
                    notes,
                ),
            )
            conn.commit()

    def list_models(self, limit: int = 50) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT model_id, created_at, base_model, adapter_path,
                       dataset_manifest_path, training_config_json, metrics_json,
                       status, notes
                FROM model_registry
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        output: list[dict[str, object]] = []
        for row in rows:
            output.append(
                {
                    "model_id": row[0],
                    "created_at": row[1],
                    "base_model": row[2],
                    "adapter_path": row[3],
                    "dataset_manifest_path": row[4],
                    "training_config": json.loads(row[5]),
                    "metrics": json.loads(row[6]),
                    "status": row[7],
                    "notes": row[8],
                }
            )
        return output

    def get_model(self, model_id: str) -> dict[str, object]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT model_id, created_at, base_model, adapter_path,
                       dataset_manifest_path, training_config_json, metrics_json,
                       status, notes
                FROM model_registry
                WHERE model_id = ?
                """,
                (model_id,),
            ).fetchone()

        if row is None:
            raise ValueError(f"Unknown model_id: {model_id}")

        return {
            "model_id": row[0],
            "created_at": row[1],
            "base_model": row[2],
            "adapter_path": row[3],
            "dataset_manifest_path": row[4],
            "training_config": json.loads(row[5]),
            "metrics": json.loads(row[6]),
            "status": row[7],
            "notes": row[8],
        }

    def register_model_evaluation(
        self,
        *,
        evaluation_id: str,
        candidate_model_id: str,
        baseline_model_id: str,
        benchmark_manifest_path: str,
        metrics: dict[str, object],
        gate: dict[str, object],
        status: str,
        notes: str = "",
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_evaluations (
                    evaluation_id, created_at, candidate_model_id, baseline_model_id,
                    benchmark_manifest_path, metrics_json, gate_json, status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation_id,
                    now_iso,
                    candidate_model_id,
                    baseline_model_id,
                    benchmark_manifest_path,
                    json.dumps(metrics, ensure_ascii=True),
                    json.dumps(gate, ensure_ascii=True),
                    status,
                    notes,
                ),
            )
            conn.commit()

    def list_model_evaluations(
        self,
        candidate_model_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        with self._connect() as conn:
            if candidate_model_id:
                rows = conn.execute(
                    """
                    SELECT evaluation_id, created_at, candidate_model_id, baseline_model_id,
                           benchmark_manifest_path, metrics_json, gate_json, status, notes
                    FROM model_evaluations
                    WHERE candidate_model_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (candidate_model_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT evaluation_id, created_at, candidate_model_id, baseline_model_id,
                           benchmark_manifest_path, metrics_json, gate_json, status, notes
                    FROM model_evaluations
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        output: list[dict[str, object]] = []
        for row in rows:
            output.append(
                {
                    "evaluation_id": row[0],
                    "created_at": row[1],
                    "candidate_model_id": row[2],
                    "baseline_model_id": row[3],
                    "benchmark_manifest_path": row[4],
                    "metrics": json.loads(row[5]),
                    "gate": json.loads(row[6]),
                    "status": row[7],
                    "notes": row[8],
                }
            )
        return output

    def get_model_evaluation(self, evaluation_id: str) -> dict[str, object]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT evaluation_id, created_at, candidate_model_id, baseline_model_id,
                       benchmark_manifest_path, metrics_json, gate_json, status, notes
                FROM model_evaluations
                WHERE evaluation_id = ?
                """,
                (evaluation_id,),
            ).fetchone()

        if row is None:
            raise ValueError(f"Unknown evaluation_id: {evaluation_id}")

        return {
            "evaluation_id": row[0],
            "created_at": row[1],
            "candidate_model_id": row[2],
            "baseline_model_id": row[3],
            "benchmark_manifest_path": row[4],
            "metrics": json.loads(row[5]),
            "gate": json.loads(row[6]),
            "status": row[7],
            "notes": row[8],
        }

    def rebuild_knowledge_graph(self) -> dict[str, int]:
        now_iso = datetime.now(timezone.utc).isoformat()
        evidence = self.all_evidence()

        with self._connect() as conn:
            conn.execute("DELETE FROM kg_edges")
            conn.execute("DELETE FROM kg_nodes")

            node_rows: dict[str, tuple[str, str, str]] = {}
            edge_rows: list[tuple[str, str, str, str, float, str, str, str]] = []

            for row in evidence:
                claim_id = str(row["claim_id"])
                entity = str(row["entity"])
                outcome = str(row["outcome"])
                source_doi = str(row["source_doi"])
                relation = str(row["relation"])
                effect_direction = str(row["effect_direction"])
                reliability = float(row["reliability_score"])

                claim_key = f"claim:{claim_id}"
                entity_key = f"entity:{entity.lower()}"
                outcome_key = f"outcome:{outcome.lower()}"
                source_key = f"source:{source_doi.lower()}"

                node_rows[claim_key] = ("claim", claim_id, "{}")
                node_rows[entity_key] = ("entity", entity, "{}")
                node_rows[outcome_key] = ("outcome", outcome, "{}")
                node_rows[source_key] = ("source", source_doi, "{}")

                edge_rows.append(
                    (
                        claim_key,
                        entity_key,
                        "mentions_entity",
                        "neutral",
                        reliability,
                        relation,
                        claim_id,
                        now_iso,
                    )
                )
                edge_rows.append(
                    (
                        claim_key,
                        outcome_key,
                        "mentions_outcome",
                        "neutral",
                        reliability,
                        relation,
                        claim_id,
                        now_iso,
                    )
                )
                edge_rows.append(
                    (
                        source_key,
                        claim_key,
                        "reports_claim",
                        effect_direction,
                        float(row["source_reliability_score"]),
                        relation,
                        claim_id,
                        now_iso,
                    )
                )
                edge_rows.append(
                    (
                        entity_key,
                        outcome_key,
                        "affects_outcome",
                        effect_direction,
                        reliability,
                        relation,
                        claim_id,
                        now_iso,
                    )
                )

            for node_key, (node_type, label, meta_json) in node_rows.items():
                conn.execute(
                    """
                    INSERT INTO kg_nodes (node_key, node_type, label, meta_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (node_key, node_type, label, meta_json, now_iso),
                )

            for edge in edge_rows:
                conn.execute(
                    """
                    INSERT INTO kg_edges (
                        source_key, target_key, edge_type, polarity, weight,
                        relation, evidence_claim_id, event_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    edge,
                )
            conn.commit()

        return {
            "nodes": len(node_rows),
            "edges": len(edge_rows),
            "records": len(evidence),
        }

    def knowledge_graph_overview(self) -> dict[str, int]:
        with self._connect() as conn:
            nodes = conn.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()[0]
            edges = conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0]
            affect_edges = conn.execute(
                "SELECT COUNT(*) FROM kg_edges WHERE edge_type='affects_outcome'"
            ).fetchone()[0]
        return {
            "nodes": int(nodes),
            "edges": int(edges),
            "affects_outcome_edges": int(affect_edges),
        }

    def graph_support_contradiction_map(
        self,
        entity: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        where_clause = ""
        params: tuple[object, ...]
        if entity:
            where_clause = "AND n1.label = ?"
            params = (entity, limit)
        else:
            params = (limit,)

        query = f"""
        SELECT n1.label AS entity_label,
               n2.label AS outcome_label,
               SUM(CASE WHEN e.polarity='supports' THEN 1 ELSE 0 END) AS supports,
               SUM(CASE WHEN e.polarity='contradicts' THEN 1 ELSE 0 END) AS contradicts,
               ROUND(AVG(e.weight), 4) AS avg_weight
        FROM kg_edges e
        JOIN kg_nodes n1 ON n1.node_key = e.source_key
        JOIN kg_nodes n2 ON n2.node_key = e.target_key
        WHERE e.edge_type='affects_outcome'
          {where_clause}
        GROUP BY n1.label, n2.label
        ORDER BY (supports + contradicts) DESC, avg_weight DESC
        LIMIT ?
        """

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [
            {
                "entity": row[0],
                "outcome": row[1],
                "supports": int(row[2]),
                "contradicts": int(row[3]),
                "avg_weight": float(row[4]) if row[4] is not None else 0.0,
            }
            for row in rows
        ]

    def graph_neighbors(self, node_key: str, limit: int = 20) -> list[dict[str, object]]:
        query = """
        SELECT e.edge_type, e.polarity, e.weight, n2.node_key, n2.node_type, n2.label
        FROM kg_edges e
        JOIN kg_nodes n2 ON n2.node_key = e.target_key
        WHERE e.source_key = ?
        ORDER BY e.weight DESC
        LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(query, (node_key, limit)).fetchall()

        return [
            {
                "edge_type": row[0],
                "polarity": row[1],
                "weight": float(row[2]),
                "neighbor_key": row[3],
                "neighbor_type": row[4],
                "neighbor_label": row[5],
            }
            for row in rows
        ]
