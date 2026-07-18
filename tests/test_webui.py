from __future__ import annotations

import importlib
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from als_intel.webui import (
    _apply_evidence_filters,
    _apply_response_guardrails,
    _build_chat_prompt,
    _build_synthesis,
    _governance_doc_body,
    _prioritize_evidence_rows_for_question,
    _rank_cited_evidence_rows,
    _resolve_chat_candidate_limit,
    _search_evidence_rows,
)
from als_intel.static_frontend import serve_repo_asset, spa_available, serve_spa_or_static


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

    prompt, prioritized = _build_chat_prompt(messages, evidence_rows, context_limit=5, language="en")

    assert "What is the uncertainty?" in prompt
    assert "claim_id=C1" in prompt
    assert "Conversation history:" in prompt
    assert prioritized[0]["claim_id"] == "C1"


def test_resolve_chat_candidate_limit_uses_quality_preserving_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALS_CHAT_EVIDENCE_MAX_ROWS", raising=False)
    assert _resolve_chat_candidate_limit({}, context_limit=20) == 200
    assert _resolve_chat_candidate_limit({}, context_limit=50) == 500
    assert _resolve_chat_candidate_limit({"evidence_max_rows": 120}, context_limit=20) == 120
    monkeypatch.setenv("ALS_CHAT_EVIDENCE_MAX_ROWS", "0")
    assert _resolve_chat_candidate_limit({}, context_limit=20) == 200


def test_lean_filter_and_hydrate_preserve_prompt_evidence(pg_dsn: str) -> None:
    from als_intel.llm import build_grounded_prompt
    from als_intel.models import EvidenceRecord
    from als_intel.store import EvidenceStore

    store = EvidenceStore(pg_dsn)
    store.init_db()
    for idx in range(5):
        store.upsert_evidence(
            EvidenceRecord(
                claim_id=f"C{idx}",
                claim_text=f"long claim text {idx} " * 20,
                disease="ALS",
                entity=f"entity-{idx}",
                relation="modulates",
                outcome="survival",
                effect_direction="supports" if idx % 2 == 0 else "contradicts",
                study_type="observational",
                sample_size=10,
                endpoint_validity=0.5,
                replication_count=0,
                peer_reviewed=True,
                year=2024,
                source_title="title",
                source_doi=f"10.1/c{idx}",
            ),
            score_breakdown={
                "study": 0.1,
                "sample": 0.1,
                "replication": 0.1,
                "peer_review": 0.1,
                "endpoint": 0.1,
                "source": 0.1,
                "extraction": 0.1,
                "total": 0.5 + idx * 0.05,
            },
            source_score=0.5,
        )

    filters = {"min_reliability": 0.0, "evidence_types": [], "date_window": "all"}
    full_rows = store.filter_evidence(filters=filters, limit=200, lean=False)
    lean_rows = store.filter_evidence(filters=filters, limit=200, lean=True)
    assert [row["claim_id"] for row in lean_rows] == [row["claim_id"] for row in full_rows]
    assert all(not str(row.get("claim_text", "")).strip() for row in lean_rows)

    question = "What evidence matters?"
    prompt_full = build_grounded_prompt(question, full_rows, context_limit=3)
    prompt_lean = build_grounded_prompt(question, lean_rows, context_limit=3)
    assert prompt_full == prompt_lean

    hydrated = store.get_evidence_by_ids(["C4", "C2"])
    assert [row["claim_id"] for row in hydrated] == ["C4", "C2"]
    assert all(str(row.get("claim_text", "")).strip() for row in hydrated)


def test_prioritize_evidence_rows_for_question_puts_mentioned_ids_first() -> None:
    rows = [
        {"claim_id": "C_LOW", "reliability_score": 0.9},
        {"claim_id": "CTGOV_NCT00561366", "reliability_score": 0.4},
        {"claim_id": "PUBMED_39886777", "reliability_score": 0.5},
    ]
    prioritized = _prioritize_evidence_rows_for_question(
        rows,
        "Among cited claims (CTGOV_NCT00561366 and PUBMED_39886777) about sod1?",
    )
    assert [row["claim_id"] for row in prioritized[:2]] == [
        "CTGOV_NCT00561366",
        "PUBMED_39886777",
    ]


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
            "source_doi": "10.1/example",
        },
        {
            "claim_id": "C2",
            "claim_text": "Other claim",
            "entity": "other",
            "outcome": "other",
            "source_doi": "10.2/other",
        },
    ]
    matches = _search_evidence_rows(rows, "C1")
    assert [row["claim_id"] for row in matches] == ["C1"]
    matches_doi = _search_evidence_rows(rows, "10.2/other")
    assert [row["claim_id"] for row in matches_doi] == ["C2"]


