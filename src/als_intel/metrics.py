from __future__ import annotations


def consensus_stability_score(timeline: list[dict[str, object]]) -> float:
    """Estimate stability from consensus state transitions across timeline events."""
    if len(timeline) <= 1:
        return 1.0

    ordered = list(reversed(timeline))
    transitions = 0
    prev_state = str(ordered[0]["consensus_state"])
    for item in ordered[1:]:
        state = str(item["consensus_state"])
        if state != prev_state:
            transitions += 1
        prev_state = state

    max_transitions = max(len(ordered) - 1, 1)
    stability = 1.0 - (transitions / max_transitions)
    return round(max(0.0, min(stability, 1.0)), 4)


def debate_disagreement_index(debate_report: dict[str, object]) -> float:
    rounds = debate_report.get("rounds", [])
    if not isinstance(rounds, list) or not rounds:
        return 0.0

    contested = sum(1 for r in rounds if r.get("provisional_consensus") == "contested")
    score = contested / len(rounds)
    return round(max(0.0, min(score, 1.0)), 4)


def failure_pattern_recurrence_score(failure_atlas: dict[str, object]) -> float:
    distribution = failure_atlas.get("root_cause_distribution", {})
    if not isinstance(distribution, dict) or not distribution:
        return 0.0

    counts = [int(v) for v in distribution.values() if int(v) > 0]
    total = sum(counts)
    if total == 0:
        return 0.0

    top = max(counts)
    recurrence = top / total
    return round(max(0.0, min(recurrence, 1.0)), 4)


def compute_quality_metrics(
    consensus_timeline_rows: list[dict[str, object]],
    debate_report: dict[str, object],
    failure_atlas: dict[str, object],
) -> dict[str, float]:
    return {
        "consensus_stability_score": consensus_stability_score(consensus_timeline_rows),
        "debate_disagreement_index": debate_disagreement_index(debate_report),
        "failure_pattern_recurrence_score": failure_pattern_recurrence_score(failure_atlas),
    }
