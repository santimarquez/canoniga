from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from als_intel.store import EvidenceStore


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8").strip()
    return 0 if not text else len(text.splitlines())


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.splitlines()]


def _resolve_data_path(manifest_path: Path, p: Path) -> Path:
    if p.is_absolute():
        return p
    candidates = [(Path.cwd() / p).resolve(), (manifest_path.parent / p).resolve()]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _metadata(row: dict[str, object]) -> dict[str, object]:
    meta = row.get("metadata", {})
    return meta if isinstance(meta, dict) else {}


def _family_score(family_name: str, rows: list[dict[str, object]]) -> float:
    if not rows:
        return 0.0

    if family_name == "grounding":
        with_claim = sum(1 for row in rows if _metadata(row).get("claim_id"))
        return round(with_claim / len(rows), 4)

    if family_name == "contradiction":
        contradiction_rows = sum(1 for row in rows if int(_metadata(row).get("contradiction_count", 0)) > 0)
        return round(contradiction_rows / len(rows), 4)

    if family_name == "uncertainty":
        uncertainty_rows = 0
        valid_rows = 0
        for row in rows:
            meta = _metadata(row)
            if "reliability_score" not in meta:
                continue
            try:
                reliability = float(meta.get("reliability_score"))
                valid_rows += 1
            except (TypeError, ValueError):
                continue
            if 0.35 <= reliability <= 0.75:
                uncertainty_rows += 1
        if valid_rows == 0:
            return 1.0
        return round(uncertainty_rows / len(rows), 4)

    if family_name == "actionability":
        actionable_rows = 0
        valid_rows = 0
        for row in rows:
            meta = _metadata(row)
            if "reliability_score" not in meta:
                continue
            try:
                reliability = float(meta.get("reliability_score"))
                valid_rows += 1
            except (TypeError, ValueError):
                continue
            if reliability >= 0.55:
                actionable_rows += 1
        if valid_rows == 0:
            return 1.0
        return round(actionable_rows / len(rows), 4)

    return 0.0


def _model_quality_score(model: dict[str, object]) -> float:
    metrics = model.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}

    val_loss = float(metrics.get("val_loss_estimate", 1.5))
    train_rows = int(metrics.get("train_rows", 0))
    status = str(model.get("status", "simulated"))

    loss_component = max(0.0, min(1.0, 1.0 - (val_loss / 2.5)))
    size_component = min(1.0, train_rows / 500.0)
    status_component = 1.0 if status == "trained" else 0.7 if status == "simulated" else 0.2
    return round((0.55 * loss_component) + (0.25 * size_component) + (0.20 * status_component), 4)


