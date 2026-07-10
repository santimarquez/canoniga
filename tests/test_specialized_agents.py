from pathlib import Path

from als_intel.agents.clinical_trial import build_clinical_trial_analysis
from als_intel.agents.historical import build_failure_atlas
from als_intel.agents.repurposing import build_repurposing_report
from als_intel.pipeline import ingest_file
from als_intel.store import EvidenceStore


def test_clinical_trial_and_repurposing_agents(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "specialized.jsonl"
    input_file.write_text(
        "\n".join(
            [
                '{"claim_id":"P1","claim_text":"interventional benefit observed","disease":"ALS","entity":"target_p","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"interventional","sample_size":180,"endpoint_validity":0.82,"replication_count":1,"peer_reviewed":true,"year":2026,"source_title":"P1","source_doi":"10.1/p1","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.9}',
                '{"claim_id":"P2","claim_text":"mixed cohort negative signal","disease":"ALS","entity":"target_p","relation":"associated_with","outcome":"progression","effect_direction":"contradicts","study_type":"observational","sample_size":90,"endpoint_validity":0.6,"replication_count":0,"peer_reviewed":true,"year":2026,"source_title":"P2","source_doi":"10.1/p2","cohort":"mixed","model_system":"human","source_type":"journal","extraction_confidence":0.88}',
                '{"claim_id":"P3","claim_text":"preclinical support only","disease":"ALS","entity":"target_q","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"preclinical","sample_size":40,"endpoint_validity":0.55,"replication_count":0,"peer_reviewed":false,"year":2025,"source_title":"P3","source_doi":"10.1/p3","cohort":"unknown","model_system":"mouse","source_type":"preprint","extraction_confidence":0.75}'
            ]
        ),
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    store = EvidenceStore(db_path)
    store.rebuild_knowledge_graph()
    support_map = store.graph_support_contradiction_map(limit=20)
    atlas = build_failure_atlas(store.all_evidence())

    trial_report = build_clinical_trial_analysis(store.all_evidence(), support_map, atlas)
    assert trial_report["count"] >= 1
    assert "trial_feasibility_score" in trial_report["items"][0]
    assert 0.0 <= float(trial_report["items"][0]["trial_feasibility_score"]) <= 1.0

    repurpose_report = build_repurposing_report(store.all_evidence(), support_map, atlas)
    assert repurpose_report["count"] >= 1
    assert "repurposing_priority_score" in repurpose_report["items"][0]
    assert 0.0 <= float(repurpose_report["items"][0]["repurposing_priority_score"]) <= 1.0
    assert "mcda_components" in repurpose_report["items"][0]
    assert 0.0 <= float(repurpose_report["items"][0]["mcda_components"]["mcda_score"]) <= 1.0
