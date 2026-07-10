from pathlib import Path

from als_intel.agents.debate import build_debate_report
from als_intel.agents.historical import build_failure_atlas
from als_intel.metrics import (
    compute_quality_metrics,
    consensus_stability_score,
    debate_disagreement_index,
    failure_pattern_recurrence_score,
)
from als_intel.pipeline import ingest_file
from als_intel.store import EvidenceStore


def test_metric_primitives() -> None:
    timeline = [
        {"consensus_state": "supporting_signal"},
        {"consensus_state": "supporting_signal"},
        {"consensus_state": "contradicting_signal"},
    ]
    stability = consensus_stability_score(timeline)
    assert 0.0 <= stability <= 1.0

    debate = {
        "rounds": [
            {"provisional_consensus": "contested"},
            {"provisional_consensus": "leaning_support"},
            {"provisional_consensus": "contested"},
        ]
    }
    disagreement = debate_disagreement_index(debate)
    assert disagreement == 0.6667

    atlas = {"root_cause_distribution": {"wrong_biology": 3, "wrong_cohort": 1}}
    recurrence = failure_pattern_recurrence_score(atlas)
    assert recurrence == 0.75


def test_compute_quality_metrics_integration(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "metrics.jsonl"
    input_file.write_text(
        "\n".join(
            [
                '{"claim_id":"M1","claim_text":"positive","disease":"ALS","entity":"target_m","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"interventional","sample_size":140,"endpoint_validity":0.8,"replication_count":1,"peer_reviewed":true,"year":2026,"source_title":"M1","source_doi":"10.1/m1","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.9}',
                '{"claim_id":"M2","claim_text":"negative","disease":"ALS","entity":"target_m","relation":"associated_with","outcome":"progression","effect_direction":"contradicts","study_type":"interventional","sample_size":70,"endpoint_validity":0.52,"replication_count":0,"peer_reviewed":true,"year":2026,"source_title":"M2","source_doi":"10.1/m2","cohort":"mixed","model_system":"human","source_type":"registry","extraction_confidence":0.85}'
            ]
        ),
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    store = EvidenceStore(db_path)
    timeline = store.consensus_timeline(entity="target_m", limit=100)
    debate = build_debate_report(store.all_evidence(), store.contradiction_pairs())
    atlas = build_failure_atlas(store.all_evidence())
    metrics = compute_quality_metrics(timeline, debate, atlas)

    assert set(metrics.keys()) == {
        "consensus_stability_score",
        "debate_disagreement_index",
        "failure_pattern_recurrence_score",
    }
    assert all(0.0 <= float(v) <= 1.0 for v in metrics.values())
