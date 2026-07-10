from __future__ import annotations

import json
import time
from pathlib import Path

from als_intel.sync import run_incremental_sync


def load_sync_plan(plan_file: str | Path) -> list[dict[str, object]]:
    payload = json.loads(Path(plan_file).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Sync plan must be a JSON list")
    return payload


def run_scheduled_sync(
    db_path: str,
    plan_file: str,
    cycles: int = 1,
    interval_seconds: int = 3600,
) -> dict[str, object]:
    jobs = load_sync_plan(plan_file)
    if cycles < 1:
        raise ValueError("cycles must be >= 1")
    if interval_seconds < 0:
        raise ValueError("interval_seconds must be >= 0")

    all_runs: list[dict[str, object]] = []
    for cycle in range(cycles):
        for job in jobs:
            extractor_config = job.get("extractor_config", {})
            stage_config = job.get("stage_config", {})
            if not isinstance(extractor_config, dict):
                extractor_config = {}
            if not isinstance(stage_config, dict):
                stage_config = {}
            result = run_incremental_sync(
                db_path=db_path,
                source=str(job["source"]),
                query=str(job["query"]),
                max_results=int(job.get("max_results", 20)),
                from_file=str(job["from_file"]) if job.get("from_file") else None,
                extractor_config=extractor_config,
                stage_config=stage_config,
            )
            result["cycle"] = cycle + 1
            all_runs.append(result)

        if cycle < cycles - 1 and interval_seconds > 0:
            time.sleep(interval_seconds)

    inserted = sum(int(r["inserted"]) for r in all_runs)
    updated = sum(int(r["updated"]) for r in all_runs)
    unchanged = sum(int(r["unchanged"]) for r in all_runs)

    return {
        "cycles": cycles,
        "jobs": len(jobs),
        "runs": all_runs,
        "totals": {
            "inserted": inserted,
            "updated": updated,
            "unchanged": unchanged,
        },
    }
