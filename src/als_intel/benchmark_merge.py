from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


VALID_FAMILIES = {"grounding", "contradiction", "uncertainty", "actionability"}


def _discover_jsonl_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if not input_path.exists():
        return []
    return sorted([p for p in input_path.glob("*.jsonl") if p.is_file()])


def _family_from_filename(path: Path) -> str | None:
    lower = path.name.lower()
    for family in sorted(VALID_FAMILIES):
        if family in lower:
            return family
    return None


def _normalize_messages(messages: object) -> list[dict[str, str]] | None:
    if not isinstance(messages, list):
        return None
    normalized: list[dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role and content:
            normalized.append({"role": role, "content": content})
    return normalized or None


def _normalize_expected(expected: object) -> dict[str, list[str]]:
    must_include: list[str] = []
    if isinstance(expected, dict):
        raw = expected.get("must_include")
        if isinstance(raw, list):
            must_include = [str(x).strip() for x in raw if str(x).strip()]
        elif raw is not None:
            token = str(raw).strip()
            must_include = [token] if token else []
    return {"must_include": must_include}


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_row(row: object, *, source_file: Path, line_number: int) -> tuple[dict[str, object] | None, str | None]:
    if not isinstance(row, dict):
        return None, "row must be a JSON object"

    metadata_raw = row.get("metadata", {})
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}

    file_family = _family_from_filename(source_file)
    family = str(metadata.get("family", "")).strip().lower() or file_family
    if family not in VALID_FAMILIES:
        return None, "unable to infer valid metadata.family"

    claim_id = str(metadata.get("claim_id", "")).strip()
    if not claim_id:
        return None, "metadata.claim_id must be non-empty"

    contradiction_count = max(0, _safe_int(metadata.get("contradiction_count", 0), 0))
    reliability_score = _safe_float(metadata.get("reliability_score", 0.0), 0.0)
    reliability_score = min(1.0, max(0.0, reliability_score))

    prompt = row.get("prompt")
    prompt_text = str(prompt).strip() if isinstance(prompt, str) else ""
    messages = _normalize_messages(row.get("messages"))
    if not prompt_text and not messages:
        return None, "row must include prompt or messages"

    normalized: dict[str, object] = {
        "metadata": {
            "family": family,
            "claim_id": claim_id,
            "contradiction_count": contradiction_count,
            "reliability_score": reliability_score,
            "source_file": str(source_file),
            "source_line": line_number,
        }
    }

    if prompt_text:
        normalized["prompt"] = prompt_text
        normalized["expected"] = _normalize_expected(row.get("expected"))
    if messages:
        normalized["messages"] = messages

    return normalized, None


def _row_sort_key(row: dict[str, object]) -> tuple[float, int, str, int]:
    meta = row.get("metadata", {})
    metadata = meta if isinstance(meta, dict) else {}
    return (
        float(metadata.get("reliability_score", 0.0)),
        int(metadata.get("contradiction_count", 0)),
        str(metadata.get("family", "")),
        -int(metadata.get("source_line", 0)),
    )


def _dedupe_rows(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], int]:
    by_claim: dict[str, dict[str, object]] = {}
    duplicates_removed = 0

    for row in rows:
        metadata = row.get("metadata", {})
        claim_id = str((metadata if isinstance(metadata, dict) else {}).get("claim_id", "")).strip()
        if not claim_id:
            continue
        current = by_claim.get(claim_id)
        if current is None:
            by_claim[claim_id] = row
            continue
        duplicates_removed += 1
        if _row_sort_key(row) > _row_sort_key(current):
            by_claim[claim_id] = row

    deduped = sorted(
        by_claim.values(),
        key=lambda row: str(((row.get("metadata") or {}).get("claim_id", ""))),
    )
    return deduped, duplicates_removed


def merge_benchmark_templates(
    *,
    input_path: str,
    output_dir: str,
) -> dict[str, object]:
    base = Path(input_path)
    files = _discover_jsonl_files(base)
    if not files:
        raise FileNotFoundError(f"No JSONL template files found at: {base}")

    parsed_rows = 0
    invalid_rows: list[dict[str, object]] = []
    normalized_rows: list[dict[str, object]] = []

    for file_path in files:
        text = file_path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            parsed_rows += 1
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                invalid_rows.append(
                    {
                        "file": str(file_path),
                        "line": idx,
                        "error": f"invalid JSON: {exc.msg}",
                    }
                )
                continue

            normalized, err = _normalize_row(raw, source_file=file_path, line_number=idx)
            if err:
                invalid_rows.append({"file": str(file_path), "line": idx, "error": err})
                continue
            if normalized is not None:
                normalized_rows.append(normalized)

    if not normalized_rows:
        raise ValueError("No valid benchmark rows found after normalization")

    family_rows: dict[str, list[dict[str, object]]] = {k: [] for k in sorted(VALID_FAMILIES)}
    for row in normalized_rows:
        metadata = row.get("metadata", {})
        family = str((metadata if isinstance(metadata, dict) else {}).get("family", ""))
        if family in family_rows:
            family_rows[family].append(row)

    deduped_families: dict[str, list[dict[str, object]]] = {}
    family_duplicates_removed: dict[str, int] = {}
    for family_name, rows in family_rows.items():
        deduped, removed = _dedupe_rows(rows)
        deduped_families[family_name] = deduped
        family_duplicates_removed[family_name] = removed

    merged_rows: list[dict[str, object]] = []
    for family_name in sorted(VALID_FAMILIES):
        merged_rows.extend(deduped_families[family_name])

    benchmark_rows, merged_duplicates_removed = _dedupe_rows(merged_rows)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    benchmark_path = out / "benchmark.jsonl"
    manifest_path = out / "benchmark_manifest.json"

    benchmark_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=True) for row in benchmark_rows),
        encoding="utf-8",
    )

    family_files: dict[str, str] = {}
    family_counts: dict[str, int] = {}
    for family_name in sorted(VALID_FAMILIES):
        family_path = out / f"benchmark_{family_name}.jsonl"
        rows = deduped_families[family_name]
        family_path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=True) for row in rows),
            encoding="utf-8",
        )
        family_files[family_name] = str(family_path)
        family_counts[family_name] = len(rows)

    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(base),
        "files_checked": len(files),
        "rows_parsed": parsed_rows,
        "rows_valid": len(normalized_rows),
        "rows_invalid": len(invalid_rows),
        "deduplication": {
            "family_duplicates_removed": family_duplicates_removed,
            "merged_duplicates_removed": merged_duplicates_removed,
        },
        "benchmark_size": len(benchmark_rows),
        "family_counts": family_counts,
        "files": {
            "benchmark": str(benchmark_path),
            "manifest": str(manifest_path),
            "families": family_files,
        },
        "normalization_errors": invalid_rows,
    }

    manifest_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result