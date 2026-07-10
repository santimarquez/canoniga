from __future__ import annotations

import json
from pathlib import Path

from als_intel.benchmark_merge import merge_benchmark_templates


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


def test_merge_benchmark_templates_builds_manifest_and_family_files(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    templates.mkdir(parents=True, exist_ok=True)

    (templates / "template_grounding.jsonl").write_text(
        json.dumps(
            {
                "prompt": "Ground this claim.",
                "expected": {"must_include": ["citation"]},
                "metadata": {
                    "family": "grounding",
                    "claim_id": "C1",
                    "contradiction_count": 0,
                    "reliability_score": 0.7,
                },
            }
        ),
        encoding="utf-8",
    )
    (templates / "template_contradiction.jsonl").write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "Compare support and contradiction."},
                    {"role": "assistant", "content": "Needs both sides."},
                ],
                "metadata": {
                    "family": "contradiction",
                    "claim_id": "C2",
                    "contradiction_count": 2,
                    "reliability_score": 0.6,
                },
            }
        ),
        encoding="utf-8",
    )

    out = tmp_path / "benchmark"
    result = merge_benchmark_templates(input_path=str(templates), output_dir=str(out))

    assert result["benchmark_size"] == 2
    assert result["rows_invalid"] == 0
    assert (out / "benchmark.jsonl").exists()
    assert (out / "benchmark_manifest.json").exists()

    families = result["files"]["families"]
    for family_name in ["grounding", "contradiction", "uncertainty", "actionability"]:
        assert Path(str(families[family_name])).exists()


def test_merge_benchmark_templates_dedupes_and_normalizes_rows(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    templates.mkdir(parents=True, exist_ok=True)

    (templates / "template_grounding.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "prompt": "Ground claim duplicate (low quality).",
                        "metadata": {
                            "claim_id": "C3",
                            "contradiction_count": "-2",
                            "reliability_score": "0.4",
                        },
                    }
                ),
                json.dumps(
                    {
                        "prompt": "Ground claim duplicate (preferred).",
                        "expected": {"must_include": "claim id"},
                        "metadata": {
                            "family": "grounding",
                            "claim_id": "C3",
                            "contradiction_count": "1",
                            "reliability_score": "0.9",
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    out = tmp_path / "benchmark"
    result = merge_benchmark_templates(input_path=str(templates), output_dir=str(out))

    rows = _read_jsonl(out / "benchmark.jsonl")
    assert len(rows) == 1
    assert result["deduplication"]["family_duplicates_removed"]["grounding"] == 1

    row = rows[0]
    metadata = row["metadata"]
    assert metadata["family"] == "grounding"
    assert metadata["claim_id"] == "C3"
    assert metadata["contradiction_count"] == 1
    assert metadata["reliability_score"] == 0.9
    assert row["expected"]["must_include"] == ["claim id"]