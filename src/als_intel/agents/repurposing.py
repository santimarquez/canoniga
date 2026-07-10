from __future__ import annotations

from collections import Counter

from als_intel.scoring import therapeutic_mcda_score


def build_repurposing_report(
    evidence_rows: list[dict[str, object]],
    support_map_rows: list[dict[str, object]],
    failure_atlas: dict[str, object],
) -> dict[str, object]:
    by_entity: dict[str, list[dict[str, object]]] = {}
    for row in evidence_rows:
        entity = str(row["entity"])
        by_entity.setdefault(entity, []).append(row)

    failures_by_entity: dict[str, int] = Counter()
    for entry in failure_atlas.get("entries", []):
        entity = str(entry.get("entity", ""))
        failures_by_entity[entity] += 1

    ranked: list[dict[str, object]] = []
    for row in support_map_rows:
        entity = str(row["entity"])
        entity_rows = by_entity.get(entity, [])
        if not entity_rows:
            continue

        avg_reliability = sum(float(r["reliability_score"]) for r in entity_rows) / max(len(entity_rows), 1)
        avg_source_reliability = sum(float(r["source_reliability_score"]) for r in entity_rows) / max(
            len(entity_rows), 1
        )
        human_ratio = sum(1 for r in entity_rows if str(r["model_system"]) == "human") / max(len(entity_rows), 1)
        interventional_ratio = sum(1 for r in entity_rows if str(r["study_type"]) == "interventional") / max(
            len(entity_rows), 1
        )
        peer_review_ratio = sum(1 for r in entity_rows if bool(r["peer_reviewed"])) / max(len(entity_rows), 1)
        known_cohort_ratio = sum(1 for r in entity_rows if str(r["cohort"]) != "unknown") / max(len(entity_rows), 1)

        outcome_counts = Counter(str(r["outcome"]) for r in entity_rows)
        endpoint_consistency = max(outcome_counts.values()) / max(len(entity_rows), 1)

        supports = int(row["supports"])
        contradicts = int(row["contradicts"])
        evidence_balance = supports / max(supports + contradicts, 1)
        failure_penalty = min(failures_by_entity.get(entity, 0) / 3.0, 1.0)

        biological_plausibility = (
            0.55 * evidence_balance
            + 0.25 * avg_reliability
            + 0.20 * interventional_ratio
        )
        evidence_strength = (
            0.40 * avg_reliability
            + 0.35 * avg_source_reliability
            + 0.25 * interventional_ratio
        )
        safety_profile = (
            0.45 * human_ratio
            + 0.30 * peer_review_ratio
            + 0.25 * (1.0 - failure_penalty)
        )
        clinical_feasibility = (
            0.35 * interventional_ratio
            + 0.35 * endpoint_consistency
            + 0.30 * known_cohort_ratio
        )
        mcda = therapeutic_mcda_score(
            biological_plausibility=biological_plausibility,
            evidence_strength=evidence_strength,
            safety_profile=safety_profile,
            clinical_feasibility=clinical_feasibility,
            prior_failure_penalty=failure_penalty,
        )
        score = float(mcda["mcda_score"])

        ranked.append(
            {
                "entity": entity,
                "outcome": row["outcome"],
                "repurposing_priority_score": score,
                "mcda_components": mcda,
                "evidence_snapshot": {
                    "supports": supports,
                    "contradicts": contradicts,
                    "avg_reliability": round(float(avg_reliability), 4),
                    "avg_source_reliability": round(float(avg_source_reliability), 4),
                    "human_evidence_ratio": round(float(human_ratio), 4),
                    "interventional_ratio": round(float(interventional_ratio), 4),
                    "endpoint_consistency": round(float(endpoint_consistency), 4),
                },
                "risk_adjustments": {
                    "failure_penalty": round(float(failure_penalty), 4),
                },
                "next_steps": [
                    "Evaluate target engagement biomarkers for the mechanism.",
                    "Prioritize candidates with established safety and CNS exposure evidence.",
                ],
            }
        )

    ranked.sort(key=lambda x: x["repurposing_priority_score"], reverse=True)
    return {
        "items": ranked,
        "count": len(ranked),
    }