def test_build_synthesis_uses_only_grounded_sections() -> None:
    synthesis = _build_synthesis(
        answer=(
            "## Direct Answer\n"
            "Concise answer mentioning claim_id=C1\n\n"
            "## Contradictions or Uncertainty\n"
            "None noted"
        ),
        evidence_rows=[
            {
                "claim_id": "C1",
                "claim_text": "Claim",
                "reliability_score": 0.8,
                "source_doi": "10.1/x",
            }
        ],
        contradiction_rows=[],
    )
    assert synthesis["direct_answer"] == "Concise answer mentioning claim_id=C1"
    assert "C1" in synthesis.get("mentioned_claim_ids", [])


def test_apply_response_guardrails_fills_missing_claim_ids() -> None:
    synthesis = {
        "direct_answer": "Draft",
        "mentioned_claim_ids": [],
        "supporting_claim_ids": [],
        "contradictions_summary": "",
        "next_validation_step": "",
    }
    guarded, flags = _apply_response_guardrails(
        answer="Draft",
        synthesis=synthesis,
        evidence_rows=[
            {
                "claim_id": "C9",
                "claim_text": "Claim",
                "reliability_score": 0.7,
                "source_doi": "10.9/x",
            }
        ],
        contradiction_rows=[],
        language="en",
    )
    assert guarded["mentioned_claim_ids"] == ["C9"]
    assert "mentioned_claim_ids_filled" in flags
    assert "executable_follow_up_query" not in guarded


def test_build_synthesis_extracts_executable_follow_up_query() -> None:
    synthesis = _build_synthesis(
        answer=(
            "## Direct Answer\n"
            "Answer with C1\n\n"
            "## Executable follow-up query\n"
            "Among cited claims about SOD1, do cohorts disagree on survival?\n"
        ),
        evidence_rows=[
            {
                "claim_id": "C1",
                "claim_text": "Claim",
                "reliability_score": 0.8,
                "source_doi": "10.1/x",
            }
        ],
        contradiction_rows=[],
    )
    assert "Among cited claims about SOD1" in str(synthesis.get("executable_follow_up_query", ""))


def test_apply_response_guardrails_prefers_llm_executable_query() -> None:
    guarded, flags = _apply_response_guardrails(
        answer="Draft",
        synthesis={
            "direct_answer": "Draft",
            "supporting_claim_ids": ["CTGOV_NCT00561366", "PUBMED_39886777"],
            "executable_follow_up_query": "Do SOD1 cohorts disagree on treatment response?",
        },
        evidence_rows=[
            {
                "claim_id": "CTGOV_NCT00561366",
                "claim_text": "Claim",
                "reliability_score": 0.8,
                "source_doi": "10.1/x",
                "entity": "sod1",
                "outcome": "survival",
                "effect_direction": "supports",
            },
            {
                "claim_id": "PUBMED_39886777",
                "claim_text": "Claim 2",
                "reliability_score": 0.7,
                "source_doi": "10.1/y",
                "entity": "sod1",
                "outcome": "alsfrs",
                "effect_direction": "contradicts",
            },
        ],
        contradiction_rows=[
            {
                "claim_a": "CTGOV_NCT00561366",
                "claim_b": "PUBMED_39886777",
                "entity": "sod1",
                "outcome_a": "survival",
                "outcome_b": "alsfrs",
                "contradiction_type": "endpoint_mismatch",
            }
        ],
        language="en",
    )
    query = str(guarded["executable_follow_up_query"])
    assert "Do SOD1 cohorts disagree on treatment response" in query
    assert "CTGOV_NCT00561366" in query
    assert "PUBMED_39886777" in query
    assert "executable_follow_up_query_from_llm" in flags


