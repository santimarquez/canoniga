from __future__ import annotations

from als_intel.extractors.claim_builder import build_record_from_doc, maybe_llm_refine_claim, build_pubmed_claim


def test_llm_extraction_uses_mocked_ollama_when_enabled(monkeypatch) -> None:
    doc = {
        "source": "pubmed",
        "source_id": "LLM9001",
        "title": "Microglial activation in ALS progression",
        "abstract": (
            "Microglial activation was associated with faster ALS progression "
            "and reduced survival in a longitudinal cohort."
        ),
        "year": 2025,
        "journal": "Neurology",
    }
    base_claim = build_pubmed_claim(doc)

    def _fake_generate_with_ollama(*, prompt: str, model: str, **kwargs):  # noqa: ANN003
        assert "entity" in prompt
        return (
            '{"entity": "microglial activation", "relation": "associated_with", '
            '"outcome": "survival", "effect_direction": "supports"}'
        )

    monkeypatch.setenv("ALS_CLAIM_EXTRACTION_LLM", "1")
    monkeypatch.setattr(
        "als_intel.llm.generate_with_ollama",
        _fake_generate_with_ollama,
    )
    refined = maybe_llm_refine_claim(doc, base_claim)
    assert refined is not None
    assert refined.entity == "microglial activation"
    assert refined.extraction_method.endswith("+llm")
    record = build_record_from_doc(doc)
    assert record.entity == "microglial activation"


def test_llm_extraction_falls_back_when_mock_returns_invalid_json(monkeypatch) -> None:
    doc = {
        "source": "pubmed",
        "source_id": "LLM9002",
        "title": "Mitochondrial dysfunction in ALS",
        "abstract": "Mitochondrial dysfunction biomarkers tracked disease progression in ALS patients.",
        "year": 2024,
        "journal": "Brain",
    }
    base_claim = build_pubmed_claim(doc)

    def _bad_generate(*, prompt: str, model: str, **kwargs):  # noqa: ANN003
        return "not-json"

    monkeypatch.setenv("ALS_CLAIM_EXTRACTION_LLM", "1")
    monkeypatch.setattr("als_intel.llm.generate_with_ollama", _bad_generate)
    refined = maybe_llm_refine_claim(doc, base_claim)
    assert refined is not None
    assert refined.entity == base_claim.entity
    assert "+llm" not in refined.extraction_method
