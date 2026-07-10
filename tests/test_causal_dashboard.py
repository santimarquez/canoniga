from pathlib import Path

from als_intel.agents.causal_dashboard import build_causal_risk_dashboard
from als_intel.pipeline import ingest_file
from als_intel.store import EvidenceStore


def test_causal_dashboard_blocks_when_strong_support_is_low(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "causal.jsonl"
    input_file.write_text(
        "\n".join(
            [
                '{"claim_id":"CD1","claim_text":"weak observational support","disease":"ALS","entity":"target_cd","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"observational","sample_size":90,"endpoint_validity":0.62,"replication_count":0,"peer_reviewed":true,"year":2026,"source_title":"CD1","source_doi":"10.1/cd1","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.85}',
                '{"claim_id":"CD2","claim_text":"contradictory result","disease":"ALS","entity":"target_cd","relation":"associated_with","outcome":"progression","effect_direction":"contradicts","study_type":"observational","sample_size":85,"endpoint_validity":0.58,"replication_count":0,"peer_reviewed":true,"year":2026,"source_title":"CD2","source_doi":"10.1/cd2","cohort":"cohort_b","model_system":"human","source_type":"journal","extraction_confidence":0.83}'
            ]
        ),
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    store = EvidenceStore(db_path)
    dashboard = build_causal_risk_dashboard(
        evidence_rows=store.all_evidence(),
        contradiction_rows=store.contradiction_pairs(),
        promotion_risk_threshold=0.45,
        minimum_strong_support_ratio=0.3,
    )

    assert dashboard["count"] >= 1
    top = dashboard["items"][0]
    assert top["entity"] == "target_cd"
    assert 0.0 <= float(top["causal_risk_score"]) <= 1.0
    assert top["blocked_from_promotion"] is True


def test_causal_dashboard_unblocks_with_interventional_or_genetic_support(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "causal_strong.jsonl"
    input_file.write_text(
        "\n".join(
            [
                '{"claim_id":"CS1","claim_text":"interventional support","disease":"ALS","entity":"target_cs","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"interventional","sample_size":180,"endpoint_validity":0.8,"replication_count":1,"peer_reviewed":true,"year":2026,"source_title":"CS1","source_doi":"10.1/cs1","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.9,"causal_evidence_type":"interventional"}',
                '{"claim_id":"CS2","claim_text":"genetic support","disease":"ALS","entity":"target_cs","relation":"genetic_association","outcome":"progression","effect_direction":"supports","study_type":"observational","sample_size":160,"endpoint_validity":0.76,"replication_count":1,"peer_reviewed":true,"year":2026,"source_title":"CS2","source_doi":"10.1/cs2","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.88,"causal_evidence_type":"genetic"}',
                '{"claim_id":"CS3","claim_text":"one contradiction","disease":"ALS","entity":"target_cs","relation":"associated_with","outcome":"progression","effect_direction":"contradicts","study_type":"observational","sample_size":90,"endpoint_validity":0.6,"replication_count":0,"peer_reviewed":true,"year":2026,"source_title":"CS3","source_doi":"10.1/cs3","cohort":"cohort_b","model_system":"human","source_type":"journal","extraction_confidence":0.84}'
            ]
        ),
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    store = EvidenceStore(db_path)
    dashboard = build_causal_risk_dashboard(
        evidence_rows=store.all_evidence(),
        contradiction_rows=store.contradiction_pairs(),
        promotion_risk_threshold=0.6,
        minimum_strong_support_ratio=0.4,
    )
    item = dashboard["items"][0]
    assert item["entity"] == "target_cs"
    assert item["support_snapshot"]["strong_support_ratio"] >= 0.4
    assert item["blocked_from_promotion"] is False