def test_apply_response_guardrails_templates_executable_query_from_contradictions() -> None:
    guarded, flags = _apply_response_guardrails(
        answer="Draft",
        synthesis={
            "direct_answer": "Draft",
            "supporting_claim_ids": ["CTGOV_NCT00561366", "PUBMED_39886777"],
        },
        evidence_rows=[
            {
                "claim_id": "CTGOV_NCT00561366",
                "claim_text": "Claim",
                "reliability_score": 0.8,
                "source_doi": "10.1/x",
            },
            {
                "claim_id": "PUBMED_39886777",
                "claim_text": "Claim 2",
                "reliability_score": 0.7,
                "source_doi": "10.1/y",
            },
        ],
        contradiction_rows=[
            {
                "claim_a": "CTGOV_NCT00561366",
                "claim_b": "PUBMED_39886777",
                "entity": "sod1",
                "outcome_a": "survival",
                "outcome_b": "alsfrs",
                "contradiction_type": "endpoint_mismatch",
            }
        ],
        language="en",
    )
    assert "executable_follow_up_query_templated" in flags
    query = str(guarded.get("executable_follow_up_query", ""))
    assert "sod1" in query.lower()
    assert "endpoint" in query.lower()
    assert "CTGOV_NCT00561366" in query
    assert "PUBMED_39886777" in query


def test_apply_response_guardrails_rejects_generic_and_external_executable_query() -> None:
    guarded, flags = _apply_response_guardrails(
        answer="Draft",
        synthesis={
            "direct_answer": "Draft",
            "executable_follow_up_query": (
                "Run a stratified follow-up validation focusing on cohort and endpoint differences."
            ),
        },
        evidence_rows=[],
        contradiction_rows=[],
        language="en",
    )
    assert "executable_follow_up_query" not in guarded
    assert "executable_follow_up_query_from_llm" not in flags

    guarded_ext, _ = _apply_response_guardrails(
        answer="Draft",
        synthesis={
            "direct_answer": "Draft",
            "executable_follow_up_query": "Requires external integration: Query GTEx for expression.",
        },
        evidence_rows=[],
        contradiction_rows=[],
        language="en",
    )
    assert "executable_follow_up_query" not in guarded_ext


def test_rank_cited_evidence_rows_orders_by_reliability_and_recency() -> None:
    rows = [
        {"claim_id": "C_OLD", "reliability_score": 0.9, "year": 2010},
        {"claim_id": "C_NEW_HIGH", "reliability_score": 0.95, "year": 2024},
        {"claim_id": "C_MID", "reliability_score": 0.8, "year": 2020},
    ]
    ranked = _rank_cited_evidence_rows(rows)
    assert [row["claim_id"] for row in ranked][:2] == ["C_NEW_HIGH", "C_OLD"]


def test_default_timeout_seconds_defaults_to_300(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALS_TIMEOUT_SECONDS", raising=False)
    import als_intel.webui as webui_module

    importlib.reload(webui_module)
    assert webui_module.DEFAULT_TIMEOUT_SECONDS == 300


def test_governance_doc_body_serves_mission_md() -> None:
    payload = _governance_doc_body("MISSION.md")
    assert payload is not None
    assert "MTVL AI / Canoniga Mission" in payload["title"]
    assert "Objective" in payload["body_html"]
    assert "<pre" not in payload["body_html"]


def test_brand_logo_svg_is_well_formed_xml() -> None:
    import xml.etree.ElementTree as ET

    from als_intel.brand import logo_path

    ET.parse(logo_path())


def test_serve_repo_asset_returns_logo_svg() -> None:
    handler = MagicMock(spec=BaseHTTPRequestHandler)
    handler.wfile = BytesIO()
    handled = serve_repo_asset(handler, "/assets/mtvl-ai-logo.svg")
    assert handled is True
    handler.send_response.assert_called_once()
    body = handler.wfile.getvalue()
    assert b"<svg" in body.lower()


def test_serve_repo_asset_rejects_traversal() -> None:
    handler = MagicMock(spec=BaseHTTPRequestHandler)
    handler.wfile = BytesIO()
    assert serve_repo_asset(handler, "/assets/../src/als_intel/webui.py") is False


@pytest.mark.skipif(not spa_available(), reason="frontend build not present")
def test_serve_spa_or_static_serves_index() -> None:
    handler = MagicMock(spec=BaseHTTPRequestHandler)
    handler.wfile = BytesIO()
    handled = serve_spa_or_static(handler, "/app")
    assert handled is True
    handler.send_response.assert_called_once()
    body = handler.wfile.getvalue()
    assert b"<div id=\"app\"></div>" in body or b'id="app"' in body


@pytest.mark.skipif(not spa_available(), reason="frontend build not present")
def test_built_frontend_assets_exist() -> None:
    dist = Path(__file__).resolve().parents[1] / "assets" / "dist"
    assert (dist / "index.html").is_file()
    assert any(dist.glob("assets/*.js"))
