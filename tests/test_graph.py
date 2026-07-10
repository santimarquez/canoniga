from pathlib import Path

from als_intel.pipeline import ingest_file
from als_intel.store import EvidenceStore


def test_graph_build_and_overview(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "graph.jsonl"
    input_file.write_text(
        "\n".join(
            [
                '{"claim_id":"G1","claim_text":"microglia supports progression","disease":"ALS","entity":"microglial activation","relation":"associated_with","outcome":"progression_rate","effect_direction":"supports","study_type":"observational","sample_size":100,"endpoint_validity":0.7,"replication_count":1,"peer_reviewed":true,"year":2025,"source_title":"G1","source_doi":"10.1/g1","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.9}',
                '{"claim_id":"G2","claim_text":"microglia contradicts progression","disease":"ALS","entity":"microglial activation","relation":"associated_with","outcome":"progression_rate","effect_direction":"contradicts","study_type":"observational","sample_size":95,"endpoint_validity":0.6,"replication_count":0,"peer_reviewed":true,"year":2026,"source_title":"G2","source_doi":"10.1/g2","cohort":"cohort_b","model_system":"human","source_type":"journal","extraction_confidence":0.88}'
            ]
        ),
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    store = EvidenceStore(db_path)
    build = store.rebuild_knowledge_graph()
    assert build["records"] == 2
    assert build["nodes"] >= 6
    assert build["edges"] >= 8

    overview = store.knowledge_graph_overview()
    assert overview["nodes"] >= 6
    assert overview["edges"] >= 8
    assert overview["affects_outcome_edges"] >= 2


def test_graph_support_map_and_neighbors(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "graph2.jsonl"
    input_file.write_text(
        "\n".join(
            [
                '{"claim_id":"H1","claim_text":"entity a supports","disease":"ALS","entity":"entity_a","relation":"associated_with","outcome":"outcome_x","effect_direction":"supports","study_type":"observational","sample_size":90,"endpoint_validity":0.65,"replication_count":0,"peer_reviewed":true,"year":2025,"source_title":"H1","source_doi":"10.1/h1","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.86}',
                '{"claim_id":"H2","claim_text":"entity a contradicts","disease":"ALS","entity":"entity_a","relation":"associated_with","outcome":"outcome_x","effect_direction":"contradicts","study_type":"observational","sample_size":85,"endpoint_validity":0.62,"replication_count":0,"peer_reviewed":true,"year":2025,"source_title":"H2","source_doi":"10.1/h2","cohort":"cohort_b","model_system":"human","source_type":"journal","extraction_confidence":0.84}'
            ]
        ),
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    store = EvidenceStore(db_path)
    store.rebuild_knowledge_graph()

    support_map = store.graph_support_contradiction_map(entity="entity_a", limit=10)
    assert len(support_map) >= 1
    assert support_map[0]["entity"] == "entity_a"
    assert support_map[0]["supports"] >= 1
    assert support_map[0]["contradicts"] >= 1

    neighbors = store.graph_neighbors(node_key="entity:entity_a", limit=10)
    assert len(neighbors) >= 1
    assert any(n["edge_type"] == "affects_outcome" for n in neighbors)
