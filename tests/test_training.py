from __future__ import annotations

import json
from pathlib import Path

from als_intel.training import run_training_pipeline
from als_intel.store import EvidenceStore


def _write_dataset_manifest(tmp_path: Path) -> tuple[Path, Path, Path]:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    train = dataset_dir / "train.jsonl"
    val = dataset_dir / "val.jsonl"
    manifest = dataset_dir / "manifest.json"

    train.write_text('{"messages": []}\n{"messages": []}', encoding="utf-8")
    val.write_text('{"messages": []}', encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "files": {
                    "train": str(train),
                    "val": str(val),
                }
            }
        ),
        encoding="utf-8",
    )
    return manifest, train, val


def test_run_training_pipeline_simulated_registers_model(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    manifest, _, _ = _write_dataset_manifest(tmp_path)

    result = run_training_pipeline(
        db_path=str(db_path),
        dataset_manifest_path=str(manifest),
        base_model="llama3.1:8b",
        output_dir=str(tmp_path / "models"),
        model_id="als-test-model",
        epochs=2,
        batch_size=2,
    )

    assert result["model_id"] == "als-test-model"
    assert result["status"] == "simulated"

    store = EvidenceStore(db_path)
    models = store.list_models(limit=10)
    assert len(models) == 1
    assert models[0]["model_id"] == "als-test-model"
    assert models[0]["status"] == "simulated"


def test_run_training_pipeline_external_command_failure_marked_failed(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    manifest, _, _ = _write_dataset_manifest(tmp_path)

    result = run_training_pipeline(
        db_path=str(db_path),
        dataset_manifest_path=str(manifest),
        base_model="llama3.1:8b",
        output_dir=str(tmp_path / "models"),
        model_id="als-failed-model",
        trainer_command="exit 3",
    )

    assert result["status"] == "failed"
    assert result["metrics"]["trainer_exit_code"] == 3

    store = EvidenceStore(db_path)
    model = store.get_model("als-failed-model")
    assert model["status"] == "failed"
