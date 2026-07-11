from __future__ import annotations

from als_intel.extraction_fidelity import evaluate_extraction_fidelity


def test_extraction_fidelity_meets_threshold() -> None:
    report = evaluate_extraction_fidelity()
    assert report["cases"] >= 10
    assert float(report["field_accuracy"]) >= 0.70
    assert float(report["structured_claim_ratio"]) >= 0.70
    assert bool(report["passed"]) is True


def test_pubmed_structured_claim_text_not_title_only() -> None:
    report = evaluate_extraction_fidelity()
    pubmed_cases = [
        row for row in report["per_case"]
        if str(row.get("source")) == "pubmed"
    ]
    assert pubmed_cases
    assert all(bool(row.get("claim_text_structured")) for row in pubmed_cases)


def test_ctgov_terminated_trials_contradict() -> None:
    from als_intel.extractors.claim_builder import build_record_from_doc

    record = build_record_from_doc(
        {
            "source": "ctgov",
            "source_id": "NCT99900002",
            "title": "Failed trial of protein aggregation inhibitor in ALS",
            "trial_status": "Terminated",
            "termination_reason": "Lack of efficacy",
            "primary_endpoint": "ALS functional rating scale",
            "intervention_arm": "Protein aggregation inhibitor",
            "year": 2024,
            "journal": "clinicaltrials.gov",
        }
    )
    assert record.effect_direction == "contradicts"
    assert "protein aggregation" in record.entity.lower()
    assert record.claim_text != "Failed trial of protein aggregation inhibitor in ALS"
