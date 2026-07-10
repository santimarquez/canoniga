from __future__ import annotations

import json
from pathlib import Path

from als_intel.webui import _apply_response_guardrails, _build_synthesis


def _load_queries() -> list[dict[str, str]]:
    fixture_path = Path(__file__).parent / "fixtures" / "regression_queries.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_canonical_regression_query_set_has_expected_size_and_shape() -> None:
    queries = _load_queries()

    assert 20 <= len(queries) <= 30
    ids = [str(item.get("id", "")).strip() for item in queries]
    prompts = [str(item.get("prompt", "")).strip() for item in queries]

    assert all(ids)
    assert all(prompts)
    assert len(ids) == len(set(ids))
    assert len(prompts) == len(set(prompts))


def test_regression_queries_pass_minimum_synthesis_guardrails() -> None:
    queries = _load_queries()
    evidence_rows = [
        {"claim_id": "C1", "reliability_score": 0.9},
        {"claim_id": "C2", "reliability_score": 0.8},
    ]
    contradiction_rows = [{"claim_a": "C1", "claim_b": "C2"}]

    for item in queries:
        prompt = str(item["prompt"])
        answer = (
            "Direct answer for: " + prompt + "\n\n"
            "Supporting references: claim_id=C1 and claim_id=C2.\n\n"
            "Contradictions remain due to endpoint heterogeneity.\n\n"
            "1. Validate in a stratified follow-up cohort."
        )
        synthesis = _build_synthesis(
            answer=answer,
            evidence_rows=evidence_rows,
            contradiction_rows=contradiction_rows,
        )
        guarded, _ = _apply_response_guardrails(
            answer=answer,
            synthesis=synthesis,
            evidence_rows=evidence_rows,
            contradiction_rows=contradiction_rows,
        )

        assert str(guarded.get("direct_answer", "")).strip()
        assert isinstance(guarded.get("supporting_claim_ids"), list)
        assert len(guarded.get("supporting_claim_ids", [])) >= 1
        assert str(guarded.get("contradictions_summary", "")).strip()
        assert str(guarded.get("next_validation_step", "")).strip()
