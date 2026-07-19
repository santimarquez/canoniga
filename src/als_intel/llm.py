from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from als_intel.model_catalog import (
    annotate_installed_model,
    family_pref,
    infer_model_size_b,
    recommended_missing,
    tier_rank,
)


DEFAULT_SYSTEM_PROMPT = (
    "You are a scientific ALS research assistant. "
    "Ground answers in the provided evidence context. "
    "Clearly separate evidence-backed statements from uncertainty. "
    "Do not claim cures; propose testable next steps."
)

_COMPLEXITY_KEYWORDS = (
    "compare",
    "contrast",
    "contradict",
    "contradiction",
    "mechanism",
    "mechanistic",
    "causal",
    "causality",
    "pathway",
    "hypothesis",
    "trade-off",
    "tradeoff",
    "systematic",
    "synthesize",
    "synthesis",
    "uncertainty",
    "limitations",
    "validate",
    "replication",
)


class LocalLLMError(RuntimeError):
    pass


def _effective_timeout_seconds(timeout_seconds: int, *, streaming: bool = False) -> int:
    requested = max(1, int(timeout_seconds))
    floor = 180 if streaming else 120
    return max(requested, floor)


def parse_model_allowlist(raw: str | None = None) -> list[str]:
    configured = raw if raw is not None else str(os.getenv("ALS_OLLAMA_MODELS") or "")
    return [part.strip() for part in configured.split(",") if part.strip()]


def _allowlist_matches(name: str, allowlist: list[str]) -> bool:
    if not allowlist:
        return True
    lowered = name.lower()
    for entry in allowlist:
        needle = entry.lower()
        if lowered == needle or lowered.startswith(needle):
            return True
    return False


