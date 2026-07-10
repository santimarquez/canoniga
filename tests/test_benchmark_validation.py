from __future__ import annotations

import json
from pathlib import Path

from als_intel.benchmark_templates import scaffold_benchmark_templates
from als_intel.benchmark_validation import validate_benchmark_files


def test_validate_benchmarks_passes_for_scaffolded_templates(tmp_path: Path) -> None:
    scaffold = scaffold_benchmark_templates(str(tmp_path / "templates"))
    report = validate_benchmark_files(
        input_path=str(tmp_path / "templates"),
        fail_on_error=True,
    )

    assert report["status"] == "ok"
    assert report["invalid_rows"] == 0
    assert report["files_checked"] >= 4
    assert scaffold["template_counts"]["grounding"] == 1


def test_validate_benchmarks_returns_report_with_errors_when_not_strict(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.jsonl"
    bad_file.write_text(
        "\n".join(
            [
                json.dumps({"prompt": "bad row", "metadata": {"family": "grounding"}}),
                "{not-json}",
            ]
        ),
        encoding="utf-8",
    )

    report_path = tmp_path / "reports" / "validation.json"
    report = validate_benchmark_files(
        input_path=str(bad_file),
        output_report_path=str(report_path),
        fail_on_error=False,
    )

    assert report["status"] == "failed"
    assert report["invalid_rows"] >= 2
    assert report_path.exists()


def test_validate_benchmarks_strict_mode_raises(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad2.jsonl"
    bad_file.write_text(json.dumps({"messages": []}), encoding="utf-8")

    try:
        validate_benchmark_files(input_path=str(bad_file), fail_on_error=True)
        assert False, "expected validation ValueError"
    except ValueError as exc:
        assert "benchmark validation failed" in str(exc)
