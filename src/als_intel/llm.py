from __future__ import annotations

import json
from collections.abc import Iterator
from urllib.error import URLError
from urllib.request import Request, urlopen


DEFAULT_SYSTEM_PROMPT = (
    "You are a scientific ALS research assistant. "
    "Ground answers in the provided evidence context. "
    "Clearly separate evidence-backed statements from uncertainty. "
    "Do not claim cures; propose testable next steps."
)


class LocalLLMError(RuntimeError):
    pass


def _effective_timeout_seconds(timeout_seconds: int, *, streaming: bool = False) -> int:
    requested = max(1, int(timeout_seconds))
    floor = 180 if streaming else 120
    return max(requested, floor)


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
        "Output format:\n"
        "1) Direct answer\n"
        "2) Supporting evidence references (claim_id list)\n"
        "3) Contradictions or uncertainty\n"
        "4) Suggested validation next steps"
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
