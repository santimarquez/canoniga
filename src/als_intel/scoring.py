from __future__ import annotations

from als_intel.models import EvidenceRecord


STUDY_TYPE_WEIGHT = {
    "meta_analysis": 1.0,
    "interventional": 0.85,
    "observational": 0.7,
    "preclinical": 0.45,
}

SOURCE_TYPE_WEIGHT = {
    "journal": 1.0,
    "registry": 0.9,
    "conference": 0.8,
    "preprint": 0.65,
}


def therapeutic_mcda_score(
    *,
    biological_plausibility: float,
    evidence_strength: float,
    safety_profile: float,
    clinical_feasibility: float,
    prior_failure_penalty: float,
) -> dict[str, float]:
    bio = max(0.0, min(biological_plausibility, 1.0))
    evidence = max(0.0, min(evidence_strength, 1.0))
    safety = max(0.0, min(safety_profile, 1.0))
    feasibility = max(0.0, min(clinical_feasibility, 1.0))
    penalty = max(0.0, min(prior_failure_penalty, 1.0))

    score = (
        0.28 * bio
        + 0.24 * evidence
        + 0.18 * safety
        + 0.20 * feasibility
        + 0.10 * (1.0 - penalty)
    )
    score = round(max(0.0, min(score, 1.0)), 4)

    return {
        "biological_plausibility": round(bio, 4),
        "evidence_strength": round(evidence, 4),
        "safety_profile": round(safety, 4),
        "clinical_feasibility": round(feasibility, 4),
        "prior_failure_penalty": round(penalty, 4),
        "mcda_score": score,
    }


def source_reliability_score(record: EvidenceRecord) -> float:
    """Score source trustworthiness independently from claim-level evidence."""
    source_component = SOURCE_TYPE_WEIGHT.get(record.source_type.lower(), 0.7)
    peer_component = 1.0 if record.peer_reviewed else 0.65
    extraction_component = record.extraction_confidence

    score = 0.45 * source_component + 0.35 * peer_component + 0.20 * extraction_component
    return round(max(0.0, min(score, 1.0)), 4)


def score_components(record: EvidenceRecord) -> dict[str, float]:
    study_component = STUDY_TYPE_WEIGHT[record.study_type]
    sample_component = min(record.sample_size / 300.0, 1.0)
    replication_component = min(record.replication_count / 3.0, 1.0)
    peer_component = 1.0 if record.peer_reviewed else 0.65
    endpoint_component = record.endpoint_validity
    source_component = SOURCE_TYPE_WEIGHT.get(record.source_type.lower(), 0.7)
    extraction_component = record.extraction_confidence

    total = (
        0.24 * study_component
        + 0.16 * sample_component
        + 0.16 * replication_component
        + 0.14 * peer_component
        + 0.12 * endpoint_component
        + 0.10 * source_component
        + 0.08 * extraction_component
    )
    total = round(max(0.0, min(total, 1.0)), 4)

    return {
        "study": round(study_component, 4),
        "sample": round(sample_component, 4),
        "replication": round(replication_component, 4),
        "peer_review": round(peer_component, 4),
        "endpoint": round(endpoint_component, 4),
        "source": round(source_component, 4),
        "extraction": round(extraction_component, 4),
        "total": total,
    }


def reliability_score(record: EvidenceRecord) -> float:
    """Compute an interpretable reliability score in [0,1]."""
    return score_components(record)["total"]
