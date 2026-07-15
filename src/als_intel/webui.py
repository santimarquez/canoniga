from __future__ import annotations

import argparse
import base64
from pathlib import Path
from collections import deque
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import secrets
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen

from als_intel.auth import AuthService, build_auth_config
from als_intel.brand import (
    LANDING_DASHBOARD_URL_PATH,
    LETTERMARK_LOGO_URL_PATH,
    LOGO_URL_PATH,
    landing_dashboard_bytes,
    landing_dashboard_mime_type,
    lettermark_logo_bytes,
    lettermark_logo_mime_type,
    logo_bytes,
    logo_mime_type,
)
from als_intel.i18n import locale_cookie_header, resolve_locale
from als_intel.landing import APP_ROUTE
from als_intel.static_frontend import serve_repo_asset, serve_spa_or_static
from als_intel.llm import LocalLLMError, build_grounded_prompt, generate_with_ollama, generate_with_ollama_stream
from als_intel.manual_sync import ManualSyncError, get_manual_sync_status, start_manual_sync
from als_intel.markdown_render import extract_markdown_title, render_markdown_to_html
from als_intel.profile import public_profile_summary
from als_intel.store import EvidenceStore

MAX_PROFILE_AVATAR_BYTES = 256 * 1024


DEFAULT_DB_PATH = os.getenv("ALS_DB_PATH", "data/als_intel.sqlite")
DEFAULT_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
DEFAULT_PORT = int(os.getenv("ALS_WEB_PORT", "8000"))

PUBLIC_PAGE_PATHS = {"/", "/index.html", "/login", "/privacy", "/terms"}
APP_PAGE_PATHS = {APP_ROUTE, f"{APP_ROUTE}/index.html"}
DEFAULT_CONTEXT_LIMIT = int(os.getenv("ALS_CONTEXT_LIMIT", "20"))
DEFAULT_TEMPERATURE = float(os.getenv("ALS_TEMPERATURE", "0.1"))
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("ALS_TIMEOUT_SECONDS", "300"))
DEFAULT_AUTH_ENABLED = os.getenv("ALS_AUTH_ENABLED", "1").strip() not in {"0", "false", "False"}
MAX_CITED_EVIDENCE_ROWS = 80
TELEMETRY_MAX_RECENT = 200

_RECENT_QUERY_TELEMETRY: deque[dict[str, object]] = deque(maxlen=TELEMETRY_MAX_RECENT)
_RECENT_QUERY_TELEMETRY_LOCK = Lock()

GOVERNANCE_DOC_NAMES = (
    "MISSION.md",
    "ETHICS_AND_OVERSIGHT.md",
    "HUMAN_OVERSIGHT.md",
)


def _json_response(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: dict[str, Any],
    *,
    extra_headers: dict[str, str] | None = None,
) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    if extra_headers:
        for key, value in extra_headers.items():
            handler.send_header(str(key), str(value))
    handler.end_headers()
    handler.wfile.write(body)


def _stream_json_event(handler: BaseHTTPRequestHandler, payload: dict[str, Any]) -> None:
    line = json.dumps(payload, ensure_ascii=True).encode("utf-8") + b"\n"
    handler.wfile.write(line)
    handler.wfile.flush()


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, object]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    try:
        parsed = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Request body must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Request body must be a JSON object")
    return parsed


def _new_trace_id() -> str:
    return f"trace_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000000) % 1000000:06d}"


def _append_query_telemetry(trace: dict[str, object]) -> None:
    with _RECENT_QUERY_TELEMETRY_LOCK:
        _RECENT_QUERY_TELEMETRY.appendleft(trace)


def _recent_query_telemetry(limit: int = 25) -> list[dict[str, object]]:
    safe_limit = max(1, min(int(limit or 25), TELEMETRY_MAX_RECENT))
    with _RECENT_QUERY_TELEMETRY_LOCK:
        return list(_RECENT_QUERY_TELEMETRY)[:safe_limit]


def _extract_latest_user_message(messages: list[dict[str, object]]) -> str:
    for message in reversed(messages):
        if str(message.get("role", "")).lower() == "user":
            content = str(message.get("content", "")).strip()
            if content:
                return content
    return ""


def _build_chat_prompt(
  messages: list[dict[str, object]],
  evidence_rows: list[dict[str, object]],
  context_limit: int,
  language: str,
) -> str:
    latest_user_message = _extract_latest_user_message(messages)
    if not latest_user_message:
        raise ValueError("At least one user message is required")

    prompt = build_grounded_prompt(latest_user_message, evidence_rows, context_limit=context_limit)
    language_normalized = str(language or "en").strip().lower()
    if language_normalized == "es":
      prompt += "\n\nOutput language requirement: Respond entirely in Spanish."
    else:
      prompt += "\n\nOutput language requirement: Respond entirely in English."
    transcript_lines: list[str] = []
    for message in messages[-20:]:
        role = str(message.get("role", "")).strip().lower()
        content = str(message.get("content", "")).strip()
        if not role or not content:
            continue
        transcript_lines.append(f"{role.title()}: {content}")

    if transcript_lines:
        prompt += "\n\nConversation history:\n" + "\n".join(transcript_lines)
    return prompt


def _apply_evidence_filters(evidence_rows: list[dict[str, object]], filters: dict[str, object]) -> list[dict[str, object]]:
    if not filters:
        return list(evidence_rows)
    evidence_types = {
        str(x).strip().lower()
        for x in (filters.get("evidence_types") or [])
        if str(x).strip()
    }
    date_window = str(filters.get("date_window", "all")).strip().lower()
    highlight_contradictions = bool(filters.get("highlight_contradictions", False))
    try:
        min_reliability = float(filters.get("min_reliability", 0.0))
    except (TypeError, ValueError):
        min_reliability = 0.0

    current_year = time.gmtime().tm_year

    output: list[dict[str, object]] = []
    for row in evidence_rows:
      raw_reliability = row.get("reliability_score")
      if raw_reliability in {None, ""}:
        if min_reliability > 0.0:
          continue
        reliability = 0.0
      else:
        try:
          reliability = float(raw_reliability)
        except (TypeError, ValueError):
          if min_reliability > 0.0:
            continue
          reliability = 0.0

      if reliability < min_reliability:
        continue

      if evidence_types:
        causal_type = str(row.get("causal_evidence_type", "")).strip().lower()
        if causal_type not in evidence_types:
          continue

      row_year = int(row.get("year", 0) or 0)
      if date_window == "last5" and row_year and row_year < current_year - 5:
        continue
      if date_window == "last10" and row_year and row_year < current_year - 10:
        continue

      output.append(row)

    if highlight_contradictions:
        output.sort(
            key=lambda row: (
                0 if str(row.get("effect_direction", "")).strip().lower() == "contradicts" else 1,
                -float(row.get("reliability_score", 0.0) or 0.0),
            )
        )

    return output


def _contradiction_pairs_from_rows(
    evidence_rows: list[dict[str, object]],
    *,
    limit: int = 300,
  ) -> list[dict[str, str | float]]:
    safe_limit = max(1, min(int(limit or 300), 2000))
    by_entity: dict[str, dict[str, list[dict[str, object]]]] = {}

    for row in evidence_rows:
      entity = str(row.get("entity", "")).strip().lower()
      if not entity:
        continue
      direction = str(row.get("effect_direction", "")).strip().lower()
      bucket = by_entity.setdefault(entity, {"supports": [], "contradicts": []})
      if direction == "supports":
        bucket["supports"].append(row)
      elif direction == "contradicts":
        bucket["contradicts"].append(row)

    output: list[dict[str, str | float]] = []
    for entity, buckets in by_entity.items():
      supports = sorted(
        buckets.get("supports", []),
        key=lambda row: -float(row.get("reliability_score", 0.0) or 0.0),
      )[:15]
      contradicts = sorted(
        buckets.get("contradicts", []),
        key=lambda row: -float(row.get("reliability_score", 0.0) or 0.0),
      )[:15]
      if not supports or not contradicts:
        continue

      for support in supports:
        for contra in contradicts:
          outcome_a = str(support.get("outcome", ""))
          outcome_b = str(contra.get("outcome", ""))
          score_a = float(support.get("reliability_score", 0.0) or 0.0)
          score_b = float(contra.get("reliability_score", 0.0) or 0.0)
          contradiction_type = "direction_conflict"
          follow_up = "Run replication study with matched endpoint definitions and harmonized analysis plan."
          if outcome_a != outcome_b:
            contradiction_type = "endpoint_mismatch"
            follow_up = "Design an endpoint-alignment study with both outcomes measured in the same cohort."
          output.append(
            {
              "claim_a": str(support.get("claim_id", "")),
              "claim_b": str(contra.get("claim_id", "")),
              "entity": entity,
              "outcome_a": outcome_a,
              "outcome_b": outcome_b,
              "score_a": score_a,
              "score_b": score_b,
              "contradiction_type": contradiction_type,
              "follow_up_experiment": follow_up,
            }
          )
          if len(output) >= safe_limit:
            output.sort(key=lambda row: -(float(row.get("score_a", 0.0)) + float(row.get("score_b", 0.0))))
            return output

    output.sort(key=lambda row: -(float(row.get("score_a", 0.0)) + float(row.get("score_b", 0.0))))
    return output[:safe_limit]


