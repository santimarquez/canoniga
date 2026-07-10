from __future__ import annotations


def skeptic_review(contradictions: list[dict[str, object]]) -> list[dict[str, object]]:
    """Generate falsification-focused alerts from contradiction inventory."""
    alerts: list[dict[str, object]] = []
    for item in contradictions:
        ctype = str(item["contradiction_type"])
        severity = "medium"
        if ctype == "direction_conflict":
            severity = "high"
        if ctype == "endpoint_mismatch":
            severity = "medium"
        if ctype == "cohort_mismatch":
            severity = "medium"
        if ctype == "model_system_mismatch":
            severity = "low"

        alerts.append(
            {
                "pair": f"{item['claim_a']} vs {item['claim_b']}",
                "entity": item["entity"],
                "contradiction_type": ctype,
                "severity": severity,
                "recommended_test": item["follow_up_experiment"],
            }
        )
    return alerts
