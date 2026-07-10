from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _hash_bucket(key: str) -> int:
    digest = hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()
    return int(digest[:8], 16) % 100


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


def _metadata(row: dict[str, object]) -> dict[str, object]:
    meta = row.get("metadata", {})
    return meta if isinstance(meta, dict) else {}


def _claim_id(row: dict[str, object]) -> str:
    return str(_metadata(row).get("claim_id", ""))


def _reliability(row: dict[str, object]) -> float:
    try:
        return float(_metadata(row).get("reliability_score", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _resolve_data_path(manifest_path: Path, p: Path) -> Path:
    if p.is_absolute():
        return p
    candidates = [(Path.cwd() / p).resolve(), (manifest_path.parent / p).resolve()]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def build_benchmark_pack(
    *,
    dataset_manifest_path: str,
    output_dir: str,
    min_examples: int = 20,
    max_examples: int = 200,
) -> dict[str, object]:
    if min_examples <= 0:
        raise ValueError("min_examples must be > 0")
    if max_examples < min_examples:
        raise ValueError("max_examples must be >= min_examples")

    manifest_path = Path(dataset_manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Dataset manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files", {})
    train_path = _resolve_data_path(manifest_path, Path(str(files.get("train", ""))))
    val_path = _resolve_data_path(manifest_path, Path(str(files.get("val", ""))))

    train_rows = _read_jsonl(train_path)
    val_rows = _read_jsonl(val_path)

    benchmark_rows = list(val_rows)
    val_ids = {
        str((r.get("metadata") or {}).get("claim_id", ""))
        for r in benchmark_rows
        if isinstance(r, dict)
    }

    if len(benchmark_rows) < min_examples:
        train_candidates = sorted(
            [
                r
                for r in train_rows
                if str((r.get("metadata") or {}).get("claim_id", "")) not in val_ids
            ],
            key=lambda r: (
                _hash_bucket(str((r.get("metadata") or {}).get("claim_id", ""))),
                str((r.get("metadata") or {}).get("claim_id", "")),
            ),
        )
        needed = min(min_examples - len(benchmark_rows), len(train_candidates))
        benchmark_rows.extend(train_candidates[:needed])

    benchmark_rows = benchmark_rows[:max_examples]

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    benchmark_jsonl = out / "benchmark.jsonl"
    benchmark_manifest = out / "benchmark_manifest.json"

    benchmark_jsonl.write_text(
        "\n".join(json.dumps(row, ensure_ascii=True) for row in benchmark_rows),
        encoding="utf-8",
    )

    result = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_manifest_path": str(manifest_path.resolve()),
        "benchmark_size": len(benchmark_rows),
        "min_examples": min_examples,
        "max_examples": max_examples,
        "source_counts": {
            "val_source_rows": len(val_rows),
            "train_source_rows": len(train_rows),
        },
        "files": {},
    }

    families: dict[str, list[dict[str, object]]] = {
        "grounding": [r for r in benchmark_rows if _claim_id(r)],
        "contradiction": [r for r in benchmark_rows if int(_metadata(r).get("contradiction_count", 0)) > 0],
        "uncertainty": [r for r in benchmark_rows if 0.35 <= _reliability(r) <= 0.75],
        "actionability": [r for r in benchmark_rows if _reliability(r) >= 0.55],
    }

    family_files: dict[str, str] = {}
    family_counts: dict[str, int] = {}
    for family_name, family_rows in families.items():
        family_path = out / f"benchmark_{family_name}.jsonl"
        family_path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=True) for row in family_rows),
            encoding="utf-8",
        )
        family_files[family_name] = str(family_path)
        family_counts[family_name] = len(family_rows)

    result["family_counts"] = family_counts
    result["files"] = {
        "benchmark": str(benchmark_jsonl),
        "manifest": str(benchmark_manifest),
        "families": family_files,
    }
    benchmark_manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
