from __future__ import annotations

import json
from pathlib import Path


DEFAULT_GOLD_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "extraction_fidelity_gold.json"
)
MIN_FIELD_ACCURACY = 0.70
MIN_STRUCTURED_CLAIM_RATIO = 0.70


def load_gold_cases(path: str | Path | None = None) -> list[dict[str, object]]:
    gold_path = Path(path) if path is not None else DEFAULT_GOLD_PATH
    payload = json.loads(gold_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("extraction fidelity gold file must be a JSON list")
    return payload


def evaluate_extraction_fidelity(
    *,
    gold_path: str | Path | None = None,
    min_field_accuracy: float = MIN_FIELD_ACCURACY,
    min_structured_claim_ratio: float = MIN_STRUCTURED_CLAIM_RATIO,
) -> dict[str, object]:
    from als_intel.extractors.claim_builder import compare_to_gold

    cases = load_gold_cases(gold_path)
    if not cases:
        raise ValueError("no gold extraction cases found")

    per_case: list[dict[str, object]] = []
    field_hits = 0
    field_total = 0
    structured_hits = 0

    for case in cases:
        doc = case.get("doc")
        expected = case.get("expected")
        if not isinstance(doc, dict) or not isinstance(expected, dict):
            continue
        result = compare_to_gold(doc, expected)
        matches = result["matches"]
        if isinstance(matches, dict):
            field_hits += sum(1 for ok in matches.values() if ok)
            field_total += len(matches)
        if bool(result.get("claim_text_structured")):
            structured_hits += 1
        per_case.append(
            {
                "source": doc.get("source"),
                "source_id": doc.get("source_id"),
                "field_accuracy": result["field_accuracy"],
                "claim_text_structured": result["claim_text_structured"],
                "matches": matches,
            }
        )

    field_accuracy = field_hits / max(field_total, 1)
    structured_claim_ratio = structured_hits / max(len(per_case), 1)
    passed = field_accuracy >= min_field_accuracy and structured_claim_ratio >= min_structured_claim_ratio

    return {
        "family": "extraction_fidelity",
        "passed": passed,
        "cases": len(per_case),
        "field_accuracy": round(field_accuracy, 4),
        "structured_claim_ratio": round(structured_claim_ratio, 4),
        "thresholds": {
            "min_field_accuracy": min_field_accuracy,
            "min_structured_claim_ratio": min_structured_claim_ratio,
        },
        "per_case": per_case,
    }
