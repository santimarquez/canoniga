from __future__ import annotations

from unittest.mock import patch

import json

from als_intel.llm import (
    LocalLLMError,
    _effective_timeout_seconds,
    build_grounded_prompt,
    generate_with_ollama,
    generate_with_ollama_stream,
    infer_model_size_b,
    list_ollama_models,
    resolve_chat_model,
    score_question_complexity,
)


class _FakeResponse:
    def __init__(self, payload: str) -> None:
        self._payload = payload.encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


class _FakeStreamResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = [line.encode("utf-8") for line in lines]

    def __enter__(self) -> "_FakeStreamResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def __iter__(self):
        return iter(self._lines)


def test_build_grounded_prompt_contains_question_and_claims() -> None:
    evidence = [
        {
            "claim_id": "C1",
            "entity": "microglial activation",
            "outcome": "progression_rate",
            "effect_direction": "supports",
            "study_type": "observational",
            "causal_evidence_type": "observational",
            "reliability_score": 0.7,
            "source_doi": "10.1/c1",
        }
    ]
    prompt = build_grounded_prompt("What matters most?", evidence, context_limit=5)
    assert "What matters most?" in prompt
    assert "claim_id=C1" in prompt
    assert "entity=microglial activation" in prompt


def test_effective_timeout_seconds_enforces_floor() -> None:
    assert _effective_timeout_seconds(60, streaming=False) == 120
    assert _effective_timeout_seconds(60, streaming=True) == 180
    assert _effective_timeout_seconds(300, streaming=True) == 300


def test_generate_with_ollama_uses_floored_timeout() -> None:
    with patch("als_intel.llm.urlopen", return_value=_FakeResponse('{"response":"ok answer"}')) as mocked_urlopen:
        generate_with_ollama(prompt="p", model="m", timeout_seconds=10)

    assert mocked_urlopen.call_args.kwargs["timeout"] == 120


def test_generate_with_ollama_stream_uses_floored_timeout() -> None:
    stream_lines = [
        '{"response":"Hi","done":false}\n',
        '{"response":"","done":true}\n',
    ]
    with patch("als_intel.llm.urlopen", return_value=_FakeStreamResponse(stream_lines)) as mocked_urlopen:
        chunks = list(generate_with_ollama_stream(prompt="p", model="m", timeout_seconds=10))

    assert mocked_urlopen.call_args.kwargs["timeout"] == 180
    assert chunks == ["Hi"]


def test_generate_with_ollama_stream_yields_chunks_until_done() -> None:
    stream_lines = [
        '{"response":"Chunk ","done":false}\n',
        '{"response":"two.","done":false}\n',
        '{"response":"","done":true}\n',
    ]
    with patch("als_intel.llm.urlopen", return_value=_FakeStreamResponse(stream_lines)):
        chunks = list(generate_with_ollama_stream(prompt="p", model="m", timeout_seconds=300))

    assert chunks == ["Chunk ", "two."]


def test_generate_with_ollama_parses_response() -> None:
    with patch("als_intel.llm.urlopen", return_value=_FakeResponse('{"response":"ok answer"}')):
        text = generate_with_ollama(prompt="p", model="m")
    assert text == "ok answer"


def test_generate_with_ollama_raises_on_empty_response() -> None:
    with patch("als_intel.llm.urlopen", return_value=_FakeResponse('{"response":""}')):
        try:
            generate_with_ollama(prompt="p", model="m")
            assert False, "Expected LocalLLMError"
        except LocalLLMError:
            assert True


def test_list_ollama_models_filters_allowlist() -> None:
    payload = {
        "models": [
            {"name": "llama3.1:8b", "size": 1},
            {"name": "qwen2.5:14b", "size": 2},
            {"name": "gemma2:9b", "size": 3},
        ]
    }
    with patch("als_intel.llm.urlopen", return_value=_FakeResponse(json.dumps(payload))):
        catalog = list_ollama_models(
            host="http://ollama.test",
            default_model="llama3.1:8b",
            allowlist=["qwen", "gemma2"],
        )
    names = [row["name"] for row in catalog["models"]]
    assert names == ["gemma2:9b", "qwen2.5:14b"]
    assert catalog["error"] is None
    assert catalog["models"][0]["tier"] == "balanced"
    assert catalog["models"][0]["family"] == "gemma"
    assert isinstance(catalog["recommended"], list)
    assert all(row["installed"] is False for row in catalog["recommended"])


def test_resolve_chat_model_prefers_larger_for_complex_questions() -> None:
    available = ["llama3.1:8b", "qwen2.5:14b", "gemma2:2b"]
    short, mode_short = resolve_chat_model(
        "What is ALS?",
        available=available,
        default="llama3.1:8b",
        selection="auto",
    )
    assert mode_short == "auto"
    assert short in {"gemma2:2b", "llama3.1:8b"}

    complex_q = (
        "Compare contradictory mechanistic causal pathways and synthesize "
        "uncertainty with validation next steps across claim trade-offs."
    )
    assert score_question_complexity(complex_q) >= 6
    large, mode_large = resolve_chat_model(
        complex_q,
        available=available,
        default="llama3.1:8b",
        selection="auto",
    )
    assert mode_large == "auto"
    assert large == "qwen2.5:14b"
    assert infer_model_size_b("qwen2.5:14b") == 14


def test_resolve_chat_model_prefers_high_tier_when_available() -> None:
    available = ["gemma2:2b", "llama3.1:8b", "llama3.1:70b"]
    complex_q = (
        "Compare contradictory mechanistic causal pathways and synthesize "
        "uncertainty with validation next steps across claim trade-offs."
    )
    chosen, mode = resolve_chat_model(
        complex_q,
        available=available,
        default="llama3.1:8b",
        selection="auto",
    )
    assert mode == "auto"
    assert chosen == "llama3.1:70b"


def test_resolve_chat_model_manual_selection() -> None:
    model, mode = resolve_chat_model(
        "Anything",
        available=["llama3.1:8b", "gemma2:9b"],
        default="llama3.1:8b",
        selection="gemma2:9b",
    )
    assert model == "gemma2:9b"
    assert mode == "manual"
