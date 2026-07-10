from __future__ import annotations

import json
from pathlib import Path

from als_intel.evaluation import evaluate_model_candidate
from als_intel.store import EvidenceStore


def _write_eval_manifest(tmp_path: Path) -> Path:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    val = dataset_dir / "val.jsonl"
    manifest = dataset_dir / "manifest.json"

    val.write_text(
        "\n".join(
            [
                json.dumps({"messages": [], "metadata": {"claim_id": "C1", "contradiction_count": 1}}),
                json.dumps({"messages": [], "metadata": {"claim_id": "C2", "contradiction_count": 0}}),
            ]
        ),
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps({"files": {"val": str(val)}}),
        encoding="utf-8",
    )
    return manifest


def _write_eval_manifest_with_families(tmp_path: Path) -> Path:
    dataset_dir = tmp_path / "dataset_families"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    benchmark = dataset_dir / "benchmark.jsonl"
    grounding = dataset_dir / "benchmark_grounding.jsonl"
    contradiction = dataset_dir / "benchmark_contradiction.jsonl"
    uncertainty = dataset_dir / "benchmark_uncertainty.jsonl"
    actionability = dataset_dir / "benchmark_actionability.jsonl"
    manifest = dataset_dir / "benchmark_manifest.json"

    rows = [
        {"messages": [], "metadata": {"claim_id": "G1", "contradiction_count": 0, "reliability_score": 0.8}},
        {"messages": [], "metadata": {"claim_id": "G2", "contradiction_count": 1, "reliability_score": 0.65}},
    ]
    benchmark.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    grounding.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    contradiction.write_text(json.dumps(rows[1]), encoding="utf-8")
    uncertainty.write_text(json.dumps(rows[1]), encoding="utf-8")
    actionability.write_text(json.dumps(rows[0]), encoding="utf-8")

    manifest.write_text(
        json.dumps(
            {
                "files": {
                    "benchmark": str(benchmark),
                    "families": {
                        "grounding": str(grounding),
                        "contradiction": str(contradiction),
                        "uncertainty": str(uncertainty),
                        "actionability": str(actionability),
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _register_model(store: EvidenceStore, model_id: str, status: str, val_loss: float, train_rows: int) -> None:
    store.register_model(
        model_id=model_id,
        base_model="llama3.1:8b",
        adapter_path=f"/tmp/{model_id}",
        dataset_manifest_path="/tmp/manifest.json",
        training_config={"epochs": 2},
        metrics={"val_loss_estimate": val_loss, "train_rows": train_rows, "status": status},
        status=status,
    )


def test_evaluate_model_candidate_registers_passed_evaluation(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()

    _register_model(store, "baseline-a", "simulated", val_loss=1.2, train_rows=50)
    _register_model(store, "candidate-a", "trained", val_loss=0.6, train_rows=200)

    manifest = _write_eval_manifest(tmp_path)
    result = evaluate_model_candidate(
        db_path=str(db_path),
        candidate_model_id="candidate-a",
        benchmark_manifest_path=str(manifest),
        output_dir=str(tmp_path / "eval"),
        min_grounding_score=0.0,
        max_hallucination_risk=1.0,
        min_overall_score=0.0,
        min_benchmark_size=1,
    )

    assert result["status"] == "passed"
    assert result["gate"]["passed"] is True

    rows = store.list_model_evaluations(limit=10)
    assert len(rows) == 1
    assert rows[0]["candidate_model_id"] == "candidate-a"


def test_evaluate_model_candidate_fails_gate_when_thresholds_too_strict(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()

    _register_model(store, "candidate-b", "failed", val_loss=2.0, train_rows=5)
    manifest = _write_eval_manifest(tmp_path)

    result = evaluate_model_candidate(
        db_path=str(db_path),
        candidate_model_id="candidate-b",
        benchmark_manifest_path=str(manifest),
        output_dir=str(tmp_path / "eval"),
        min_grounding_score=0.95,
        max_hallucination_risk=0.05,
        min_overall_score=0.95,
        min_benchmark_size=1,
    )

    assert result["status"] == "failed"
    assert result["gate"]["passed"] is False
    assert len(result["gate"]["fail_reasons"]) >= 1


def test_evaluate_model_candidate_blocks_when_benchmark_too_small(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    _register_model(store, "candidate-c", "trained", val_loss=0.8, train_rows=150)
    manifest = _write_eval_manifest(tmp_path)

    try:
        evaluate_model_candidate(
            db_path=str(db_path),
            candidate_model_id="candidate-c",
            benchmark_manifest_path=str(manifest),
            output_dir=str(tmp_path / "eval"),
            min_benchmark_size=5,
        )
        assert False, "expected ValueError for benchmark size precheck"
    except ValueError as exc:
        assert "benchmark too small for gated evaluation" in str(exc)


def test_evaluate_model_candidate_enforces_family_thresholds(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    _register_model(store, "candidate-d", "trained", val_loss=0.7, train_rows=150)

    manifest = _write_eval_manifest_with_families(tmp_path)
    result = evaluate_model_candidate(
        db_path=str(db_path),
        candidate_model_id="candidate-d",
        benchmark_manifest_path=str(manifest),
        output_dir=str(tmp_path / "eval"),
        min_benchmark_size=1,
        min_family_examples=1,
        min_family_actionability_score=1.1,
    )

    assert result["status"] == "failed"
    assert any("family_score_below_threshold(actionability" in reason for reason in result["gate"]["fail_reasons"])
