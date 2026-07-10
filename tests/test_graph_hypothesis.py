from pathlib import Path

from als_intel.agents.hypothesis_graph import build_graph_gap_hypotheses
from als_intel.pipeline import ingest_file
from als_intel.store import EvidenceStore


def test_graph_gap_hypotheses_generation(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "gap.jsonl"
    input_file.write_text(
        "\n".join(
            [
                '{"claim_id":"Z1","claim_text":"signal supports","disease":"ALS","entity":"target_z","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"observational","sample_size":110,"endpoint_validity":0.72,"replication_count":1,"peer_reviewed":true,"year":2025,"source_title":"Z1","source_doi":"10.1/z1","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.9}',
                '{"claim_id":"Z2","claim_text":"signal contradicts","disease":"ALS","entity":"target_z","relation":"associated_with","outcome":"progression","effect_direction":"contradicts","study_type":"observational","sample_size":95,"endpoint_validity":0.64,"replication_count":0,"peer_reviewed":true,"year":2026,"source_title":"Z2","source_doi":"10.1/z2","cohort":"cohort_b","model_system":"human","source_type":"journal","extraction_confidence":0.87}'
            ]
        ),
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    store = EvidenceStore(db_path)
    store.rebuild_knowledge_graph()
    support_map = store.graph_support_contradiction_map(limit=20)
    cards = build_graph_gap_hypotheses(
        evidence_rows=store.all_evidence(),
        support_map_rows=support_map,
        drift_rows=store.confidence_drift(),
        limit=10,
    )

    assert len(cards) >= 1
    top = cards[0]
    assert "underexplored_index" in top
    assert "why_now_score" in top
    assert 0.0 <= float(top["underexplored_index"]) <= 1.0
    assert 0.0 <= float(top["why_now_score"]) <= 1.0


def test_graph_gap_hypothesis_requires_signoff(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "gap_signoff.jsonl"
    input_file.write_text(
        '{"claim_id":"S1","claim_text":"supports","disease":"ALS","entity":"target_s","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"observational","sample_size":100,"endpoint_validity":0.7,"replication_count":0,"peer_reviewed":true,"year":2026,"source_title":"S1","source_doi":"10.1/s1","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.88}',
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    store = EvidenceStore(db_path)
    store.rebuild_knowledge_graph()
    support_map = store.graph_support_contradiction_map(limit=20)

    gated_none = build_graph_gap_hypotheses(
        evidence_rows=store.all_evidence(),
        support_map_rows=support_map,
        drift_rows=store.confidence_drift(),
        limit=10,
        require_review_signoff=True,
        approved_claim_ids=store.approved_claim_ids(),
    )
    assert len(gated_none) == 0

    store.record_review_decision("S1", "approve", "reviewer", "ok")
    gated_after = build_graph_gap_hypotheses(
        evidence_rows=store.all_evidence(),
        support_map_rows=support_map,
        drift_rows=store.confidence_drift(),
        limit=10,
        require_review_signoff=True,
        approved_claim_ids=store.approved_claim_ids(),
    )
    assert len(gated_after) >= 1
