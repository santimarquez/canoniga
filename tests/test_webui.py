from __future__ import annotations

from als_intel.brand import LOGO_PRIMARY_COLOR, favicon_link_tag, render_inline_logo
from als_intel.webui import (
    LOGIN_TEMPLATE,
    PAGE_TEMPLATE,
    _apply_evidence_filters,
    _apply_response_guardrails,
    _build_chat_prompt,
    _build_synthesis,
    _rank_cited_evidence_rows,
    _search_evidence_rows,
)


def test_build_chat_prompt_uses_latest_user_message_and_context() -> None:
    messages = [
        {"role": "system", "content": "You are helpful"},
        {"role": "user", "content": "What is the claim?"},
        {"role": "assistant", "content": "Draft answer"},
        {"role": "user", "content": "What is the uncertainty?"},
    ]
    evidence_rows = [
        {
            "claim_id": "C1",
            "entity": "entity-a",
            "outcome": "outcome-a",
            "effect_direction": "positive",
            "study_type": "cohort",
            "causal_evidence_type": "observational",
            "reliability_score": 0.7,
            "source_doi": "10.1/example",
        }
    ]

    prompt = _build_chat_prompt(messages, evidence_rows, context_limit=5, language="en")

    assert "What is the uncertainty?" in prompt
    assert "claim_id=C1" in prompt
    assert "Conversation history:" in prompt


def test_apply_evidence_filters_respects_min_reliability_and_type() -> None:
    rows = [
        {
            "claim_id": "C1",
            "causal_evidence_type": "observational",
            "reliability_score": 0.8,
            "year": 2022,
        },
        {
            "claim_id": "C2",
            "causal_evidence_type": "interventional",
            "reliability_score": 0.5,
            "year": 2018,
        },
    ]
    filtered = _apply_evidence_filters(
        rows,
        {
            "evidence_types": ["observational"],
            "min_reliability": 0.7,
            "date_window": "all",
        },
    )
    assert [row["claim_id"] for row in filtered] == ["C1"]


def test_search_evidence_rows_matches_claim_id_and_doi() -> None:
    rows = [
        {
            "claim_id": "C1",
            "claim_text": "Metformin improves insulin sensitivity",
            "entity": "metformin",
            "outcome": "insulin resistance",
            "source_doi": "10.1000/abc",
        },
        {
            "claim_id": "C2",
            "claim_text": "No effect observed",
            "entity": "metformin",
            "outcome": "glucose",
            "source_doi": "10.1000/xyz",
        },
    ]
    assert [r["claim_id"] for r in _search_evidence_rows(rows, "C1")] == ["C1"]
    assert [r["claim_id"] for r in _search_evidence_rows(rows, "xyz")] == ["C2"]


def test_build_synthesis_only_includes_answer_grounded_sections() -> None:
    evidence_rows = [
        {"claim_id": "C1"},
        {"claim_id": "C2"},
    ]
    contradictions = [
        {
            "claim_a": "C1",
            "claim_b": "C9",
            "contradiction_type": "direction_conflict",
        }
    ]
    synthesis = _build_synthesis(
        answer=(
            "**Direct Answer** Text.\n\n"
            "**Supporting Evidence References**\n"
            "1. claim_id=C1\n"
            "2. claim_id=C9\n\n"
            "**Contradictions or Uncertainty**\n"
            "Potential endpoint mismatch.\n\n"
            "**Suggested Validation Next Steps**\n"
            "Run a confirmatory trial."
        ),
        evidence_rows=evidence_rows,
        contradiction_rows=contradictions,
    )
    assert "Direct Answer" in synthesis["direct_answer"]
    assert synthesis["supporting_claim_ids"] == ["C1"]
    assert "Potential endpoint mismatch." in str(synthesis["contradictions_summary"])
    assert synthesis["next_validation_step"] == "Run a confirmatory trial."


