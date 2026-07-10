from __future__ import annotations

from collections import Counter


def build_clinical_trial_analysis(
    evidence_rows: list[dict[str, object]],
    support_map_rows: list[dict[str, object]],
    failure_atlas: dict[str, object],
) -> dict[str, object]:
    by_entity: dict[str, list[dict[str, object]]] = {}
    for row in evidence_rows:
        entity = str(row["entity"])
        by_entity.setdefault(entity, []).append(row)

    failures_by_entity: dict[str, Counter[str]] = {}
    for entry in failure_atlas.get("entries", []):
        entity = str(entry.get("entity", ""))
        cause = str(entry.get("root_cause", "wrong_biology"))
        failures_by_entity.setdefault(entity, Counter())
        failures_by_entity[entity][cause] += 1

    analyses: list[dict[str, object]] = []
    for row in support_map_rows:
        entity = str(row["entity"])
        entity_rows = by_entity.get(entity, [])
        if not entity_rows:
            continue

        interventional_ratio = (
            sum(1 for r in entity_rows if str(r["study_type"]) == "interventional") / max(len(entity_rows), 1)
        )
        known_cohort_ratio = (
            sum(1 for r in entity_rows if str(r["cohort"]) != "unknown") / max(len(entity_rows), 1)
        )

        outcome_counts = Counter(str(r["outcome"]) for r in entity_rows)
        endpoint_consistency = max(outcome_counts.values()) / max(len(entity_rows), 1)
        contradiction_pressure = int(row["contradicts"]) / max(int(row["supports"]) + int(row["contradicts"]), 1)

        feasibility = (
            0.30 * interventional_ratio
            + 0.25 * known_cohort_ratio
            + 0.20 * endpoint_consistency
            + 0.25 * (1.0 - contradiction_pressure)
        )
        feasibility = round(max(0.0, min(feasibility, 1.0)), 4)

        failure_counter = failures_by_entity.get(entity, Counter())
        major_failure_modes = [k for k, _ in failure_counter.most_common(3)]

        analyses.append(
            {
                "entity": entity,
                "outcome": row["outcome"],
                "supports": int(row["supports"]),
                "contradicts": int(row["contradicts"]),
                "trial_feasibility_score": feasibility,
                "key_risks": {
                    "contradiction_pressure": round(float(contradiction_pressure), 4),
                    "major_failure_modes": major_failure_modes,
                },
                "recommended_trial_design": [
                    "Use stratified cohorts with predefined progression endpoints.",
                    "Pre-register subgroup analyses and harmonize endpoint definitions.",
                ],
            }
        )

    analyses.sort(key=lambda x: x["trial_feasibility_score"], reverse=True)
    return {
        "items": analyses,
        "count": len(analyses),
    }
