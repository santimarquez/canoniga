from __future__ import annotations

from als_intel.agents.guardrails import apply_causal_risk_guardrail


def _classify_statement(score: float) -> str:
    if score >= 0.75:
        return "fact"
    if score >= 0.5:
        return "hypothesis"
    return "conjecture"


def literature_review(
    evidence_rows: list[dict[str, object]],
    contradiction_density: dict[str, float] | None = None,
    require_review_signoff: bool = False,
    approved_claim_ids: set[str] | None = None,
) -> list[dict[str, object]]:
    """Create labeled statements with explicit confidence and provenance context."""
    contradiction_density = contradiction_density or {}
    approved_claim_ids = approved_claim_ids or set()
    reviews: list[dict[str, object]] = []
    for row in evidence_rows:
        claim_id = str(row["claim_id"])
        score = float(row["reliability_score"])
        base_label = _classify_statement(score)
        entity = str(row["entity"])
        density = float(contradiction_density.get(entity, 0.0))
        final_label, final_confidence, guardrail_reason = apply_causal_risk_guardrail(
            base_label,
            score,
            density,
        )

        withheld_by_signoff = False
        if require_review_signoff and final_label in {"fact", "hypothesis"} and claim_id not in approved_claim_ids:
            withheld_by_signoff = True
            final_label = "withheld_pending_review"

        reviews.append(
            {
                "claim_id": claim_id,
                "label": final_label,
                "confidence": final_confidence,
                "claim_text": row["claim_text"],
                "source_doi": row["source_doi"],
                "entity": entity,
                "outcome": row["outcome"],
                "source_reliability_score": float(row["source_reliability_score"]),
                "contradiction_density": density,
                "guardrail_applied": guardrail_reason is not None,
                "guardrail_reason": guardrail_reason,
                "withheld_by_review_signoff": withheld_by_signoff,
            }
        )
    return reviews
