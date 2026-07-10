# Platform Next Steps Plan

## Goal
Improve reliability and trust of the investigator experience by adding measurable telemetry, response quality guardrails, and iterative retrieval/UX improvements.

## Status Legend
- [ ] Not started
- [~] In progress
- [x] Done

## Work Plan

### 1) Query Observability
- [x] Add backend per-query telemetry with phase timings:
  - `loading_evidence`
  - `building_prompt`
  - `generating`
  - `post_processing`
- [x] Persist recent traces in memory (bounded ring buffer).
- [x] Expose diagnostics endpoint for recent traces.
- [x] Include trace summary in chat responses.
- [x] Add UI diagnostics indicator for last query timings.

### 2) Response Quality Guardrails
- [x] Add minimum-structure validation for final payload.
- [x] Enforce at least one cited claim when evidence exists.
- [x] Add contradictions/uncertainty requirement when conflict is detected.

### 3) Regression Evaluation Set
- [x] Create a canonical query set (20-30 prompts).
- [x] Add property-based assertions (citations present, sections present, etc.).
- [x] Integrate into CI-compatible test command.

### 4) Evidence Relevance Ranking
- [x] Introduce source/reliability weighting in evidence selection.
- [x] Balance recency and study-type diversity.
- [x] Track impact on citation quality.

### 5) Transparency UX
- [x] Surface rows retrieved/cited/model/latency in UI.
- [x] Show streaming/fallback path used.

## Progress Log
- 2026-07-02: Plan created and moved datasource plan into `ai/plans/`.
- 2026-07-02: Started implementation of Step 1 (query observability).
- 2026-07-02: Implemented backend query telemetry ring buffer and endpoint `GET /api/telemetry/recent?limit=N`.
- 2026-07-02: Added telemetry payload to `/api/chat` and stream `final` event responses.
- 2026-07-02: Added first UI telemetry surface in chat status (phase timing summary after response).
- 2026-07-02: Added dedicated diagnostics panel in the evidence sidebar, backed by `/api/telemetry/recent` with refresh + auto-update.
- 2026-07-02: Implemented response guardrails (`direct_answer`, cited IDs, contradictions summary, next-step fallback) and exposed guardrail flags in sync/stream payloads.
- 2026-07-02: Added evidence ranking for cited rows balancing reliability, recency, and study-type diversity.
- 2026-07-02: Added impact tracking via telemetry (`evidence_count`, `cited_evidence_count`, `guardrail_flags`) and ranking-focused tests.
- 2026-07-02: Added canonical regression query fixture (`tests/fixtures/regression_queries.json`) and CI-friendly target `make test-regression-queries`.
- 2026-07-02: Wired explicit regression query gate into GitHub workflows (`benchmark-gate.yml` and `benchmark-gate-strict.yml`) and validated with `make test-regression-queries`.
- 2026-07-02: Added README CI visibility section with workflow links and ready-to-enable GitHub badge templates.
- 2026-07-02: Started auth/session implementation: added magic-link auth backend (`src/als_intel/auth.py`), user/auth/activity schema in `store.py`, protected and user-scoped session APIs, and login metadata/auth endpoints.
- 2026-07-02: Added login gate UX with database and source/article summary visibility plus magic-link request/verify flow in `webui.py`.
- 2026-07-02: Added auth ownership integration test in `tests/test_webui_api.py` with dedicated auth-enabled fixture; focused suites passing (`38 passed`, regression queries `2 passed`).
- 2026-07-02: Phase 2 implementation started with Security baseline slice: CSRF enforcement on authenticated POST endpoints, CSRF token propagation in auth responses/UI fetch wrapper, and IP-based magic-link throttling (`ALS_MAGIC_LINK_RATE_LIMIT_IP_COUNT`).
- 2026-07-02: Added focused security regression coverage for CSRF-required protected writes and IP-based request-link rate limiting; targeted suites passing (`44 passed`).
- 2026-07-02: Added session renewal/rotation via `/api/auth/status` with configurable renew window (`ALS_SESSION_RENEW_WINDOW_SECONDS`) and login-time revocation of any pre-existing session token.
- 2026-07-02: Added authenticated user activity timeline endpoint (`GET /api/auth/audit`) and store query support for security/audit event inspection.
- 2026-07-02: Expanded focused security tests for rotation and audit timeline scoping; targeted suites passing (`46 passed`).
