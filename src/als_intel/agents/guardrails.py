from __future__ import annotations


HIGH_CONTRADICTION_DENSITY = 0.34


def contradiction_density_by_entity(
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
) -> dict[str, float]:
    claim_counts: dict[str, int] = {}
    contradiction_counts: dict[str, int] = {}

    for row in evidence_rows:
        entity = str(row["entity"])
        claim_counts[entity] = claim_counts.get(entity, 0) + 1

    for row in contradiction_rows:
        entity = str(row["entity"])
        contradiction_counts[entity] = contradiction_counts.get(entity, 0) + 1

    density: dict[str, float] = {}
    for entity, count in claim_counts.items():
        contradiction_count = contradiction_counts.get(entity, 0)
        density[entity] = round(contradiction_count / max(count, 1), 4)

    return density


def apply_causal_risk_guardrail(label: str, confidence: float, density: float) -> tuple[str, float, str | None]:
    """
    Prevent overconfident outputs in regions with dense contradictions.

    If a claim would be labeled as fact but contradiction density is high,
    downgrade to hypothesis and cap confidence below fact threshold.
    """
    if label == "fact" and density >= HIGH_CONTRADICTION_DENSITY:
        capped_confidence = min(confidence, 0.74)
        return (
            "hypothesis",
            round(capped_confidence, 4),
            "High contradiction density for entity; fact label blocked by causal-risk guardrail.",
        )
    return (label, confidence, None)
