from pathlib import Path

from als_intel.agents.orchestrator import build_agent_report

from als_intel.pipeline import ingest_file
from als_intel.store import EvidenceStore


def test_ingestion_and_contradictions(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "evidence.jsonl"

    input_file.write_text(
        "\n".join(
            [
                '{"claim_id":"A","claim_text":"s","disease":"ALS","entity":"microglia","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"observational","sample_size":100,"endpoint_validity":0.7,"replication_count":1,"peer_reviewed":true,"year":2024,"source_title":"A","source_doi":"10.1/a","cohort":"cohort_a","model_system":"human"}',
                '{"claim_id":"B","claim_text":"c","disease":"ALS","entity":"microglia","relation":"associated_with","outcome":"progression","effect_direction":"contradicts","study_type":"observational","sample_size":95,"endpoint_validity":0.6,"replication_count":0,"peer_reviewed":true,"year":2025,"source_title":"B","source_doi":"10.1/b","cohort":"cohort_b","model_system":"human"}',
            ]
        ),
        encoding="utf-8",
    )

    count = ingest_file(str(db_path), str(input_file))
    assert count == 2

    store = EvidenceStore(db_path)
    summary = store.summary()
    assert summary["records"] == 2
    assert 0.0 <= summary["avg_source_reliability"] <= 1.0

    pairs = store.contradiction_pairs()
    assert len(pairs) == 1
    assert pairs[0]["contradiction_type"] == "cohort_mismatch"

    lineage = store.claim_lineage("A")
    assert lineage["lineage_counts"]["contradicting"] == 1
    assert lineage["lineage"]["contradicting_citations"][0]["claim_id"] == "B"


def test_drift_and_agent_report(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "evidence.jsonl"

    input_file.write_text(
        "\n".join(
            [
                '{"claim_id":"X","claim_text":"first","disease":"ALS","entity":"pathway_y","relation":"modulates","outcome":"motor","effect_direction":"supports","study_type":"preclinical","sample_size":40,"endpoint_validity":0.5,"replication_count":0,"peer_reviewed":false,"year":2025,"source_title":"X1","source_doi":"10.1/x1","model_system":"mouse","source_type":"preprint","extraction_confidence":0.7}',
                '{"claim_id":"Y","claim_text":"counter","disease":"ALS","entity":"pathway_y","relation":"modulates","outcome":"biomarker","effect_direction":"contradicts","study_type":"observational","sample_size":160,"endpoint_validity":0.75,"replication_count":1,"peer_reviewed":true,"year":2026,"source_title":"Y1","source_doi":"10.1/y1","model_system":"human","source_type":"journal","extraction_confidence":0.9}',
            ]
        ),
        encoding="utf-8",
    )

    count = ingest_file(str(db_path), str(input_file))
    assert count == 2
    # Re-ingest one updated claim to create history drift.
    input_file.write_text(
        '{"claim_id":"X","claim_text":"first updated","disease":"ALS","entity":"pathway_y","relation":"modulates","outcome":"motor","effect_direction":"supports","study_type":"interventional","sample_size":120,"endpoint_validity":0.72,"replication_count":1,"peer_reviewed":true,"year":2026,"source_title":"X2","source_doi":"10.1/x2","model_system":"human","source_type":"journal","extraction_confidence":0.92}',
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    store = EvidenceStore(db_path)
    drift = store.confidence_drift("X")
    assert len(drift) == 1
    assert drift[0]["points"] == 2
    assert drift[0]["delta"] > 0

    report = build_agent_report(store.all_evidence(), store.contradiction_pairs())
    assert "literature_agent" in report
    assert "skeptic_agent" in report


def test_guardrail_blocks_fact_when_contradictions_dense(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "evidence.jsonl"

    input_file.write_text(
        "\n".join(
            [
                '{"claim_id":"F1","claim_text":"meta positive","disease":"ALS","entity":"target_z","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"meta_analysis","sample_size":500,"endpoint_validity":1.0,"replication_count":4,"peer_reviewed":true,"year":2026,"source_title":"F1","source_doi":"10.1/f1","source_type":"journal","extraction_confidence":1.0}',
                '{"claim_id":"F2","claim_text":"meta negative","disease":"ALS","entity":"target_z","relation":"associated_with","outcome":"progression","effect_direction":"contradicts","study_type":"meta_analysis","sample_size":500,"endpoint_validity":1.0,"replication_count":4,"peer_reviewed":true,"year":2026,"source_title":"F2","source_doi":"10.1/f2","source_type":"journal","extraction_confidence":1.0}',
            ]
        ),
        encoding="utf-8",
    )

    ingest_file(str(db_path), str(input_file))
    store = EvidenceStore(db_path)
    report = build_agent_report(store.all_evidence(), store.contradiction_pairs())

    items = report["literature_agent"]["items"]
    assert all(item["label"] != "fact" for item in items)
    assert report["literature_agent"]["guardrail_blocked_facts"] == 2


def test_agent_report_withholds_high_impact_without_signoff(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "evidence.jsonl"

    input_file.write_text(
        '{"claim_id":"R1","claim_text":"interventional signal","disease":"ALS","entity":"target_r","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"interventional","sample_size":240,"endpoint_validity":0.82,"replication_count":1,"peer_reviewed":true,"year":2026,"source_title":"R1","source_doi":"10.1/r1","source_type":"journal","extraction_confidence":0.95}',
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    store = EvidenceStore(db_path)
    gated = build_agent_report(
        store.all_evidence(),
        store.contradiction_pairs(),
        require_review_signoff=True,
        approved_claim_ids=store.approved_claim_ids(),
    )
    assert gated["literature_agent"]["counts"]["withheld_pending_review"] >= 1
    assert gated["literature_agent"]["withheld_high_impact"] >= 1

    store.record_review_decision(
        claim_id="R1",
        decision="approve",
        reviewer="reviewer",
        notes="approved for report exposure",
    )
    ungated_after = build_agent_report(
        store.all_evidence(),
        store.contradiction_pairs(),
        require_review_signoff=True,
        approved_claim_ids=store.approved_claim_ids(),
    )
    labels = [item["label"] for item in ungated_after["literature_agent"]["items"] if item["claim_id"] == "R1"]
    assert labels
    assert labels[0] in {"fact", "hypothesis", "conjecture"}
