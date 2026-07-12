from __future__ import annotations

import json
from pathlib import Path

from als_intel.agents.historical import build_failure_atlas
from als_intel.store import EvidenceStore
from als_intel.sync import run_incremental_sync


def test_ctgov_provenance_chain_reaches_failure_atlas(tmp_path: Path) -> None:
    fixture_path = tmp_path / "ctgov_results.json"
    fixture_path.write_text(
        json.dumps(
            [
                {
                    "source": "ctgov",
                    "source_id": "NCT_PROV_001",
                    "title": "Completed ALS trial with negative primary endpoint",
                    "year": 2023,
                    "journal": "clinicaltrials.gov",
                    "trial_status": "Completed",
                    "phase": "PHASE3",
                    "enrollment": 210,
                    "primary_endpoint": "Change in ALSFRS-R",
                    "primary_endpoint_result": "No significant difference versus placebo",
                    "termination_reason": "",
                    "intervention_arm": "Neuroprotective agent",
                }
            ]
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "provenance.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()

    result = run_incremental_sync(
        db_path=str(db_path),
        source="ctgov",
        query="als",
        max_results=10,
        from_file=str(fixture_path),
    )
    assert result["status"] == "ok"
    assert result["inserted"] >= 1

    enriched = store.all_evidence_with_provenance()
    assert enriched
    row = enriched[0]
    provenance = row.get("extraction_provenance")
    assert isinstance(provenance, dict)
    assert provenance.get("primary_endpoint_result") == "No significant difference versus placebo"
    assert provenance.get("trial_status") == "Completed"

    atlas = build_failure_atlas(enriched)
    assert atlas["structured_trial_failures"] >= 1
    assert atlas["entries"][0]["primary_endpoint_result"] == "No significant difference versus placebo"
    assert atlas["entries"][0]["root_cause"] == "endpoint_sensitivity"
