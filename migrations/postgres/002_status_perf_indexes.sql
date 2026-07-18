-- Performance indexes for DB status widget and sync polling hot paths.

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
