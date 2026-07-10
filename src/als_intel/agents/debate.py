from __future__ import annotations


def build_debate_report(
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
) -> dict[str, object]:
    by_claim = {str(r["claim_id"]): r for r in evidence_rows}

    rounds: list[dict[str, object]] = []
    for idx, contradiction in enumerate(contradiction_rows, start=1):
        claim_a = str(contradiction["claim_a"])
        claim_b = str(contradiction["claim_b"])
        row_a = by_claim.get(claim_a)
        row_b = by_claim.get(claim_b)
        if row_a is None or row_b is None:
            continue

        challenger = claim_a if float(row_a["reliability_score"]) < float(row_b["reliability_score"]) else claim_b
        defender = claim_b if challenger == claim_a else claim_a
        challenger_row = by_claim[challenger]
        defender_row = by_claim[defender]

        rounds.append(
            {
                "round": idx,
                "topic_entity": contradiction["entity"],
                "challenge": {
                    "agent": "skeptic",
                    "claim_id": challenger,
                    "argument": (
                        f"Competing evidence challenges interpretation for {contradiction['entity']} "
                        f"({contradiction['contradiction_type']})."
                    ),
                    "evidence_strength": float(challenger_row["reliability_score"]),
                },
                "rebuttal": {
                    "agent": "literature",
                    "claim_id": defender,
                    "argument": (
                        "Primary claim remains viable but requires stratified validation and endpoint harmonization."
                    ),
                    "evidence_strength": float(defender_row["reliability_score"]),
                },
                "provisional_consensus": (
                    "contested"
                    if abs(float(row_a["reliability_score"]) - float(row_b["reliability_score"])) < 0.1
                    else "leaning_support"
                ),
            }
        )

    return {
        "round_count": len(rounds),
        "rounds": rounds,
        "protocol": {
            "version": "v1",
            "steps": [
                "skeptic challenge",
                "literature rebuttal",
                "provisional consensus",
            ],
        },
    }
