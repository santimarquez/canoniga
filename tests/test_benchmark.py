from __future__ import annotations

import json
from pathlib import Path

from als_intel.benchmark import build_benchmark_pack


def _write_dataset_manifest(tmp_path: Path) -> Path:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    train = dataset_dir / "train.jsonl"
    val = dataset_dir / "val.jsonl"
    manifest = dataset_dir / "manifest.json"

    train.write_text(
        "\n".join(
            [
                json.dumps({"messages": [], "metadata": {"claim_id": "T1"}}),
                json.dumps({"messages": [], "metadata": {"claim_id": "T2"}}),
                json.dumps({"messages": [], "metadata": {"claim_id": "T3"}}),
            ]
        ),
        encoding="utf-8",
    )
    val.write_text(json.dumps({"messages": [], "metadata": {"claim_id": "V1"}}), encoding="utf-8")
    manifest.write_text(
        json.dumps({"files": {"train": str(train), "val": str(val)}}),
        encoding="utf-8",
    )
    return manifest


def test_build_benchmark_pack_promotes_from_train_when_val_too_small(tmp_path: Path) -> None:
    manifest = _write_dataset_manifest(tmp_path)
    out_dir = tmp_path / "bench"

    result = build_benchmark_pack(
        dataset_manifest_path=str(manifest),
        output_dir=str(out_dir),
        min_examples=3,
        max_examples=5,
    )

    assert result["benchmark_size"] >= 3
    assert (out_dir / "benchmark.jsonl").exists()
    assert (out_dir / "benchmark_manifest.json").exists()
    assert "family_counts" in result
    assert "families" in result["files"]
    families = result["files"]["families"]
    assert Path(str(families["grounding"])).exists()
    assert Path(str(families["contradiction"])).exists()
    assert Path(str(families["uncertainty"])).exists()
    assert Path(str(families["actionability"])).exists()
