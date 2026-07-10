from __future__ import annotations

from collections import defaultdict

from als_intel.agents.causal_dashboard import build_causal_risk_dashboard


def _trial_feasibility(rows: list[dict[str, object]]) -> tuple[float, list[str]]:
    total = max(len(rows), 1)
    interventional = sum(1 for r in rows if r.get("study_type") == "interventional")
    human = sum(1 for r in rows if r.get("model_system") == "human")

    outcomes: dict[str, int] = defaultdict(int)
    known_cohort = 0
    for r in rows:
        outcomes[str(r.get("outcome", "unknown"))] += 1
        if str(r.get("cohort", "unknown")) != "unknown":
            known_cohort += 1

    endpoint_consistency = max(outcomes.values()) / total if outcomes else 0.0
    interventional_ratio = interventional / total
    human_ratio = human / total
    known_cohort_ratio = known_cohort / total

    score = (
        0.35 * interventional_ratio
        + 0.25 * human_ratio
        + 0.25 * endpoint_consistency
        + 0.15 * known_cohort_ratio
    )
    score = round(max(0.0, min(score, 1.0)), 4)

    notes: list[str] = []
    if interventional_ratio < 0.3:
        notes.append("Low interventional evidence coverage.")
    if human_ratio < 0.5:
        notes.append("Limited human model evidence.")
    if endpoint_consistency < 0.6:
        notes.append("Endpoint definitions are heterogeneous.")
    if known_cohort_ratio < 0.5:
        notes.append("Cohort metadata is sparse.")
    if not notes:
        notes.append("Trial compatibility profile is acceptable for early validation design.")

    return score, notes


def _causal_risk(supports: list[dict[str, object]], contradicts: list[dict[str, object]]) -> tuple[float, dict[str, int]]:
    weights = {
        "interventional": 1.0,
        "genetic": 0.9,
        "mechanistic": 0.75,
        "observational": 0.55,
        "negative": 0.2,
    }
    profile = {
        "interventional": 0,
        "genetic": 0,
        "mechanistic": 0,
        "observational": 0,
        "negative": 0,
    }

    for row in supports + contradicts:
        ctype = str(row.get("causal_evidence_type", "observational"))
        if ctype not in profile:
            ctype = "observational"
        profile[ctype] += 1

    support_strength = 0.0
    if supports:
        support_strength = sum(
            weights.get(str(r.get("causal_evidence_type", "observational")), 0.55) for r in supports
        ) / len(supports)

    contradiction_pressure = len(contradicts) / max(len(supports) + len(contradicts), 1)
    risk = 0.65 * (1.0 - support_strength) + 0.35 * contradiction_pressure
    return round(max(0.0, min(risk, 1.0)), 4), profile


def build_hypothesis_queue(
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
    limit: int = 10,
    require_review_signoff: bool = False,
    approved_claim_ids: set[str] | None = None,
    enforce_causal_gate: bool = False,
    causal_promotion_overrides: set[str] | None = None,
    promotion_risk_threshold: float = 0.5,
    minimum_strong_support_ratio: float = 0.3,
) -> list[dict[str, object]]:
    approved_claim_ids = approved_claim_ids or set()
    causal_promotion_overrides = causal_promotion_overrides or set()
    by_entity: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in evidence_rows:
        by_entity[str(row["entity"])].append(row)

    blocked_entities: set[str] = set()
    overridden_blocked_entities: set[str] = set()
    if enforce_causal_gate and by_entity:
        dashboard = build_causal_risk_dashboard(
            evidence_rows=evidence_rows,
            contradiction_rows=contradiction_rows,
            limit=max(len(by_entity), limit),
            promotion_risk_threshold=promotion_risk_threshold,
            minimum_strong_support_ratio=minimum_strong_support_ratio,
        )
        for item in dashboard["items"]:
            entity_name = str(item["entity"])
            if bool(item["blocked_from_promotion"]):
                if entity_name in causal_promotion_overrides:
                    overridden_blocked_entities.add(entity_name)
                else:
                    blocked_entities.add(entity_name)

    contradiction_by_entity: dict[str, int] = defaultdict(int)
    for c in contradiction_rows:
        contradiction_by_entity[str(c["entity"])] += 1

    cards: list[dict[str, object]] = []
    for entity, rows in by_entity.items():
        if entity in blocked_entities:
            continue

        supports = [r for r in rows if r["effect_direction"] == "supports"]
        contradicts = [r for r in rows if r["effect_direction"] == "contradicts"]
        if not supports and not contradicts:
            continue

        if require_review_signoff:
            has_approved_support = any(str(r["claim_id"]) in approved_claim_ids for r in supports)
            if not has_approved_support:
                continue

        avg_support = sum(float(r["reliability_score"]) for r in supports) / max(len(supports), 1)
        avg_contradiction = sum(float(r["reliability_score"]) for r in contradicts) / max(len(contradicts), 1)
        contradiction_density = contradiction_by_entity[entity] / max(len(rows), 1)
        trial_feasibility_score, trial_notes = _trial_feasibility(rows)
        causal_risk_score, causal_profile = _causal_risk(supports, contradicts)

        confidence = max(0.05, min(0.95, avg_support - 0.35 * contradiction_density))
        false_inference_risk = max(0.05, min(0.95, 0.2 + 0.5 * contradiction_density + 0.2 * avg_contradiction))
        priority_score = round(
            (
                0.35 * contradiction_density
                + 0.25 * avg_support
                + 0.15 * (1.0 - false_inference_risk)
                + 0.25 * trial_feasibility_score
            ),
            4,
        )

        cards.append(
            {
                "entity": entity,
                "hypothesis": f"Perturbing {entity} may influence ALS progression and should be tested with stratified cohorts.",
                "biological_rationale": "Multiple records implicate this mechanism with mixed directionality, suggesting unresolved context-specific effects.",
                "supporting_evidence": [
                    {
                        "claim_id": r["claim_id"],
                        "source_doi": r["source_doi"],
                        "reliability_score": r["reliability_score"],
                    }
                    for r in supports[:5]
                ],
                "contradictory_evidence": [
                    {
                        "claim_id": r["claim_id"],
                        "source_doi": r["source_doi"],
                        "reliability_score": r["reliability_score"],
                    }
                    for r in contradicts[:5]
                ],
                "confidence_score": round(confidence, 4),
                "false_inference_risk": round(false_inference_risk, 4),
                "causal_risk_score": causal_risk_score,
                "causal_evidence_profile": causal_profile,
                "causal_gate_override_applied": entity in overridden_blocked_entities,
                "trial_feasibility_score": trial_feasibility_score,
                "trial_compatibility_notes": trial_notes,
                "priority_score": priority_score,
                "suggested_validation_experiments": [
                    "Run subtype-stratified observational replication with harmonized endpoints.",
                    "Execute perturbation study with predefined biomarker and progression endpoints.",
                ],
            }
        )

    cards.sort(key=lambda c: c["priority_score"], reverse=True)
    return cards[:limit]