def evaluate_model_candidate(
    *,
    db_path: str,
    candidate_model_id: str,
    benchmark_manifest_path: str,
    output_dir: str,
    baseline_model_id: str | None = None,
    min_grounding_score: float = 0.55,
    max_hallucination_risk: float = 0.45,
    min_overall_score: float = 0.60,
    min_improvement_over_baseline: float = 0.02,
    min_benchmark_size: int = 20,
    min_family_examples: int = 1,
    min_family_grounding_score: float = 0.50,
    min_family_contradiction_score: float = 0.50,
    min_family_uncertainty_score: float = 0.50,
    min_family_actionability_score: float = 0.50,
    notes: str = "",
) -> dict[str, object]:
    store = EvidenceStore(db_path)
    store.init_db()

    candidate = store.get_model(candidate_model_id)
    baseline = store.get_model(baseline_model_id) if baseline_model_id else None

    manifest_path = Path(benchmark_manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Benchmark manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files", {})
    benchmark_file_value = files.get("benchmark") or files.get("val")
    if not benchmark_file_value:
        raise ValueError("Benchmark manifest must include files.benchmark or files.val")
    benchmark_path = _resolve_data_path(manifest_path, Path(str(benchmark_file_value)))
    val_rows = _load_jsonl(benchmark_path)

    family_files = files.get("families", {}) if isinstance(files.get("families", {}), dict) else {}
    family_rows: dict[str, list[dict[str, object]]] = {}
    for family_name in ["grounding", "contradiction", "uncertainty", "actionability"]:
        family_file = family_files.get(family_name)
        if family_file:
            family_rows[family_name] = _load_jsonl(_resolve_data_path(manifest_path, Path(str(family_file))))
        else:
            family_rows[family_name] = list(val_rows)

    benchmark_size = len(val_rows)
    if benchmark_size < min_benchmark_size:
        raise ValueError(
            "benchmark too small for gated evaluation: "
            f"{benchmark_size} < required {min_benchmark_size}. "
            "Use build-benchmark-pack or increase validation split size."
        )
    with_claim_id = 0
    with_contradictions = 0
    for row in val_rows:
        metadata = _metadata(row)
        if metadata.get("claim_id"):
            with_claim_id += 1
        if int(metadata.get("contradiction_count", 0)) > 0:
            with_contradictions += 1

    citation_presence_rate = 0.0 if benchmark_size == 0 else round(with_claim_id / benchmark_size, 4)
    contradiction_coverage = 0.0 if benchmark_size == 0 else round(with_contradictions / benchmark_size, 4)

    candidate_quality = _model_quality_score(candidate)
    baseline_quality = _model_quality_score(baseline) if baseline else 0.0

    grounding_score = round((0.65 * citation_presence_rate) + (0.35 * candidate_quality), 4)
    contradiction_handling_score = round((0.6 * contradiction_coverage) + (0.4 * candidate_quality), 4)
    uncertainty_calibration_score = round((0.75 * candidate_quality) + (0.25 * min(1.0, benchmark_size / 100.0)), 4)
    hallucination_risk = round(max(0.0, min(1.0, 1.0 - grounding_score)), 4)

    overall_score = round(
        (0.4 * grounding_score)
        + (0.25 * contradiction_handling_score)
        + (0.2 * uncertainty_calibration_score)
        + (0.15 * (1.0 - hallucination_risk)),
        4,
    )
    improvement_over_baseline = round(overall_score - baseline_quality, 4) if baseline else None

    failures: list[str] = []
    if grounding_score < min_grounding_score:
        failures.append(
            f"grounding_score_below_threshold({grounding_score:.4f} < {min_grounding_score:.4f})"
        )
    if hallucination_risk > max_hallucination_risk:
        failures.append(
            f"hallucination_risk_above_threshold({hallucination_risk:.4f} > {max_hallucination_risk:.4f})"
        )
    if overall_score < min_overall_score:
        failures.append(
            f"overall_score_below_threshold({overall_score:.4f} < {min_overall_score:.4f})"
        )
    if baseline and improvement_over_baseline is not None and improvement_over_baseline < min_improvement_over_baseline:
        failures.append(
            "improvement_below_threshold"
            f"({improvement_over_baseline:.4f} < {min_improvement_over_baseline:.4f})"
        )

    family_thresholds = {
        "grounding": min_family_grounding_score,
        "contradiction": min_family_contradiction_score,
        "uncertainty": min_family_uncertainty_score,
        "actionability": min_family_actionability_score,
    }
    family_scores: dict[str, float] = {}
    family_counts: dict[str, int] = {}
    for family_name, rows in family_rows.items():
        family_counts[family_name] = len(rows)
        family_scores[family_name] = _family_score(family_name, rows)
        if len(rows) < min_family_examples:
            failures.append(
                "family_benchmark_too_small"
                f"({family_name}: {len(rows)} < {min_family_examples})"
            )
        elif family_scores[family_name] < family_thresholds[family_name]:
            failures.append(
                "family_score_below_threshold"
                f"({family_name}: {family_scores[family_name]:.4f} < {family_thresholds[family_name]:.4f})"
            )

    gate_passed = len(failures) == 0
    gate = {
        "passed": gate_passed,
        "min_grounding_score": min_grounding_score,
        "max_hallucination_risk": max_hallucination_risk,
        "min_overall_score": min_overall_score,
        "min_improvement_over_baseline": min_improvement_over_baseline,
          "min_family_examples": min_family_examples,
          "family_thresholds": family_thresholds,
        "fail_reasons": failures,
    }

    metrics = {
        "benchmark_size": benchmark_size,
        "benchmark_val_file": str(benchmark_path),
        "citation_presence_rate": citation_presence_rate,
        "contradiction_coverage": contradiction_coverage,
        "candidate_quality": candidate_quality,
        "baseline_quality": baseline_quality if baseline else None,
        "grounding_score": grounding_score,
        "contradiction_handling_score": contradiction_handling_score,
        "uncertainty_calibration_score": uncertainty_calibration_score,
        "hallucination_risk": hallucination_risk,
        "overall_score": overall_score,
        "improvement_over_baseline": improvement_over_baseline,
          "family_scores": family_scores,
          "family_counts": family_counts,
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    eval_digest = hashlib.sha1(
        f"{candidate_model_id}|{baseline_model_id or ''}|{stamp}".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:8]
    evaluation_id = f"eval-{stamp}-{eval_digest}"

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{evaluation_id}.json"
    report = {
        "evaluation_id": evaluation_id,
        "candidate_model_id": candidate_model_id,
        "baseline_model_id": baseline_model_id or "",
        "status": "passed" if gate_passed else "failed",
        "metrics": metrics,
        "gate": gate,
        "benchmark_manifest_path": str(manifest_path.resolve()),
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    store.register_model_evaluation(
        evaluation_id=evaluation_id,
        candidate_model_id=candidate_model_id,
        baseline_model_id=baseline_model_id or "",
        benchmark_manifest_path=str(manifest_path.resolve()),
        metrics=metrics,
        gate=gate,
        status="passed" if gate_passed else "failed",
        notes=notes,
    )

    return {
        **report,
        "report_path": str(report_path),
    }
