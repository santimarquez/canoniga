from als_intel.models import EvidenceRecord, infer_causal_evidence_type
from als_intel.scoring import reliability_score, score_components, source_reliability_score, therapeutic_mcda_score


def test_reliability_score_bounds() -> None:
    record = EvidenceRecord(
        claim_id="T1",
        claim_text="Example",
        disease="ALS",
        entity="entity",
        relation="associated_with",
        outcome="outcome",
        effect_direction="supports",
        study_type="observational",
        sample_size=150,
        endpoint_validity=0.7,
        replication_count=1,
        peer_reviewed=True,
        year=2025,
        source_title="Title",
        source_doi="10.1000/test",
        source_type="journal",
        extraction_confidence=0.95,
    )

    score = reliability_score(record)
    assert 0.0 <= score <= 1.0


def test_score_components_have_expected_keys() -> None:
    record = EvidenceRecord(
        claim_id="T2",
        claim_text="Example",
        disease="ALS",
        entity="entity",
        relation="associated_with",
        outcome="outcome",
        effect_direction="supports",
        study_type="interventional",
        sample_size=200,
        endpoint_validity=0.8,
        replication_count=2,
        peer_reviewed=True,
        year=2026,
        source_title="Title",
        source_doi="10.1000/test2",
        source_type="registry",
        extraction_confidence=0.88,
    )

    components = score_components(record)
    expected = {
        "study",
        "sample",
        "replication",
        "peer_review",
        "endpoint",
        "source",
        "extraction",
        "total",
    }
    assert set(components.keys()) == expected
    assert 0.0 <= components["total"] <= 1.0


def test_source_reliability_separate_score() -> None:
    record = EvidenceRecord(
        claim_id="T3",
        claim_text="Example",
        disease="ALS",
        entity="entity",
        relation="associated_with",
        outcome="outcome",
        effect_direction="supports",
        study_type="observational",
        sample_size=80,
        endpoint_validity=0.6,
        replication_count=0,
        peer_reviewed=False,
        year=2026,
        source_title="Title",
        source_doi="10.1000/test3",
        source_type="preprint",
        extraction_confidence=0.7,
    )

    source_score = source_reliability_score(record)
    claim_score = reliability_score(record)
    assert 0.0 <= source_score <= 1.0
    assert 0.0 <= claim_score <= 1.0


def test_causal_evidence_type_inference() -> None:
    assert infer_causal_evidence_type("interventional", "supports", "associated_with", "target_x") == "interventional"
    assert infer_causal_evidence_type("observational", "supports", "modulates", "target_x") == "mechanistic"
    assert infer_causal_evidence_type("observational", "supports", "associated_with", "gene SOD1") == "genetic"
    assert infer_causal_evidence_type("observational", "contradicts", "associated_with", "target_x") == "negative"


def test_therapeutic_mcda_score_bounds_and_keys() -> None:
    result = therapeutic_mcda_score(
        biological_plausibility=0.8,
        evidence_strength=0.7,
        safety_profile=0.6,
        clinical_feasibility=0.65,
        prior_failure_penalty=0.2,
    )
    expected = {
        "biological_plausibility",
        "evidence_strength",
        "safety_profile",
        "clinical_feasibility",
        "prior_failure_penalty",
        "mcda_score",
    }
    assert set(result.keys()) == expected
    assert 0.0 <= result["mcda_score"] <= 1.0
