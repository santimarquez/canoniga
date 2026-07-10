# Automation-First Roadmap Plan

## Objective
Move the platform from assisted analysis to automation-first operation while preserving investigator control, auditability, and quality gates.

## Prioritization Model
- Impact on analyst throughput (0-5)
- Reliability and trust improvement (0-5)
- Implementation effort (0-5, lower is better)
- Data readiness and observability fit (0-5)
- Time to first measurable value (0-5)

Scoring: `priority = impact + reliability + data_readiness + time_to_value - effort`

## Ranked Initiatives
1. Autonomous Investigation Runs with Quality Gates
- Why: Enables end-to-end auto execution with guardrails and measurable outcomes.
- Scope: Run lifecycle, gate checks, replay baseline, persistent run history.

2. Auto-Summary and Export Pipelines
- Why: Converts run outcomes into consistent outputs with less manual work.
- Scope: Scheduled summaries, report templates, delivery hooks.

3. Experiment and Prompt Optimization Loop
- Why: Improves answer quality over time using controlled comparisons.
- Scope: A/B prompts, cohort-level metrics, decision logging.

4. Source Reliability and Freshness Monitoring
- Why: Prevents stale evidence from reducing trust.
- Scope: freshness alarms, source drift checks, remediation queue.

5. Assisted-to-Autonomous Handoff Controls
- Why: Keeps humans in control where confidence is low.
- Scope: handoff thresholds, review queues, explainability signals.

## 90-Day Execution Plan

### Days 1-30: Foundation (Completed)
- Build autonomous run persistence (`investigation_runs`).
- Add APIs to start runs, list runs, fetch run details.
- Add quality gate evaluation for each run.
- Add golden replay endpoint and baseline diff.
- Add targeted API tests for lifecycle and ownership.

### Days 31-60: Scale and Safety (Completed)
- Add scheduled run automation and queueing.
- Add run retries with bounded backoff and idempotency keys.
- Add source freshness alarms and quality dashboards.
- Add richer replay comparisons (citations, contradictions, coverage).

### Days 61-90: Optimization and Productization (Completed)
- Add prompt/strategy experiments and automatic winner selection.
- Add objective templates for recurring investigations.
- Add automation controls UI with run approvals and rollback.
- Add export automation to downstream reporting channels.

## Weekly Metrics
- Autonomous run success rate.
- Quality gate pass rate.
- Replay stability rate.
- Median time-to-report.
- Analyst manual intervention rate.
- Citation integrity pass rate.
- Evidence freshness compliance.

## Progress Log

### 2026-07-02
- Created roadmap plan in `ai/plans` with explicit progress tracking.
- Started implementation of Days 1-30 foundation scope:
  - Added `investigation_runs` persistence schema.
  - Added run lifecycle store methods.
  - Added run start/replay/list/detail API endpoints.
  - Added quality gate and replay diff helpers.
- Added lifecycle integration test coverage for:
  - run start,
  - run list/detail,
  - replay baseline,
  - user ownership isolation.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `40 passed`.
- Next checkpoint:
  - Add quality-gate threshold configuration via environment variables.
  - Add richer replay diffs (citation overlap and contradiction deltas).

### 2026-07-03
- Completed remaining Days 1-30 checkpoint items:
  - Added quality-gate threshold configuration through environment variables:
    - `ALS_RUN_GATE_FRESHNESS_WINDOW_YEARS`
    - `ALS_RUN_GATE_MAX_CONTRADICTION_DENSITY`
    - `ALS_RUN_GATE_REQUIRE_CITATION_INTEGRITY`
    - `ALS_RUN_GATE_REQUIRE_CONTRADICTION_SUMMARY`
  - Expanded replay diff payload with richer comparisons:
    - citation overlap ratio and shared citation IDs,
    - contradiction count/density deltas,
    - changed quality-check statuses.
- Added test coverage updates in `tests/test_webui_api.py`:
  - replay payload structure assertions for citation and contradiction deltas,
  - env-driven quality-gate threshold behavior validation.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `43 passed`.
- Next checkpoint (Days 31-60):
  - Implement scheduled run queueing and execution orchestration.
  - Add retries with bounded backoff and idempotency keys for run starts.

### 2026-07-03 (Phase 2 Update)
- Implemented Days 31-60 scheduling/retry/idempotency slice:
  - Extended `investigation_runs` persistence for queue/retry semantics:
    - `idempotency_key`, `require_review_signoff`, `scheduled_for`, `attempt_count`, `max_attempts`.
  - Added queue and claim execution support in store layer:
    - queue creation,
    - due-run claiming,
    - idempotency lookup,
    - retry-or-fail transition with bounded backoff.
  - Added run execution API capabilities:
    - `POST /api/investigation/runs/queue`
    - `GET /api/investigation/runs/queued/execute`
    - idempotent `POST /api/investigation/runs/start` via `idempotency_key`.
  - Added retry backoff config support:
    - `ALS_RUN_RETRY_BACKOFF_SECONDS`
