from __future__ import annotations

import json
from pathlib import Path

from als_intel.extractors.claim_builder import build_record_from_doc, maybe_llm_refine_claim, build_pubmed_claim


CURATED_LLM_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "curated" / "template_llm_extraction.jsonl"


def _load_curated_llm_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in CURATED_LLM_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        metadata = row.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("doc"), dict):
            rows.append(metadata)
    return rows


def _structured_ratio(docs: list[dict[str, object]], *, use_llm: bool, monkeypatch) -> float:
    if use_llm:
        monkeypatch.setenv("ALS_CLAIM_EXTRACTION_LLM", "1")

        def _mock_generate(*, prompt: str, model: str, **kwargs):  # noqa: ANN003
            for doc in docs:
                entity = str(doc.get("deterministic_entity", ""))
                if entity and entity.lower() in prompt.lower():
                    return json.dumps(
                        {
                            "entity": entity,
                            "relation": "associated_with",
                            "outcome": "disease progression",
                            "effect_direction": "supports",
                        }
                    )
            return "{}"

        monkeypatch.setattr("als_intel.llm.generate_with_ollama", _mock_generate)
    else:
        monkeypatch.delenv("ALS_CLAIM_EXTRACTION_LLM", raising=False)

    hits = 0
    for item in docs:
        doc = item["doc"]
        if not isinstance(doc, dict):
            continue
        if use_llm:
            base = build_pubmed_claim(doc)
            maybe_llm_refine_claim(doc, base)
        record = build_record_from_doc(doc)
        if record.claim_text and record.entity and record.effect_direction:
            hits += 1
    return hits / max(len(docs), 1)


def test_curated_llm_extraction_rows_validate() -> None:
    from als_intel.benchmark_validation import validate_benchmark_files

    report = validate_benchmark_files(input_path=str(CURATED_LLM_PATH.parent), fail_on_error=True)
    llm_file = next(
        item for item in report["per_file"] if str(item["file"]).endswith("template_llm_extraction.jsonl")
    )
    assert int(llm_file["valid_rows"]) >= 5


def test_llm_extraction_preserves_structured_claim_ratio(monkeypatch) -> None:
    rows = _load_curated_llm_rows()
    assert len(rows) >= 5
    deterministic_ratio = _structured_ratio(rows, use_llm=False, monkeypatch=monkeypatch)
    llm_ratio = _structured_ratio(rows, use_llm=True, monkeypatch=monkeypatch)
    assert deterministic_ratio >= 0.7
    assert llm_ratio >= deterministic_ratio
