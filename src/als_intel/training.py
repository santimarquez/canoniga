from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from als_intel.store import EvidenceStore


def _count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return 0
    return len(text.splitlines())


def _default_model_id(base_model: str, dataset_manifest_path: Path, seed: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    key = f"{base_model}|{dataset_manifest_path.resolve()}|{seed}|{stamp}"
    digest = hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"als-{stamp}-{digest}"


def run_training_pipeline(
    *,
    db_path: str,
    dataset_manifest_path: str,
    base_model: str,
    output_dir: str,
    epochs: int = 3,
    batch_size: int = 4,
    learning_rate: float = 2e-4,
    seed: int = 42,
    trainer_command: str | None = None,
    model_id: str | None = None,
    notes: str = "",
) -> dict[str, object]:
    if epochs <= 0:
        raise ValueError("epochs must be > 0")
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if learning_rate <= 0.0:
        raise ValueError("learning_rate must be > 0")

    manifest_path = Path(dataset_manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Dataset manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files", {})
    train_file = Path(str(files.get("train", "")))
    val_file = Path(str(files.get("val", "")))

    def _resolve_data_path(p: Path) -> Path:
        if p.is_absolute():
            return p
        candidates = [
            (Path.cwd() / p).resolve(),
            (manifest_path.parent / p).resolve(),
        ]
        for c in candidates:
            if c.exists():
                return c
        return candidates[0]

    train_file = _resolve_data_path(train_file)
    val_file = _resolve_data_path(val_file)

    if not train_file.exists():
        raise FileNotFoundError(f"train file not found: {train_file}")
    if not val_file.exists():
        raise FileNotFoundError(f"val file not found: {val_file}")

    final_model_id = model_id or _default_model_id(base_model, manifest_path, seed)
    run_dir = Path(output_dir) / final_model_id
    run_dir.mkdir(parents=True, exist_ok=True)

    training_config = {
        "model_id": final_model_id,
        "base_model": base_model,
        "dataset_manifest_path": str(manifest_path.resolve()),
        "train_file": str(train_file),
        "val_file": str(val_file),
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "seed": seed,
        "trainer_command": trainer_command or "",
    }
    (run_dir / "training_config.json").write_text(json.dumps(training_config, indent=2), encoding="utf-8")

    train_rows = _count_jsonl_rows(train_file)
    val_rows = _count_jsonl_rows(val_file)
    estimated_steps = max(1, ((train_rows + batch_size - 1) // batch_size) * epochs)

    status = "simulated"
    trainer_exit_code = 0
    trainer_output = "simulated_training: no external trainer command provided"
    adapter_path = run_dir / "adapter-metadata.json"

    if trainer_command:
        command = trainer_command.format(
            train_file=str(train_file),
            val_file=str(val_file),
            output_dir=str(run_dir),
            base_model=base_model,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            seed=seed,
        )
        completed = subprocess.run(command, shell=True, capture_output=True, text=True)
        trainer_exit_code = int(completed.returncode)
        trainer_output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        status = "trained" if trainer_exit_code == 0 else "failed"
        (run_dir / "trainer.log").write_text(trainer_output, encoding="utf-8")
        if status == "trained":
            adapter_path = run_dir / "adapter.bin"
            adapter_path.write_text("external-training-completed", encoding="utf-8")
    else:
        adapter_path.write_text(
            json.dumps(
                {
                    "mode": "simulated",
                    "base_model": base_model,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "train_rows": train_rows,
                    "val_rows": val_rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    val_loss_estimate = round(max(0.05, (1.25 / max(val_rows, 1)) + (0.8 / max(train_rows, 1))), 4)
    metrics = {
        "train_rows": train_rows,
        "val_rows": val_rows,
        "estimated_steps": estimated_steps,
        "val_loss_estimate": val_loss_estimate,
        "trainer_exit_code": trainer_exit_code,
        "status": status,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    store = EvidenceStore(db_path)
    store.init_db()
    store.register_model(
        model_id=final_model_id,
        base_model=base_model,
        adapter_path=str(adapter_path),
        dataset_manifest_path=str(manifest_path.resolve()),
        training_config=training_config,
        metrics=metrics,
        status=status,
        notes=notes,
    )

    return {
        "model_id": final_model_id,
        "status": status,
        "output_dir": str(run_dir),
        "adapter_path": str(adapter_path),
        "metrics": metrics,
    }
