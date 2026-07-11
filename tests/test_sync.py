from pathlib import Path
import sqlite3
from typing import Any

from als_intel.hypothesis import build_hypothesis_queue
from als_intel.scheduler import run_scheduled_sync
from als_intel.store import EvidenceStore
from als_intel.sync import run_incremental_sync


def test_init_db_migrates_legacy_investigation_runs_table(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS investigation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                objective TEXT NOT NULL,
                filters_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                replay_of_run_id TEXT NOT NULL DEFAULT '',
                report_json TEXT NOT NULL DEFAULT '{}',
                quality_gate_json TEXT NOT NULL DEFAULT '{}',
                replay_diff_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                error_text TEXT NOT NULL DEFAULT ''
            );
            """
        )
        conn.commit()

    store = EvidenceStore(db_path)
    store.init_db()

    with sqlite3.connect(db_path) as conn:
        col_rows = conn.execute("PRAGMA table_info(investigation_runs)").fetchall()
        cols = {str(row[1]) for row in col_rows}
        assert "idempotency_key" in cols
        assert "attempt_count" in cols
        assert "max_attempts" in cols
        assert "scheduled_for" in cols
        assert "require_review_signoff" in cols

        idx_rows = conn.execute("PRAGMA index_list(investigation_runs)").fetchall()
        idx_names = {str(row[1]) for row in idx_rows}
        assert "idx_investigation_runs_user_idempotency" in idx_names


def test_incremental_sync_and_change_log(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    pubmed_fixture = Path("examples/pubmed_sample.json")

    first = run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="amyotrophic lateral sclerosis",
        from_file=str(pubmed_fixture),
    )
    assert first["status"] == "ok"
    assert first["inserted"] == 2

    second = run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="amyotrophic lateral sclerosis",
        from_file=str(pubmed_fixture),
    )
    assert second["status"] == "ok"
    assert second["unchanged"] == 2

    store = EvidenceStore(db_path)
    changes_first = store.recent_changes(run_id=int(first["run_id"]))
    changes_second = store.recent_changes(run_id=int(second["run_id"]))
    assert len(changes_first) == 2
    assert len(changes_second) == 0


def test_sync_plus_hypothesis_queue(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="als",
        from_file="examples/pubmed_sample.json",
    )
    run_incremental_sync(
        db_path=str(db_path),
        source="ctgov",
        query="als",
        from_file="examples/ctgov_sample.json",
    )

    store = EvidenceStore(db_path)
    cards = build_hypothesis_queue(store.all_evidence(), store.contradiction_pairs(), limit=5)
    assert len(cards) >= 1
    top = cards[0]
    assert "hypothesis" in top
    assert "supporting_evidence" in top
    assert "contradictory_evidence" in top
    assert "trial_feasibility_score" in top
    assert 0.0 <= top["trial_feasibility_score"] <= 1.0
    assert "trial_compatibility_notes" in top
    assert "causal_risk_score" in top
    assert 0.0 <= top["causal_risk_score"] <= 1.0
    assert "causal_evidence_profile" in top


def test_schedule_sync_once(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_scheduled_sync(
        db_path=str(db_path),
        plan_file="examples/sync_plan.json",
        cycles=1,
        interval_seconds=0,
    )
    assert result["cycles"] == 1
    assert result["jobs"] == 2
    assert len(result["runs"]) == 2
    assert result["totals"]["inserted"] == 4


def test_review_flags_detect_density_and_delta(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    # First ingestion creates contradictory pressure on microglial activation.
    run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="als",
        from_file="examples/pubmed_sample.json",
    )

    # Insert and update same claim to trigger a confidence delta.
    manual_file = tmp_path / "manual.jsonl"
    manual_file.write_text(
        "\n".join(
            [
                '{"claim_id":"DELTA1","claim_text":"weak preclinical signal","disease":"ALS","entity":"neuroinflammation","relation":"associated_with","outcome":"disease_progression","effect_direction":"supports","study_type":"preclinical","sample_size":25,"endpoint_validity":0.4,"replication_count":0,"peer_reviewed":false,"year":2025,"source_title":"weak","source_doi":"10.1/delta1","cohort":"unknown","model_system":"mouse","source_type":"preprint","extraction_confidence":0.6}',
                '{"claim_id":"DELTA1","claim_text":"strong replicated interventional evidence","disease":"ALS","entity":"neuroinflammation","relation":"associated_with","outcome":"disease_progression","effect_direction":"supports","study_type":"interventional","sample_size":220,"endpoint_validity":0.85,"replication_count":2,"peer_reviewed":true,"year":2026,"source_title":"strong","source_doi":"10.1/delta1b","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.95}'
            ]
        ),
        encoding="utf-8",
    )

    from als_intel.pipeline import ingest_file

    ingest_file(str(db_path), str(manual_file))

    store = EvidenceStore(db_path)
    flags = store.review_flags(delta_threshold=0.10, contradiction_density_threshold=0.20)
    assert len(flags) >= 1
    assert any(f["claim_id"] == "DELTA1" for f in flags)


def test_hypothesis_requires_signoff(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="als",
        from_file="examples/pubmed_sample.json",
    )

    store = EvidenceStore(db_path)
    without_gate = build_hypothesis_queue(
        store.all_evidence(),
        store.contradiction_pairs(),
        limit=10,
        require_review_signoff=False,
    )
    with_gate = build_hypothesis_queue(
        store.all_evidence(),
        store.contradiction_pairs(),
        limit=10,
        require_review_signoff=True,
        approved_claim_ids=store.approved_claim_ids(),
    )

    assert len(without_gate) >= 1
    assert len(with_gate) == 0

    store.record_review_decision(
        claim_id="PUBMED_40000001",
        decision="approve",
        reviewer="qa-reviewer",
        notes="Sufficient mechanistic and study-design confidence for queue inclusion",
    )
    with_gate_after = build_hypothesis_queue(
        store.all_evidence(),
        store.contradiction_pairs(),
        limit=10,
        require_review_signoff=True,
        approved_claim_ids=store.approved_claim_ids(),
    )

    assert len(with_gate_after) >= 1
    decisions = store.list_review_decisions(claim_id="PUBMED_40000001")
    assert decisions[0]["decision"] == "approve"


def test_hypothesis_causal_gate_blocks_and_override_unblocks(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="als",
        from_file="examples/pubmed_sample.json",
    )

    store = EvidenceStore(db_path)
    blocked = build_hypothesis_queue(
        store.all_evidence(),
        store.contradiction_pairs(),
        limit=10,
        enforce_causal_gate=True,
    )
    assert len(blocked) == 0

    unblocked = build_hypothesis_queue(
        store.all_evidence(),
        store.contradiction_pairs(),
        limit=10,
        enforce_causal_gate=True,
        causal_promotion_overrides={"microglial activation"},
    )
    assert len(unblocked) >= 1
    assert any(c["entity"] == "microglial activation" for c in unblocked)
    assert any(c["causal_gate_override_applied"] for c in unblocked)


def test_sync_state_updates_after_successful_runs(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="als",
        from_file="examples/pubmed_sample.json",
    )

    store = EvidenceStore(db_path)
    state = store.get_sync_state("pubmed")
    assert state is not None
    assert state["source_name"] == "pubmed"
    assert state["last_sync_run_id"] is not None
    assert state["last_sync_timestamp"]
    assert state["last_successful_timestamp"]
    assert int(state["failure_count"]) == 0


def test_pubmed_incremental_query_uses_last_successful_timestamp(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "als.sqlite"

    # Seed a successful run so sync_state has last_successful_timestamp.
    run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="amyotrophic lateral sclerosis",
        from_file="examples/pubmed_sample.json",
    )

    captured: dict[str, Any] = {}

    def _fake_fetch_pubmed(*, query: str, max_results: int, from_file: str | None = None):
        captured["query"] = query
        captured["max_results"] = max_results
        captured["from_file"] = from_file
        return []

    monkeypatch.setattr("als_intel.sync.fetch_pubmed", _fake_fetch_pubmed)

    result = run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="amyotrophic lateral sclerosis",
        max_results=15,
        from_file=None,
    )

    assert result["status"] == "ok"
    assert int(result["records_seen"]) == 0
    assert "effective_query" in result
    assert "Date - Publication" in str(result["effective_query"])
    assert captured["from_file"] is None
    assert captured["max_results"] == 15
    assert "Date - Publication" in str(captured["query"])


def test_stage_sync_state_tracks_metadata_checkpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="als",
        from_file="examples/pubmed_sample.json",
    )

    assert result["metadata_stage"] == "metadata_enrichment"
    assert result["metadata_stage_last_successful"]

    store = EvidenceStore(db_path)
    stage_state = store.get_stage_sync_state("pubmed", "metadata_enrichment")
    assert stage_state is not None
    assert stage_state["last_successful_timestamp"]
    assert int(stage_state["failure_count"]) == 0


def test_stage_sync_state_failure_does_not_advance_last_successful(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "als.sqlite"
    run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="als",
        from_file="examples/pubmed_sample.json",
    )

    store = EvidenceStore(db_path)
    baseline = store.get_stage_sync_state("pubmed", "metadata_enrichment")
    assert baseline is not None
    baseline_success = baseline["last_successful_timestamp"]
    assert baseline_success

    def _raise_fetch(*, query: str, max_results: int, from_file: str | None = None):
        raise RuntimeError("forced connector failure")

    monkeypatch.setattr("als_intel.sync.fetch_pubmed", _raise_fetch)

    failed = run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="als",
        max_results=5,
    )
    assert failed["status"] == "failed"

    after = store.get_stage_sync_state("pubmed", "metadata_enrichment")
    assert after is not None
    assert after["last_successful_timestamp"] == baseline_success
    assert int(after["failure_count"]) == 1


def test_pubmed_metadata_enrichment_upserts_metadata(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "als.sqlite"

    def _fake_fetch_pubmed(*, query: str, max_results: int, from_file: str | None = None):
        return [
            {
                "source": "pubmed",
                "source_id": "9990001",
                "title": "Microglial activation in ALS progression",
                "year": 2025,
                "journal": "Neuro Journal",
            }
        ]

    def _fake_fetch_pubmed_metadata(pmids: list[str]):
        assert pmids == ["9990001"]
        return {
            "9990001": {
                "abstract_text": "Test abstract",
                "journal": "Neuro Journal",
                "pubdate": "2025 Jan",
                "authors": ["A. Author", "B. Author"],
                "mesh_terms": ["Amyotrophic Lateral Sclerosis"],
                "affiliations": ["Test Institute"],
                "references": ["12345"],
                "raw": {"uid": "9990001"},
            }
        }

    monkeypatch.setattr("als_intel.sync.fetch_pubmed", _fake_fetch_pubmed)
    monkeypatch.setattr("als_intel.sync.fetch_pubmed_metadata", _fake_fetch_pubmed_metadata)

    result = run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="als",
        max_results=5,
    )
    assert result["status"] == "ok"
    assert result["metadata_stage_status"] == "ok"
    assert int(result["metadata_enriched_records"]) == 1

    store = EvidenceStore(db_path)
    metadata = store.get_evidence_source_metadata("PUBMED_9990001")
    assert metadata is not None
    assert metadata["source_id"] == "9990001"
    assert metadata["abstract_text"] == "Test abstract"
    assert metadata["authors"] == ["A. Author", "B. Author"]


def test_pubmed_metadata_enrichment_uses_stage_cursor(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "als.sqlite"
    fetch_calls: list[list[str]] = []
    call_count = {"n": 0}

    def _fake_fetch_pubmed(*, query: str, max_results: int, from_file: str | None = None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [
                {
                    "source": "pubmed",
                    "source_id": "7770001",
                    "title": "ALS mechanism baseline",
                    "year": 2024,
                    "journal": "Baseline Journal",
                }
            ]
        return []

    def _fake_fetch_pubmed_metadata(pmids: list[str]):
        fetch_calls.append(pmids)
        return {
            pmid: {
                "abstract_text": "A",
                "journal": "J",
                "pubdate": "2024",
                "authors": ["X"],
                "mesh_terms": [],
                "affiliations": [],
                "references": [],
                "raw": {"uid": pmid},
            }
            for pmid in pmids
        }

    monkeypatch.setattr("als_intel.sync.fetch_pubmed", _fake_fetch_pubmed)
    monkeypatch.setattr("als_intel.sync.fetch_pubmed_metadata", _fake_fetch_pubmed_metadata)

    first = run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="als",
        max_results=5,
    )
    second = run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="als",
        max_results=5,
    )

    assert first["metadata_stage_status"] == "ok"
    assert second["metadata_stage_status"] == "ok"
    assert int(first["metadata_enriched_records"]) == 1
    assert int(second["metadata_enriched_records"]) == 0
    assert fetch_calls == [["7770001"]]


def test_pubmed_fixture_produces_non_uniform_reliability(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    run_incremental_sync(
        db_path=str(db_path),
        source="pubmed",
        query="als",
        from_file="examples/pubmed_sample.json",
    )

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) >= 2
    reliability_values = {round(float(row["reliability_score"]), 4) for row in rows}
    assert len(reliability_values) > 1


def test_pmc_sync_from_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="pmc",
        query="als",
        from_file="examples/pmc_sample.json",
    )
    assert result["status"] == "ok"
    assert int(result["inserted"]) == 4
    assert result["source"] == "pmc"

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) == 4
    assert all(str(row["claim_id"]).startswith("PMC_") for row in rows)


def test_ncbi_gene_sync_from_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="ncbi_gene",
        query="als",
        from_file="examples/ncbi_gene_sample.json",
    )
    assert result["status"] == "ok"
    assert int(result["inserted"]) == 2
    assert result["source"] == "ncbi_gene"

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) == 2
    assert all(str(row["claim_id"]).startswith("NCBI_GENE_") for row in rows)


def test_uniprot_sync_from_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="uniprot",
        query="als",
        from_file="examples/uniprot_sample.json",
    )
    assert result["status"] == "ok"
    assert int(result["inserted"]) == 2
    assert result["source"] == "uniprot"

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) == 2
    assert all(str(row["claim_id"]).startswith("UNIPROT_") for row in rows)


def test_go_sync_from_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="go",
        query="als",
        from_file="examples/go_sample.json",
    )
    assert result["status"] == "ok"
    assert int(result["inserted"]) == 2
    assert result["source"] == "go"

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) == 2
    assert all(str(row["claim_id"]).startswith("GO_") for row in rows)


def test_reactome_sync_from_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="reactome",
        query="als",
        from_file="examples/reactome_sample.json",
    )
    assert result["status"] == "ok"
    assert int(result["inserted"]) == 2
    assert result["source"] == "reactome"

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) == 2
    assert all(str(row["claim_id"]).startswith("REACTOME_") for row in rows)


def test_geo_sync_from_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="geo",
        query="als",
        from_file="examples/geo_sample.json",
    )
    assert result["status"] == "ok"
    assert int(result["inserted"]) == 2
    assert result["source"] == "geo"

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) == 2
    assert all(str(row["claim_id"]).startswith("GEO_") for row in rows)


def test_arrayexpress_sync_from_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="arrayexpress",
        query="als",
        from_file="examples/arrayexpress_sample.json",
    )
    assert result["status"] == "ok"
    assert int(result["inserted"]) == 2
    assert result["source"] == "arrayexpress"

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) == 2
    assert all(str(row["claim_id"]).startswith("ARRAYEXPRESS_") for row in rows)


def test_kegg_sync_from_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="kegg",
        query="als",
        from_file="examples/kegg_sample.json",
    )
    assert result["status"] == "ok"
    assert int(result["inserted"]) == 2
    assert result["source"] == "kegg"

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) == 2
    assert all(str(row["claim_id"]).startswith("KEGG_") for row in rows)


def test_pride_sync_from_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="pride",
        query="als",
        from_file="examples/pride_sample.json",
    )
    assert result["status"] == "ok"
    assert int(result["inserted"]) == 2
    assert result["source"] == "pride"

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) == 2
    assert all(str(row["claim_id"]).startswith("PRIDE_") for row in rows)


def test_metabolomics_workbench_sync_from_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="metabolomics_workbench",
        query="als",
        from_file="examples/metabolomics_workbench_sample.json",
    )
    assert result["status"] == "ok"
    assert int(result["inserted"]) == 2
    assert result["source"] == "metabolomics_workbench"

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) == 2
    assert all(str(row["claim_id"]).startswith("METABOLOMICS_WORKBENCH_") for row in rows)


def test_chembl_sync_from_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="chembl",
        query="als",
        from_file="examples/chembl_sample.json",
    )
    assert result["status"] == "ok"
    assert int(result["inserted"]) == 2
    assert result["source"] == "chembl"

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) == 2
    assert all(str(row["claim_id"]).startswith("CHEMBL_") for row in rows)


def test_open_targets_sync_from_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="open_targets",
        query="als",
        from_file="examples/open_targets_sample.json",
    )
    assert result["status"] == "ok"
    assert int(result["inserted"]) == 2
    assert result["source"] == "open_targets"

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) == 2
    assert all(str(row["claim_id"]).startswith("OPEN_TARGETS_") for row in rows)


def test_fda_labels_sync_from_fixture(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    result = run_incremental_sync(
        db_path=str(db_path),
        source="fda_labels",
        query="als",
        from_file="examples/fda_labels_sample.json",
    )
    assert result["status"] == "ok"
    assert int(result["inserted"]) == 2
    assert result["source"] == "fda_labels"

    store = EvidenceStore(db_path)
    rows = store.all_evidence()
    assert len(rows) == 2
    assert all(str(row["claim_id"]).startswith("FDA_LABELS_") for row in rows)


def test_schedule_sync_supports_extractor_and_stage_config(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        """
[
  {
    "source": "pubmed",
    "query": "amyotrophic lateral sclerosis",
    "from_file": "examples/pubmed_sample.json",
    "max_results": 10,
    "extractor_config": {"disable_incremental": true},
    "stage_config": {"enabled": false}
  }
]
""".strip(),
        encoding="utf-8",
    )

    result = run_scheduled_sync(
        db_path=str(db_path),
        plan_file=str(plan_file),
        cycles=1,
        interval_seconds=0,
    )
    assert result["cycles"] == 1
    assert result["jobs"] == 1
    assert len(result["runs"]) == 1
    run = result["runs"][0]
    assert run["query"] == "amyotrophic lateral sclerosis"
    assert run["effective_query"] == "amyotrophic lateral sclerosis"
    assert run["metadata_stage_status"] == "ok"
    assert run["metadata_stage_notes"] == "disabled_by_stage_config"


def test_schedule_sync_mixed_sources(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    plan_file = tmp_path / "mixed-plan.json"
    plan_file.write_text(
        """
