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
    _rank_cited_evidence_rows,
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
        answer="Direct answer mentioning claim_id=C1\n**Contradictions or Uncertainty**\nNone noted",
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
    assert synthesis["direct_answer"]
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
