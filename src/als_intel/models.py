from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VALID_STUDY_TYPES = {"observational", "interventional", "preclinical", "meta_analysis"}
VALID_EFFECT_DIRECTIONS = {"supports", "contradicts", "neutral"}
VALID_CAUSAL_EVIDENCE_TYPES = {"observational", "interventional", "mechanistic", "genetic", "negative"}


def infer_causal_evidence_type(study_type: str, effect_direction: str, relation: str, entity: str) -> str:
    relation_lower = relation.strip().lower()
    entity_lower = entity.strip().lower()

    if effect_direction == "contradicts":
        return "negative"
    if study_type == "interventional":
        return "interventional"
    if "gene" in entity_lower or relation_lower in {"genetic_association", "variant_association"}:
        return "genetic"
    if relation_lower in {"causes", "modulates", "activates", "inhibits", "regulates"}:
        return "mechanistic"
    return "observational"


@dataclass(slots=True)
class EvidenceRecord:
    claim_id: str
    claim_text: str
    disease: str
    entity: str
    relation: str
    outcome: str
    effect_direction: str
    study_type: str
    sample_size: int
    endpoint_validity: float
    replication_count: int
    peer_reviewed: bool
    year: int
    source_title: str
    source_doi: str
    cohort: str = "unknown"
    model_system: str = "unspecified"
    source_type: str = "journal"
    extraction_confidence: float = 1.0
    causal_evidence_type: str = "observational"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceRecord":
        study_type = str(payload["study_type"]).strip().lower()
        effect_direction = str(payload["effect_direction"]).strip().lower()
        endpoint_validity = float(payload["endpoint_validity"])
        extraction_confidence = float(payload.get("extraction_confidence", 1.0))
        causal_evidence_type = str(
            payload.get(
                "causal_evidence_type",
                infer_causal_evidence_type(
                    study_type=study_type,
                    effect_direction=effect_direction,
                    relation=str(payload["relation"]),
                    entity=str(payload["entity"]),
                ),
            )
        ).strip().lower()

        if study_type not in VALID_STUDY_TYPES:
            raise ValueError(f"Invalid study_type: {study_type}")
        if effect_direction not in VALID_EFFECT_DIRECTIONS:
            raise ValueError(f"Invalid effect_direction: {effect_direction}")
        if not 0.0 <= endpoint_validity <= 1.0:
            raise ValueError("endpoint_validity must be in [0,1]")
        if not 0.0 <= extraction_confidence <= 1.0:
            raise ValueError("extraction_confidence must be in [0,1]")
        if causal_evidence_type not in VALID_CAUSAL_EVIDENCE_TYPES:
            raise ValueError(f"Invalid causal_evidence_type: {causal_evidence_type}")

        return cls(
            claim_id=str(payload["claim_id"]),
            claim_text=str(payload["claim_text"]),
            disease=str(payload["disease"]),
            entity=str(payload["entity"]),
            relation=str(payload["relation"]),
            outcome=str(payload["outcome"]),
            effect_direction=effect_direction,
            study_type=study_type,
            sample_size=int(payload["sample_size"]),
            endpoint_validity=endpoint_validity,
            replication_count=int(payload["replication_count"]),
            peer_reviewed=bool(payload["peer_reviewed"]),
            year=int(payload["year"]),
            source_title=str(payload["source_title"]),
            source_doi=str(payload["source_doi"]),
            cohort=str(payload.get("cohort", "unknown")),
            model_system=str(payload.get("model_system", "unspecified")),
            source_type=str(payload.get("source_type", "journal")),
            extraction_confidence=extraction_confidence,
            causal_evidence_type=causal_evidence_type,
        )
