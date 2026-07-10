from __future__ import annotations

import json
from pathlib import Path


VALID_FAMILIES = {"grounding", "contradiction", "uncertainty", "actionability"}


def _discover_jsonl_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if not input_path.exists():
        return []
    return sorted([p for p in input_path.glob("*.jsonl") if p.is_file()])


def _validate_row(row: dict[str, object]) -> list[str]:
    errors: list[str] = []

    if not isinstance(row, dict):
        return ["row must be a JSON object"]

    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        return ["metadata must be an object"]

    family = metadata.get("family")
    if family is None:
        errors.append("metadata.family is required")
    elif str(family) not in VALID_FAMILIES:
        errors.append("metadata.family must be one of grounding|contradiction|uncertainty|actionability")

    claim_id = metadata.get("claim_id")
    if claim_id is None or not str(claim_id).strip():
        errors.append("metadata.claim_id must be a non-empty string")

    contradiction_count = metadata.get("contradiction_count")
    try:
        contradiction_int = int(contradiction_count)
        if contradiction_int < 0:
            errors.append("metadata.contradiction_count must be >= 0")
    except (TypeError, ValueError):
        errors.append("metadata.contradiction_count must be an integer")

    reliability_score = metadata.get("reliability_score")
    try:
        reliability_float = float(reliability_score)
        if not 0.0 <= reliability_float <= 1.0:
            errors.append("metadata.reliability_score must be in [0,1]")
    except (TypeError, ValueError):
        errors.append("metadata.reliability_score must be a float")

    has_prompt = isinstance(row.get("prompt"), str)
    has_messages = isinstance(row.get("messages"), list)
    if not (has_prompt or has_messages):
        errors.append("row must include either prompt (string) or messages (list)")

    if has_prompt:
        expected = row.get("expected")
        if not isinstance(expected, dict):
            errors.append("expected must be an object when prompt is provided")
        else:
            must_include = expected.get("must_include")
            if not isinstance(must_include, list) or not all(isinstance(x, str) for x in must_include):
                errors.append("expected.must_include must be a list of strings")

    return errors


def validate_benchmark_files(
    *,
    input_path: str,
    output_report_path: str | None = None,
    fail_on_error: bool = True,
) -> dict[str, object]:
    base = Path(input_path)
    files = _discover_jsonl_files(base)
    if not files:
        raise FileNotFoundError(f"No JSONL benchmark files found at: {base}")

    per_file: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    total_rows = 0
    valid_rows = 0

    for file_path in files:
        text = file_path.read_text(encoding="utf-8").strip()
        lines = [] if not text else text.splitlines()

        file_errors = 0
        file_valid = 0
        for idx, line in enumerate(lines, start=1):
            total_rows += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(
                    {
                        "file": str(file_path),
                        "line": idx,
                        "error": f"invalid JSON: {exc.msg}",
                    }
                )
                file_errors += 1
                continue

            row_errors = _validate_row(row)
            if row_errors:
                for err in row_errors:
                    errors.append(
                        {
                            "file": str(file_path),
                            "line": idx,
                            "error": err,
                        }
                    )
                file_errors += 1
            else:
                file_valid += 1
                valid_rows += 1

        per_file.append(
            {
                "file": str(file_path),
                "rows": len(lines),
                "valid_rows": file_valid,
                "invalid_rows": file_errors,
            }
        )

    report = {
        "input_path": str(base),
        "files_checked": len(files),
        "rows_checked": total_rows,
        "valid_rows": valid_rows,
        "invalid_rows": len(errors),
        "status": "ok" if not errors else "failed",
        "per_file": per_file,
        "errors": errors,
    }

    if output_report_path:
        out = Path(output_report_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if errors and fail_on_error:
        raise ValueError(
            "benchmark validation failed: "
            f"{len(errors)} error(s) across {len(files)} file(s)"
        )

    return report
