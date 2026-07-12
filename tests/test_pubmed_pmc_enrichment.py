from __future__ import annotations

from unittest.mock import patch

from als_intel.connectors import fetch_pmc
from als_intel.extractors.pubmed import PubMedExtractor
from als_intel.models import EvidenceRecord
from als_intel.scoring import score_components, source_reliability_score
from als_intel.store import EvidenceStore


def test_pmc_fetch_fulltext_flag_triggers_body_fetch() -> None:
    docs = [
        {
            "pmcid": "PMC123",
            "title": "ALS excitotoxicity study",
            "journalTitle": "Neuron",
            "pubYear": "2021",
            "abstractText": "Glutamate excitotoxicity in motor neurons.",
        }
    ]

    with patch("als_intel.connectors._http_get_json", return_value={"resultList": {"result": docs}}):
        with patch("als_intel.connectors._fetch_pmc_body_snippet", return_value="Full text snippet") as mocked:
            rows = fetch_pmc("als", max_results=100, fetch_fulltext=True)
            mocked.assert_called_once_with("PMC123")
            assert rows[0]["body_text"] == "Full text snippet"


def test_pubmed_metadata_enrichment_updates_mesh_and_abstract(tmp_path) -> None:
    db_path = tmp_path / "pubmed_meta.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    record = EvidenceRecord(
        claim_id="PUBMED_39999001",
        claim_text="Microglial activation associated with ALS progression.",
        disease="ALS",
        entity="microglial activation",
        relation="associated_with",
        outcome="disease progression",
        effect_direction="supports",
        study_type="observational",
        sample_size=120,
        endpoint_validity=0.7,
        replication_count=1,
        peer_reviewed=True,
        year=2025,
        source_title="Microglial activation study",
        source_doi="39999001",
        causal_evidence_type="observational",
    )
    breakdown = score_components(record)
    source_score = source_reliability_score(record)
    store.upsert_evidence(record, breakdown, source_score)

    metadata = {
        "39999001": {
            "abstract_text": "Microglial activation was associated with ALS progression.",
            "mesh_terms": ["Microglia", "Neuroinflammation"],
            "authors": ["A. Investigator"],
            "references": [],
        }
    }

    extractor = PubMedExtractor()
    with patch("als_intel.sync.fetch_pubmed_metadata", return_value=metadata):
        status, notes, enriched = extractor.run_metadata_enrichment(
            store=store,
            last_stage_successful_timestamp=None,
            source_sync_status="ok",
            stage_config={"enabled": True, "metadata_limit": 10},
        )

    assert status == "ok"
    assert enriched == 1
    row = store.get_evidence_source_metadata("PUBMED_39999001")
    assert row is not None
    assert "Microglia" in row["mesh_terms"]
    assert "Microglial activation" in row["abstract_text"]
