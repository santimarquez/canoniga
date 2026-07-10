from __future__ import annotations

import json
from pathlib import Path

from als_intel.benchmark_merge import merge_benchmark_templates
from als_intel.benchmark_validation import validate_benchmark_files
from als_intel.evaluation import evaluate_model_candidate


DEFAULT_GATE_POLICY = {
    "min_grounding_score": 0.65,
    "max_hallucination_risk": 0.35,
    "min_overall_score": 0.70,
    "min_improvement_over_baseline": 0.02,
    "min_benchmark_size": 20,
    "min_family_examples": 5,
    "min_family_grounding_score": 0.75,
    "min_family_contradiction_score": 0.65,
    "min_family_uncertainty_score": 0.60,
    "min_family_actionability_score": 0.65,
}


def _load_policy(policy_file: str | None) -> tuple[dict[str, float | int], str]:
    policy = dict(DEFAULT_GATE_POLICY)
    if not policy_file:
        return policy, "defaults"

    path = Path(policy_file)
    if not path.exists():
        raise FileNotFoundError(f"Gate policy file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Gate policy file must contain a JSON object")

    for key, default_val in DEFAULT_GATE_POLICY.items():
        if key in raw:
            cast = int if isinstance(default_val, int) else float
            policy[key] = cast(raw[key])

    return policy, str(path)


def run_benchmark_gate(
    *,
    db_path: str,
    candidate_model_id: str,
    input_path: str,
    output_dir: str,
    policy_file: str | None = None,
    baseline_model_id: str | None = None,
    min_grounding_score: float = 0.65,
    max_hallucination_risk: float = 0.35,
    min_overall_score: float = 0.70,
    min_improvement_over_baseline: float = 0.02,
    min_benchmark_size: int = 20,
    min_family_examples: int = 5,
    min_family_grounding_score: float = 0.75,
    min_family_contradiction_score: float = 0.65,
    min_family_uncertainty_score: float = 0.60,
    min_family_actionability_score: float = 0.65,
    notes: str = "",
) -> dict[str, object]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    validation_report_path = out / "validation_report.json"
    merged_dir = out / "merged"
    eval_dir = out / "eval"
    policy, policy_source = _load_policy(policy_file)

    validation = validate_benchmark_files(
        input_path=input_path,
        output_report_path=str(validation_report_path),
        fail_on_error=True,
    )

    merge = merge_benchmark_templates(
        input_path=input_path,
        output_dir=str(merged_dir),
    )

    evaluation = evaluate_model_candidate(
        db_path=db_path,
        candidate_model_id=candidate_model_id,
        baseline_model_id=baseline_model_id,
        benchmark_manifest_path=str(merged_dir / "benchmark_manifest.json"),
        output_dir=str(eval_dir),
        min_grounding_score=float(policy.get("min_grounding_score", min_grounding_score)),
        max_hallucination_risk=float(policy.get("max_hallucination_risk", max_hallucination_risk)),
        min_overall_score=float(policy.get("min_overall_score", min_overall_score)),
        min_improvement_over_baseline=float(
            policy.get("min_improvement_over_baseline", min_improvement_over_baseline)
        ),
        min_benchmark_size=int(policy.get("min_benchmark_size", min_benchmark_size)),
        min_family_examples=int(policy.get("min_family_examples", min_family_examples)),
        min_family_grounding_score=float(
            policy.get("min_family_grounding_score", min_family_grounding_score)
        ),
        min_family_contradiction_score=float(
            policy.get("min_family_contradiction_score", min_family_contradiction_score)
        ),
        min_family_uncertainty_score=float(
            policy.get("min_family_uncertainty_score", min_family_uncertainty_score)
        ),
        min_family_actionability_score=float(
            policy.get("min_family_actionability_score", min_family_actionability_score)
        ),
        notes=notes,
    )

    summary = {
        "status": "passed" if evaluation.get("status") == "passed" else "failed",
        "candidate_model_id": candidate_model_id,
        "baseline_model_id": baseline_model_id or "",
        "policy_source": policy_source,
        "policy": policy,
        "steps": {
            "validate": {
                "status": validation.get("status", "unknown"),
                "files_checked": validation.get("files_checked", 0),
                "invalid_rows": validation.get("invalid_rows", 0),
                "report": str(validation_report_path),
            },
            "merge": {
                "benchmark_size": merge.get("benchmark_size", 0),
                "rows_invalid": merge.get("rows_invalid", 0),
                "manifest": str(merged_dir / "benchmark_manifest.json"),
            },
            "evaluate": {
                "status": evaluation.get("status", "unknown"),
                "evaluation_id": evaluation.get("evaluation_id", ""),
                "report": evaluation.get("report_path", ""),
            },
        },
        "gate": evaluation.get("gate", {}),
        "metrics": evaluation.get("metrics", {}),
    }

    summary_path = out / "benchmark_gate_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary