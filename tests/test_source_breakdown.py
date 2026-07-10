from __future__ import annotations

from pathlib import Path

from als_intel.models import EvidenceRecord
from als_intel.store import EvidenceStore


def _record(claim_id: str) -> EvidenceRecord:
    return EvidenceRecord(
        claim_id=claim_id,
        claim_text=f"Synthetic claim {claim_id}",
        disease="ALS",
        entity="entity-a",
        relation="modulates",
        outcome="outcome-a",
        effect_direction="supports",
        study_type="observational",
        sample_size=40,
        endpoint_validity=0.75,
        replication_count=1,
        peer_reviewed=True,
        year=2024,
        source_title=f"Study {claim_id}",
        source_doi=f"10.1000/{claim_id.lower()}",
        causal_evidence_type="observational",
    )


def test_source_breakdown_top_four_plus_others(tmp_path: Path) -> None:
    db_path = tmp_path / "source_breakdown.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()

    # Create 12 evidence rows and map 11 of them to 5 named sources.
    source_map = {
        "pubmed": ["C1", "C2", "C3", "C4", "C5"],
        "ctgov": ["C6", "C7", "C8"],
        "cochrane": ["C9", "C10"],
        "geo": ["C11"],
        "who": ["C12"],
    }

    for claim_id in [f"C{i}" for i in range(1, 13)]:
        store.upsert_evidence(
            _record(claim_id),
            score_breakdown={
                "study": 0.2,
                "sample": 0.1,
                "replication": 0.1,
                "peer_review": 0.1,
                "endpoint": 0.1,
                "source": 0.1,
                "extraction": 0.1,
                "total": 0.7,
            },
            source_score=0.8,
        )

    for source_name, claim_ids in source_map.items():
        for claim_id in claim_ids:
            if claim_id == "C12":
                # Leave one evidence row without metadata to validate unmapped -> Others.
                continue
            store.upsert_evidence_source_metadata(
                claim_id=claim_id,
                source_name=source_name,
                source_id=f"src-{claim_id}",
                abstract_text="",
                journal="",
                pubdate="",
                authors=[],
                mesh_terms=[],
                affiliations=[],
                references=[],
                metadata={},
            )

    rows = store.source_article_breakdown()

    assert rows == [
        {"source": "PubMed", "articles": 5},
        {"source": "ClinicalTrials.gov", "articles": 3},
        {"source": "cochrane", "articles": 2},
        {"source": "GEO (Gene Expression Omnibus)", "articles": 1},
        {"source": "Others", "articles": 1},
    ]
