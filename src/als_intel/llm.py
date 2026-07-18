from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


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

_SIZE_PATTERNS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"(?:^|[:\-_])70b(?:$|[:\-_])", re.I), 70),
    (re.compile(r"(?:^|[:\-_])65b(?:$|[:\-_])", re.I), 65),
    (re.compile(r"(?:^|[:\-_])34b(?:$|[:\-_])", re.I), 34),
    (re.compile(r"(?:^|[:\-_])33b(?:$|[:\-_])", re.I), 33),
    (re.compile(r"(?:^|[:\-_])32b(?:$|[:\-_])", re.I), 32),
    (re.compile(r"(?:^|[:\-_])27b(?:$|[:\-_])", re.I), 27),
    (re.compile(r"(?:^|[:\-_])22b(?:$|[:\-_])", re.I), 22),
    (re.compile(r"(?:^|[:\-_])14b(?:$|[:\-_])", re.I), 14),
    (re.compile(r"(?:^|[:\-_])13b(?:$|[:\-_])", re.I), 13),
    (re.compile(r"(?:^|[:\-_])12b(?:$|[:\-_])", re.I), 12),
    (re.compile(r"(?:^|[:\-_])9b(?:$|[:\-_])", re.I), 9),
    (re.compile(r"(?:^|[:\-_])8b(?:$|[:\-_])", re.I), 8),
    (re.compile(r"(?:^|[:\-_])7b(?:$|[:\-_])", re.I), 7),
    (re.compile(r"(?:^|[:\-_])4b(?:$|[:\-_])", re.I), 4),
    (re.compile(r"(?:^|[:\-_])3b(?:$|[:\-_])", re.I), 3),
    (re.compile(r"(?:^|[:\-_])2b(?:$|[:\-_])", re.I), 2),
    (re.compile(r"(?:^|[:\-_])1b(?:$|[:\-_])", re.I), 1),
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
    """Fetch installed Ollama tags and optionally filter by allowlist."""
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
            "error": f"Could not reach Ollama at {resolved_host}: {exc}",
        }

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "host": resolved_host,
            "default": resolved_default,
            "models": [],
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
        models.append({"id": name, "name": name, "size": size})

    models.sort(key=lambda item: str(item.get("name", "")).lower())
    return {
        "host": resolved_host,
        "default": resolved_default,
        "models": models,
        "error": None,
    }


def infer_model_size_b(name: str) -> int:
    text = str(name or "").strip().lower()
    for pattern, size in _SIZE_PATTERNS:
        if pattern.search(text):
            return size
    if "gemma2" in text or "gemma-2" in text:
        return 9
    if "gemma" in text:
        return 7
    if "qwen" in text:
        return 7
    if "llama" in text:
        return 8
    if "mistral" in text or "mixtral" in text:
        return 7
    if "phi" in text:
        return 3
    return 5


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
        ranked = sorted(
            names,
            key=lambda name: (infer_model_size_b(name), name.lower()),
        )
        if complexity >= 6:
            chosen = ranked[-1]
        elif complexity >= 3:
            chosen = ranked[len(ranked) // 2]
        else:
            chosen = ranked[0]
        if (
            default_name in names
            and complexity < 3
            and infer_model_size_b(default_name) <= infer_model_size_b(chosen) + 2
        ):
            chosen = default_name
        return chosen, "auto"
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