def test_apply_evidence_filters_highlight_contradictions_promotes_contradictory_rows() -> None:
    rows = [
        {
            "claim_id": "C1",
            "causal_evidence_type": "observational",
            "effect_direction": "supports",
            "reliability_score": 0.95,
            "year": 2023,
        },
        {
            "claim_id": "C2",
            "causal_evidence_type": "observational",
            "effect_direction": "contradicts",
            "reliability_score": 0.50,
            "year": 2023,
        },
    ]

    filtered = _apply_evidence_filters(
        rows,
        {
            "evidence_types": ["observational"],
            "min_reliability": 0.0,
            "date_window": "all",
            "highlight_contradictions": True,
        },
    )

    assert [row["claim_id"] for row in filtered] == ["C2", "C1"]


def test_apply_evidence_filters_excludes_missing_reliability_unless_min_zero() -> None:
    rows = [
        {
            "claim_id": "C1",
            "causal_evidence_type": "observational",
            "reliability_score": 0.8,
            "year": 2024,
        },
        {
            "claim_id": "C2",
            "causal_evidence_type": "observational",
            "year": 2024,
        },
    ]

    filtered_non_zero = _apply_evidence_filters(
        rows,
        {
            "evidence_types": ["observational"],
            "min_reliability": 0.5,
            "date_window": "all",
        },
    )
    assert [row["claim_id"] for row in filtered_non_zero] == ["C1"]

    filtered_zero = _apply_evidence_filters(
        rows,
        {
            "evidence_types": ["observational"],
            "min_reliability": 0.0,
            "date_window": "all",
        },
    )
    assert [row["claim_id"] for row in filtered_zero] == ["C1", "C2"]


def test_page_template_includes_db_provenance_fields() -> None:
    template_text = PAGE_TEMPLATE.template
    assert "API endpoint:" in template_text
    assert "Query used:" in template_text
    assert "Source version:" in template_text
    assert "Source license:" in template_text
    assert "Extracted at:" in template_text


def test_apply_response_guardrails_fills_required_fields_when_missing() -> None:
    evidence_rows = [
        {"claim_id": "C1", "reliability_score": 0.9},
        {"claim_id": "C2", "reliability_score": 0.7},
    ]
    contradiction_rows = [{"claim_a": "C1", "claim_b": "C2"}]

    guarded, flags = _apply_response_guardrails(
        answer="Interim answer with no explicit structure.",
        synthesis={"direct_answer": "", "mentioned_claim_ids": [], "supporting_claim_ids": []},
        evidence_rows=evidence_rows,
        contradiction_rows=contradiction_rows,
        language="en",
    )

    assert guarded["direct_answer"] == "Interim answer with no explicit structure."
    assert guarded["mentioned_claim_ids"] == ["C1", "C2"]
    assert guarded["supporting_claim_ids"] == ["C1", "C2"]
    assert isinstance(guarded.get("contradictions_summary"), str)
    assert isinstance(guarded.get("next_validation_step"), str)
    assert "mentioned_claim_ids_filled" in flags
    assert "supporting_claim_ids_filled" in flags
    assert "contradictions_summary_filled" in flags


def test_rank_cited_evidence_rows_prioritizes_reliability_and_recency() -> None:
    rows = [
        {
            "claim_id": "C_OLD_LOW",
            "reliability_score": 0.3,
            "year": 2005,
            "study_type": "observational",
        },
        {
            "claim_id": "C_NEW_HIGH",
            "reliability_score": 0.95,
            "year": 2024,
            "study_type": "interventional",
        },
        {
            "claim_id": "C_MID",
            "reliability_score": 0.7,
            "year": 2021,
            "study_type": "meta_analysis",
        },
    ]

    ranked = _rank_cited_evidence_rows(rows)

    assert [row["claim_id"] for row in ranked][:2] == ["C_NEW_HIGH", "C_MID"]


def test_login_template_includes_magic_link_confirmation_panel() -> None:
    html = LOGIN_TEMPLATE.substitute(
        auth_enabled="true",
        current_year="2026",
        logo_html=render_inline_logo(height_px=48),
        favicon_tag=favicon_link_tag(),
    )
    assert "<svg" in html
    assert LOGO_PRIMARY_COLOR in html
    assert 'id="loginRequestPanel"' in html
    assert 'id="loginResultPanel"' in html
    assert "Check your email" in html
    assert "showLoginResultPanel" in html
