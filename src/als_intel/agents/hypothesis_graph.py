from __future__ import annotations

from collections import defaultdict


def build_graph_gap_hypotheses(
    evidence_rows: list[dict[str, object]],
    support_map_rows: list[dict[str, object]],
    drift_rows: list[dict[str, object]],
    limit: int = 10,
    require_review_signoff: bool = False,
    approved_claim_ids: set[str] | None = None,
) -> list[dict[str, object]]:
    approved_claim_ids = approved_claim_ids or set()

    by_entity_claims: dict[str, list[dict[str, object]]] = defaultdict(list)
    claim_to_entity: dict[str, str] = {}
    for row in evidence_rows:
        entity = str(row["entity"])
        claim_id = str(row["claim_id"])
        by_entity_claims[entity].append(row)
        claim_to_entity[claim_id] = entity

    drift_entity: dict[str, dict[str, float]] = defaultdict(lambda: {"abs_delta_sum": 0.0, "count": 0.0, "updates": 0.0})
    for d in drift_rows:
        claim_id = str(d["claim_id"])
        entity = claim_to_entity.get(claim_id)
        if entity is None:
            continue
        abs_delta = abs(float(d["delta"]))
        points = int(d["points"])
        drift_entity[entity]["abs_delta_sum"] += abs_delta
        drift_entity[entity]["count"] += 1.0
        drift_entity[entity]["updates"] += max(points - 1, 0)

    cards: list[dict[str, object]] = []
    for row in support_map_rows:
        entity = str(row["entity"])
        outcome = str(row["outcome"])
        claims = by_entity_claims.get(entity, [])
        if not claims:
            continue

        supports = int(row["supports"])
        contradicts = int(row["contradicts"])
        total_signal = max(supports + contradicts, 1)
        contradiction_ratio = contradicts / total_signal

        claim_count = len(claims)
        underexplored_signal = 1.0 / (1.0 + claim_count)

        drift_info = drift_entity.get(entity, {"abs_delta_sum": 0.0, "count": 0.0, "updates": 0.0})
        drift_signal = (
            (drift_info["abs_delta_sum"] / max(drift_info["count"], 1.0)) if drift_info["count"] > 0 else 0.0
        )
        update_signal = min(drift_info["updates"] / max(claim_count, 1), 1.0)

        why_now_score = max(0.0, min(1.0, 0.45 * drift_signal + 0.35 * contradiction_ratio + 0.20 * update_signal))
        underexplored_index = max(0.0, min(1.0, 0.50 * underexplored_signal + 0.30 * contradiction_ratio + 0.20 * drift_signal))

        priority = max(0.0, min(1.0, 0.50 * underexplored_index + 0.50 * why_now_score))

        supports_rows = [c for c in claims if str(c["effect_direction"]) == "supports"]
        if require_review_signoff:
            has_approved_support = any(str(c["claim_id"]) in approved_claim_ids for c in supports_rows)
            if not has_approved_support:
                continue

        cards.append(
            {
                "entity": entity,
                "outcome": outcome,
                "gap_type": "underexplored_mechanism_cluster",
                "underexplored_index": round(underexplored_index, 4),
                "why_now_score": round(why_now_score, 4),
                "priority_score": round(priority, 4),
                "rationale": (
                    "Signal appears scientifically relevant yet underexplored, with contradiction/drift patterns "
                    "that justify immediate targeted validation."
                ),
                "evidence_counts": {
                    "claims": claim_count,
                    "supports": supports,
                    "contradicts": contradicts,
                },
                "suggested_validation_experiments": [
                    "Run targeted replication in pre-specified patient subgroups.",
                    "Compare harmonized endpoint panels across cohorts to resolve contradiction structure.",
                ],
            }
        )

    cards.sort(key=lambda c: c["priority_score"], reverse=True)
    return cards[:limit]
