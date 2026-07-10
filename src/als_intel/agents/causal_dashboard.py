from __future__ import annotations

from collections import defaultdict


STRONG_CAUSAL_TYPES = {"interventional", "genetic"}


def build_causal_risk_dashboard(
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
    *,
    entity: str | None = None,
    limit: int = 50,
    promotion_risk_threshold: float = 0.5,
    minimum_strong_support_ratio: float = 0.3,
) -> dict[str, object]:
    by_entity: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in evidence_rows:
        key = str(row["entity"])
        if entity and key != entity:
            continue
        by_entity[key].append(row)

    contradiction_count_by_entity: dict[str, int] = defaultdict(int)
    for row in contradiction_rows:
        key = str(row["entity"])
        if entity and key != entity:
            continue
        contradiction_count_by_entity[key] += 1

    items: list[dict[str, object]] = []
    for entity_key, rows in by_entity.items():
        supports = [r for r in rows if str(r["effect_direction"]) == "supports"]
        contradicts = [r for r in rows if str(r["effect_direction"]) == "contradicts"]

        support_count = len(supports)
        strong_support_count = sum(
            1 for r in supports if str(r.get("causal_evidence_type", "observational")) in STRONG_CAUSAL_TYPES
        )
        strong_support_ratio = strong_support_count / max(support_count, 1)

        contradiction_density = contradiction_count_by_entity[entity_key] / max(len(rows), 1)
        avg_support_reliability = (
            sum(float(r["reliability_score"]) for r in supports) / max(support_count, 1)
        )

        causal_risk_score = (
            0.45 * (1.0 - strong_support_ratio)
            + 0.35 * contradiction_density
            + 0.20 * (1.0 - avg_support_reliability)
        )
        causal_risk_score = round(max(0.0, min(causal_risk_score, 1.0)), 4)

        blocked = (
            causal_risk_score >= promotion_risk_threshold
            and strong_support_ratio < minimum_strong_support_ratio
        )

        reasons: list[str] = []
        if strong_support_ratio < minimum_strong_support_ratio:
            reasons.append(
                (
                    "insufficient_strong_causal_support"
                    f"({strong_support_ratio:.4f} < {minimum_strong_support_ratio:.4f})"
                )
            )
        if causal_risk_score >= promotion_risk_threshold:
            reasons.append(
                (
                    "causal_risk_above_promotion_threshold"
                    f"({causal_risk_score:.4f} >= {promotion_risk_threshold:.4f})"
                )
            )
        if contradiction_density > 0.0:
            reasons.append(f"contradiction_density={contradiction_density:.4f}")

        items.append(
            {
                "entity": entity_key,
                "causal_risk_score": causal_risk_score,
                "blocked_from_promotion": blocked,
                "support_snapshot": {
                    "claims": len(rows),
                    "supports": support_count,
                    "contradicts": len(contradicts),
                    "strong_interventional_or_genetic_supports": strong_support_count,
                    "strong_support_ratio": round(strong_support_ratio, 4),
                    "avg_support_reliability": round(float(avg_support_reliability), 4),
                    "contradiction_density": round(float(contradiction_density), 4),
                },
                "reasons": reasons,
                "recommended_actions": [
                    "Prioritize interventional or genetic evidence collection before promotion.",
                    "Run contradiction-resolving replication with harmonized endpoints and cohorts.",
                ],
            }
        )

    items.sort(key=lambda x: x["causal_risk_score"], reverse=True)
    clipped = items[:limit]
    return {
        "count": len(clipped),
        "blocked_count": sum(1 for x in clipped if bool(x["blocked_from_promotion"])),
        "items": clipped,
    }
