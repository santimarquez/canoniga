from __future__ import annotations

from collections import Counter


ROOT_CAUSES = {
    "wrong_biology": "Target mechanism likely not disease-driving in tested context.",
    "wrong_cohort": "Population selection likely mismatched disease subtype or stage.",
    "wrong_timing": "Intervention timing may be too late or biologically mistimed.",
    "endpoint_sensitivity": "Chosen endpoint may be insufficiently sensitive to biological change.",
    "underpowered_design": "Sample size appears insufficient for expected effect size.",
    "execution_retention": "Operational/adherence/retention factors may mask effect.",
}


def _infer_root_cause(row: dict[str, object]) -> str:
    text = f"{row.get('claim_text', '')} {row.get('source_title', '')}".lower()
    sample = int(row.get("sample_size", 0))
    endpoint_validity = float(row.get("endpoint_validity", 0.0))
    cohort = str(row.get("cohort", "unknown"))

    if sample > 0 and sample < 60:
        return "underpowered_design"
    if endpoint_validity < 0.55:
        return "endpoint_sensitivity"
    if "late" in text or "advanced" in text:
        return "wrong_timing"
    if cohort == "unknown" or "mixed" in cohort:
        return "wrong_cohort"
    if "dropout" in text or "adherence" in text or "retention" in text:
        return "execution_retention"
    return "wrong_biology"


def build_failure_atlas(evidence_rows: list[dict[str, object]]) -> dict[str, object]:
    failures = [
        r
        for r in evidence_rows
        if str(r.get("effect_direction")) == "contradicts"
        and str(r.get("study_type")) in {"interventional", "observational"}
    ]

    entries: list[dict[str, object]] = []
    counter: Counter[str] = Counter()
    for row in failures:
        cause = _infer_root_cause(row)
        counter[cause] += 1
        entries.append(
            {
                "claim_id": row["claim_id"],
                "entity": row["entity"],
                "outcome": row["outcome"],
                "source_doi": row["source_doi"],
                "root_cause": cause,
                "root_cause_rationale": ROOT_CAUSES[cause],
                "reliability_score": row["reliability_score"],
            }
        )

    lessons = [
        {
            "root_cause": key,
            "count": count,
            "recommended_guardrail": ROOT_CAUSES[key],
        }
        for key, count in counter.most_common()
    ]

    return {
        "total_failed_or_negative_records": len(failures),
        "root_cause_distribution": dict(counter),
        "entries": entries,
        "lessons": lessons,
    }
