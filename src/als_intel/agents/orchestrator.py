from __future__ import annotations

from als_intel.agents.guardrails import contradiction_density_by_entity
from als_intel.agents.literature import literature_review
from als_intel.agents.skeptic import skeptic_review
from als_intel.agents.systems_biology import build_systems_biology_report


def build_agent_report(
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
    require_review_signoff: bool = False,
    approved_claim_ids: set[str] | None = None,
    support_map_rows: list[dict[str, object]] | None = None,
    graph_neighbor_rows: list[dict[str, object]] | None = None,
    systems_biology_limit: int = 5,
) -> dict[str, object]:
    density = contradiction_density_by_entity(evidence_rows, contradiction_rows)
    literature = literature_review(
        evidence_rows,
        density,
        require_review_signoff=require_review_signoff,
        approved_claim_ids=approved_claim_ids,
    )
    skeptic = skeptic_review(contradiction_rows)

    systems_biology: dict[str, object] | None = None
    if support_map_rows:
        systems_biology = build_systems_biology_report(
            evidence_rows=evidence_rows,
            support_map_rows=support_map_rows,
            graph_neighbor_rows=graph_neighbor_rows,
            limit=systems_biology_limit,
        )

    report: dict[str, object] = {
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
    if systems_biology is not None:
        report["systems_biology_agent"] = systems_biology
    return report
