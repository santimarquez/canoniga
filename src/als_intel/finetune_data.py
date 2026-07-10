from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Literal


SYSTEM_PROMPT = (
    "You are an ALS scientific assistant. "
    "Use evidence, state uncertainty explicitly, preserve contradictions, "
    "and propose testable next steps."
)

SplitStrategy = Literal["claim_hash", "entity_outcome_hash"]
OutputFormat = Literal["messages", "completion"]


def _deterministic_bucket(claim_id: str) -> int:
    digest = hashlib.sha1(claim_id.encode("utf-8"), usedforsecurity=False).hexdigest()
    return int(digest[:8], 16) % 100


def _hash_bucket(key: str) -> int:
    digest = hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()
    return int(digest[:8], 16) % 100


def _build_text_fields(
    row: dict[str, object], contradictions_for_claim: list[dict[str, object]]
) -> tuple[str, str, dict[str, object]]:
    claim_id = str(row.get("claim_id", ""))
    reliability = float(row.get("reliability_score", 0.0))
    source_reliability = float(row.get("source_reliability_score", 0.0))
    effect_direction = str(row.get("effect_direction", "neutral"))

    evidence_strength = "high" if reliability >= 0.75 else "medium" if reliability >= 0.55 else "low"
    uncertainty = "low" if reliability >= 0.75 else "moderate" if reliability >= 0.55 else "high"

    contradiction_lines = []
    for c in contradictions_for_claim:
        other = str(c["claim_b"] if str(c["claim_a"]) == claim_id else c["claim_a"])
        contradiction_lines.append(
            (
                f"- contradiction_with={other} "
                f"type={c.get('contradiction_type')}"
            )
        )

    contradiction_block = "\n".join(contradiction_lines) if contradiction_lines else "- none"

    user = (
        "Analyze this ALS evidence item and provide a structured scientific interpretation.\n\n"
        f"claim_id={claim_id}\n"
        f"claim_text={row.get('claim_text')}\n"
        f"entity={row.get('entity')}\n"
        f"outcome={row.get('outcome')}\n"
        f"relation={row.get('relation')}\n"
        f"effect_direction={effect_direction}\n"
        f"study_type={row.get('study_type')}\n"
        f"causal_evidence_type={row.get('causal_evidence_type', 'observational')}\n"
        f"sample_size={row.get('sample_size')}\n"
        f"endpoint_validity={row.get('endpoint_validity')}\n"
        f"reliability_score={reliability}\n"
        f"source_reliability_score={source_reliability}\n"
        "Known contradictions:\n"
        f"{contradiction_block}"
    )

    assistant = (
        f"Direct answer: This is a {evidence_strength}-strength {effect_direction} signal for "
        f"{row.get('entity')} on {row.get('outcome')}.\n"
        f"Supporting evidence references: [{claim_id}]\n"
        f"Contradictions or uncertainty: Uncertainty is {uncertainty}; "
        f"{len(contradictions_for_claim)} contradiction links are currently known.\n"
        "Suggested validation next steps: "
        "run subgroup-stratified replication with harmonized endpoints and pre-registered analyses."
    )

    metadata = {
        "claim_id": claim_id,
        "entity": row.get("entity"),
        "outcome": row.get("outcome"),
        "reliability_score": reliability,
        "source_reliability_score": source_reliability,
        "contradiction_count": len(contradictions_for_claim),
    }
    return user, assistant, metadata


def _row_to_example(
    row: dict[str, object],
    contradictions_for_claim: list[dict[str, object]],
    output_format: OutputFormat,
) -> dict[str, object]:
    user, assistant, metadata = _build_text_fields(row, contradictions_for_claim)
    if output_format == "completion":
        return {
            "prompt": f"{SYSTEM_PROMPT}\n\nUser:\n{user}\n\nAssistant:",
            "completion": assistant,
            "metadata": metadata,
        }

    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "metadata": metadata,
    }