def list_ollama_models(
    *,
    host: str = "http://localhost:11434",
    default_model: str = "llama3.1:8b",
    allowlist: list[str] | None = None,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Fetch installed Ollama tags, enrich with catalog tiers, and list missing recommended."""
    resolved_host = str(host or "http://localhost:11434").rstrip("/")
    resolved_default = str(default_model or "llama3.1:8b").strip() or "llama3.1:8b"
    filters = list(allowlist) if allowlist is not None else parse_model_allowlist()
    req = Request(url=f"{resolved_host}/api/tags", method="GET")
    try:
        with urlopen(req, timeout=max(1, int(timeout_seconds))) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
    except URLError as exc:
        return {
            "host": resolved_host,
            "default": resolved_default,
            "models": [],
            "recommended": recommended_missing([], limit=12),
            "error": f"Could not reach Ollama at {resolved_host}: {exc}",
        }

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "host": resolved_host,
            "default": resolved_default,
            "models": [],
            "recommended": recommended_missing([], limit=12),
            "error": "Ollama /api/tags returned invalid JSON.",
        }

    models: list[dict[str, object]] = []
    for row in parsed.get("models", []) if isinstance(parsed, dict) else []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("model") or "").strip()
        if not name or not _allowlist_matches(name, filters):
            continue
        size_raw = row.get("size")
        try:
            size = int(size_raw) if size_raw is not None else None
        except (TypeError, ValueError):
            size = None
        models.append(annotate_installed_model(name, size=size))

    models.sort(key=lambda item: str(item.get("name", "")).lower())
    installed_names = [str(item.get("name", "")) for item in models]
    recommended = [
        row
        for row in recommended_missing(installed_names, limit=12)
        if _allowlist_matches(str(row.get("name", "")), filters)
    ]
    return {
        "host": resolved_host,
        "default": resolved_default,
        "models": models,
        "recommended": recommended,
        "error": None,
    }


def score_question_complexity(question: str) -> int:
    text = str(question or "").strip()
    if not text:
        return 0
    lowered = text.lower()
    score = 0
    score += min(4, len(text) // 160)
    score += min(3, lowered.count("?") + lowered.count("\n"))
    sentence_breaks = sum(1 for ch in text if ch in ".!;")
    score += min(2, sentence_breaks)
    hits = sum(1 for keyword in _COMPLEXITY_KEYWORDS if keyword in lowered)
    score += min(5, hits)
    if len(text.split()) >= 40:
        score += 2
    return score


def _auto_pick_model(names: list[str], *, complexity: int, default_name: str) -> str:
    """Pick among installed models using catalog tier + complexity (quality floor)."""
    annotated = [annotate_installed_model(name) for name in names]

    def pick_best(rows: list[dict[str, object]], *, prefer_larger: bool) -> dict[str, object]:
        def key(row: dict[str, object]) -> tuple:
            size = infer_model_size_b(str(row.get("name", "")))
            fam = family_pref(str(row.get("family", "unknown")))
            name = str(row.get("name", "")).lower()
            if prefer_larger:
                # Quality floor: larger first, then known families.
                return (-size, fam, name)
            return (fam, -size, name)

        return sorted(rows, key=key)[0]

    if complexity >= 6:
        # Prefer High/Best; never Fast when a higher tier is installed.
        eligible = [row for row in annotated if tier_rank(str(row.get("tier"))) >= 2]
        if not eligible:
            max_rank = max(tier_rank(str(row.get("tier"))) for row in annotated)
            eligible = [row for row in annotated if tier_rank(str(row.get("tier"))) == max_rank]
        return str(pick_best(eligible, prefer_larger=True).get("name", names[0]))

    if complexity >= 3:
        # Prefer Balanced, else High/Best (skip Fast when anything stronger exists).
        preferred = [row for row in annotated if tier_rank(str(row.get("tier"))) == 1]
        if not preferred:
            preferred = [row for row in annotated if tier_rank(str(row.get("tier"))) >= 1]
        if not preferred:
            preferred = annotated
        return str(pick_best(preferred, prefer_larger=True).get("name", names[0]))

    # Low: prefer Fast, else Balanced (avoid jumping to Best for short questions).
    preferred = [row for row in annotated if tier_rank(str(row.get("tier"))) == 0]
    if not preferred:
        preferred = [row for row in annotated if tier_rank(str(row.get("tier"))) <= 1]
    if not preferred:
        preferred = annotated
    chosen_row = pick_best(preferred, prefer_larger=False)
    chosen_name = str(chosen_row.get("name", ""))
    if (
        default_name in names
        and tier_rank(str(annotate_installed_model(default_name).get("tier")))
        <= tier_rank(str(chosen_row.get("tier"))) + 1
        and infer_model_size_b(default_name) <= infer_model_size_b(chosen_name) + 2
    ):
        return default_name
    return chosen_name


def resolve_chat_model(
    question: str,
    *,
    available: list[str],
    default: str,
    selection: str | None = None,
) -> tuple[str, str]:
    """Return (resolved_model, selection_mode) where selection_mode is auto|manual."""
    names = [str(item).strip() for item in available if str(item).strip()]
    default_name = str(default or "").strip() or "llama3.1:8b"
    requested = str(selection if selection is not None else "").strip()
    if not requested or requested.lower() == "auto":
        if not names:
            return default_name, "auto"
        complexity = score_question_complexity(question)
        return _auto_pick_model(names, complexity=complexity, default_name=default_name), "auto"
    return requested, "manual"


def build_grounded_prompt(question: str, evidence_rows: list[dict[str, object]], context_limit: int = 20) -> str:
    clipped = evidence_rows[: max(context_limit, 1)]
    lines: list[str] = []
    for row in clipped:
        lines.append(
            (
                f"- claim_id={row.get('claim_id')} "
                f"entity={row.get('entity')} "
                f"outcome={row.get('outcome')} "
                f"direction={row.get('effect_direction')} "
                f"study_type={row.get('study_type')} "
                f"causal_type={row.get('causal_evidence_type', 'observational')} "
                f"reliability={row.get('reliability_score')} "
                f"source={row.get('source_doi')}"
            )
        )

    context_block = "\n".join(lines) if lines else "- No evidence rows available."
    return (
        "You are answering using local ALS evidence.\n"
        "Use only the context below and be explicit about uncertainty.\n\n"
        "Execution policy:\n"
        "- Only claim actions as executable now if they can be done with the provided local evidence context.\n"
        "- If a proposed next step needs external datasets/APIs/tools not available in this run, label it as 'Requires external integration:' and name the missing dependency.\n"
        "- Do not imply that external analysis has already been executed unless it is explicitly present in the provided context.\n\n"
        f"Question:\n{question}\n\n"
        "Evidence context:\n"
        f"{context_block}\n\n"
        "Output format (markdown):\n"
        "## Direct Answer\n"
        "<concise evidence-grounded answer>\n\n"
        "## Supporting evidence references\n"
        "<claim_id list, one per line>\n\n"
        "## Contradictions or uncertainty\n"
        "<conflicts, gaps, or limitations>\n\n"
        "## Suggested validation next steps\n"
        "<testable next steps>\n\n"
        "## Executable follow-up query\n"
        "<one concrete investigator question runnable against this local evidence DB, "
        "including specific claim_id values from the evidence context when available, "
        "or write NONE if only external work remains>"
    )


def generate_with_ollama(
    *,
    prompt: str,
    model: str,
    host: str = "http://localhost:11434",
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    temperature: float = 0.1,
    timeout_seconds: int = 60,
) -> str:
    payload = {
        "model": model,
        "system": system_prompt,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url=f"{host.rstrip('/')}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    effective_timeout = _effective_timeout_seconds(timeout_seconds, streaming=False)
    try:
        with urlopen(req, timeout=effective_timeout) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
    except URLError as exc:
        raise LocalLLMError(
            "Could not reach local LLM endpoint. Ensure Ollama is running at "
            f"{host} and the model '{model}' is available."
        ) from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LocalLLMError("Local LLM returned invalid JSON response.") from exc

    text = str(parsed.get("response", "")).strip()
    if not text:
        raise LocalLLMError("Local LLM response was empty.")
    return text


def generate_with_ollama_stream(
    *,
    prompt: str,
    model: str,
    host: str = "http://localhost:11434",
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    temperature: float = 0.1,
    timeout_seconds: int = 60,
) -> Iterator[str]:
    payload = {
        "model": model,
        "system": system_prompt,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": temperature,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url=f"{host.rstrip('/')}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    effective_timeout = _effective_timeout_seconds(timeout_seconds, streaming=True)
    try:
        with urlopen(req, timeout=effective_timeout) as resp:  # noqa: S310
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LocalLLMError("Local LLM returned invalid JSON stream payload.") from exc
                chunk = str(parsed.get("response", ""))
                if chunk:
                    yield chunk
                if bool(parsed.get("done", False)):
                    break
    except URLError as exc:
        raise LocalLLMError(
            "Could not reach local LLM endpoint. Ensure Ollama is running at "
            f"{host} and the model '{model}' is available."
        ) from exc
