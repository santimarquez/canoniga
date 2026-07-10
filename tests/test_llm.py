from __future__ import annotations

from unittest.mock import patch

from als_intel.llm import LocalLLMError, build_grounded_prompt, generate_with_ollama


class _FakeResponse:
    def __init__(self, payload: str) -> None:
        self._payload = payload.encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


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
