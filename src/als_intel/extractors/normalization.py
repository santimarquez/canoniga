from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from als_intel.models import EvidenceRecord


KEYWORD_ENTITY_MAP = {
    "microgl": "microglial activation",
    "neuroinflamm": "neuroinflammation",
    "mitochond": "mitochondrial dysfunction",
    "protein aggreg": "protein aggregation",
    "rna": "rna processing",
    "axonal": "axonal transport",
}


def infer_entity(title: str) -> str:
    lower = title.lower()
    for token, entity in KEYWORD_ENTITY_MAP.items():
        if token in lower:
            return entity
    return "als mechanism (unspecified)"


def infer_effect_direction(title: str) -> str:
    lower = title.lower()
    negative_markers = ["no association", "did not", "failed", "negative"]
    positive_markers = ["improved", "benefit", "associated", "reduced", "effective"]
    if any(m in lower for m in negative_markers):
        return "contradicts"
    if any(m in lower for m in positive_markers):
        return "supports"
    return "neutral"


def infer_study_type(source: str, title: str) -> str:
    if source == "ctgov":
        return "interventional"
    lower = title.lower()
    if any(token in lower for token in ["meta-analysis", "meta analysis", "systematic review"]):
        return "meta_analysis"
    if any(token in lower for token in ["trial", "randomized", "placebo", "double-blind", "phase "]):
        return "interventional"
    if any(token in lower for token in ["mouse", "mice", "rat", "zebrafish", "in vitro", "cell line", "preclinical"]):
        return "preclinical"
    return "observational"


def infer_sample_size(source: str, title: str, study_type: str) -> int:
    lower = title.lower()
    match = re.search(r"\b(?:n\s*=\s*|n\s*:\s*|)(\d{2,5})\b", lower)
    if match:
        parsed = int(match.group(1))
        return max(20, min(parsed, 3000))

    baseline = {
        "meta_analysis": 320,
        "interventional": 160,
        "observational": 95,
        "preclinical": 48,
    }.get(study_type, 90)
    if source == "ctgov":
        baseline = max(baseline, 180)
    return baseline


def infer_replication_count(title: str) -> int:
    lower = title.lower()
    if "multicenter" in lower or "multi-center" in lower:
        return 2
    if "replication" in lower or "validation" in lower:
        return 1
    return 0


def infer_endpoint_validity(study_type: str, title: str, year: int) -> float:
    base = {
        "meta_analysis": 0.86,
        "interventional": 0.78,
        "observational": 0.62,
        "preclinical": 0.50,
    }.get(study_type, 0.60)

    lower = title.lower()
    if any(token in lower for token in ["alsfrs", "survival", "mortality", "functional", "biomarker"]):
        base += 0.04
    if year >= datetime.now(timezone.utc).year - 3:
        base += 0.03
    return round(max(0.35, min(base, 0.95)), 4)


def infer_source_type(source: str, title: str, journal: str) -> str:
    if source == "ctgov":
        return "registry"
    lower = f"{title} {journal}".lower()
    if "preprint" in lower or "medrxiv" in lower or "biorxiv" in lower:
        return "preprint"
    return "journal"


def infer_extraction_confidence(source_id: str, title: str, journal: str, year: int) -> float:
    score = 0.70
    if source_id.strip():
        score += 0.05
    if journal.strip():
        score += 0.06
    if year > 0:
        score += 0.04
    if len(title.strip()) >= 40:
        score += 0.03
    return round(max(0.45, min(score, 0.95)), 4)


def claim_id(source: str, source_id: str, title: str) -> str:
    if source_id:
        return f"{source.upper()}_{source_id}"
    digest = hashlib.sha1(f"{source}:{title}".encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"{source.upper()}_{digest}"


def record_from_doc(doc: dict[str, Any]) -> EvidenceRecord:
    source = str(doc.get("source", "unknown"))
    title = str(doc.get("title", "")).strip() or "Untitled record"
    source_id = str(doc.get("source_id", "")).strip()
    journal = str(doc.get("journal", "")).strip()

    study_type = infer_study_type(source, title)
    effect_direction = infer_effect_direction(title)
    entity = infer_entity(title)
    year = int(doc.get("year", 0) or 0)
    year = year if year > 0 else 2000
    sample_size = infer_sample_size(source, title, study_type)
    replication_count = infer_replication_count(title)
    endpoint_validity = infer_endpoint_validity(study_type, title, year)
    source_type = infer_source_type(source, title, journal)
    extraction_confidence = infer_extraction_confidence(source_id, title, journal, year)
    peer_reviewed = source == "pubmed" and source_type != "preprint"

    return EvidenceRecord(
        claim_id=claim_id(source, source_id, title),
        claim_text=title,
        disease="ALS",
        entity=entity,
        relation="associated_with",
        outcome="disease_progression",
        effect_direction=effect_direction,
        study_type=study_type,
        sample_size=sample_size,
        endpoint_validity=endpoint_validity,
        replication_count=replication_count,
        peer_reviewed=peer_reviewed,
        year=year,
        source_title=title,
        source_doi=str(doc.get("source_id", "unknown")),
        cohort="mixed",
        model_system="human",
        source_type=source_type,
        extraction_confidence=extraction_confidence,
    )
