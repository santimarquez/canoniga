# Longitudinal Operations Runbook

Unattended nightly monitoring for Canoniga using the investigation worker and sync scheduler.

## Objective

Keep evidence fresh, rebuild the knowledge graph, re-rank hypotheses, and surface quality-gate failures for human review.

## Recommended nightly flow

1. Sync all public sources
2. Rebuild knowledge graph
3. Execute investigation worker tick
4. Review freshness alarms and pending review queue

## Local cron example

```cron
15 2 * * * cd /path/to/canoniga && make sync-all-sources >> logs/sync.log 2>&1
30 2 * * * cd /path/to/canoniga && .venv/bin/python -m als_intel init-db --db data/als_intel.sqlite && .venv/bin/python -c "from als_intel.store import EvidenceStore; s=EvidenceStore('data/als_intel.sqlite'); s.rebuild_knowledge_graph(); print('kg_rebuilt')" >> logs/kg.log 2>&1
45 2 * * * curl -fsS -X POST http://localhost:8000/api/investigation/runs/worker/tick >> logs/worker.log 2>&1
```

## Docker dev example

```bash
make docker-sync-all-sources
make docker-hypothesis-check
curl -fsS -X POST http://localhost:8000/api/investigation/runs/worker/tick
curl -fsS http://localhost:8000/api/automation/dashboard
curl -fsS http://localhost:8000/api/automation/freshness/alarms
```

## Success checks

- `freshness_compliance_rate` remains above configured threshold on automation dashboard
- Review queue `pending_total` is triaged within 24 hours
- 7-day replay stability metric remains stable across investigation runs

## Escalation

If freshness alarms fire for more than two consecutive nights:

1. Inspect `sync_runs` notes for failing sources
2. Re-run `make sync-all-sources` manually with `SYNC_ALL_PLAN=config/sync_plan.all_public_sources.json`
3. Hold hypothesis promotion until signoff queue is cleared