def _should_translate_cited_rows(*, payload: dict[str, object], language: str) -> bool:
    if str(language or "").strip().lower() != "es":
      return False

    explicit = payload.get("translate_evidence_rows")
    if isinstance(explicit, bool):
      return explicit
    if isinstance(explicit, str):
      normalized = explicit.strip().lower()
      if normalized in {"1", "true", "yes", "on"}:
        return True
      if normalized in {"0", "false", "no", "off"}:
        return False

    return str(os.getenv("ALS_TRANSLATE_EVIDENCE_ROWS", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _search_evidence_rows(evidence_rows: list[dict[str, object]], query: str) -> list[dict[str, object]]:
    q = query.strip().lower()
    if not q:
        return list(evidence_rows)

    output: list[dict[str, object]] = []
    for row in evidence_rows:
        haystack = " ".join(
            [
                str(row.get("claim_id", "")),
                str(row.get("claim_text", "")),
                str(row.get("entity", "")),
                str(row.get("outcome", "")),
                str(row.get("source_doi", "")),
            ]
        ).lower()
        if q in haystack:
            output.append(row)
    return output


def _build_source_url_for_row(row: dict[str, object]) -> str:
    claim_id = str(row.get("claim_id", "") or "").strip()
    source_doi = str(row.get("source_doi", "") or "").strip()
    if not source_doi:
        return ""

    lower_source = source_doi.lower()
    if lower_source.startswith("http://") or lower_source.startswith("https://"):
        return source_doi

    if claim_id.upper().startswith("PUBMED_") and source_doi.isdigit():
        return f"https://pubmed.ncbi.nlm.nih.gov/{source_doi}/"

    if claim_id.upper().startswith("CTGOV_") and source_doi.upper().startswith("NCT"):
        return f"https://clinicaltrials.gov/study/{source_doi}"

    if claim_id.upper().startswith("NCBI_GENE_") and source_doi.isdigit():
      return f"https://www.ncbi.nlm.nih.gov/gene/{source_doi}"

    if claim_id.upper().startswith("UNIPROT_"):
      return f"https://www.uniprot.org/uniprotkb/{source_doi}"

    if claim_id.upper().startswith("GO_"):
      return f"https://www.ebi.ac.uk/QuickGO/term/{source_doi}"

    if claim_id.upper().startswith("REACTOME_"):
      return f"https://reactome.org/content/detail/{source_doi}"

    if claim_id.upper().startswith("GEO_"):
      return f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={source_doi}"

    if claim_id.upper().startswith("ARRAYEXPRESS_"):
      return f"https://www.ebi.ac.uk/biostudies/arrayexpress/studies/{source_doi}"

    if claim_id.upper().startswith("KEGG_"):
      return f"https://www.kegg.jp/entry/{source_doi}"

    if claim_id.upper().startswith("PRIDE_"):
      return f"https://www.ebi.ac.uk/pride/archive/projects/{source_doi}"

    if claim_id.upper().startswith("METABOLOMICS_WORKBENCH_"):
      return f"https://www.metabolomicsworkbench.org/data/show_study.php?STUDY_ID={source_doi}"

    if claim_id.upper().startswith("CHEMBL_"):
      return f"https://www.ebi.ac.uk/chembl/compound_report_card/{source_doi}/"

    if claim_id.upper().startswith("OPEN_TARGETS_"):
      return f"https://platform.opentargets.org/search?q={source_doi}"

    if claim_id.upper().startswith("FDA_LABELS_"):
      return "https://open.fda.gov/apis/drug/label/"

    if source_doi.isdigit():
        return f"https://pubmed.ncbi.nlm.nih.gov/{source_doi}/"

    if source_doi.upper().startswith("NCT"):
        return f"https://clinicaltrials.gov/study/{source_doi}"

    return f"https://doi.org/{source_doi}"


def _attach_source_urls_to_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in rows:
        updated = dict(row)
        updated["source_url"] = _build_source_url_for_row(updated)
        output.append(updated)
    return output


def _parse_positive_int(value: object, default: int, *, min_value: int = 1, max_value: int = 500) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < min_value:
        return min_value
    if parsed > max_value:
        return max_value
    return parsed


def _parse_non_negative_int(value: object, default: int, *, max_value: int = 100000) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 0:
        return 0
    if parsed > max_value:
        return max_value
    return parsed


def _resolve_chat_evidence_limit(payload: dict[str, object]) -> int | None:
    raw_value = payload.get("evidence_max_rows")
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
      raw_value = os.getenv("ALS_CHAT_EVIDENCE_MAX_ROWS", "0")

    try:
      parsed = int(raw_value)
    except (TypeError, ValueError):
      parsed = 0

    if parsed <= 0:
      return None
    return min(parsed, 20000)


def _paginate_rows(rows: list[dict[str, object]], *, limit: int, offset: int) -> tuple[list[dict[str, object]], int, bool]:
    total = len(rows)
    start = min(offset, total)
    end = min(start + limit, total)
    page_rows = rows[start:end]
    return page_rows, total, end < total


def _build_report_markdown(payload: dict[str, object], *, locale: str = "en") -> str:
    from als_intel.i18n import t as translate

    synthesis = payload.get("synthesis") if isinstance(payload.get("synthesis"), dict) else {}
    synthesis = synthesis if isinstance(synthesis, dict) else {}

    answer = str(synthesis.get("direct_answer") or payload.get("answer") or "")
    supporting_ids = synthesis.get("supporting_claim_ids") if isinstance(synthesis.get("supporting_claim_ids"), list) else []
    supporting_ids = [str(x) for x in supporting_ids]
    contradictions = str(synthesis.get("contradictions_summary") or "")
    next_step = str(synthesis.get("next_validation_step") or "")
    generated_seconds = float(payload.get("generated_seconds", 0.0) or 0.0)
    safe_locale = locale if locale in {"en", "es"} else "en"
    na = translate(safe_locale, "time_na")

    lines = [
        f"# {translate(safe_locale, 'report_md_title')}",
        "",
        f"{translate(safe_locale, 'report_md_generated')}: {generated_seconds:.3f}",
        "",
        f"## {translate(safe_locale, 'report_md_direct')}",
        answer or na,
    ]

    if supporting_ids:
      lines.extend(["", f"## {translate(safe_locale, 'report_md_supporting')}"])
      for claim_id in supporting_ids:
        lines.append(f"- {claim_id}")

    if contradictions:
      lines.extend(["", f"## {translate(safe_locale, 'report_md_contradictions')}", contradictions])

    if next_step:
      lines.extend(["", f"## {translate(safe_locale, 'report_md_next_step')}", next_step])

    lines.append("")

    return "\n".join(lines)


def _build_investigator_synthesis(
    *,
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
    require_review_signoff: bool,
    approved_claim_ids: set[str],
    store: Any | None = None,
) -> dict[str, object]:
    from als_intel.agents.debate import build_debate_report
    from als_intel.agents.orchestrator import build_agent_report
    from als_intel.agents.systems_biology import build_systems_biology_report
    from als_intel.hypothesis import build_hypothesis_queue

    systems_biology_report: dict[str, object] = {"count": 0, "items": []}
    support_map: list[dict[str, object]] = []
    neighbor_rows: list[dict[str, object]] = []
    if store is not None:
        support_map = store.graph_support_contradiction_map(limit=30)
        for row in support_map:
            entity = str(row.get("entity", "")).strip()
            if not entity:
                continue
            for neighbor in store.graph_neighbors(entity, limit=6):
                neighbor_rows.append(
                    {
                        "entity": entity,
                        "neighbor_entity": str(neighbor.get("neighbor_label", "")),
                        "neighbor_label": str(neighbor.get("neighbor_label", "")),
                        "edge_type": str(neighbor.get("edge_type", "")),
                        "neighbor_type": str(neighbor.get("neighbor_type", "")),
                        "polarity": str(neighbor.get("polarity", "")),
                        "weight": neighbor.get("weight", 0.0),
                    }
                )
        systems_biology_report = build_systems_biology_report(
            evidence_rows=evidence_rows,
            support_map_rows=support_map,
            graph_neighbor_rows=neighbor_rows,
            limit=5,
        )

    agent_report = build_agent_report(
        evidence_rows=evidence_rows,
        contradiction_rows=contradiction_rows,
        require_review_signoff=require_review_signoff,
        approved_claim_ids=approved_claim_ids,
        support_map_rows=support_map or None,
        graph_neighbor_rows=neighbor_rows or None,
        systems_biology_limit=5,
    )
    if isinstance(agent_report.get("systems_biology_agent"), dict):
        systems_biology_report = agent_report["systems_biology_agent"]

    return {
        "agent_report": agent_report,
        "hypothesis_queue": build_hypothesis_queue(
            evidence_rows=evidence_rows,
            contradiction_rows=contradiction_rows,
            limit=5,
            require_review_signoff=require_review_signoff,
            approved_claim_ids=approved_claim_ids,
        ),
        "debate_report": build_debate_report(
            evidence_rows=evidence_rows,
            contradiction_rows=contradiction_rows,
        ),
        "systems_biology_report": systems_biology_report,
    }


def _evaluate_report_gate(
    *,
    report_payload: dict[str, object],
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
  ) -> dict[str, object]:
    freshness_window_years = max(0, int(os.getenv("ALS_RUN_GATE_FRESHNESS_WINDOW_YEARS", "5") or 5))
    max_contradiction_density = float(os.getenv("ALS_RUN_GATE_MAX_CONTRADICTION_DENSITY", "1.0") or 1.0)
    require_citation_integrity = os.getenv("ALS_RUN_GATE_REQUIRE_CITATION_INTEGRITY", "1").strip() not in {"0", "false", "False"}
    require_contradiction_summary = os.getenv("ALS_RUN_GATE_REQUIRE_CONTRADICTION_SUMMARY", "1").strip() not in {"0", "false", "False"}

    latest_year = max((int(row.get("year", 0) or 0) for row in evidence_rows), default=0)
    now_year = datetime.now(timezone.utc).year
    freshness_ok = latest_year >= (now_year - freshness_window_years) if latest_year > 0 else False

    composition = report_payload.get("composition") if isinstance(report_payload.get("composition"), dict) else {}
    agent_report = composition.get("agent_report") if isinstance(composition.get("agent_report"), dict) else {}
    supporting_claim_ids = agent_report.get("supporting_claim_ids") if isinstance(agent_report.get("supporting_claim_ids"), list) else []
    evidence_claim_id_set = {str(row.get("claim_id", "")).strip() for row in evidence_rows if str(row.get("claim_id", "")).strip()}
    citation_integrity_measured = bool(supporting_claim_ids) and all(
      str(cid).strip() in evidence_claim_id_set for cid in supporting_claim_ids
    )
    citation_integrity_ok = citation_integrity_measured if require_citation_integrity else True

    contradiction_density = 0.0
    if evidence_rows:
      contradiction_density = len(contradiction_rows) / float(len(evidence_rows))
    contradiction_coverage_measured = not contradiction_rows or bool(agent_report.get("contradictions_summary"))
    contradiction_density_ok = contradiction_density <= max_contradiction_density
    contradiction_coverage_ok = (
      contradiction_density_ok
      and (contradiction_coverage_measured if require_contradiction_summary else True)
    )

    checks = {
      "freshness": {
        "passed": freshness_ok,
        "latest_year": latest_year,
        "threshold_year": now_year - freshness_window_years,
        "window_years": freshness_window_years,
      },
      "citation_integrity": {
        "passed": citation_integrity_ok,
        "measured_passed": citation_integrity_measured,
        "required": require_citation_integrity,
        "supporting_claim_ids_count": len(supporting_claim_ids),
      },
      "contradiction_coverage": {
        "passed": contradiction_coverage_ok,
        "summary_measured_passed": contradiction_coverage_measured,
        "summary_required": require_contradiction_summary,
        "density_passed": contradiction_density_ok,
        "max_density": round(max_contradiction_density, 4),
        "contradiction_density": round(contradiction_density, 4),
        "contradictions": len(contradiction_rows),
      },
    }
    passed = all(bool(item.get("passed", False)) for item in checks.values())
    return {
      "passed": passed,
      "checks": checks,
      "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_replay_diff(
    *,
    baseline_run: dict[str, object],
    current_report: dict[str, object],
    current_quality_gate: dict[str, object],
  ) -> dict[str, object]:
    baseline_report = baseline_run.get("report") if isinstance(baseline_run.get("report"), dict) else {}
    baseline_gate = baseline_run.get("quality_gate") if isinstance(baseline_run.get("quality_gate"), dict) else {}

    baseline_composition = baseline_report.get("composition") if isinstance(baseline_report.get("composition"), dict) else {}
    baseline_agent_report = baseline_composition.get("agent_report") if isinstance(baseline_composition.get("agent_report"), dict) else {}
    baseline_supporting_claim_ids = [
        str(cid).strip()
        for cid in baseline_agent_report.get("supporting_claim_ids", [])
        if str(cid).strip()
    ] if isinstance(baseline_agent_report.get("supporting_claim_ids"), list) else []

    current_composition = current_report.get("composition") if isinstance(current_report.get("composition"), dict) else {}
    current_agent_report = current_composition.get("agent_report") if isinstance(current_composition.get("agent_report"), dict) else {}
    current_supporting_claim_ids = [
        str(cid).strip()
        for cid in current_agent_report.get("supporting_claim_ids", [])
        if str(cid).strip()
    ] if isinstance(current_agent_report.get("supporting_claim_ids"), list) else []

    baseline_count = int(baseline_report.get("evidence_count", 0) or 0)
    current_count = int(current_report.get("evidence_count", 0) or 0)
    baseline_pass = bool(baseline_gate.get("passed", False))
    current_pass = bool(current_quality_gate.get("passed", False))

    baseline_checks = baseline_gate.get("checks") if isinstance(baseline_gate.get("checks"), dict) else {}
    current_checks = current_quality_gate.get("checks") if isinstance(current_quality_gate.get("checks"), dict) else {}
    baseline_contradictions = int(
        (baseline_checks.get("contradiction_coverage") or {}).get("contradictions", 0)
        if isinstance(baseline_checks.get("contradiction_coverage"), dict) else 0
    )
    current_contradictions = int(
        (current_checks.get("contradiction_coverage") or {}).get("contradictions", 0)
        if isinstance(current_checks.get("contradiction_coverage"), dict) else 0
    )
    baseline_density = float(
        (baseline_checks.get("contradiction_coverage") or {}).get("contradiction_density", 0.0)
        if isinstance(baseline_checks.get("contradiction_coverage"), dict) else 0.0
    )
    current_density = float(
        (current_checks.get("contradiction_coverage") or {}).get("contradiction_density", 0.0)
        if isinstance(current_checks.get("contradiction_coverage"), dict) else 0.0
    )

    baseline_citation_set = set(baseline_supporting_claim_ids)
    current_citation_set = set(current_supporting_claim_ids)
    shared_citations = sorted(baseline_citation_set.intersection(current_citation_set))
    union_count = len(baseline_citation_set.union(current_citation_set))
    citation_overlap_ratio = (len(shared_citations) / union_count) if union_count else 1.0

    check_status_changed: list[str] = []
    for check_name in sorted(set(baseline_checks.keys()).union(set(current_checks.keys()))):
        baseline_check_passed = bool(
            (baseline_checks.get(check_name) or {}).get("passed", False)
            if isinstance(baseline_checks.get(check_name), dict) else False
        )
        current_check_passed = bool(
            (current_checks.get(check_name) or {}).get("passed", False)
            if isinstance(current_checks.get(check_name), dict) else False
        )
        if baseline_check_passed != current_check_passed:
            check_status_changed.append(check_name)

    return {
        "baseline_run_id": str(baseline_run.get("run_id", "")),
        "evidence_count_delta": current_count - baseline_count,
        "quality_gate_changed": baseline_pass != current_pass,
        "baseline_passed": baseline_pass,
        "current_passed": current_pass,
        "citation_overlap": {
            "baseline_count": len(baseline_supporting_claim_ids),
            "current_count": len(current_supporting_claim_ids),
            "shared_count": len(shared_citations),
            "shared_claim_ids": shared_citations[:20],
            "overlap_ratio": round(citation_overlap_ratio, 4),
        },
        "contradiction_delta": {
            "baseline_count": baseline_contradictions,
            "current_count": current_contradictions,
            "count_delta": current_contradictions - baseline_contradictions,
            "baseline_density": round(baseline_density, 4),
            "current_density": round(current_density, 4),
            "density_delta": round(current_density - baseline_density, 4),
        },
        "changed_checks": check_status_changed,
    }


def _build_autonomous_run_report(
    *,
    objective: str,
    filters: dict[str, object],
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
    require_review_signoff: bool,
    approved_claim_ids: set[str],
    store: EvidenceStore | None = None,
  ) -> dict[str, object]:
    composition = _build_investigator_synthesis(
      evidence_rows=evidence_rows,
      contradiction_rows=contradiction_rows,
      require_review_signoff=require_review_signoff,
      approved_claim_ids=approved_claim_ids,
      store=store,
    )
    return {
      "objective": objective,
      "filters": filters,
      "evidence_count": len(evidence_rows),
      "composition": composition,
      "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _execute_investigation_run(
    *,
    store: EvidenceStore,
    user_id: str,
    run_id: str,
    objective: str,
    filters: dict[str, object],
    require_review_signoff: bool,
  ) -> dict[str, object]:
    evidence_rows = _attach_source_urls_to_rows(store.all_evidence())
    filtered_rows = _apply_evidence_filters(evidence_rows, filters)
    contradictions = store.contradiction_pairs()
    approved_claim_ids = store.approved_claim_ids() if require_review_signoff else set()
    report = _build_autonomous_run_report(
      objective=objective,
      filters=filters,
      evidence_rows=filtered_rows,
      contradiction_rows=contradictions,
      require_review_signoff=require_review_signoff,
      approved_claim_ids=approved_claim_ids,
      store=store,
    )
    gate = _evaluate_report_gate(
      report_payload=report,
      evidence_rows=filtered_rows,
      contradiction_rows=contradictions,
    )
    handoff_on_gate_fail = str(os.getenv("ALS_AUTOMATION_HANDOFF_ON_GATE_FAIL", "1")).strip() not in {"0", "false", "False"}
    approval_status = "auto_approved"
    if require_review_signoff:
        approval_status = "pending"
    elif handoff_on_gate_fail and not bool(gate.get("passed", False)):
        approval_status = "pending"

    store.complete_investigation_run(
      user_id=user_id,
      run_id=run_id,
      status="completed",
      report=report,
      quality_gate=gate,
      replay_diff={},
      approval_status=approval_status,
    )
    return store.get_investigation_run(user_id=user_id, run_id=run_id)


def _score_experiment_variant(run_row: dict[str, object]) -> float:
    quality_gate = run_row.get("quality_gate") if isinstance(run_row.get("quality_gate"), dict) else {}
    checks = quality_gate.get("checks") if isinstance(quality_gate.get("checks"), dict) else {}
    contradiction = checks.get("contradiction_coverage") if isinstance(checks.get("contradiction_coverage"), dict) else {}
    contradiction_density = float(contradiction.get("contradiction_density", 1.0) or 1.0)
    evidence_count = int(run_row.get("evidence_count") or (run_row.get("report") or {}).get("evidence_count", 0) or 0)
    gate_bonus = 100.0 if bool(quality_gate.get("passed", False)) else 0.0
    return round(gate_bonus + float(evidence_count) - (contradiction_density * 100.0), 4)


def _execute_due_queued_runs(
    *,
    store: EvidenceStore,
    due_runs: list[dict[str, object]],
    backoff_base_seconds: int,
  ) -> list[dict[str, object]]:
    executed_rows: list[dict[str, object]] = []
    for run in due_runs:
      run_id = str(run.get("run_id", ""))
      user_id = str(run.get("user_id", ""))
      if not run_id or not user_id:
        continue
      try:
        final_row = _execute_investigation_run(
          store=store,
          user_id=user_id,
          run_id=run_id,
          objective=str(run.get("objective", "")),
          filters=run.get("filters") if isinstance(run.get("filters"), dict) else {},
          require_review_signoff=bool(run.get("require_review_signoff", False)),
        )
        executed_rows.append(final_row)
      except Exception as exc:
        attempts = int(run.get("attempt_count", 1) or 1)
        retry_state = store.retry_or_fail_investigation_run(
          user_id=user_id,
          run_id=run_id,
          error_text=str(exc),
          backoff_seconds=backoff_base_seconds * max(1, attempts),
        )
        executed_rows.append(
          {
            "run_id": run_id,
            "user_id": user_id,
            "status": "queued" if bool(retry_state.get("requeued", False)) else "failed",
            "retry": retry_state,
            "error_text": str(exc),
          }
        )
    return executed_rows


def _build_synthesis(
    *,
    answer: str,
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
) -> dict[str, object]:
  del contradiction_rows  # Synthesis sections are extracted from the model answer only.

  evidence_claim_ids = [str(r.get("claim_id", "")) for r in evidence_rows if str(r.get("claim_id", "")).strip()]
  evidence_claim_id_set = set(evidence_claim_ids)

  mentioned_claim_ids: list[str] = []
  for match in re.finditer(r"claim_id\s*[:=]\s*([A-Za-z0-9_:\-]+)", answer, flags=re.IGNORECASE):
    claim_id = str(match.group(1) or "").strip()
    if not claim_id or claim_id not in evidence_claim_id_set or claim_id in mentioned_claim_ids:
      continue
    mentioned_claim_ids.append(claim_id)

  for claim_id in sorted(evidence_claim_ids, key=len, reverse=True):
    if claim_id in mentioned_claim_ids:
      continue
    if re.search(rf"(?<![A-Za-z0-9_]){re.escape(claim_id)}(?![A-Za-z0-9_])", answer):
      mentioned_claim_ids.append(claim_id)

  supporting_claim_ids = mentioned_claim_ids[:5]

  def _extract_section(text: str, heading_patterns: list[str]) -> str:
    headings_group = "|".join(heading_patterns)
    pattern = re.compile(
      rf"(?is)(?:\*\*\s*(?:{headings_group})\s*\*\*|^\s*#{{1,4}}\s*(?:{headings_group})\s*$)\s*(.+?)(?=\n\s*(?:\*\*|#{{1,4}}\s)|\Z)",
    )
    match = pattern.search(text)
    if not match:
      return ""
    return str(match.group(1) or "").strip()

  contradictions_summary = _extract_section(
    answer,
    [
      r"Contradictions\s+or\s+Uncertainty",
      r"Contradicciones\s+o\s+incertidumbre",
    ],
  )
  next_validation_step = _extract_section(
    answer,
    [
      r"Suggested\s+Validation\s+Next\s+Steps",
      r"Pasos\s+de\s+validaci[o\u00f3]n\s+sugeridos",
      r"Siguientes?\s+pasos?\s+de\s+validaci[o\u00f3]n",
    ],
  )

  synthesis: dict[str, object] = {
    "direct_answer": answer,
  }
  if mentioned_claim_ids:
    synthesis["mentioned_claim_ids"] = mentioned_claim_ids
  if supporting_claim_ids:
    synthesis["supporting_claim_ids"] = supporting_claim_ids
  if contradictions_summary:
    synthesis["contradictions_summary"] = contradictions_summary
  if next_validation_step:
    synthesis["next_validation_step"] = next_validation_step
  return synthesis


def _step_requires_external_integration(step_text: str) -> bool:
    text = str(step_text or "").strip().lower()
    if not text:
      return False

    external_markers = [
      "gtex",
      "tcga",
      "depmap",
      "geo",
      "arrayexpress",
      "uk biobank",
      "clinicaltrials.gov",
      "pubmed api",
      "public database",
      "public dataset",
      "base de datos publica",
      "bases de datos publicas",
      "dataset publico",
      "datos publicos",
      "external api",
      "api externa",
    ]
    return any(marker in text for marker in external_markers)


def _label_next_step_for_capability(step_text: str, language: str) -> tuple[str, bool]:
    normalized = str(step_text or "").strip()
    if not normalized:
      return "", False

    lower = normalized.lower()
    if lower.startswith("requires external integration:") or lower.startswith("requiere integracion externa:"):
      return normalized, False

    if not _step_requires_external_integration(normalized):
      return normalized, False

    language_normalized = str(language or "en").strip().lower()
    if language_normalized == "es":
      return f"Requiere integracion externa: {normalized}", True
    return f"Requires external integration: {normalized}", True


def _verify_cited_claim_ids(
    *,
    synthesis: dict[str, object],
    evidence_rows: list[dict[str, object]],
) -> tuple[dict[str, object], list[str]]:
    guarded = dict(synthesis)
    flags: list[str] = []
    by_id = {
        str(row.get("claim_id", "")).strip(): row
        for row in evidence_rows
        if str(row.get("claim_id", "")).strip()
    }

    for field in ("mentioned_claim_ids", "supporting_claim_ids"):
        raw_ids = guarded.get(field) if isinstance(guarded.get(field), list) else []
        verified: list[str] = []
        for claim_id in raw_ids:
            cid = str(claim_id).strip()
            if not cid:
                continue
            row = by_id.get(cid)
            if row is None:
                flags.append(f"invalid_claim_id:{cid}")
                continue
            if not str(row.get("claim_text", "")).strip():
                flags.append(f"empty_claim_text:{cid}")
            verified.append(cid)
        if verified:
            guarded[field] = verified
        elif field in guarded:
            guarded[field] = []
    return guarded, flags


def _apply_response_guardrails(
    *,
    answer: str,
    synthesis: dict[str, object],
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
  language: str,
) -> tuple[dict[str, object], list[str]]:
    guarded = dict(synthesis)
    flags: list[str] = []

    direct_answer = str(guarded.get("direct_answer") or answer or "").strip()
    if not direct_answer:
        direct_answer = str(answer or "").strip()
        flags.append("direct_answer_filled")
    guarded["direct_answer"] = direct_answer

    evidence_claim_ids = [str(r.get("claim_id", "")).strip() for r in evidence_rows if str(r.get("claim_id", "")).strip()]
    evidence_claim_id_set = set(evidence_claim_ids)

    mentioned_raw = guarded.get("mentioned_claim_ids") if isinstance(guarded.get("mentioned_claim_ids"), list) else []
    mentioned_claim_ids = [
        str(cid).strip() for cid in mentioned_raw
        if str(cid).strip() and str(cid).strip() in evidence_claim_id_set
    ]
    if evidence_rows and not mentioned_claim_ids:
        ranked = sorted(
            evidence_rows,
            key=lambda row: -float(row.get("reliability_score", 0.0) or 0.0),
        )
        mentioned_claim_ids = [
            str(row.get("claim_id", "")).strip()
            for row in ranked
            if str(row.get("claim_id", "")).strip()
        ][:5]
        if mentioned_claim_ids:
            flags.append("mentioned_claim_ids_filled")
    if mentioned_claim_ids:
        guarded["mentioned_claim_ids"] = mentioned_claim_ids

    supporting_raw = guarded.get("supporting_claim_ids") if isinstance(guarded.get("supporting_claim_ids"), list) else []
    supporting_claim_ids = [
        str(cid).strip() for cid in supporting_raw
        if str(cid).strip() and str(cid).strip() in evidence_claim_id_set
    ]
    if evidence_rows and not supporting_claim_ids:
        supporting_claim_ids = mentioned_claim_ids[:5]
        if supporting_claim_ids:
            flags.append("supporting_claim_ids_filled")
    if supporting_claim_ids:
        guarded["supporting_claim_ids"] = supporting_claim_ids

    contradictions_summary = str(guarded.get("contradictions_summary") or "").strip()
    if contradiction_rows and not contradictions_summary:
        contradictions_summary = (
            "Conflicting evidence is present across sources and study designs; "
            "treat this conclusion as provisional until stratified validation is completed."
        )
        flags.append("contradictions_summary_filled")
    if contradictions_summary:
        guarded["contradictions_summary"] = contradictions_summary

    next_validation_step = str(guarded.get("next_validation_step") or "").strip()
    if not next_validation_step:
        numbered_steps = re.findall(r"(?m)^\s*\d+[\.)]\s+(.+)$", str(answer or ""))
        if numbered_steps:
            next_validation_step = str(numbered_steps[0]).strip()
            flags.append("next_validation_step_extracted")
        elif contradiction_rows:
            next_validation_step = "Run a stratified follow-up validation focusing on cohort and endpoint differences."
            flags.append("next_validation_step_filled")
    if next_validation_step:
      labeled_next_step, was_labeled = _label_next_step_for_capability(next_validation_step, language)
      if was_labeled:
        flags.append("next_validation_step_external_labeled")
      guarded["next_validation_step"] = labeled_next_step

    guarded, verification_flags = _verify_cited_claim_ids(
        synthesis=guarded,
        evidence_rows=evidence_rows,
    )
    flags.extend(verification_flags)
    guarded["verification_flags"] = verification_flags

    return guarded, flags


def _rank_cited_evidence_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    if not rows:
        return []

    current_year = time.gmtime().tm_year
    remaining = list(rows)
    selected: list[dict[str, object]] = []
    by_study_type: dict[str, int] = {}

    def _row_score(row: dict[str, object], diversity_penalty: float) -> float:
        reliability = float(row.get("reliability_score", 0.0) or 0.0)
        year = int(row.get("year", 0) or 0)
        recency = 0.0
        if year > 0:
            recency = max(0.0, min(1.0, (year - 2000) / max(1, current_year - 2000)))
        study_type = str(row.get("study_type", "")).strip().lower()
        study_bonus = {
            "interventional": 0.08,
            "meta_analysis": 0.06,
            "genetic": 0.05,
            "mechanistic": 0.04,
            "observational": 0.03,
        }.get(study_type, 0.02)
        return reliability * 0.72 + recency * 0.18 + study_bonus - diversity_penalty

    while remaining:
        best_row = None
        best_score = float("-inf")
        for row in remaining:
            study_type = str(row.get("study_type", "")).strip().lower() or "unknown"
            penalty = by_study_type.get(study_type, 0) * 0.04
            score = _row_score(row, penalty)
            if score > best_score:
                best_score = score
                best_row = row
        assert best_row is not None
        selected.append(best_row)
        remaining.remove(best_row)
        best_type = str(best_row.get("study_type", "")).strip().lower() or "unknown"
        by_study_type[best_type] = by_study_type.get(best_type, 0) + 1

    return selected


def _extract_json_array(raw_text: str) -> list[object]:
    raw_text = str(raw_text or "").strip()
    if not raw_text:
        return []
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    start = raw_text.find("[")
    end = raw_text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        parsed = json.loads(raw_text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _translate_evidence_rows_for_language(
    *,
    rows: list[dict[str, object]],
    language: str,
    model: str,
    host: str,
    temperature: float,
    timeout_seconds: int,
    max_rows: int | None = None,
) -> list[dict[str, object]]:
    language_normalized = str(language or "en").strip().lower()
    if language_normalized != "es" or not rows:
        return rows

    effective_rows = rows
    if max_rows is not None:
        safe_max = max(1, int(max_rows))
        effective_rows = rows[:safe_max]

    source_texts = [str(row.get("claim_text", "")).strip() for row in effective_rows]
    if not any(source_texts):
        return effective_rows

    numbered_lines = [f"{idx + 1}. {text}" for idx, text in enumerate(source_texts)]
    prompt = (
        "Translate the following clinical evidence node texts from English to Spanish.\n"
        "Return ONLY a valid JSON array of strings with exactly the same length and order.\n"
        "Do not add commentary, markdown, numbering, or extra keys.\n\n"
        "Texts:\n"
        + "\n".join(numbered_lines)
    )

    try:
        translated_raw = generate_with_ollama(
            prompt=prompt,
            model=model,
            host=host,
            temperature=0.0,
            timeout_seconds=timeout_seconds,
        )
    except Exception:
      return effective_rows

    translated_items = _extract_json_array(translated_raw)
    if len(translated_items) != len(effective_rows):
      return effective_rows

    translated_rows: list[dict[str, object]] = []
    for index, row in enumerate(effective_rows):
        updated = dict(row)
        translated_text = str(translated_items[index] if translated_items[index] is not None else "").strip()
        if translated_text:
            updated["claim_text"] = translated_text
        translated_rows.append(updated)
    return translated_rows


def _repo_docs_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "docs"


def _governance_doc_body(doc_name: str) -> dict[str, str] | None:
    safe_name = Path(doc_name).name
    if not safe_name.endswith(".md"):
        return None
    doc_path = _repo_docs_dir() / safe_name
    if not doc_path.is_file():
        return None
    markdown = doc_path.read_text(encoding="utf-8")
    page_title = extract_markdown_title(markdown) or safe_name.replace(".md", "").replace("_", " ")
    body_html = render_markdown_to_html(markdown, skip_top_heading=True)
    return {"title": page_title, "body_html": body_html}


def _write_brand_logo(handler: BaseHTTPRequestHandler) -> None:
    data = logo_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", logo_mime_type())
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "public, max-age=86400")
    handler.end_headers()
    handler.wfile.write(data)


def _write_static_asset(handler: BaseHTTPRequestHandler, *, data: bytes, mime_type: str) -> None:
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", mime_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "public, max-age=86400")
    handler.end_headers()
    handler.wfile.write(data)


def _is_public_page(path: str) -> bool:
    return path in PUBLIC_PAGE_PATHS or path.startswith("/docs/")


def _is_app_page(path: str) -> bool:
    return path in APP_PAGE_PATHS


def _profile_payload_for_client(profile: dict[str, object]) -> dict[str, object]:
    summary = public_profile_summary(profile)
    return {
        **summary,
        "profile_updated_at": str(profile.get("profile_updated_at") or ""),
    }


def _decode_profile_avatar(payload: dict[str, object]) -> tuple[bytes | None, str | None, bool]:
    clear_avatar = bool(payload.get("clear_avatar", False))
    if clear_avatar:
        return None, None, True
    raw_avatar = payload.get("avatar_base64")
    if raw_avatar is None:
        return None, None, False
    avatar_text = str(raw_avatar or "").strip()
    if not avatar_text:
        return b"", "", True
    mime_type = str(payload.get("avatar_mime_type") or "image/png").strip().lower()
    if mime_type not in {"image/png", "image/jpeg", "image/jpg", "image/webp"}:
        raise ValueError("avatar_mime_type must be image/png, image/jpeg, or image/webp")
    avatar_bytes = base64.b64decode(avatar_text, validate=True)
    if len(avatar_bytes) > MAX_PROFILE_AVATAR_BYTES:
        raise ValueError(f"Avatar must be {MAX_PROFILE_AVATAR_BYTES} bytes or smaller")
    return avatar_bytes, mime_type, False


class ChatHandler(BaseHTTPRequestHandler):
    server_version = "ALSIntelChat/2.0"
    protocol_version = "HTTP/1.1"

    def _settings(self) -> dict[str, object]:
        return {
            "db_path": os.getenv("ALS_DB_PATH", DEFAULT_DB_PATH),
            "ollama_host": os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST),
            "model": os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            "context_limit": int(os.getenv("ALS_CONTEXT_LIMIT", str(DEFAULT_CONTEXT_LIMIT))),
            "temperature": float(os.getenv("ALS_TEMPERATURE", str(DEFAULT_TEMPERATURE))),
            "timeout_seconds": int(os.getenv("ALS_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
        "auth_enabled": os.getenv("ALS_AUTH_ENABLED", "1").strip() not in {"0", "false", "False"},
        }

    def _auth_service(self) -> AuthService:
      return AuthService(build_auth_config())

    def _client_ip(self) -> str:
      forwarded = str(self.headers.get("X-Forwarded-For", "")).strip()
      if forwarded:
        return forwarded.split(",", 1)[0].strip()
      return str(self.client_address[0] if self.client_address else "")

    def _cookie_value(self, key: str) -> str:
      raw = str(self.headers.get("Cookie", ""))
      for item in raw.split(";"):
        part = item.strip()
        if not part or "=" not in part:
          continue
        k, v = part.split("=", 1)
        if k.strip() == key:
          return v.strip()
      return ""

    def _resolve_request_locale(self, query_params: dict[str, list[str]]) -> tuple[str, bool]:
        query_lang = str((query_params.get("lang") or [""])[0]).strip()
        return resolve_locale(
            accept_language=self.headers.get("Accept-Language"),
            cookie_header=self.headers.get("Cookie"),
            query_lang=query_lang,
        )

    def _send_html(self, body: bytes, *, locale: str, should_set_locale: bool) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if should_set_locale:
            self.send_header("Set-Cookie", locale_cookie_header(locale))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _session_token(self, cookie_name: str) -> str:
      bearer = str(self.headers.get("Authorization", "")).strip()
      if bearer.lower().startswith("bearer "):
        token = bearer[7:].strip()
        if token:
          return token
      return self._cookie_value(cookie_name)

    def _csrf_secret(self) -> str:
      return str(os.getenv("ALS_CSRF_SECRET", "als-csrf-secret-local"))

    def _csrf_token_for_session(self, session_token: str) -> str:
      raw = f"{self._csrf_secret()}:{session_token}".encode("utf-8")
      return hashlib.sha256(raw).hexdigest()

    def _csrf_token_from_request(self) -> str:
      return str(self.headers.get("X-CSRF-Token", "")).strip()

    def _require_csrf(self, *, settings: dict[str, object], auth_service: AuthService, path: str) -> bool:
      if not bool(settings.get("auth_enabled", False)):
        return True
      session_token = self._session_token(auth_service.config.cookie_name)
      if not session_token:
        _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
        return False
      expected = self._csrf_token_for_session(session_token)
      provided = self._csrf_token_from_request()
      if not provided or not secrets.compare_digest(expected, provided):
        _json_response(self, HTTPStatus.FORBIDDEN, {"error": "CSRF token is required"})
        return False
      return True

    def _current_user(self, settings: dict[str, object]) -> dict[str, str] | None:
      if not bool(settings.get("auth_enabled", False)):
        return {"user_id": "anonymous", "email": "anonymous@local"}
      service = self._auth_service()
      token = self._session_token(service.config.cookie_name)
      if not token:
        return None
      store = self._store(str(settings["db_path"]))
      return service.resolve_session(store=store, session_token=token)

    def _require_auth(self, settings: dict[str, object]) -> dict[str, str] | None:
      user = self._current_user(settings)
      if user is None:
        _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
        return None
      return user

    def _record_activity(
      self,
      *,
      settings: dict[str, object],
      user_id: str,
      activity_type: str,
      endpoint: str,
      payload: dict[str, object] | None = None,
    ) -> None:
      if not bool(settings.get("auth_enabled", False)):
        return
      store = self._store(str(settings["db_path"]))
      store.log_user_activity(
        user_id=user_id,
        activity_type=activity_type,
        endpoint=endpoint,
        payload=payload,
      )

    def _format_auth_cookie(self, *, auth_service: AuthService, value: str, max_age: int) -> str:
      same_site = str(auth_service.config.cookie_same_site or "Lax").capitalize()
      if same_site not in {"Lax", "Strict", "None"}:
        same_site = "Lax"
      cookie_expires = datetime.now(timezone.utc) + timedelta(seconds=max_age)
      cookie_value = (
        f"{auth_service.config.cookie_name}={value}; "
        f"Path={auth_service.config.cookie_path}; "
        f"SameSite={same_site}; "
        f"Max-Age={max_age}; "
        f"Expires={cookie_expires.strftime('%a, %d %b %Y %H:%M:%S GMT')}"
      )
      if auth_service.config.cookie_http_only:
        cookie_value += "; HttpOnly"
      if auth_service.config.cookie_secure:
        cookie_value += "; Secure"
      if auth_service.config.cookie_domain:
        cookie_value += f"; Domain={auth_service.config.cookie_domain}"
      return cookie_value

    def _store(self, db_path: str) -> EvidenceStore:
        store = EvidenceStore(db_path)
        store.init_db()
        return store

    def _handle_worker_tick(self, *, provided_token: str, limit: int) -> None:
        expected_token = str(os.getenv("ALS_AUTOMATION_WORKER_TOKEN", "")).strip()
        if not expected_token or provided_token != expected_token:
            _json_response(self, HTTPStatus.FORBIDDEN, {"error": "invalid worker token"})
            return
        backoff_base_seconds = _parse_positive_int(
            os.getenv("ALS_RUN_RETRY_BACKOFF_SECONDS", "30"),
            30,
            max_value=3600,
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        settings = self._settings()
        store = self._store(str(settings["db_path"]))
        due_runs = store.claim_due_queued_runs(now_iso=now_iso, limit=limit)
        executed_rows = _execute_due_queued_runs(
            store=store,
            due_runs=due_runs,
            backoff_base_seconds=backoff_base_seconds,
        )
        _json_response(
            self,
            HTTPStatus.OK,
            {
                "rows": executed_rows,
                "executed": len(executed_rows),
                "claimed": len(due_runs),
                "limit": limit,
                "now": now_iso,
            },
        )

    def _is_browser_page_request(self, path: str) -> bool:
        if path == "/healthz":
            return False
        if path.startswith("/api/"):
            return False
        if path.startswith("/app-assets/"):
            return False
        if path.startswith("/assets/"):
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query_params = parse_qs(parsed.query)

        if path.startswith("/assets/") and not path.startswith("/assets/dist/"):
            if serve_repo_asset(self, path):
                return

        if path == LOGO_URL_PATH:
            try:
                _write_brand_logo(self)
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND, "Logo not found")
            return

        if path == LETTERMARK_LOGO_URL_PATH:
            try:
                _write_static_asset(
                    self,
                    data=lettermark_logo_bytes(),
                    mime_type=lettermark_logo_mime_type(),
                )
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND, "Logo not found")
            return

        if path == LANDING_DASHBOARD_URL_PATH:
            try:
                _write_static_asset(
                    self,
                    data=landing_dashboard_bytes(),
                    mime_type=landing_dashboard_mime_type(),
                )
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND, "Image not found")
            return

        settings = self._settings()
        auth_user: dict[str, str] | None = None
        if bool(settings.get("auth_enabled", False)) and self._is_browser_page_request(path):
            auth_user = self._current_user(settings)
            magic_token = str((query_params.get("magic_token") or [""])[0]).strip()
            if auth_user is None:
                if magic_token and path in {"/", "/index.html"}:
                    location = f"/login?magic_token={quote(magic_token, safe='')}"
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", location)
                    self.end_headers()
                    return
                if not _is_public_page(path):
                    next_target = path
                    if parsed.query:
                        next_target = f"{path}?{parsed.query}"
                    location = f"/login?next={quote(next_target, safe='/?:=&')}"
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", location)
                    self.end_headers()
                    return
            if auth_user is not None:
                if path == "/login":
                    next_query = str((query_params.get("next") or [APP_ROUTE])[0]).strip() or APP_ROUTE
                    if not next_query.startswith("/"):
                        next_query = APP_ROUTE
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", next_query)
                    self.end_headers()
                    return
                if not _is_public_page(path) and not _is_app_page(path):
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", APP_ROUTE)
                    self.end_headers()
                    return

        if path == "/login" and not bool(settings.get("auth_enabled", False)):
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", APP_ROUTE)
            self.end_headers()
            return

        if path.startswith("/api/governance/"):
            doc_name = unquote(path[len("/api/governance/") :]).lstrip("/")
            payload = _governance_doc_body(doc_name)
            if payload is None:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Governance document not found"})
                return
            _json_response(self, HTTPStatus.OK, payload)
            return

        if serve_spa_or_static(self, path):
            locale, should_set_locale = self._resolve_request_locale(query_params)
            if should_set_locale:
                # SPA already sent; set locale cookie on a second response is not possible here.
                # Client persists locale via localStorage; cookie can be set on next API call if needed.
                pass
            return

        if path == "/healthz":
            _json_response(self, HTTPStatus.OK, {"status": "ok"})
            return

        if path == "/api/status":
            try:
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                summary = store.summary()
                flags = store.review_flags()
                source_breakdown = store.source_article_breakdown()
                latest_sync_at = store.latest_sync_timestamp()
                manual_sync = get_manual_sync_status(db_path=str(settings["db_path"]))
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "records_total": int(summary.get("records", 0)),
                        "avg_reliability": float(summary.get("avg_reliability", 0.0)),
                        "supports_count": int(summary.get("supports", 0)),
                        "contradicts_count": int(summary.get("contradicts", 0)),
                        "review_flags_count": len(flags),
                        "model": str(settings.get("model", "")),
                        "db_synced": True,
                        "source_breakdown": source_breakdown,
                        "latest_sync_at": latest_sync_at,
                        "manual_sync": {
                            "can_trigger_all": manual_sync.get("can_trigger_all"),
                            "can_trigger": manual_sync.get("can_trigger"),
                            "cooldown_remaining_seconds": manual_sync.get("cooldown_remaining_seconds"),
                            "next_available_at": manual_sync.get("next_available_at"),
                            "in_progress": manual_sync.get("in_progress"),
                            "manual_sync_active": manual_sync.get("manual_sync_active"),
                            "current_scope": manual_sync.get("current_scope"),
                            "current_source": manual_sync.get("current_source"),
                            "completed_sources": manual_sync.get("completed_sources"),
                            "total_sources": manual_sync.get("total_sources"),
                            "progress_percent": manual_sync.get("progress_percent"),
                            "estimated_remaining_seconds": manual_sync.get("estimated_remaining_seconds"),
                            "estimated_completion_at": manual_sync.get("estimated_completion_at"),
                            "sources": manual_sync.get("sources"),
                        },
                    },
                )
            except Exception as exc:  # pragma: no cover
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/auth/status":
          try:
            settings = self._settings()
            auth_service = self._auth_service()
            token = self._session_token(auth_service.config.cookie_name)
            store = self._store(str(settings["db_path"]))
            user, rotated_token = auth_service.resolve_session_with_rotation(
              store=store,
              session_token=token,
              user_agent=str(self.headers.get("User-Agent", "")),
              ip_address=self._client_ip(),
            ) if token else (None, None)
            csrf_token: str | None = None
            if user is not None:
              session_token = rotated_token or token
              if session_token:
                csrf_token = self._csrf_token_for_session(session_token)
            profile_summary: dict[str, object] | None = None
            if user is not None:
              loaded = store.get_user_profile(user_id=str(user["user_id"]), include_avatar_bytes=False)
              if loaded is not None:
                profile_summary = _profile_payload_for_client(loaded)
            extra_headers = None
            if rotated_token:
              extra_headers = {
                "Set-Cookie": self._format_auth_cookie(
                  auth_service=auth_service,
                  value=rotated_token,
                  max_age=auth_service.config.session_ttl_seconds,
                )
              }
            _json_response(
              self,
              HTTPStatus.OK,
              {
                "auth_enabled": bool(settings.get("auth_enabled", False)),
                "authenticated": user is not None,
                "user": user,
                "profile": profile_summary,
                "csrf_token": csrf_token,
              },
              extra_headers=extra_headers,
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/auth/profile":
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                store = self._store(str(settings["db_path"]))
                profile = store.get_user_profile(user_id=str(user["user_id"]), include_avatar_bytes=False)
                if profile is None:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": "Profile not found"})
                    return
                _json_response(self, HTTPStatus.OK, {"profile": _profile_payload_for_client(profile)})
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/auth/profile/avatar":
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                store = self._store(str(settings["db_path"]))
                profile = store.get_user_profile(user_id=str(user["user_id"]), include_avatar_bytes=True)
                if profile is None or not profile.get("has_avatar"):
                    self.send_error(HTTPStatus.NOT_FOUND, "Avatar not found")
                    return
                avatar_bytes = profile.get("avatar_data")
                if not isinstance(avatar_bytes, (bytes, bytearray)) or not avatar_bytes:
                    self.send_error(HTTPStatus.NOT_FOUND, "Avatar not found")
                    return
                mime_type = str(profile.get("avatar_mime_type") or "image/png")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(avatar_bytes)))
                self.send_header("Cache-Control", "private, max-age=300")
                self.end_headers()
                self.wfile.write(bytes(avatar_bytes))
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/auth/login-metadata":
            try:
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                summary = store.summary()
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "db_path": str(settings["db_path"]),
                        "records_total": int(summary.get("records", 0)),
                        "source_breakdown": store.source_article_breakdown(),
                        "latest_sync_at": store.latest_sync_timestamp(),
                        "avg_reliability": float(summary.get("avg_reliability", 0.0)),
                    },
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/auth/audit":
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                limit = _parse_positive_int((query_params.get("limit") or ["100"])[0], 100, max_value=500)
                activity_type = str((query_params.get("activity_type") or [""])[0]).strip()
                store = self._store(str(settings["db_path"]))
                rows = store.list_user_activity(
                    user_id=str(user["user_id"]),
                    limit=limit,
                    activity_type=activity_type or None,
                )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": rows,
                        "total": len(rows),
                        "limit": limit,
                        "activity_type": activity_type or None,
                    },
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/investigation/runs":
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                limit = _parse_positive_int((query_params.get("limit") or ["20"])[0], 20, max_value=200)
                store = self._store(str(settings["db_path"]))
                rows = store.list_investigation_runs(user_id=str(user["user_id"]), limit=limit)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": rows,
                        "total": len(rows),
                        "limit": limit,
                    },
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/investigation/runs/review-queue":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            limit = _parse_positive_int((query_params.get("limit") or ["50"])[0], 50, max_value=200)
            offset = _parse_non_negative_int((query_params.get("offset") or ["0"])[0], 0, max_value=10000)
            status_filter = str((query_params.get("status") or [""])[0]).strip().lower()
            risk_filter = str((query_params.get("risk") or [""])[0]).strip().lower()
            sort_value = str((query_params.get("sort") or ["created_desc"])[0]).strip().lower()
            store = self._store(str(settings["db_path"]))
            rows, total, has_more = store.list_investigation_review_queue(
              user_id=str(user["user_id"]),
              limit=limit,
              offset=offset,
              status=status_filter,
              risk_level=risk_filter,
              sort=sort_value,
            )
            _json_response(
              self,
              HTTPStatus.OK,
              {
                "rows": rows,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "status": status_filter or "any",
                "risk": risk_filter or "any",
                "sort": sort_value or "created_desc",
              },
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/investigation/runs/review-queue/summary":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            store = self._store(str(settings["db_path"]))
            payload = store.investigation_review_queue_summary(user_id=str(user["user_id"]))
            _json_response(
              self,
              HTTPStatus.OK,
              payload,
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/investigation/templates":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            limit = _parse_positive_int((query_params.get("limit") or ["50"])[0], 50, max_value=200)
            store = self._store(str(settings["db_path"]))
            rows = store.list_investigation_templates(user_id=str(user["user_id"]), limit=limit)
            _json_response(
              self,
              HTTPStatus.OK,
              {
                "rows": rows,
                "total": len(rows),
                "limit": limit,
              },
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/automation/experiments":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            limit = _parse_positive_int((query_params.get("limit") or ["20"])[0], 20, max_value=200)
            store = self._store(str(settings["db_path"]))
            rows = store.list_automation_experiments(user_id=str(user["user_id"]), limit=limit)
            _json_response(
              self,
              HTTPStatus.OK,
              {
                "rows": rows,
                "total": len(rows),
                "limit": limit,
              },
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/automation/exports":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            limit = _parse_positive_int((query_params.get("limit") or ["20"])[0], 20, max_value=200)
            store = self._store(str(settings["db_path"]))
            rows = store.list_automation_exports(user_id=str(user["user_id"]), limit=limit)
            _json_response(
              self,
              HTTPStatus.OK,
              {
                "rows": rows,
                "total": len(rows),
                "limit": limit,
              },
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/automation/dashboard":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            window_days = _parse_positive_int((query_params.get("days") or ["30"])[0], 30, max_value=365)
            store = self._store(str(settings["db_path"]))
            user_id = str(user["user_id"])
            metrics = store.investigation_dashboard_metrics(user_id=user_id, days=window_days)
            review_queue_summary = store.investigation_review_queue_summary(user_id=user_id)
            metrics["review_queue"] = review_queue_summary
            _json_response(self, HTTPStatus.OK, metrics)
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/failure-atlas":
          try:
            from als_intel.agents.historical import build_failure_atlas

            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            store = self._store(str(settings["db_path"]))
            atlas = build_failure_atlas(store.all_evidence_with_provenance())
            _json_response(self, HTTPStatus.OK, atlas)
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/automation/freshness/alarms":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            stale_after_hours = _parse_positive_int(
              (query_params.get("stale_after_hours") or [os.getenv("ALS_FRESHNESS_STALE_HOURS", "24")])[0],
              int(os.getenv("ALS_FRESHNESS_STALE_HOURS", "24") or "24"),
              max_value=24 * 365,
            )
            failure_threshold = _parse_non_negative_int(
              (query_params.get("failure_threshold") or [os.getenv("ALS_FRESHNESS_FAILURE_THRESHOLD", "2")])[0],
              int(os.getenv("ALS_FRESHNESS_FAILURE_THRESHOLD", "2") or "2"),
              max_value=100,
            )
            store = self._store(str(settings["db_path"]))
            rows = store.freshness_alarms(
              stale_after_hours=stale_after_hours,
              failure_threshold=failure_threshold,
            )
            _json_response(
              self,
              HTTPStatus.OK,
              {
                "rows": rows,
                "total": len(rows),
                "stale_after_hours": stale_after_hours,
                "failure_threshold": failure_threshold,
              },
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/sync/manual/status":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            status_payload = get_manual_sync_status(db_path=str(settings["db_path"]))
            _json_response(self, HTTPStatus.OK, status_payload)
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/investigation/runs/worker/tick":
          try:
            provided_token = str((query_params.get("token") or [""])[0]).strip()
            auth_header = str(self.headers.get("Authorization", "")).strip()
            if auth_header.lower().startswith("bearer "):
              provided_token = auth_header[7:].strip() or provided_token
            limit = _parse_positive_int((query_params.get("limit") or ["20"])[0], 20, max_value=200)
            self._handle_worker_tick(provided_token=provided_token, limit=limit)
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/investigation/runs/queued/execute":
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                limit = _parse_positive_int((query_params.get("limit") or ["5"])[0], 5, max_value=50)
                backoff_base_seconds = _parse_positive_int(
                    os.getenv("ALS_RUN_RETRY_BACKOFF_SECONDS", "30"),
                    30,
                    max_value=3600,
                )
                now_iso = datetime.now(timezone.utc).isoformat()
                store = self._store(str(settings["db_path"]))
                due_runs = [
                    row
                    for row in store.claim_due_queued_runs(now_iso=now_iso, limit=limit)
                    if str(row.get("user_id", "")) == str(user["user_id"])
                ]
                executed_rows = _execute_due_queued_runs(
                  store=store,
                  due_runs=due_runs,
                  backoff_base_seconds=backoff_base_seconds,
                )

                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": executed_rows,
                        "executed": len(executed_rows),
                        "limit": limit,
                        "now": now_iso,
                    },
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path.startswith("/api/investigation/runs/"):
            run_id = unquote(path.removeprefix("/api/investigation/runs/")).strip()
            if not run_id:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "run_id is required"})
                return
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                store = self._store(str(settings["db_path"]))
                row = store.get_investigation_run(user_id=str(user["user_id"]), run_id=run_id)
                _json_response(self, HTTPStatus.OK, row)
            except ValueError as exc:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/telemetry/recent":
            try:
                limit = _parse_positive_int((query_params.get("limit") or ["25"])[0], 25, max_value=TELEMETRY_MAX_RECENT)
                traces = _recent_query_telemetry(limit)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "traces": traces,
                        "total": len(traces),
                        "limit": limit,
                    },
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/session/list":
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                limit = _parse_positive_int((query_params.get("limit") or ["50"])[0], 50, max_value=200)
                offset = _parse_non_negative_int((query_params.get("offset") or ["0"])[0], 0)
                store = self._store(str(settings["db_path"]))
                sessions = store.list_investigator_sessions(
                    user_id=str(user["user_id"]),
                    limit=min(5000, offset + limit),
                )
                paged_sessions = sessions[offset : offset + limit]
                self._record_activity(
                    settings=settings,
                    user_id=str(user["user_id"]),
                    activity_type="session_list",
                    endpoint=path,
                    payload={"limit": limit, "offset": offset},
                )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "sessions": paged_sessions,
                        "total": len(sessions),
                        "limit": limit,
                        "offset": offset,
                        "has_more": offset + limit < len(sessions),
                    },
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path.startswith("/api/session/"):
            session_id = unquote(path.removeprefix("/api/session/")).strip()
            if not session_id:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "session_id is required"})
                return
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                store = self._store(str(settings["db_path"]))
                payload = store.get_investigator_session(user_id=str(user["user_id"]), session_id=session_id)
                self._record_activity(
                    settings=settings,
                    user_id=str(user["user_id"]),
                    activity_type="session_get",
                    endpoint=path,
                    payload={"session_id": session_id},
                )
                _json_response(self, HTTPStatus.OK, payload)
            except ValueError as exc:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path.startswith("/api/evidence/"):
            claim_id = unquote(path.removeprefix("/api/evidence/")).strip()
            if not claim_id:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "claim_id is required"})
                return
            try:
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                _json_response(self, HTTPStatus.OK, store.claim_lineage(claim_id))
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path != "/api/auth/profile":
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            payload = _read_json_body(self)
            settings = self._settings()
            auth_service = self._auth_service()
            if not self._require_csrf(settings=settings, auth_service=auth_service, path=path):
                return
            user = self._require_auth(settings)
            if user is None:
                return
            store = self._store(str(settings["db_path"]))
            display_name = str(payload.get("display_name") or "").strip()
            title = str(payload.get("title") or "").strip()
            institution = str(payload.get("institution") or "").strip()
            avatar_bytes, avatar_mime_type, clear_avatar = _decode_profile_avatar(payload)
            updated = store.upsert_user_profile(
                user_id=str(user["user_id"]),
                display_name=display_name,
                title=title,
                institution=institution,
                avatar_bytes=avatar_bytes,
                avatar_mime_type=avatar_mime_type,
                clear_avatar=clear_avatar,
            )
            self._record_activity(
                settings=settings,
                user_id=str(user["user_id"]),
                activity_type="profile_update",
                endpoint=path,
                payload={"display_name": display_name, "has_avatar": bool(updated.get("has_avatar"))},
            )
            _json_response(self, HTTPStatus.OK, {"profile": _profile_payload_for_client(updated)})
        except ValueError as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path not in {
            "/api/auth/request-link",
            "/api/auth/verify-link",
            "/api/auth/logout",
            "/api/chat",
          "/api/chat/stream",
            "/api/evidence/filter",
            "/api/evidence/search",
            "/api/database/nodes",
            "/api/database/node/metadata",
            "/api/hypothesis/queue",
            "/api/review/flags",
            "/api/review/decision",
            "/api/review/decisions",
            "/api/evidence/compare",
            "/api/session/save",
            "/api/export/summary",
            "/api/synthesis",
            "/api/investigation/runs/start",
            "/api/investigation/runs/replay",
            "/api/investigation/runs/queue",
            "/api/investigation/runs/queued/execute",
            "/api/investigation/runs/approve",
            "/api/investigation/runs/rollback",
            "/api/investigation/templates/save",
            "/api/investigation/templates/run",
            "/api/automation/experiments/run",
            "/api/export/automated",
            "/api/investigation/runs/worker/tick",
            "/api/sync/manual/trigger",
        }:
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        try:
            payload = _read_json_body(self)
            settings = self._settings()
            auth_service = self._auth_service()

            if path == "/api/investigation/runs/worker/tick":
                auth_header = str(self.headers.get("Authorization", "")).strip()
                provided_token = ""
                if auth_header.lower().startswith("bearer "):
                    provided_token = auth_header[7:].strip()
                if not provided_token:
                    provided_token = str(payload.get("token", "")).strip()
                limit = _parse_positive_int(payload.get("limit", 20), 20, max_value=200)
                self._handle_worker_tick(provided_token=provided_token, limit=limit)
                return

            if path == "/api/auth/request-link":
                email = str(payload.get("email", "")).strip()
                store = self._store(str(settings["db_path"]))
                normalized_email = AuthService.normalize_email(email)
                existing_user = store.get_user_by_email(normalized_email)
                if existing_user is None and AuthService.is_valid_email(normalized_email):
                    deterministic_user_id = f"usr_{AuthService.token_hash(normalized_email)[:16]}"
                    existing_user = store.get_or_create_user(user_id=deterministic_user_id, email=normalized_email)
                try:
                    _, magic_link = auth_service.create_magic_link(
                        store=store,
                        email=email,
                        requested_ip=self._client_ip(),
                    )
                except ValueError as exc:
                    message = str(exc)
                    if "Too many magic-link requests" in message:
                        if existing_user is not None:
                            store.log_user_activity(
                                user_id=str(existing_user["user_id"]),
                                activity_type="auth_magic_link_rate_limited",
                                endpoint=path,
                                payload={},
                            )
                        _json_response(self, HTTPStatus.TOO_MANY_REQUESTS, {"error": message})
                        return
                    raise
                locale, _ = self._resolve_request_locale({})
                payload_locale = str(payload.get("language", "")).strip()
                if payload_locale:
                    from als_intel.i18n import normalize_locale

                    normalized_payload_locale = normalize_locale(payload_locale)
                    if normalized_payload_locale is not None:
                        locale = normalized_payload_locale
                delivery = auth_service.send_magic_link(
                    email=normalized_email,
                    magic_link=magic_link,
                    locale=locale,
                )
                if existing_user is not None:
                    store.log_user_activity(
                        user_id=str(existing_user["user_id"]),
                        activity_type="auth_magic_link_requested",
                        endpoint=path,
                        payload={"delivery_mode": delivery.get("mode", "unknown")},
                    )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "email": normalized_email,
                        "delivery_mode": delivery.get("mode", "unknown"),
                        "magic_link": delivery.get("magic_link") if delivery.get("mode") == "dev" else None,
                    },
                )
                return

            if path == "/api/auth/verify-link":
                token = str(payload.get("token", "")).strip()
                if not token:
                    raise ValueError("token is required")
                store = self._store(str(settings["db_path"]))
                previous_session = self._session_token(auth_service.config.cookie_name)
                if previous_session:
                  auth_service.revoke_session(store=store, session_token=previous_session)
                user, session_token = auth_service.consume_magic_token(
                    store=store,
                    token=token,
                    user_agent=str(self.headers.get("User-Agent", "")),
                    ip_address=self._client_ip(),
                )
                cookie_value = self._format_auth_cookie(
                    auth_service=auth_service,
                    value=session_token,
                    max_age=auth_service.config.session_ttl_seconds,
                )
                store.log_user_activity(
                    user_id=str(user["user_id"]),
                    activity_type="auth_login",
                    endpoint=path,
                    payload={"email": str(user["email"])},
                )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "authenticated": True,
                        "user": user,
                        "csrf_token": self._csrf_token_for_session(session_token),
                    },
                    extra_headers={"Set-Cookie": cookie_value},
                )
                return

            if path == "/api/auth/logout":
                if bool(settings.get("auth_enabled", False)) and not self._require_csrf(
                    settings=settings,
                    auth_service=auth_service,
                    path=path,
                ):
                    return
                token = self._session_token(auth_service.config.cookie_name)
                store = self._store(str(settings["db_path"]))
                user_for_logout = self._current_user(settings)
                if token:
                    auth_service.revoke_session(store=store, session_token=token)
                if user_for_logout is not None:
                    store.log_user_activity(
                        user_id=str(user_for_logout["user_id"]),
                        activity_type="auth_logout",
                        endpoint=path,
                        payload={},
                    )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {"ok": True},
                    extra_headers={
                        "Set-Cookie": self._format_auth_cookie(
                            auth_service=auth_service,
                            value="",
                            max_age=0,
                        )
                    },
                )
                return

            public_paths: set[str] = {
                "/api/auth/request-link",
                "/api/auth/verify-link",
            }
            current_user: dict[str, str] | None = None
            if not bool(settings.get("auth_enabled", False)):
              current_user = {"user_id": "anonymous", "email": "anonymous@local"}
            elif path not in public_paths:
              current_user = self._require_auth(settings)
              if current_user is None:
                return
              if not self._require_csrf(
                settings=settings,
                auth_service=auth_service,
                path=path,
              ):
                return

            if path == "/api/sync/manual/trigger":
                if current_user is None:
                    _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                    return
                scope = str(payload.get("scope", "")).strip().lower()
                source = str(payload.get("source", "")).strip().lower()
                if scope == "all":
                    resolved_scope = "all"
                elif source:
                    resolved_scope = source
                elif scope:
                    resolved_scope = scope
                else:
                    _json_response(
                        self,
                        HTTPStatus.BAD_REQUEST,
                        {"error": "scope or source is required"},
                    )
                    return
                try:
                    started = start_manual_sync(
                        db_path=str(settings["db_path"]),
                        scope=resolved_scope,
                        triggered_by=str(current_user.get("user_id", "anonymous")),
                    )
                except ManualSyncError as exc:
                    _json_response(self, HTTPStatus(exc.status_code), {"error": str(exc)})
                    return
                self._record_activity(
                    settings=settings,
                    user_id=str(current_user.get("user_id", "anonymous")),
                    activity_type="manual_sync_triggered",
                    endpoint=path,
                    payload={"scope": resolved_scope},
                )
                _json_response(self, HTTPStatus.ACCEPTED, started)
                return

            if path == "/api/chat/stream":
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("Connection", "close")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()

                trace_id = _new_trace_id()
                trace_started_perf = time.perf_counter()
                trace: dict[str, object] = {
                    "trace_id": trace_id,
                    "mode": "stream",
                    "path": path,
                    "started_at": int(time.time()),
                    "status": "ok",
                    "phase_seconds": {},
                }
                if current_user is not None:
                    trace["user_id"] = str(current_user.get("user_id", ""))

                try:
                    phase_loading_started = time.perf_counter()
                    _stream_json_event(self, {"type": "status", "phase": "loading_evidence", "message": "Loading and filtering evidence..."})

                    settings = self._settings()
                    db_path = str(payload.get("db_path") or settings["db_path"])
                    store = self._store(db_path)

                    filters = payload.get("filters", {})
                    if not isinstance(filters, dict):
                        filters = {}
                    filtered_rows = _attach_source_urls_to_rows(
                      store.filter_evidence(
                        filters=filters,
                        limit=_resolve_chat_evidence_limit(payload),
                      )
                    )

                    raw_messages = payload.get("messages", [])
                    if not isinstance(raw_messages, list):
                        raise ValueError("messages must be a list")
                    messages = [message for message in raw_messages if isinstance(message, dict)][-40:]

                    host = str(payload.get("host") or settings["ollama_host"])
                    model = str(payload.get("model") or settings["model"])
                    context_limit = _parse_positive_int(payload.get("context_limit") or settings["context_limit"], int(settings["context_limit"]), max_value=200)
                    temperature = float(payload.get("temperature") or settings["temperature"])
                    timeout_seconds = int(payload.get("timeout_seconds") or settings["timeout_seconds"])
                    language = str(payload.get("language") or "en").strip().lower()
                    if language not in {"en", "es"}:
                        language = "en"

                    trace["model"] = model
                    trace["language"] = language
                    trace["phase_seconds"]["loading_evidence"] = round(time.perf_counter() - phase_loading_started, 4)

                    _stream_json_event(self, {"type": "status", "phase": "building_prompt", "message": "Building grounded prompt..."})
                    phase_prompt_started = time.perf_counter()
                    prompt = _build_chat_prompt(messages, filtered_rows, context_limit, language)
                    trace["phase_seconds"]["building_prompt"] = round(time.perf_counter() - phase_prompt_started, 4)
                    _stream_json_event(self, {"type": "status", "phase": "generating", "message": "Generating answer..."})

                    phase_generation_started = time.perf_counter()
                    streamed_chunks: list[str] = []
                    for chunk in generate_with_ollama_stream(
                        prompt=prompt,
                        model=model,
                        host=host,
                        temperature=temperature,
                        timeout_seconds=timeout_seconds,
                    ):
                        streamed_chunks.append(chunk)
                        _stream_json_event(self, {"type": "chunk", "delta": chunk})

                    answer = "".join(streamed_chunks).strip()
                    if not answer:
                        raise LocalLLMError("Local LLM response was empty.")

                    generated_seconds = time.perf_counter() - phase_generation_started
                    trace["phase_seconds"]["generating"] = round(generated_seconds, 4)

                    _stream_json_event(self, {"type": "status", "phase": "post_processing", "message": "Linking citations and synthesis metadata..."})
                    phase_post_started = time.perf_counter()
                    contradictions = _contradiction_pairs_from_rows(filtered_rows, limit=300)
                    synthesis = _build_synthesis(answer=answer, evidence_rows=filtered_rows, contradiction_rows=contradictions)
                    synthesis, guardrail_flags = _apply_response_guardrails(
                      answer=answer,
                      synthesis=synthesis,
                      evidence_rows=filtered_rows,
                      contradiction_rows=contradictions,
                      language=language,
                    )
                    mentioned_claim_ids = synthesis.get("mentioned_claim_ids") if isinstance(synthesis.get("mentioned_claim_ids"), list) else []
                    mentioned_claim_id_set = {str(x) for x in mentioned_claim_ids if str(x).strip()}
                    cited_evidence_rows = [
                        row for row in filtered_rows if str(row.get("claim_id", "")).strip() in mentioned_claim_id_set
                    ]
                    cited_evidence_rows = _rank_cited_evidence_rows(cited_evidence_rows)
                    cited_evidence_rows = cited_evidence_rows[:MAX_CITED_EVIDENCE_ROWS]
                    if _should_translate_cited_rows(payload=payload, language=language):
                      cited_evidence_rows = _translate_evidence_rows_for_language(
                        rows=cited_evidence_rows,
                        language=language,
                        model=model,
                        host=host,
                        temperature=temperature,
                        timeout_seconds=min(timeout_seconds, 20),
                        max_rows=20,
                      )
                    trace["phase_seconds"]["post_processing"] = round(time.perf_counter() - phase_post_started, 4)
                    trace["evidence_count"] = len(filtered_rows)
                    trace["cited_evidence_count"] = len(cited_evidence_rows)
                    trace["guardrail_flags"] = guardrail_flags
                    trace["verification_flags"] = (
                        synthesis.get("verification_flags")
                        if isinstance(synthesis.get("verification_flags"), list)
                        else []
                    )
                    trace["total_seconds"] = round(sum(float(v) for v in trace["phase_seconds"].values()), 4)
                    _append_query_telemetry(trace)
                    if current_user is not None:
                        self._record_activity(
                            settings=settings,
                            user_id=str(current_user["user_id"]),
                            activity_type="chat_stream",
                            endpoint=path,
                            payload={"evidence_count": len(filtered_rows), "trace_id": str(trace.get("trace_id", ""))},
                        )

                    _stream_json_event(
                        self,
                        {
                            "type": "final",
                            "answer": answer,
                            "evidence_count": len(filtered_rows),
                            "model": model,
                            "host": host,
                            "generated_seconds": round(generated_seconds, 3),
                            "synthesis": synthesis,
                            "evidence_rows": cited_evidence_rows,
                            "response_mode": "stream",
                            "guardrail_flags": guardrail_flags,
                            "telemetry": trace,
                        },
                    )
                except Exception as exc:
                    trace["status"] = "error"
                    trace["error"] = str(exc)
                    trace["total_seconds"] = round(time.perf_counter() - trace_started_perf, 4)
                    _append_query_telemetry(trace)
                    _stream_json_event(self, {"type": "error", "error": str(exc)})
                self.close_connection = True
                return

            if path == "/api/session/save":
                if current_user is None:
                    _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                    return
                session_id = str(payload.get("session_id", "")).strip()
                if not session_id:
                    raise ValueError("session_id is required")

                title = str(payload.get("title", "")).strip()
                question = str(payload.get("question", "")).strip()
                messages = payload.get("messages", [])
                report = payload.get("report", {})
                filters = payload.get("filters", {})
                evidence_claim_ids = payload.get("evidence_claim_ids", [])

                if not isinstance(messages, list):
                    raise ValueError("messages must be a list")
                if not isinstance(report, dict):
                    raise ValueError("report must be an object")
                if not isinstance(filters, dict):
                    raise ValueError("filters must be an object")
                if not isinstance(evidence_claim_ids, list):
                    raise ValueError("evidence_claim_ids must be a list")

                store = self._store(str(settings["db_path"]))
                saved = store.save_investigator_session(
                    user_id=str(current_user["user_id"]),
                    session_id=session_id,
                    title=title,
                    question=question,
                    messages=[m for m in messages if isinstance(m, dict)],
                    report=report,
                    filters=filters,
                    evidence_claim_ids=[str(cid) for cid in evidence_claim_ids if str(cid).strip()],
                )
                self._record_activity(
                    settings=settings,
                    user_id=str(current_user["user_id"]),
                    activity_type="session_save",
                    endpoint=path,
                    payload={"session_id": session_id, "message_count": len(messages)},
                )
                _json_response(self, HTTPStatus.OK, saved)
                return

            if path == "/api/evidence/compare":
                claim_a = str(payload.get("claim_a", "")).strip()
                claim_b = str(payload.get("claim_b", "")).strip()
                if not claim_a or not claim_b:
                    raise ValueError("claim_a and claim_b are required")
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                left = store.claim_lineage(claim_a)
                right = store.claim_lineage(claim_b)

                left_support = {
                    str(row.get("claim_id", ""))
                    for row in left.get("lineage", {}).get("supporting_citations", [])
                }
                right_support = {
                    str(row.get("claim_id", ""))
                    for row in right.get("lineage", {}).get("supporting_citations", [])
                }
                left_contra = {
                    str(row.get("claim_id", ""))
                    for row in left.get("lineage", {}).get("contradicting_citations", [])
                }
                right_contra = {
                    str(row.get("claim_id", ""))
                    for row in right.get("lineage", {}).get("contradicting_citations", [])
                }

                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "claim_a": left.get("claim", {}),
                        "claim_b": right.get("claim", {}),
                        "shared_supporting_count": len(left_support & right_support),
                        "shared_contradicting_count": len(left_contra & right_contra),
                    "follow_up_suggestion": (
                      "Run a stratified follow-up experiment focused on endpoint differences across cohorts and study design."
                    ),
                    },
                )
                return

            if path == "/api/export/summary":
                report = payload.get("report", {})
                if not isinstance(report, dict):
                    raise ValueError("report must be an object")
                locale, _ = self._resolve_request_locale({})
                payload_locale = str(payload.get("language", "")).strip()
                if payload_locale:
                    from als_intel.i18n import normalize_locale

                    normalized_payload_locale = normalize_locale(payload_locale)
                    if normalized_payload_locale is not None:
                        locale = normalized_payload_locale
                markdown = _build_report_markdown(report, locale=locale)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "json_filename": "synthesis_report.json",
                        "json_content": json.dumps(report, indent=2),
                        "markdown_filename": "synthesis_report.md",
                        "markdown_content": markdown,
                    },
                )
                return

            if path == "/api/database/nodes":
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                rows = _attach_source_urls_to_rows(store.all_evidence())
                rows.sort(
                    key=lambda row: (
                        -int(row.get("year", 0) or 0),
                        -float(row.get("reliability_score", 0.0) or 0.0),
                    )
                )
                query = str(payload.get("query", ""))
                searched_rows = _search_evidence_rows(rows, query)
                limit = _parse_positive_int(payload.get("limit", 25), 25, max_value=200)
                offset = _parse_non_negative_int(payload.get("offset", 0), 0)
                page_rows, total, has_more = _paginate_rows(searched_rows, limit=limit, offset=offset)
                enriched_rows: list[dict[str, object]] = []
                for row in page_rows:
                    row_claim_id = str(row.get("claim_id", "")).strip()
                    source_metadata = store.get_evidence_source_metadata(row_claim_id) if row_claim_id else None
                    row_with_meta: dict[str, object] = dict(row)
                    if source_metadata is not None:
                        metadata_payload = source_metadata.get("metadata", {})
                        if not isinstance(metadata_payload, dict):
                            metadata_payload = {}
                        row_with_meta["source_metadata"] = {
                            "journal": str(source_metadata.get("journal", "") or ""),
                            "pubdate": str(source_metadata.get("pubdate", "") or ""),
                            "authors_count": len(source_metadata.get("authors", [])),
                            "mesh_terms_count": len(source_metadata.get("mesh_terms", [])),
                            "has_abstract": bool(str(source_metadata.get("abstract_text", "") or "").strip()),
                            "enriched_at": str(source_metadata.get("enriched_at", "") or ""),
                            "api_endpoint": str(metadata_payload.get("api_endpoint", "") or ""),
                            "query_used": str(metadata_payload.get("query_used", "") or ""),
                            "source_version": str(metadata_payload.get("source_version", "") or ""),
                            "source_license": str(metadata_payload.get("source_license", "") or ""),
                        }
                    enriched_rows.append(row_with_meta)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": enriched_rows,
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                        "has_more": has_more,
                    },
                )
                return

            if path == "/api/database/node/metadata":
                claim_id = str(payload.get("claim_id", "")).strip()
                if not claim_id:
                    raise ValueError("claim_id is required")
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                metadata = store.get_evidence_source_metadata(claim_id)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "claim_id": claim_id,
                        "found": metadata is not None,
                        "metadata": metadata,
                    },
                )
                return

            if path == "/api/review/flags":
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                delta_threshold = float(payload.get("delta_threshold", 0.15) or 0.15)
                contradiction_density_threshold = float(payload.get("contradiction_density_threshold", 0.34) or 0.34)
                flags = store.review_flags(
                    delta_threshold=delta_threshold,
                    contradiction_density_threshold=contradiction_density_threshold,
                )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "flags": flags,
                        "total": len(flags),
                    },
                )
                return

            if path == "/api/review/decision":
                claim_id = str(payload.get("claim_id", "")).strip()
                decision = str(payload.get("decision", "")).strip()
                reviewer = str(payload.get("reviewer", "")).strip()
                notes = str(payload.get("notes", "")).strip()
                if not claim_id:
                    raise ValueError("claim_id is required")
                if not decision:
                    raise ValueError("decision is required")
                if not reviewer:
                    raise ValueError("reviewer is required")

                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                store.record_review_decision(
                    claim_id=claim_id,
                    decision=decision,
                    reviewer=reviewer,
                    notes=notes,
                )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "claim_id": claim_id,
                        "decision": decision,
                        "reviewer": reviewer,
                    },
                )
                return

            if path == "/api/review/decisions":
                claim_id = str(payload.get("claim_id", "")).strip() or None
                limit = _parse_positive_int(payload.get("limit", 20), 20, max_value=200)
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                rows = store.list_review_decisions(claim_id=claim_id, limit=limit)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": rows,
                        "total": len(rows),
                        "limit": limit,
                    },
                )
                return

            if path == "/api/hypothesis/queue":
                from als_intel.hypothesis import build_hypothesis_queue

                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                evidence_rows = store.all_evidence()
                contradiction_rows = store.contradiction_pairs()

                limit = _parse_positive_int(payload.get("limit", 8), 8, max_value=50)
                require_review_signoff = bool(payload.get("require_review_signoff", False))
                enforce_causal_gate = bool(payload.get("enforce_causal_gate", False))
                overrides_raw = payload.get("causal_gate_override_entities", [])
                if not isinstance(overrides_raw, list):
                    overrides_raw = []
                overrides = {str(x).strip() for x in overrides_raw if str(x).strip()}

                approved_claim_ids = store.approved_claim_ids() if require_review_signoff else set()

                queue = build_hypothesis_queue(
                    evidence_rows=evidence_rows,
                    contradiction_rows=contradiction_rows,
                    limit=limit,
                    require_review_signoff=require_review_signoff,
                    approved_claim_ids=approved_claim_ids,
                    enforce_causal_gate=enforce_causal_gate,
                    causal_promotion_overrides=overrides,
                )
                baseline_queue = build_hypothesis_queue(
                    evidence_rows=evidence_rows,
                    contradiction_rows=contradiction_rows,
                    limit=limit,
                    require_review_signoff=False,
                    approved_claim_ids=set(),
                    enforce_causal_gate=False,
                    causal_promotion_overrides=set(),
                )
                baseline_entities = {str(row.get("entity", "")).strip() for row in baseline_queue if str(row.get("entity", "")).strip()}
                queue_entities = {str(row.get("entity", "")).strip() for row in queue if str(row.get("entity", "")).strip()}
                removed_entities = sorted(baseline_entities - queue_entities)

                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "queue": queue,
                        "baseline_total": len(baseline_queue),
                        "total": len(queue),
                        "removed_entities": removed_entities,
                        "require_review_signoff": require_review_signoff,
                        "enforce_causal_gate": enforce_causal_gate,
                    },
                )
                return

            if path == "/api/investigation/runs/start":
                if current_user is None:
                    _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                    return
                objective = str(payload.get("objective", "")).strip()
                if not objective:
                    raise ValueError("objective is required")
                filters = payload.get("filters", {})
                if not isinstance(filters, dict):
                    raise ValueError("filters must be an object")
                require_review_signoff = bool(payload.get("require_review_signoff", False))
                idempotency_key = str(payload.get("idempotency_key", "")).strip()
                max_attempts = _parse_positive_int(payload.get("max_attempts", 1), 1, max_value=10)

                store = self._store(str(settings["db_path"]))
                if idempotency_key:
                    existing = store.find_investigation_run_by_idempotency(
                        user_id=str(current_user["user_id"]),
                        idempotency_key=idempotency_key,
                    )
                    if existing is not None:
                        _json_response(self, HTTPStatus.OK, existing)
                        return
                run_id = f"run_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                store.create_investigation_run(
                    run_id=run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                    idempotency_key=idempotency_key,
                    max_attempts=max_attempts,
                    replay_of_run_id="",
                )
                try:
                    _execute_investigation_run(
                        store=store,
                        user_id=str(current_user["user_id"]),
                        run_id=run_id,
                        objective=objective,
                        filters=filters,
                        require_review_signoff=require_review_signoff,
                    )
                except Exception as exc:
                    retry_state = store.retry_or_fail_investigation_run(
                        user_id=str(current_user["user_id"]),
                        run_id=run_id,
                        error_text=str(exc),
                        backoff_seconds=_parse_positive_int(
                            os.getenv("ALS_RUN_RETRY_BACKOFF_SECONDS", "30"),
                            30,
                            max_value=3600,
                        ),
                    )
                    if not bool(retry_state.get("requeued", False)):
                        raise

                final_row = store.get_investigation_run(user_id=str(current_user["user_id"]), run_id=run_id)
                self._record_activity(
                    settings=settings,
                    user_id=str(current_user["user_id"]),
                    activity_type="investigation_run_started",
                    endpoint=path,
                    payload={"run_id": run_id, "objective": objective, "idempotency_key": idempotency_key},
                )
                _json_response(self, HTTPStatus.OK, final_row)
                return

            if path == "/api/investigation/runs/queue":
                if current_user is None:
                    _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                    return
                objective = str(payload.get("objective", "")).strip()
                if not objective:
                    raise ValueError("objective is required")
                filters = payload.get("filters", {})
                if not isinstance(filters, dict):
                    raise ValueError("filters must be an object")
                require_review_signoff = bool(payload.get("require_review_signoff", False))
                idempotency_key = str(payload.get("idempotency_key", "")).strip()
                delay_seconds = _parse_non_negative_int(payload.get("delay_seconds", 0), 0, max_value=86400)
                max_attempts = _parse_positive_int(payload.get("max_attempts", 3), 3, max_value=10)

                store = self._store(str(settings["db_path"]))
                if idempotency_key:
                    existing = store.find_investigation_run_by_idempotency(
                        user_id=str(current_user["user_id"]),
                        idempotency_key=idempotency_key,
                    )
                    if existing is not None:
                        _json_response(self, HTTPStatus.OK, existing)
                        return

                run_id = f"run_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                scheduled_for = (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat()
                queued = store.queue_investigation_run(
                    run_id=run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                    idempotency_key=idempotency_key,
                    scheduled_for=scheduled_for,
                    max_attempts=max_attempts,
                )
                self._record_activity(
                    settings=settings,
                    user_id=str(current_user["user_id"]),
                    activity_type="investigation_run_queued",
                    endpoint=path,
                    payload={"run_id": run_id, "scheduled_for": scheduled_for, "delay_seconds": delay_seconds},
                )
                _json_response(self, HTTPStatus.OK, queued)
                return

            if path == "/api/investigation/runs/approve":
                if current_user is None:
                  _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                  return
                run_id = str(payload.get("run_id", "")).strip()
                decision = str(payload.get("decision", "approved")).strip().lower()
                reviewer = str(payload.get("reviewer") or current_user.get("email") or current_user.get("user_id") or "").strip()
                if not run_id:
                  raise ValueError("run_id is required")
                if decision not in {"approved", "rejected", "pending"}:
                  raise ValueError("decision must be approved, rejected, or pending")

                store = self._store(str(settings["db_path"]))
                row = store.set_investigation_run_approval(
                  user_id=str(current_user["user_id"]),
                  run_id=run_id,
                  status=decision,
                  reviewer=reviewer,
                )
                _json_response(self, HTTPStatus.OK, row)
                return

            if path == "/api/investigation/runs/rollback":
                if current_user is None:
                  _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                  return
                source_run_id = str(payload.get("run_id", "")).strip()
                if not source_run_id:
                  raise ValueError("run_id is required")
                reason = str(payload.get("reason", "Rollback requested")).strip() or "Rollback requested"
                queue_mode = bool(payload.get("queue", True))
                delay_seconds = _parse_non_negative_int(payload.get("delay_seconds", 0), 0, max_value=86400)

                store = self._store(str(settings["db_path"]))
                source_run = store.get_investigation_run(
                  user_id=str(current_user["user_id"]),
                  run_id=source_run_id,
                )
                objective = str(source_run.get("objective", "")).strip()
                filters = source_run.get("filters") if isinstance(source_run.get("filters"), dict) else {}
                require_review_signoff = bool(source_run.get("require_review_signoff", False))
                max_attempts = int(source_run.get("max_attempts") or 3)

                rollback_run_id = f"run_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                if queue_mode:
                  rollback_row = store.queue_investigation_run(
                    run_id=rollback_run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                    idempotency_key=f"rollback:{source_run_id}:{rollback_run_id}",
                    scheduled_for=(datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat(),
                    max_attempts=max_attempts,
                  )
                else:
                  store.create_investigation_run(
                    run_id=rollback_run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                    idempotency_key=f"rollback:{source_run_id}:{rollback_run_id}",
                    max_attempts=max_attempts,
                  )
                  rollback_row = _execute_investigation_run(
                    store=store,
                    user_id=str(current_user["user_id"]),
                    run_id=rollback_run_id,
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                  )

                source_after = store.mark_investigation_run_rolled_back(
                  user_id=str(current_user["user_id"]),
                  run_id=source_run_id,
                  rollback_run_id=rollback_run_id,
                )
                _json_response(
                  self,
                  HTTPStatus.OK,
                  {
                    "source_run": source_after,
                    "rollback_run": rollback_row,
                    "reason": reason,
                  },
                )
                return

            if path == "/api/investigation/templates/save":
                if current_user is None:
                  _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                  return
                name = str(payload.get("name", "")).strip()
                objective = str(payload.get("objective", "")).strip()
                filters = payload.get("filters", {})
                require_review_signoff = bool(payload.get("require_review_signoff", False))
                template_id = str(payload.get("template_id", "")).strip()
                if not name:
                  raise ValueError("name is required")
                if not objective:
                  raise ValueError("objective is required")
                if not isinstance(filters, dict):
                  raise ValueError("filters must be an object")
                if not template_id:
                  template_id = f"tpl_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"

                store = self._store(str(settings["db_path"]))
                saved = store.save_investigation_template(
                  template_id=template_id,
                  user_id=str(current_user["user_id"]),
                  name=name,
                  objective=objective,
                  filters=filters,
                  require_review_signoff=require_review_signoff,
                )
                _json_response(self, HTTPStatus.OK, saved)
                return

            if path == "/api/investigation/templates/run":
                if current_user is None:
                  _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                  return
                template_id = str(payload.get("template_id", "")).strip()
                if not template_id:
                  raise ValueError("template_id is required")
                queue_mode = bool(payload.get("queue", True))
                delay_seconds = _parse_non_negative_int(payload.get("delay_seconds", 0), 0, max_value=86400)
                max_attempts = _parse_positive_int(payload.get("max_attempts", 3), 3, max_value=10)

                store = self._store(str(settings["db_path"]))
                template = store.get_investigation_template(
                  user_id=str(current_user["user_id"]),
                  template_id=template_id,
                )
                store.touch_investigation_template(
                  user_id=str(current_user["user_id"]),
                  template_id=template_id,
                )
                objective = str(template.get("objective", ""))
                filters = template.get("filters") if isinstance(template.get("filters"), dict) else {}
                require_review_signoff = bool(template.get("require_review_signoff", False))
                run_id = f"run_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                if queue_mode:
                  row = store.queue_investigation_run(
                    run_id=run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                    idempotency_key=f"template:{template_id}:{run_id}",
                    scheduled_for=(datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat(),
                    max_attempts=max_attempts,
                  )
                else:
                  store.create_investigation_run(
                    run_id=run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                    idempotency_key=f"template:{template_id}:{run_id}",
                    max_attempts=max_attempts,
                  )
                  row = _execute_investigation_run(
                    store=store,
                    user_id=str(current_user["user_id"]),
                    run_id=run_id,
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                  )
                _json_response(
                  self,
                  HTTPStatus.OK,
                  {
                    "template": template,
                    "run": row,
                  },
                )
                return

            if path == "/api/automation/experiments/run":
                if current_user is None:
                  _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                  return
                name = str(payload.get("name", "")).strip() or "Automation experiment"
                objective = str(payload.get("objective", "")).strip()
                base_filters = payload.get("filters", {})
                variant_a = payload.get("variant_a", {})
                variant_b = payload.get("variant_b", {})
                if not objective:
                  raise ValueError("objective is required")
                if not isinstance(base_filters, dict):
                  raise ValueError("filters must be an object")
                if not isinstance(variant_a, dict) or not isinstance(variant_b, dict):
                  raise ValueError("variant_a and variant_b must be objects")

                variant_a_filters = variant_a.get("filters", {}) if isinstance(variant_a.get("filters"), dict) else {}
                variant_b_filters = variant_b.get("filters", {}) if isinstance(variant_b.get("filters"), dict) else {}
                require_signoff_a = bool(variant_a.get("require_review_signoff", False))
                require_signoff_b = bool(variant_b.get("require_review_signoff", False))

                store = self._store(str(settings["db_path"]))
                run_id_a = f"run_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                run_id_b = f"run_{int(time.time() * 1000) + 1}_{int(time.perf_counter() * 1000) % 1000:03d}"

                merged_a = dict(base_filters)
                merged_a.update(variant_a_filters)
                merged_b = dict(base_filters)
                merged_b.update(variant_b_filters)

                store.create_investigation_run(
                  run_id=run_id_a,
                  user_id=str(current_user["user_id"]),
                  objective=objective,
                  filters=merged_a,
                  require_review_signoff=require_signoff_a,
                  idempotency_key=f"exp:{name}:a:{run_id_a}",
                  max_attempts=1,
                )
                result_a = _execute_investigation_run(
                  store=store,
                  user_id=str(current_user["user_id"]),
                  run_id=run_id_a,
                  objective=objective,
                  filters=merged_a,
                  require_review_signoff=require_signoff_a,
                )

                store.create_investigation_run(
                  run_id=run_id_b,
                  user_id=str(current_user["user_id"]),
                  objective=objective,
                  filters=merged_b,
                  require_review_signoff=require_signoff_b,
                  idempotency_key=f"exp:{name}:b:{run_id_b}",
                  max_attempts=1,
                )
                result_b = _execute_investigation_run(
                  store=store,
                  user_id=str(current_user["user_id"]),
                  run_id=run_id_b,
                  objective=objective,
                  filters=merged_b,
                  require_review_signoff=require_signoff_b,
                )

                score_a = _score_experiment_variant(result_a)
                score_b = _score_experiment_variant(result_b)
                winner = "a" if score_a >= score_b else "b"
                experiment_id = f"exp_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                experiment = store.create_automation_experiment(
                  experiment_id=experiment_id,
                  user_id=str(current_user["user_id"]),
                  name=name,
                  objective=objective,
                  filters=base_filters,
                  variant_a=variant_a,
                  variant_b=variant_b,
                  result={
                    "run_id_a": run_id_a,
                    "run_id_b": run_id_b,
                    "score_a": score_a,
                    "score_b": score_b,
                  },
                  winner_variant=winner,
                )
                _json_response(self, HTTPStatus.OK, experiment)
                return

            if path == "/api/export/automated":
                if current_user is None:
                  _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                  return
                run_id = str(payload.get("run_id", "")).strip()
                channel = str(payload.get("channel", "markdown_file")).strip().lower()
                if not run_id:
                  raise ValueError("run_id is required")
                if channel not in {"markdown_file", "json_file", "webhook"}:
                  raise ValueError("channel must be markdown_file, json_file, or webhook")

                store = self._store(str(settings["db_path"]))
                run_row = store.get_investigation_run(user_id=str(current_user["user_id"]), run_id=run_id)
                report = run_row.get("report") if isinstance(run_row.get("report"), dict) else {}
                locale, _ = self._resolve_request_locale({})
                markdown = _build_report_markdown(report, locale=locale)
                delivery_id = f"dly_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"

                result_payload: dict[str, object] = {}
                status = "delivered"
                error_text = ""
                if channel in {"markdown_file", "json_file"}:
                  export_dir = str(os.getenv("ALS_AUTOMATION_EXPORT_DIR", "data/automation_exports")).strip() or "data/automation_exports"
                  os.makedirs(export_dir, exist_ok=True)
                  suffix = "md" if channel == "markdown_file" else "json"
                  file_path = os.path.join(export_dir, f"{run_id}.{suffix}")
                  content = markdown if channel == "markdown_file" else json.dumps(report, indent=2)
                  with open(file_path, "w", encoding="utf-8") as handle:
                    handle.write(content)
                  result_payload = {"file_path": file_path, "bytes": len(content.encode("utf-8"))}
                else:
                  webhook_url = str(payload.get("webhook_url", "")).strip()
                  if not webhook_url:
                    raise ValueError("webhook_url is required for webhook channel")
                  try:
                    req = Request(
                      webhook_url,
                      data=json.dumps(
                        {
                          "run_id": run_id,
                          "objective": run_row.get("objective", ""),
                          "quality_gate": run_row.get("quality_gate", {}),
                          "report": report,
                          "markdown": markdown,
                        },
                        ensure_ascii=True,
                      ).encode("utf-8"),
                      headers={"Content-Type": "application/json"},
                      method="POST",
                    )
                    with urlopen(req, timeout=float(os.getenv("ALS_AUTOMATION_EXPORT_TIMEOUT_SECONDS", "8") or "8")) as resp:
                      result_payload = {
                        "status_code": int(getattr(resp, "status", 200)),
                        "reason": str(getattr(resp, "reason", "")),
                      }
                  except (HTTPError, URLError, TimeoutError) as exc:
                    status = "failed"
                    error_text = str(exc)
                    result_payload = {"error": error_text}

                store.set_investigation_run_export_status(
                  user_id=str(current_user["user_id"]),
                  run_id=run_id,
                  export_status="delivered" if status == "delivered" else "failed",
                )
                export_row = store.record_automation_export(
                  delivery_id=delivery_id,
                  user_id=str(current_user["user_id"]),
                  run_id=run_id,
                  channel=channel,
                  payload={"run_id": run_id, "channel": channel},
                  result=result_payload,
                  status=status,
                  error_text=error_text,
                )
                if status != "delivered":
                  _json_response(self, HTTPStatus.BAD_GATEWAY, export_row)
                  return
                _json_response(self, HTTPStatus.OK, export_row)
                return

            if path == "/api/investigation/runs/replay":
                if current_user is None:
                    _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                    return
                source_run_id = str(payload.get("source_run_id", "")).strip()
                if not source_run_id:
                    raise ValueError("source_run_id is required")

                store = self._store(str(settings["db_path"]))
                baseline_run = store.get_investigation_run(user_id=str(current_user["user_id"]), run_id=source_run_id)
                objective = str(baseline_run.get("objective", "")).strip()
                filters = baseline_run.get("filters") if isinstance(baseline_run.get("filters"), dict) else {}

                run_id = f"run_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                store.create_investigation_run(
                    run_id=run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                  require_review_signoff=False,
                    replay_of_run_id=source_run_id,
                )

                evidence_rows = _attach_source_urls_to_rows(store.all_evidence())
                filtered_rows = _apply_evidence_filters(evidence_rows, filters)
                contradictions = store.contradiction_pairs()
                report = _build_autonomous_run_report(
                    objective=objective,
                    filters=filters,
                    evidence_rows=filtered_rows,
                    contradiction_rows=contradictions,
                    require_review_signoff=False,
                    approved_claim_ids=set(),
                )
                gate = _evaluate_report_gate(
                    report_payload=report,
                    evidence_rows=filtered_rows,
                    contradiction_rows=contradictions,
                )
                replay_diff = _build_replay_diff(
                    baseline_run=baseline_run,
                    current_report=report,
                    current_quality_gate=gate,
                )
                store.complete_investigation_run(
                    user_id=str(current_user["user_id"]),
                    run_id=run_id,
                    status="completed",
                    report=report,
                    quality_gate=gate,
                    replay_diff=replay_diff,
                )

                final_row = store.get_investigation_run(user_id=str(current_user["user_id"]), run_id=run_id)
                self._record_activity(
                    settings=settings,
                    user_id=str(current_user["user_id"]),
                    activity_type="investigation_run_replayed",
                    endpoint=path,
                    payload={"run_id": run_id, "source_run_id": source_run_id},
                )
                _json_response(self, HTTPStatus.OK, final_row)
                return

            settings = self._settings()
            db_path = str(payload.get("db_path") or settings["db_path"])
            store = self._store(db_path)

            filters = payload.get("filters", {})
            if not isinstance(filters, dict):
                filters = {}
            filtered_rows = _attach_source_urls_to_rows(
              store.filter_evidence(
                filters=filters,
                limit=_resolve_chat_evidence_limit(payload),
              )
            )

            limit = _parse_positive_int(payload.get("limit", 50), 50, max_value=500)
            offset = _parse_non_negative_int(payload.get("offset", 0), 0)

            if path == "/api/evidence/filter":
                page_rows, total, has_more = _paginate_rows(filtered_rows, limit=limit, offset=offset)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": page_rows,
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                        "has_more": has_more,
                    },
                )
                return

            if path == "/api/evidence/search":
                query = str(payload.get("query", ""))
                searched_rows = _search_evidence_rows(filtered_rows, query)
                page_rows, total, has_more = _paginate_rows(searched_rows, limit=limit, offset=offset)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": page_rows,
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                        "has_more": has_more,
                    },
                )
                return

            if path == "/api/synthesis":
                require_review_signoff = bool(payload.get("require_review_signoff", False))
                approved_claim_ids_raw = payload.get("approved_claim_ids", [])
                if not isinstance(approved_claim_ids_raw, list):
                    raise ValueError("approved_claim_ids must be a list")
                approved_claim_ids = {str(x) for x in approved_claim_ids_raw if str(x).strip()}
                contradictions = _contradiction_pairs_from_rows(filtered_rows, limit=300)
                composition = _build_investigator_synthesis(
                    evidence_rows=filtered_rows,
                    contradiction_rows=contradictions,
                    require_review_signoff=require_review_signoff,
                    approved_claim_ids=approved_claim_ids,
                    store=store,
                )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "evidence_count": len(filtered_rows),
                        "composition": composition,
                    },
                )
                return

            raw_messages = payload.get("messages", [])
            if not isinstance(raw_messages, list):
                raise ValueError("messages must be a list")
            messages = [message for message in raw_messages if isinstance(message, dict)][-40:]

            host = str(payload.get("host") or settings["ollama_host"])
            model = str(payload.get("model") or settings["model"])
            context_limit = _parse_positive_int(payload.get("context_limit") or settings["context_limit"], int(settings["context_limit"]), max_value=200)
            temperature = float(payload.get("temperature") or settings["temperature"])
            timeout_seconds = int(payload.get("timeout_seconds") or settings["timeout_seconds"])
            language = str(payload.get("language") or "en").strip().lower()
            if language not in {"en", "es"}:
              language = "en"

            trace: dict[str, object] = {
              "trace_id": _new_trace_id(),
              "mode": "sync",
              "path": path,
              "started_at": int(time.time()),
              "status": "ok",
              "model": model,
              "language": language,
              "phase_seconds": {},
            }
            if current_user is not None:
                trace["user_id"] = str(current_user.get("user_id", ""))

            phase_prompt_started = time.perf_counter()
            prompt = _build_chat_prompt(messages, filtered_rows, context_limit, language)
            trace["phase_seconds"]["building_prompt"] = round(time.perf_counter() - phase_prompt_started, 4)

            phase_generation_started = time.perf_counter()
            answer = generate_with_ollama(
                prompt=prompt,
                model=model,
                host=host,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
            )
            generated_seconds = time.perf_counter() - phase_generation_started
            trace["phase_seconds"]["generating"] = round(generated_seconds, 4)

            phase_post_started = time.perf_counter()
            contradictions = _contradiction_pairs_from_rows(filtered_rows, limit=300)
            synthesis = _build_synthesis(answer=answer, evidence_rows=filtered_rows, contradiction_rows=contradictions)
            synthesis, guardrail_flags = _apply_response_guardrails(
                answer=answer,
                synthesis=synthesis,
                evidence_rows=filtered_rows,
                contradiction_rows=contradictions,
              language=language,
            )
            mentioned_claim_ids = synthesis.get("mentioned_claim_ids") if isinstance(synthesis.get("mentioned_claim_ids"), list) else []
            mentioned_claim_id_set = {str(x) for x in mentioned_claim_ids if str(x).strip()}
            cited_evidence_rows = [
              row for row in filtered_rows if str(row.get("claim_id", "")).strip() in mentioned_claim_id_set
            ]
            cited_evidence_rows = _rank_cited_evidence_rows(cited_evidence_rows)
            cited_evidence_rows = cited_evidence_rows[:MAX_CITED_EVIDENCE_ROWS]
            if _should_translate_cited_rows(payload=payload, language=language):
              cited_evidence_rows = _translate_evidence_rows_for_language(
                rows=cited_evidence_rows,
                language=language,
                model=model,
                host=host,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
              )
            trace["phase_seconds"]["post_processing"] = round(time.perf_counter() - phase_post_started, 4)
            trace["phase_seconds"]["loading_evidence"] = 0.0
            trace["evidence_count"] = len(filtered_rows)
            trace["cited_evidence_count"] = len(cited_evidence_rows)
            trace["guardrail_flags"] = guardrail_flags
            trace["verification_flags"] = (
                synthesis.get("verification_flags")
                if isinstance(synthesis.get("verification_flags"), list)
                else []
            )
            trace["total_seconds"] = round(sum(float(v) for v in trace["phase_seconds"].values()), 4)
            _append_query_telemetry(trace)
            if current_user is not None:
              self._record_activity(
                settings=settings,
                user_id=str(current_user["user_id"]),
                activity_type="chat_sync",
                endpoint=path,
                payload={"evidence_count": len(filtered_rows), "trace_id": str(trace.get("trace_id", ""))},
              )

            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "answer": answer,
                    "evidence_count": len(filtered_rows),
                    "model": model,
                    "host": host,
                    "generated_seconds": round(generated_seconds, 3),
                    "synthesis": synthesis,
                    "evidence_rows": cited_evidence_rows,
                    "response_mode": "sync",
                    "guardrail_flags": guardrail_flags,
                    "telemetry": trace,
                },
            )
        except ValueError as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except LocalLLMError as exc:
            _json_response(self, HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="als-intel-web", description="Local ALS investigator web UI")
    parser.add_argument("--host", default=os.getenv("ALS_WEB_HOST", "0.0.0.0"), help="Host interface to bind")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite evidence database path")
    parser.add_argument("--model", default=DEFAULT_OLLAMA_MODEL, help="Ollama model name")
    parser.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST, help="Ollama base URL")
    parser.add_argument("--context-limit", type=int, default=DEFAULT_CONTEXT_LIMIT, help="Evidence rows included in prompt")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help="LLM sampling temperature")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="LLM request timeout")
    parser.add_argument("--auth-enabled", action="store_true", default=DEFAULT_AUTH_ENABLED, help="Enable authentication guardrails")
    parser.add_argument("--magic-link-dev-mode", action="store_true", default=os.getenv("ALS_MAGIC_LINK_DEV_MODE", "1") in {"1", "true", "True"}, help="Return dev magic links in API responses")
    parser.add_argument("--app-base-url", default=os.getenv("ALS_APP_BASE_URL", "http://localhost:8000"), help="Public base URL used in magic links")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    os.environ["ALS_DB_PATH"] = args.db
    os.environ["OLLAMA_HOST"] = args.ollama_host
    os.environ["OLLAMA_MODEL"] = args.model
    os.environ["ALS_CONTEXT_LIMIT"] = str(args.context_limit)
    os.environ["ALS_TEMPERATURE"] = str(args.temperature)
    os.environ["ALS_TIMEOUT_SECONDS"] = str(args.timeout_seconds)
    os.environ["ALS_AUTH_ENABLED"] = "1" if bool(args.auth_enabled) else "0"
    os.environ["ALS_MAGIC_LINK_DEV_MODE"] = "1" if bool(args.magic_link_dev_mode) else "0"
    os.environ["ALS_APP_BASE_URL"] = str(args.app_base_url)

    server = ThreadingHTTPServer((args.host, args.port), ChatHandler)
    print(f"ALS Intel Investigator UI running on http://{args.host}:{args.port}")
    print(f"Using database: {args.db}")
    print(f"Using Ollama host: {args.ollama_host}")
    print(f"Using model: {args.model}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