- Added integration tests for:
  - idempotent run start returns existing run,
  - queue + due execution lifecycle.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `45 passed`.
- Next checkpoint (Days 31-60):
  - Add queue worker scheduling trigger (periodic execution loop/cron integration).
  - Add run metrics endpoints for success/retry/failure trend dashboards.

### 2026-07-03 (Phase 3 Finalization)
- Completed remaining Days 31-60 items:
  - Added periodic worker trigger endpoint for scheduled queued execution:
    - `GET /api/investigation/runs/worker/tick?token=...&limit=...`
    - guarded by `ALS_AUTOMATION_WORKER_TOKEN` for cron/worker invocations.
  - Added automation dashboards and freshness monitoring APIs:
    - `GET /api/automation/dashboard`
    - `GET /api/automation/freshness/alarms`
  - Added source freshness configuration support:
    - `ALS_FRESHNESS_STALE_HOURS`
    - `ALS_FRESHNESS_FAILURE_THRESHOLD`

- Completed Days 61-90 optimization/productization scope:
  - Prompt/strategy experiments with automatic winner selection:
    - `POST /api/automation/experiments/run`
    - `GET /api/automation/experiments`
  - Objective templates for recurring investigations:
    - `POST /api/investigation/templates/save`
    - `POST /api/investigation/templates/run`
    - `GET /api/investigation/templates`
  - Automation controls for approvals and rollback:
    - `POST /api/investigation/runs/approve`
    - `POST /api/investigation/runs/rollback`
  - Export automation to downstream channels:
    - `POST /api/export/automated` supporting `markdown_file`, `json_file`, `webhook`
    - `GET /api/automation/exports`
    - exported file directory via `ALS_AUTOMATION_EXPORT_DIR`

- Persistence/schema updates delivered:
  - extended `investigation_runs` with approval/rollback/export tracking fields.
  - added `investigation_templates`, `automation_experiments`, and `automation_exports` tables.

- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `48 passed`.
  - `py -m pytest tests/test_sync.py -q` -> `33 passed`.
  - `py -m pytest tests/test_webui.py -q` -> `9 passed`.

### 2026-07-04 (Hardening Update)
- Extended automation dashboard KPIs to fully cover weekly metrics list:
  - `replay_stability_rate`
  - `median_time_to_report_seconds`
  - `citation_integrity_pass_rate`
  - `evidence_freshness_compliance`
  - existing metrics retained (`success_rate`, `quality_gate_pass_rate`, `manual_intervention_rate`, etc.)
- Added assisted-to-autonomous handoff behavior on gate failure:
  - New policy env: `ALS_AUTOMATION_HANDOFF_ON_GATE_FAIL` (default enabled)
  - When enabled and a run fails quality gate, run approval state is set to `pending` for human review.
- Added regression coverage:
  - dashboard payload includes new KPI fields,
  - handoff path sets `approval_status=pending` when gate fails.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `50 passed`.

### 2026-07-04 (Operations Queue Update)
- Added explicit automation review queue endpoint for handoff operations:
  - `GET /api/investigation/runs/review-queue?limit=...`
  - Returns runs pending human review with:
    - failed gate checks,
    - risk level,
    - review metadata (`approval_status`, `attempt_count`, etc.).
- Added regression coverage for:
  - handoff run appears in review queue,
  - queue payload shape for failed checks and pending status.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `50 passed`.

### 2026-07-05 (Review Operations Controls)
- Extended review queue API with operator controls for triage workflows:
  - `GET /api/investigation/runs/review-queue?limit=...&status=...&risk=...&sort=...`
  - Supported filters:
    - `status`: `any|completed|failed`
    - `risk`: `any|high|medium`
  - Supported sorting:
    - `created_desc` (default)
    - `created_asc`
    - `risk_desc`
    - `attempts_desc`
- Added queue summary endpoint for dashboard/widgets:
  - `GET /api/investigation/runs/review-queue/summary`
  - Returns:
    - pending total,
    - counts by status,
    - counts by risk,
    - top failed quality checks.
- Added integration coverage for:
  - filtered review queue responses,
  - summary payload correctness across risk/status mixes.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `51 passed`.

### 2026-07-05 (Queue Pagination Hardening)
- Upgraded review queue endpoint with explicit page navigation metadata:
  - supports `offset` query parameter,
  - returns `total`, `offset`, and `has_more` in response payload.
- Keeps filtering/sorting behavior while enabling deterministic operator pagination over larger queues.
- Added integration assertions for:
  - first/second page navigation,
  - metadata correctness for `limit`, `offset`, `total`, and `has_more`.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `51 passed`.

