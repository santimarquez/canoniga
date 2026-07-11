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


TERMINAL_STATUSES = {"terminated", "withdrawn", "suspended", "unknown status"}


def _is_structured_trial_failure(row: dict[str, object]) -> bool:
    if str(row.get("study_type")) != "interventional":
        return False
    provenance = row.get("extraction_provenance")
    if isinstance(provenance, dict):
        status = str(provenance.get("trial_status", "")).strip().lower()
        if status in TERMINAL_STATUSES:
            return True
        if str(provenance.get("termination_reason", "")).strip():
            return True
        endpoint_result = str(provenance.get("primary_endpoint_result", "")).lower()
        if endpoint_result and any(
            token in endpoint_result for token in ("no significant", "not significant", "failed to meet", "futility")
        ):
            return True
    if str(row.get("effect_direction")) == "contradicts":
        text = f"{row.get('claim_text', '')} {row.get('source_title', '')}".lower()
        return any(token in text for token in ("failed", "terminated", "withdrawn", "lack of efficacy"))
    return False


def _structured_root_cause(row: dict[str, object]) -> str:
    provenance = row.get("extraction_provenance")
    if isinstance(provenance, dict):
        reason = str(provenance.get("termination_reason", "")).lower()
        endpoint_result = str(provenance.get("primary_endpoint_result", "")).lower()
        if endpoint_result and any(
            token in endpoint_result for token in ("no significant", "not significant", "failed to meet", "futility")
        ):
            return "endpoint_sensitivity"
        if "efficacy" in reason or "futility" in reason:
            return "wrong_biology"
        if "enroll" in reason or "recruit" in reason:
            return "execution_retention"
        if "safety" in reason:
            return "wrong_cohort"
    return _infer_root_cause(row)


def build_failure_atlas(evidence_rows: list[dict[str, object]]) -> dict[str, object]:
    failures = [r for r in evidence_rows if _is_structured_trial_failure(r)]

    entries: list[dict[str, object]] = []
    counter: Counter[str] = Counter()
    structured_count = 0
    for row in failures:
        cause = _structured_root_cause(row)
        counter[cause] += 1
        provenance = row.get("extraction_provenance")
        if isinstance(provenance, dict) and (
            provenance.get("trial_status") or provenance.get("termination_reason")
        ):
            structured_count += 1
        entries.append(
            {
                "claim_id": row["claim_id"],
                "entity": row["entity"],
                "outcome": row["outcome"],
                "source_doi": row["source_doi"],
                "root_cause": cause,
                "root_cause_rationale": ROOT_CAUSES[cause],
                "reliability_score": row.get("reliability_score"),
                "trial_status": (
                    str(provenance.get("trial_status", ""))
                    if isinstance(provenance, dict)
                    else ""
                ),
                "termination_reason": (
                    str(provenance.get("termination_reason", ""))
                    if isinstance(provenance, dict)
                    else ""
                ),
                "primary_endpoint": (
                    str(provenance.get("primary_endpoint", ""))
                    if isinstance(provenance, dict)
                    else ""
                ),
                "primary_endpoint_result": (
                    str(provenance.get("primary_endpoint_result", ""))
                    if isinstance(provenance, dict)
                    else ""
                ),
                "adverse_events_summary": (
                    str(provenance.get("adverse_events_summary", ""))
                    if isinstance(provenance, dict)
                    else ""
                ),
                "phase": (
                    str(provenance.get("phase", ""))
                    if isinstance(provenance, dict)
                    else ""
                ),
                "enrollment": (
                    provenance.get("enrollment")
                    if isinstance(provenance, dict)
                    else None
                ),
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
        "structured_trial_failures": structured_count,
        "root_cause_distribution": dict(counter),
        "entries": entries,
        "lessons": lessons,
    }