[
    {
        "source": "pubmed",
        "query": "als",
        "from_file": "examples/pubmed_sample.json",
        "max_results": 10
    },
    {
        "source": "geo",
        "query": "als",
        "from_file": "examples/geo_sample.json",
        "max_results": 10
    },
    {
        "source": "chembl",
        "query": "als",
        "from_file": "examples/chembl_sample.json",
        "max_results": 10
    }
]
""".strip(),
        encoding="utf-8",
    )

    result = run_scheduled_sync(
        db_path=str(db_path),
        plan_file=str(plan_file),
        cycles=1,
        interval_seconds=0,
    )
    assert result["cycles"] == 1
    assert result["jobs"] == 3
    assert len(result["runs"]) == 3
    assert int(result["totals"]["inserted"]) == 6
    sources = {str(run["source"]) for run in result["runs"]}
    assert sources == {"pubmed", "geo", "chembl"}


def test_schedule_sync_mixed_public_source_families(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    plan_file = tmp_path / "mixed-public-plan.json"
    plan_file.write_text(
        """
[
    {
        "source": "pubmed",
        "query": "als",
        "from_file": "examples/pubmed_sample.json",
        "max_results": 10
    },
    {
        "source": "kegg",
        "query": "als",
        "from_file": "examples/kegg_sample.json",
        "max_results": 10
    },
    {
        "source": "pride",
        "query": "als",
        "from_file": "examples/pride_sample.json",
        "max_results": 10
    },
    {
        "source": "open_targets",
        "query": "als",
        "from_file": "examples/open_targets_sample.json",
        "max_results": 10
    },
    {
        "source": "fda_labels",
        "query": "als",
        "from_file": "examples/fda_labels_sample.json",
        "max_results": 10
    }
]
""".strip(),
        encoding="utf-8",
    )

    result = run_scheduled_sync(
        db_path=str(db_path),
        plan_file=str(plan_file),
        cycles=1,
        interval_seconds=0,
    )
    assert result["cycles"] == 1
    assert result["jobs"] == 5
    assert len(result["runs"]) == 5
    assert int(result["totals"]["inserted"]) == 10
    sources = [str(run["source"]) for run in result["runs"]]
    assert sources == ["pubmed", "kegg", "pride", "open_targets", "fda_labels"]


def test_schedule_sync_all_public_sources_single_cycle(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    plan_file = tmp_path / "all-public-plan.json"
    plan_file.write_text(
        """
    [
      {"source": "pubmed", "query": "als", "from_file": "examples/pubmed_sample.json", "max_results": 10},
      {"source": "ctgov", "query": "als", "from_file": "examples/ctgov_sample.json", "max_results": 10},
      {"source": "pmc", "query": "als", "from_file": "examples/pmc_sample.json", "max_results": 10},
      {"source": "ncbi_gene", "query": "als", "from_file": "examples/ncbi_gene_sample.json", "max_results": 10},
      {"source": "uniprot", "query": "als", "from_file": "examples/uniprot_sample.json", "max_results": 10},
      {"source": "go", "query": "als", "from_file": "examples/go_sample.json", "max_results": 10},
      {"source": "reactome", "query": "als", "from_file": "examples/reactome_sample.json", "max_results": 10},
      {"source": "geo", "query": "als", "from_file": "examples/geo_sample.json", "max_results": 10},
      {"source": "arrayexpress", "query": "als", "from_file": "examples/arrayexpress_sample.json", "max_results": 10},
      {"source": "kegg", "query": "als", "from_file": "examples/kegg_sample.json", "max_results": 10},
      {"source": "pride", "query": "als", "from_file": "examples/pride_sample.json", "max_results": 10},
      {"source": "metabolomics_workbench", "query": "als", "from_file": "examples/metabolomics_workbench_sample.json", "max_results": 10},
      {"source": "chembl", "query": "als", "from_file": "examples/chembl_sample.json", "max_results": 10},
      {"source": "open_targets", "query": "als", "from_file": "examples/open_targets_sample.json", "max_results": 10},
      {"source": "fda_labels", "query": "als", "from_file": "examples/fda_labels_sample.json", "max_results": 10}
    ]
    """.strip(),
        encoding="utf-8",
    )

    result = run_scheduled_sync(
        db_path=str(db_path),
        plan_file=str(plan_file),
        cycles=1,
        interval_seconds=0,
    )

    assert result["cycles"] == 1
    assert result["jobs"] == 15
    assert len(result["runs"]) == 15
    assert int(result["totals"]["inserted"]) == 32
    sources = {str(run["source"]) for run in result["runs"]}
    assert len(sources) == 15


def test_sync_persists_source_provenance_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    run_incremental_sync(
        db_path=str(db_path),
        source="geo",
        query="als",
        from_file="examples/geo_sample.json",
    )

    store = EvidenceStore(db_path)
    metadata = store.get_evidence_source_metadata("GEO_GSE123456")
    assert metadata is not None
    assert metadata["source_name"] == "geo"
    assert metadata["source_id"] == "GSE123456"
    payload = metadata["metadata"]
    assert isinstance(payload, dict)
    assert payload["api_endpoint"] == "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    assert payload["query_used"] == "als"
    assert payload["source_version"] == "live"
    assert payload["source_license"] == "unknown"
    assert payload["ingestion_mode"] == "incremental_sync"
    assert "extracted_at" in payload


def test_sync_persists_source_provenance_metadata_for_multiple_sources(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    cases = [
        (
            "kegg",
            "examples/kegg_sample.json",
            "KEGG_hsa05014",
            "hsa05014",
            "https://rest.kegg.jp/find/pathway/",
        ),
        (
            "open_targets",
            "examples/open_targets_sample.json",
            "OPEN_TARGETS_ENSG00000157764",
            "ENSG00000157764",
            "https://api.platform.opentargets.org/api/v4/graphql",
        ),
        (
            "fda_labels",
            "examples/fda_labels_sample.json",
            "FDA_LABELS_1234abcd-1111-2222-3333-444455556666",
            "1234abcd-1111-2222-3333-444455556666",
            "https://api.fda.gov/drug/label.json",
        ),
    ]

    store = EvidenceStore(db_path)
    for source, fixture, claim_id, expected_source_id, expected_endpoint in cases:
        run_incremental_sync(
            db_path=str(db_path),
            source=source,
            query="als",
            from_file=fixture,
        )
        metadata = store.get_evidence_source_metadata(claim_id)
        assert metadata is not None
        assert metadata["source_name"] == source
        assert metadata["source_id"] == expected_source_id
        payload = metadata["metadata"]
        assert isinstance(payload, dict)
        assert payload["api_endpoint"] == expected_endpoint
        assert payload["query_used"] == "als"
        assert payload["source_version"] == "live"
        assert payload["source_license"] == "unknown"
        assert payload["ingestion_mode"] == "incremental_sync"
        assert "extracted_at" in payload
