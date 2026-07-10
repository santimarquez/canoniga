from pathlib import Path

from als_intel.agents.debate import build_debate_report
from als_intel.agents.historical import build_failure_atlas
from als_intel.pipeline import ingest_file
from als_intel.store import EvidenceStore


def test_failure_atlas_and_debate_protocol(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "evidence.jsonl"
    input_file.write_text(
        "\n".join(
            [
                '{"claim_id":"S1","claim_text":"interventional benefit in cohort","disease":"ALS","entity":"target_s","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"interventional","sample_size":140,"endpoint_validity":0.78,"replication_count":1,"peer_reviewed":true,"year":2026,"source_title":"S1","source_doi":"10.1/s1","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.9}',
                '{"claim_id":"S2","claim_text":"failed trial with mixed cohort","disease":"ALS","entity":"target_s","relation":"associated_with","outcome":"progression","effect_direction":"contradicts","study_type":"interventional","sample_size":52,"endpoint_validity":0.48,"replication_count":0,"peer_reviewed":true,"year":2026,"source_title":"S2","source_doi":"10.1/s2","cohort":"mixed","model_system":"human","source_type":"registry","extraction_confidence":0.85}'
            ]
        ),
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    store = EvidenceStore(db_path)
    atlas = build_failure_atlas(store.all_evidence())
    assert atlas["total_failed_or_negative_records"] >= 1
    assert len(atlas["entries"]) >= 1

    debate = build_debate_report(store.all_evidence(), store.contradiction_pairs())
    assert debate["protocol"]["version"] == "v1"
    assert debate["round_count"] >= 1


def test_consensus_timeline(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "timeline.jsonl"

    input_file.write_text(
        '{"claim_id":"T1","claim_text":"first signal","disease":"ALS","entity":"target_t","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"observational","sample_size":100,"endpoint_validity":0.7,"replication_count":1,"peer_reviewed":true,"year":2025,"source_title":"T1","source_doi":"10.1/t1","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.88}',
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    input_file.write_text(
        '{"claim_id":"T1","claim_text":"updated signal","disease":"ALS","entity":"target_t","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"interventional","sample_size":180,"endpoint_validity":0.82,"replication_count":1,"peer_reviewed":true,"year":2026,"source_title":"T1b","source_doi":"10.1/t1b","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.9}',
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    store = EvidenceStore(db_path)
    timeline = store.consensus_timeline(entity="target_t", limit=10)
    assert len(timeline) >= 2
    assert "change_rationale" in timeline[0]
    assert timeline[0]["consensus_state"] in {
        "supporting_signal",
        "contradicting_signal",
        "neutral_signal",
    }
