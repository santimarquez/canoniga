# PostgreSQL Migration Plan

## Purpose
Migrate the platform from SQLite to PostgreSQL across all environments, including local development, while preserving behavior, data integrity, and delivery velocity.

## Objective
- Replace SQLite as the default runtime database in local, dev, staging, and production.
- Keep a temporary rollback path during rollout.
- Cut over with zero data loss and no API contract regressions.

## Scope
- Database engine migration for all persisted application data currently in SQLite.
- Schema migration framework for PostgreSQL.
- Environment and deployment changes (local Docker, dev, staging, production).
- Test, validation, observability, and rollback controls.

## Non-Goals
- Business logic redesign.
- API contract changes.
- Feature work unrelated to migration.

## Success Criteria
1. All environments run on PostgreSQL by default.
2. Full test suite passes against PostgreSQL.
3. Critical auth/session and automation flows complete without lock-related incidents.
4. Data parity checks pass for migrated datasets.
5. Rollback path is documented and tested before production cutover.

## Risks
- SQL dialect differences (SQLite vs PostgreSQL) causing runtime regressions.
- Migration ordering issues and schema drift.
- Data conversion edge cases for JSON/text/time fields.
- Environment-specific connection and credential configuration errors.

## Mitigations
- Introduce migration and parity checks before cutover.
- Add PostgreSQL-focused CI gate.
- Use staged rollout with stop/go criteria.
- Keep a reversible rollback procedure until stabilization window closes.

## Phased Plan

### Phase 0: Inventory and Readiness
- Catalog all SQL usage patterns in src/als_intel/store.py.
- Identify SQLite-specific constructs and replace with portable SQL where possible.
- Define canonical PostgreSQL schema and index strategy.
- Define migration ownership and on-call coverage for rollout windows.

Deliverables:
- SQL compatibility checklist.
- Canonical schema definition and migration order.

### Phase 1: PostgreSQL Foundation in Codebase
- Add DB configuration variables for PostgreSQL:
  - ALS_DB_ENGINE (postgres|sqlite)
  - ALS_PG_HOST
  - ALS_PG_PORT
  - ALS_PG_DB
  - ALS_PG_USER
  - ALS_PG_PASSWORD
  - ALS_PG_SSLMODE
- Add connection factory layer and adapter path.
- Keep temporary SQLite fallback for emergency rollback only.
- Add transaction and connection handling defaults for PostgreSQL pooling.

Deliverables:
- Configurable DB backend with PostgreSQL path enabled.
- Documentation updates for local and non-local environment variables.

### Phase 2: Schema Migration Framework
- Introduce migration tooling for PostgreSQL schema lifecycle.
- Port existing schema and indexes from SQLite definitions.
- Add idempotent migration scripts and migration state tracking.
- Add bootstrap command for PostgreSQL init and migration.

Deliverables:
- Versioned PostgreSQL migration scripts.
- Reproducible init and migrate workflow.

### Phase 3: Data Migration and Parity Validation
- Implement one-time data export/import path from SQLite to PostgreSQL.
- Migrate representative production-like snapshot in staging.
- Run parity checks for key tables and counts:
  - evidence
  - evidence_source_metadata
  - investigator_sessions
  - users
  - auth_magic_links
  - auth_sessions
  - user_activity
  - investigation_runs
  - investigation_templates
  - automation_experiments
  - automation_exports
- Validate critical query outputs and API responses against parity fixtures.

Deliverables:
- Data migration script and runbook.
- Parity report with signed-off counts and samples.

### Phase 4: Local Environment Cutover
- Add PostgreSQL service to local Docker stack.
- Set local default to PostgreSQL in docker-compose and dev overrides.
- Update Makefile tasks to target PostgreSQL init/migrate/bootstrap paths.
- Verify local developer workflow:
  - start stack
  - migrate schema
  - login/session flows
  - sync and automation flows

Deliverables:
- Local Docker workflow using PostgreSQL by default.
- Local setup docs updated.

### Phase 5: Dev and Staging Cutover
- Enable PostgreSQL in dev environment and run soak tests.
- Enable PostgreSQL in staging with migrated dataset.
- Run regression suites and targeted smoke flows:
  - auth magic-link flow
  - session list/get/save
  - investigation run lifecycle and queue worker tick
  - automated export paths
- Monitor errors, latency, and connection metrics.

Deliverables:
- Dev and staging on PostgreSQL.
- Go/no-go checklist for production cutover.

### Phase 6: Production Cutover
- Freeze schema-changing deploys during cutover window.
- Backup SQLite and export migration snapshot.
- Run production migration to PostgreSQL.
- Switch runtime config to PostgreSQL.
- Execute post-cutover smoke checks and monitor.

Deliverables:
- Production runtime on PostgreSQL.
- Verified smoke checks and monitoring dashboard green.

### Phase 7: Stabilization and Decommission
- Keep rollback capability for defined stabilization window.
- Address any query/index tuning findings.
- Remove SQLite default path from all environments.
- Keep SQLite only as optional offline/dev fallback if explicitly needed.

Deliverables:
- Migration closure report.
- Updated architecture docs and ops runbook.

## Environment-by-Environment Checklist

### Local
- PostgreSQL container enabled.
- App defaults use PostgreSQL.
- Developer commands updated.
- Seed/bootstrap works.

### Dev
- Secrets configured.
- Migrations auto-applied in deploy pipeline.
- Error/latency monitoring active.

### Staging
- Production-like migrated dataset validated.
- End-to-end regression green.
- Soak test completed.

### Production
- Backups created.
- Data migration completed.
- Cutover approved by checklist.
- Post-cutover smoke tests passed.

## Rollback Plan
1. Keep pre-cutover SQLite snapshot and runtime config values.
2. If severe regression occurs, switch app config back to SQLite and redeploy.
3. Re-run smoke tests on rollback path.
4. Record incident details and block next cutover until corrective actions are merged.

## Test and Verification Strategy
- CI matrix includes PostgreSQL-backed test job.
- Mandatory suites before each phase gate:
  - tests/test_webui_api.py
  - tests/test_sync.py
  - tests/test_webui.py
  - migration/parity verification script
- Add migration-specific tests for:
  - schema creation
  - idempotent migrations
  - JSON/text/time field handling
  - foreign-key integrity

## Ownership and Milestones
- Milestone 1: Foundation and schema tooling complete.
- Milestone 2: Local and dev cutover complete.
- Milestone 3: Staging parity and soak complete.
- Milestone 4: Production cutover complete.
- Milestone 5: SQLite default removed and migration closed.

## Progress Log

### 2026-07-04
- Created PostgreSQL migration plan for all environments, including local development.
- Defined phased rollout, validation gates, rollback controls, and environment-specific checklists.

### 2026-07-18
- Completed Postgres-only cutover in code: `psycopg` core dep, `als_intel/db.py`, `migrations/postgres/001_initial.sql`, EvidenceStore on Postgres, Docker/CI/Makefile wiring, `migrate-from-sqlite` CLI, full pytest green on Postgres.
- Runtime no longer supports SQLite as a backend; rollback is restore previous release + SQLite backup only.

## Current Status
- Overall: Local/dev/CI cutover complete (Phases 1–4 for app code)
- Active phase: Production cutover is ops (commands/checklist in this plan); not performed by the agent
- Blockers: none for local/Docker/CI
