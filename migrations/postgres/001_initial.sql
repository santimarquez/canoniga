-- Initial PostgreSQL schema for als-intel (ported from SQLite SCHEMA_SQL + migrations)

CREATE TABLE IF NOT EXISTS evidence (
    id BIGSERIAL PRIMARY KEY,
    claim_id TEXT NOT NULL UNIQUE,
    claim_text TEXT NOT NULL,
    disease TEXT NOT NULL,
    entity TEXT NOT NULL,
    relation TEXT NOT NULL,
    outcome TEXT NOT NULL,
    effect_direction TEXT NOT NULL,
    study_type TEXT NOT NULL,
    sample_size INTEGER NOT NULL,
    endpoint_validity DOUBLE PRECISION NOT NULL,
    replication_count INTEGER NOT NULL,
    peer_reviewed INTEGER NOT NULL,
    year INTEGER NOT NULL,
    source_title TEXT NOT NULL,
    source_doi TEXT NOT NULL,
    cohort TEXT NOT NULL DEFAULT 'unknown',
    model_system TEXT NOT NULL DEFAULT 'unspecified',
    source_type TEXT NOT NULL DEFAULT 'journal',
    extraction_confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    causal_evidence_type TEXT NOT NULL DEFAULT 'observational',
    ingested_at TEXT NOT NULL DEFAULT '',
    source_reliability_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    reliability_score DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_history (
    id BIGSERIAL PRIMARY KEY,
    claim_id TEXT NOT NULL,
    event_time TEXT NOT NULL,
    reliability_score DOUBLE PRECISION NOT NULL,
    study_component DOUBLE PRECISION NOT NULL,
    sample_component DOUBLE PRECISION NOT NULL,
    replication_component DOUBLE PRECISION NOT NULL,
    peer_component DOUBLE PRECISION NOT NULL,
    endpoint_component DOUBLE PRECISION NOT NULL,
    source_component DOUBLE PRECISION NOT NULL,
    extraction_component DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id BIGSERIAL PRIMARY KEY,
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
    id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL UNIQUE,
    last_sync_run_id BIGINT,
    last_sync_timestamp TEXT,
    last_successful_timestamp TEXT,
    failure_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(last_sync_run_id) REFERENCES sync_runs(id)
);

CREATE TABLE IF NOT EXISTS sync_stage_state (
    id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    last_sync_run_id BIGINT,
    last_sync_timestamp TEXT,
    last_successful_timestamp TEXT,
    failure_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(last_sync_run_id) REFERENCES sync_runs(id),
    UNIQUE(source_name, stage_name)
);

CREATE TABLE IF NOT EXISTS evidence_source_metadata (
    id BIGSERIAL PRIMARY KEY,
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
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL,
    claim_id TEXT NOT NULL,
    change_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES sync_runs(id)
);

CREATE TABLE IF NOT EXISTS review_decisions (
    id BIGSERIAL PRIMARY KEY,
    claim_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS investigator_sessions (
    id BIGSERIAL PRIMARY KEY,
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
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_login_at TEXT,
    display_name TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    institution TEXT NOT NULL DEFAULT '',
    avatar_data BYTEA,
    avatar_mime_type TEXT NOT NULL DEFAULT '',
    profile_updated_at TEXT
);

CREATE TABLE IF NOT EXISTS auth_magic_links (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    requested_ip TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id BIGSERIAL PRIMARY KEY,
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
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS investigation_runs (
    id BIGSERIAL PRIMARY KEY,
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
    id BIGSERIAL PRIMARY KEY,
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
    id BIGSERIAL PRIMARY KEY,
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
    id BIGSERIAL PRIMARY KEY,
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
    id BIGSERIAL PRIMARY KEY,
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
    id BIGSERIAL PRIMARY KEY,
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
    id BIGSERIAL PRIMARY KEY,
    node_key TEXT NOT NULL UNIQUE,
    node_type TEXT NOT NULL,
    label TEXT NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kg_edges (
    id BIGSERIAL PRIMARY KEY,
    source_key TEXT NOT NULL,
    target_key TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    polarity TEXT NOT NULL,
    weight DOUBLE PRECISION NOT NULL,
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
    avg_duration_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_duration_seconds DOUBLE PRECISION,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS manual_sync_events (
    id BIGSERIAL PRIMARY KEY,
    scope TEXT NOT NULL,
    triggered_by TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT NOT NULL DEFAULT '',
    run_ids_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_manual_sync_source_durations_source
ON manual_sync_source_durations (source_name);

CREATE INDEX IF NOT EXISTS idx_manual_sync_events_scope_started
ON manual_sync_events (scope, started_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_investigator_sessions_user
ON investigator_sessions (user_id, updated_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_investigation_runs_user_idempotency
ON investigation_runs (user_id, idempotency_key);

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

-- Status / sync polling performance indexes (also shipped in 002_status_perf_indexes.sql)
CREATE INDEX IF NOT EXISTS idx_sync_runs_status_started
ON sync_runs (status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_sync_runs_ended_at
ON sync_runs (ended_at DESC)
WHERE ended_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sync_runs_source_ended
ON sync_runs (source_name, COALESCE(ended_at, started_at) DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_sync_runs_source_status_ended
ON sync_runs (source_name, status, ended_at DESC);

CREATE INDEX IF NOT EXISTS idx_manual_sync_events_started
ON manual_sync_events (started_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_effect_direction
ON evidence (effect_direction);

CREATE INDEX IF NOT EXISTS idx_evidence_reliability_claim
ON evidence (reliability_score DESC, claim_id ASC);

CREATE INDEX IF NOT EXISTS idx_change_log_claim_changed
ON evidence_change_log (claim_id, changed_at);