### 2026-07-05 (Dashboard Queue Rollups)
- Integrated review queue rollups directly into automation dashboard payload:
  - `GET /api/automation/dashboard` now includes `review_queue` section with:
    - `pending_total`,
    - `by_status`,
    - `by_risk`,
    - `top_failed_checks`.
- This enables dashboard consumers to fetch KPI + queue operational state in a single request.
- Added regression coverage for:
  - dashboard response shape containing `review_queue`,
  - non-empty `pending_total` when review queue has pending runs.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `51 passed`.

### 2026-07-05 (Interactive Tool Tutorial v1)
- Implemented an in-app, step-by-step guided tutorial for the main tool UI (excluding login):
  - Added persistent `Start Tour` entry in top bar.
  - Added one-time auto-start tutorial behavior for first use (versioned local persistence).
  - Added overlay spotlight with contextual card and controls: `Back`, `Next/Finish`, `Stop`.
- Added guided investigator flow with required actions on key steps:
  - type a question,
  - run a query and wait for report,
  - inspect evidence,
  - open lineage,
  - apply filters.
- Added bilingual tutorial copy (EN/ES) and integrated it with existing translation system.
- Added tutorial lifecycle controls:
  - stop/skip from any step,
  - restart manually at any time,
  - keyboard support (`Esc` to stop, `Enter` to continue when step requirement is met),
  - spotlight reposition on resize/scroll.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `51 passed`.

### 2026-07-05 (Interactive Tool Tutorial v1.1 Coverage Expansion)
- Expanded tutorial scope to explicitly explain and highlight requested operational areas:
  - diagnostics area,
  - save session,
  - export summary,
  - copy citations,
  - evidence database explorer (open + usage),
  - saved sessions view,
  - hypothesis queue (what it is and how it works),
  - review queue (what it is and how it works),
  - validation section in synthesis workflow.
- Added new tutorial step sequencing and action signals so navigation guides users through those areas in-context.
- Added bilingual copy for all new tutorial steps (EN/ES) in existing translation system.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `51 passed`.

### 2026-07-05 (Interactive Tool Tutorial v1.2 Modes)
- Added two onboarding modes to reduce friction for first-time users:
  - `Short Tour` (core path),
  - `Full Tour` (complete operational walkthrough).
- Added in-UI mode selector next to `Start Tour` so operators can choose depth before launching the tutorial.
- Set automatic first-run onboarding to `Short Tour` by default.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `51 passed`.

### 2026-07-05 (Interactive Tool Tutorial v1.3 Settings Placement)
- Moved tutorial launch controls out of top bar and into Settings modal.
- Replaced mode selector with two explicit action buttons:
  - `Tutorial corto`
  - `Tutorial largo`
- Updated tutorial launch bindings so each button starts the corresponding mode directly.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `51 passed`.

### 2026-07-05 (Chat Performance Hardening)
- Implemented SQL-native evidence filtering for chat/synthesis paths:
  - replaced full-table load + Python filtering with `store.filter_evidence(...)` in critical request flows.
- Replaced global contradiction expansion in chat/synthesis with scoped contradiction extraction over filtered rows:
  - avoids full `contradiction_pairs()` join cost in user chat response path.
- Made cited evidence translation optional to avoid blocking final payload:
  - new behavior controlled by payload flag `translate_evidence_rows` and env fallback `ALS_TRANSLATE_EVIDENCE_ROWS`.
- Added composite evidence index tuned for contradiction-style scans:
  - `idx_evidence_entity_direction_claim_reliability`.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `51 passed`.

### 2026-07-05 (Full Evidence Coverage In Answers)
- Changed chat/synthesis evidence retrieval to use full filtered dataset by default (no SQL `LIMIT` cap).
- Added optional override to cap rows when needed:
  - request payload: `evidence_max_rows`
  - env fallback: `ALS_CHAT_EVIDENCE_MAX_ROWS` (`0`/unset means unlimited).
- Updated store filtering primitive to support optional no-limit execution.
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `51 passed`.

### 2026-07-05 (Self-Guided Capability Labeling)
- Updated grounded prompt policy to prevent claiming external analyses as already executable in-run.
- Added guardrail normalization for synthesis next steps:
  - if a suggested step references external datasets/APIs (e.g., GTEx), it is auto-labeled as external dependency.
  - labels:
    - English: `Requires external integration:`
    - Spanish: `Requiere integracion externa:`
- Validation:
  - `py -m pytest tests/test_webui_api.py -q` -> `51 passed`.

## Current Status
- Overall: In Progress (Post-90 operational hardening)
- Active phase: Review/operations hardening and observability
- Blockers: None
