from __future__ import annotations

from als_intel.agents.guardrails import contradiction_density_by_entity
from als_intel.agents.literature import literature_review
from als_intel.agents.skeptic import skeptic_review


def build_agent_report(
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
    require_review_signoff: bool = False,
    approved_claim_ids: set[str] | None = None,
) -> dict[str, object]:
    density = contradiction_density_by_entity(evidence_rows, contradiction_rows)
    literature = literature_review(
        evidence_rows,
        density,
        require_review_signoff=require_review_signoff,
        approved_claim_ids=approved_claim_ids,
    )
    skeptic = skeptic_review(contradiction_rows)

    return {
        "literature_agent": {
            "items": literature,
            "counts": {
                "fact": sum(1 for i in literature if i["label"] == "fact"),
                "hypothesis": sum(1 for i in literature if i["label"] == "hypothesis"),
                "conjecture": sum(1 for i in literature if i["label"] == "conjecture"),
                "withheld_pending_review": sum(1 for i in literature if i["label"] == "withheld_pending_review"),
            },
            "guardrail_blocked_facts": sum(1 for i in literature if i["guardrail_applied"]),
            "withheld_high_impact": sum(1 for i in literature if i["withheld_by_review_signoff"]),
        },
        "skeptic_agent": {
            "alerts": skeptic,
            "high_severity": sum(1 for i in skeptic if i["severity"] == "high"),
        },
        "entity_contradiction_density": density,
    }
