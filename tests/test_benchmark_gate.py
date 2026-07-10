from __future__ import annotations

import json
from pathlib import Path

from als_intel.benchmark_gate import run_benchmark_gate
from als_intel.store import EvidenceStore


def test_run_benchmark_gate_runs_validate_merge_and_evaluate(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    store.register_model(
        model_id="candidate-gate-a",
        base_model="llama3.1:8b",
        adapter_path="/tmp/candidate-gate-a",
        dataset_manifest_path="/tmp/manifest.json",
        training_config={"epochs": 1},
        metrics={"val_loss_estimate": 0.5, "train_rows": 300},
        status="trained",
        notes="",
    )

    templates = tmp_path / "templates"
    templates.mkdir(parents=True, exist_ok=True)
    for idx, family in enumerate(["grounding", "contradiction", "uncertainty", "actionability"], start=1):
        rows = []
        for j in range(1, 7):
            claim_id = f"{family[:1].upper()}{idx}{j}"
            rows.append(
                {
                    "prompt": f"Prompt {family} {j}",
                    "expected": {"must_include": ["citation", "limit"]},
                    "metadata": {
                        "family": family,
                        "claim_id": claim_id,
                        "contradiction_count": 1 if family == "contradiction" else 0,
                        "reliability_score": 0.65,
                    },
                }
            )
        (templates / f"template_{family}.jsonl").write_text(
            "\n".join(json.dumps(row) for row in rows),
            encoding="utf-8",
        )

    result = run_benchmark_gate(
        db_path=str(db_path),
        candidate_model_id="candidate-gate-a",
        input_path=str(templates),
        output_dir=str(tmp_path / "gate"),
        min_grounding_score=0.0,
        max_hallucination_risk=1.0,
        min_overall_score=0.0,
        min_benchmark_size=8,
        min_family_examples=2,
        min_family_grounding_score=0.0,
        min_family_contradiction_score=0.0,
        min_family_uncertainty_score=0.0,
        min_family_actionability_score=0.0,
    )

    assert result["steps"]["validate"]["status"] == "ok"
    assert result["steps"]["merge"]["benchmark_size"] >= 8
    assert result["steps"]["evaluate"]["status"] == "passed"
    assert Path(str(result["summary_path"])).exists()


def test_run_benchmark_gate_uses_policy_file(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    store = EvidenceStore(db_path)
    store.init_db()
    store.register_model(
        model_id="candidate-gate-b",
        base_model="llama3.1:8b",
        adapter_path="/tmp/candidate-gate-b",
        dataset_manifest_path="/tmp/manifest.json",
        training_config={"epochs": 1},
        metrics={"val_loss_estimate": 0.5, "train_rows": 300},
        status="trained",
        notes="",
    )

    templates = tmp_path / "templates"
    templates.mkdir(parents=True, exist_ok=True)
    for family in ["grounding", "contradiction", "uncertainty", "actionability"]:
        rows = []
        for idx in range(1, 3):
            rows.append(
                {
                    "prompt": f"Prompt {family} {idx}",
                    "expected": {"must_include": ["citation", "limit"]},
                    "metadata": {
                        "family": family,
                        "claim_id": f"{family[:1].upper()}{idx}",
                        "contradiction_count": 1 if family == "contradiction" else 0,
                        "reliability_score": 0.65,
                    },
                }
            )
        (templates / f"template_{family}.jsonl").write_text(
            "\n".join(json.dumps(row) for row in rows),
            encoding="utf-8",
        )

    policy_path = tmp_path / "gate_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "min_benchmark_size": 1,
                "min_family_examples": 1,
                "min_grounding_score": 0.0,
                "max_hallucination_risk": 1.0,
                "min_overall_score": 0.0,
                "min_family_grounding_score": 0.0,
                "min_family_contradiction_score": 0.0,
                "min_family_uncertainty_score": 0.0,
                "min_family_actionability_score": 0.0,
            }
        ),
        encoding="utf-8",
    )

    result = run_benchmark_gate(
        db_path=str(db_path),
        candidate_model_id="candidate-gate-b",
        input_path=str(templates),
        output_dir=str(tmp_path / "gate"),
        policy_file=str(policy_path),
        min_benchmark_size=100,
        min_family_examples=100,
    )

    assert result["status"] == "passed"
    assert result["policy"]["min_benchmark_size"] == 1
    assert result["policy"]["min_family_examples"] == 1