def _split_examples(
    examples: list[dict[str, object]],
    val_ratio: float,
    split_strategy: SplitStrategy,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if split_strategy == "claim_hash":
        val_cutoff = int(val_ratio * 100)
        train_examples: list[dict[str, object]] = []
        val_examples: list[dict[str, object]] = []
        for ex in examples:
            claim_id = str(ex["metadata"]["claim_id"])
            if _deterministic_bucket(claim_id) < val_cutoff:
                val_examples.append(ex)
            else:
                train_examples.append(ex)
        return train_examples, val_examples

    groups: dict[str, list[dict[str, object]]] = {}
    for ex in examples:
        entity = str(ex["metadata"].get("entity") or "")
        outcome = str(ex["metadata"].get("outcome") or "")
        groups.setdefault(f"{entity}::{outcome}", []).append(ex)

    train_examples = []
    val_examples = []
    for _, group_items in sorted(groups.items()):
        ordered = sorted(
            group_items,
            key=lambda x: (
                _hash_bucket(str(x["metadata"]["claim_id"])),
                str(x["metadata"]["claim_id"]),
            ),
        )
        val_count = int(round(len(ordered) * val_ratio))
        if val_ratio > 0.0 and len(ordered) >= 5 and val_count == 0:
            val_count = 1
        val_examples.extend(ordered[:val_count])
        train_examples.extend(ordered[val_count:])
    return train_examples, val_examples


def export_finetune_dataset(
    *,
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
    output_dir: str,
    min_reliability: float = 0.0,
    min_source_reliability: float = 0.0,
    val_ratio: float = 0.2,
    split_strategy: SplitStrategy = "claim_hash",
    output_format: OutputFormat = "messages",
    min_val_examples: int = 0,
) -> dict[str, object]:
    if not 0.0 <= min_reliability <= 1.0:
        raise ValueError("min_reliability must be in [0,1]")
    if not 0.0 <= min_source_reliability <= 1.0:
        raise ValueError("min_source_reliability must be in [0,1]")
    if not 0.0 <= val_ratio < 1.0:
        raise ValueError("val_ratio must be in [0,1)")
    if min_val_examples < 0:
        raise ValueError("min_val_examples must be >= 0")
    if split_strategy not in {"claim_hash", "entity_outcome_hash"}:
        raise ValueError("split_strategy must be claim_hash or entity_outcome_hash")
    if output_format not in {"messages", "completion"}:
        raise ValueError("output_format must be messages or completion")

    claim_id_counts = Counter(str(r.get("claim_id", "")) for r in evidence_rows)
    duplicate_claim_ids = sorted([cid for cid, count in claim_id_counts.items() if cid and count > 1])

    by_claim_contradictions: dict[str, list[dict[str, object]]] = {}
    for row in contradiction_rows:
        claim_a = str(row.get("claim_a"))
        claim_b = str(row.get("claim_b"))
        by_claim_contradictions.setdefault(claim_a, []).append(row)
        by_claim_contradictions.setdefault(claim_b, []).append(row)

    filtered_rows = [
        r
        for r in evidence_rows
        if float(r.get("reliability_score", 0.0)) >= min_reliability
        and float(r.get("source_reliability_score", 0.0)) >= min_source_reliability
    ]
    examples = [
        _row_to_example(
            r,
            by_claim_contradictions.get(str(r.get("claim_id")), []),
            output_format,
        )
        for r in filtered_rows
    ]
    train_examples, val_examples = _split_examples(examples, val_ratio, split_strategy)

    # Ensure a minimum validation set size for downstream evaluation stability.
    if min_val_examples > 0 and len(val_examples) < min_val_examples:
        needed = min(min_val_examples - len(val_examples), len(train_examples))
        if needed > 0:
            train_examples_sorted = sorted(
                train_examples,
                key=lambda x: (
                    _hash_bucket(str(x["metadata"]["claim_id"])),
                    str(x["metadata"]["claim_id"]),
                ),
            )
            promoted = train_examples_sorted[:needed]
            promoted_ids = {str(x["metadata"]["claim_id"]) for x in promoted}
            val_examples.extend(promoted)
            train_examples = [
                ex for ex in train_examples if str(ex["metadata"]["claim_id"]) not in promoted_ids
            ]

    train_ids = {str(x["metadata"].get("claim_id", "")) for x in train_examples}
    val_ids = {str(x["metadata"].get("claim_id", "")) for x in val_examples}
    leakage_ids = sorted(train_ids & val_ids)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    train_path = out / "train.jsonl"
    val_path = out / "val.jsonl"
    manifest_path = out / "manifest.json"

    train_path.write_text("\n".join(json.dumps(x, ensure_ascii=True) for x in train_examples), encoding="utf-8")
    val_path.write_text("\n".join(json.dumps(x, ensure_ascii=True) for x in val_examples), encoding="utf-8")

    manifest = {
        "total_examples": len(examples),
        "train_examples": len(train_examples),
        "val_examples": len(val_examples),
        "min_reliability": min_reliability,
        "min_source_reliability": min_source_reliability,
        "val_ratio": val_ratio,
        "min_val_examples": min_val_examples,
        "split_strategy": split_strategy,
        "output_format": output_format,
        "qa": {
            "raw_rows": len(evidence_rows),
            "rows_after_filters": len(filtered_rows),
            "dropped_low_reliability": len(
                [r for r in evidence_rows if float(r.get("reliability_score", 0.0)) < min_reliability]
            ),
            "dropped_low_source_reliability": len(
                [
                    r
                    for r in evidence_rows
                    if float(r.get("reliability_score", 0.0)) >= min_reliability
                    and float(r.get("source_reliability_score", 0.0)) < min_source_reliability
                ]
            ),
            "duplicate_claim_id_count": len(duplicate_claim_ids),
            "duplicate_claim_ids": duplicate_claim_ids,
            "claims_with_contradictions": len(
                {
                    str(r.get("claim_id"))
                    for r in filtered_rows
                    if by_claim_contradictions.get(str(r.get("claim_id")))
                }
            ),
            "contradiction_pairs_total": len(contradiction_rows),
            "train_val_leakage_count": len(leakage_ids),
            "train_val_leakage_claim_ids": leakage_ids,
            "validation_examples_below_minimum": len(val_examples) < min_val_examples,
        },
        "files": {
            "train": str(train_path),
            "val": str(val_path),
            "manifest": str(manifest_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
