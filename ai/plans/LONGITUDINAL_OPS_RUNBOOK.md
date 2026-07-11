# Longitudinal Operations Runbook

Unattended nightly monitoring for Canoniga using the investigation worker and sync scheduler.

## Objective

Keep evidence fresh, rebuild the knowledge graph, re-rank hypotheses, and surface quality-gate failures for human review.

## Canonical nightly command

Use the Makefile target that chains all three steps:

```bash
export ALS_AUTOMATION_WORKER_TOKEN="<worker-token>"
make nightly-ops
```

This runs:

1. `make sync-all-sources` (default plan: `config/sync_plan.all_public_sources.json`)
2. `als-intel graph-build --db data/als_intel.sqlite`
3. `POST /api/investigation/runs/worker/tick` (skipped if `ALS_AUTOMATION_WORKER_TOKEN` is unset)

For a faster API smoke sync (5 records per source), use:

```bash
SYNC_ALL_PLAN=config/sync_plan.smoke_public_sources.json make sync-all-sources
```

## Recommended nightly flow

1. Sync all public sources
2. Rebuild knowledge graph
3. Execute investigation worker tick
4. Review freshness alarms and pending review queue
5. Inspect failure atlas (`GET /api/failure-atlas` or `als-intel failure-atlas --db data/als_intel.sqlite`)

## Local cron example

```cron
15 2 * * * cd /path/to/canoniga && export ALS_AUTOMATION_WORKER_TOKEN="<token>" && make nightly-ops >> logs/nightly-ops.log 2>&1
```

## Docker dev example

```bash
make docker-sync-all-sources
make docker-hypothesis-check
curl -fsS -X POST http://localhost:8000/api/investigation/runs/worker/tick -H "Authorization: Bearer $ALS_AUTOMATION_WORKER_TOKEN"
curl -fsS http://localhost:8000/api/automation/dashboard
curl -fsS http://localhost:8000/api/automation/freshness/alarms
curl -fsS http://localhost:8000/api/failure-atlas
```

## Success checks

- `freshness_compliance_rate` remains above configured threshold on automation dashboard
- Review queue `pending_total` is triaged within 24 hours
- 7-day replay stability metric remains stable across investigation runs
- Failure atlas entries include structured `primary_endpoint_result` when CTGov results are present

## Escalation

If freshness alarms fire for more than two consecutive nights:

1. Inspect `sync_runs` notes for failing sources
2. Re-run `make sync-all-sources` manually with `SYNC_ALL_PLAN=config/sync_plan.all_public_sources.json`
3. Hold hypothesis promotion until signoff queue is cleared
