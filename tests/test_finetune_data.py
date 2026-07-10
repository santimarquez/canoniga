from __future__ import annotations

import json
from pathlib import Path

from als_intel.finetune_data import export_finetune_dataset
from als_intel.pipeline import ingest_file
from als_intel.store import EvidenceStore


def test_export_finetune_dataset_writes_files_and_manifest(tmp_path: Path) -> None:
    db_path = tmp_path / "als.sqlite"
    input_file = tmp_path / "finetune.jsonl"
    input_file.write_text(
        "\n".join(
            [
                '{"claim_id":"FT1","claim_text":"support","disease":"ALS","entity":"target_ft","relation":"associated_with","outcome":"progression","effect_direction":"supports","study_type":"interventional","sample_size":160,"endpoint_validity":0.8,"replication_count":1,"peer_reviewed":true,"year":2026,"source_title":"FT1","source_doi":"10.1/ft1","cohort":"cohort_a","model_system":"human","source_type":"journal","extraction_confidence":0.9}',
                '{"claim_id":"FT2","claim_text":"contradict","disease":"ALS","entity":"target_ft","relation":"associated_with","outcome":"progression","effect_direction":"contradicts","study_type":"observational","sample_size":100,"endpoint_validity":0.6,"replication_count":0,"peer_reviewed":true,"year":2026,"source_title":"FT2","source_doi":"10.1/ft2","cohort":"cohort_b","model_system":"human","source_type":"journal","extraction_confidence":0.85}'
            ]
        ),
        encoding="utf-8",
    )
    ingest_file(str(db_path), str(input_file))

    store = EvidenceStore(db_path)
    out_dir = tmp_path / "dataset"
    manifest = export_finetune_dataset(
        evidence_rows=store.all_evidence(),
        contradiction_rows=store.contradiction_pairs(),
        output_dir=str(out_dir),
        min_reliability=0.0,
        val_ratio=0.5,
    )

    assert manifest["total_examples"] == 2
    assert (out_dir / "train.jsonl").exists()
    assert (out_dir / "val.jsonl").exists()
    assert (out_dir / "manifest.json").exists()

    all_lines = []
    for name in ["train.jsonl", "val.jsonl"]:
        text = (out_dir / name).read_text(encoding="utf-8").strip()
        if text:
            all_lines.extend(text.splitlines())
    assert len(all_lines) == 2

    item = json.loads(all_lines[0])
    assert "messages" in item
    assert item["messages"][0]["role"] == "system"
    assert item["messages"][1]["role"] == "user"
    assert item["messages"][2]["role"] == "assistant"
    assert manifest["qa"]["train_val_leakage_count"] == 0
    assert manifest["qa"]["raw_rows"] == 2
    assert manifest["qa"]["rows_after_filters"] == 2


def test_export_finetune_dataset_honors_min_reliability(tmp_path: Path) -> None:
    evidence_rows = [
        {
            "claim_id": "L1",
            "claim_text": "low",
            "entity": "e",
            "outcome": "o",
            "relation": "associated_with",
            "effect_direction": "supports",
            "study_type": "observational",
            "source_doi": "d1",
            "reliability_score": 0.2,
            "source_reliability_score": 0.5,
            "causal_evidence_type": "observational",
            "sample_size": 10,
            "endpoint_validity": 0.3,
        },
        {
            "claim_id": "H1",
            "claim_text": "high",
            "entity": "e",
            "outcome": "o",
            "relation": "associated_with",
            "effect_direction": "supports",
            "study_type": "interventional",
            "source_doi": "d2",
            "reliability_score": 0.8,
            "source_reliability_score": 0.9,
            "causal_evidence_type": "interventional",
            "sample_size": 100,
            "endpoint_validity": 0.8,
        },
    ]
    out_dir = tmp_path / "dataset2"
    manifest = export_finetune_dataset(
        evidence_rows=evidence_rows,
        contradiction_rows=[],
        output_dir=str(out_dir),
        min_reliability=0.6,
        val_ratio=0.0,
    )
    assert manifest["total_examples"] == 1


def test_export_finetune_dataset_honors_min_source_reliability(tmp_path: Path) -> None:
    evidence_rows = [
        {
            "claim_id": "S1",
            "claim_text": "lower source reliability",
            "entity": "e",
            "outcome": "o",
            "relation": "associated_with",
            "effect_direction": "supports",
            "study_type": "observational",
            "source_doi": "s1",
            "reliability_score": 0.9,
            "source_reliability_score": 0.2,
            "causal_evidence_type": "observational",
            "sample_size": 30,
            "endpoint_validity": 0.6,
        },
        {
            "claim_id": "S2",
            "claim_text": "higher source reliability",
            "entity": "e",
            "outcome": "o",
            "relation": "associated_with",
            "effect_direction": "supports",
            "study_type": "interventional",
            "source_doi": "s2",
            "reliability_score": 0.9,
            "source_reliability_score": 0.85,
            "causal_evidence_type": "interventional",
            "sample_size": 120,
            "endpoint_validity": 0.8,
        },
    ]
    out_dir = tmp_path / "dataset_source"
    manifest = export_finetune_dataset(
        evidence_rows=evidence_rows,
        contradiction_rows=[],
        output_dir=str(out_dir),
        min_reliability=0.0,
        min_source_reliability=0.5,
        val_ratio=0.0,
    )

    assert manifest["total_examples"] == 1
    assert manifest["qa"]["dropped_low_source_reliability"] == 1


def test_export_finetune_dataset_completion_format(tmp_path: Path) -> None:
    evidence_rows = [
        {
            "claim_id": "C1",
            "claim_text": "example",
            "entity": "ent",
            "outcome": "out",
            "relation": "associated_with",
            "effect_direction": "supports",
            "study_type": "interventional",
            "source_doi": "c1",
            "reliability_score": 0.8,
            "source_reliability_score": 0.8,
            "causal_evidence_type": "interventional",
            "sample_size": 100,
            "endpoint_validity": 0.7,
        }
    ]

    out_dir = tmp_path / "dataset_completion"
    export_finetune_dataset(
        evidence_rows=evidence_rows,
        contradiction_rows=[],
        output_dir=str(out_dir),
        output_format="completion",
        val_ratio=0.0,
    )

    line = (out_dir / "train.jsonl").read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert "prompt" in record
    assert "completion" in record
    assert "messages" not in record


def test_export_finetune_dataset_entity_outcome_split_strategy(tmp_path: Path) -> None:
    evidence_rows = []
    for i in range(6):
        evidence_rows.append(
            {
                "claim_id": f"E{i}",
                "claim_text": f"claim {i}",
                "entity": "microglia",
                "outcome": "progression",
                "relation": "associated_with",
                "effect_direction": "supports",
                "study_type": "observational",
                "source_doi": f"doi{i}",
                "reliability_score": 0.7,
                "source_reliability_score": 0.7,
                "causal_evidence_type": "observational",
                "sample_size": 50,
                "endpoint_validity": 0.6,
            }
        )

    out_dir = tmp_path / "dataset_split"
    manifest = export_finetune_dataset(
        evidence_rows=evidence_rows,
        contradiction_rows=[],
        output_dir=str(out_dir),
        val_ratio=0.2,
        split_strategy="entity_outcome_hash",
    )

    assert manifest["split_strategy"] == "entity_outcome_hash"
    assert manifest["val_examples"] >= 1
    assert manifest["qa"]["train_val_leakage_count"] == 0


def test_export_finetune_dataset_enforces_min_val_examples(tmp_path: Path) -> None:
    evidence_rows = []
    for i in range(4):
        evidence_rows.append(
            {
                "claim_id": f"MV{i}",
                "claim_text": f"claim {i}",
                "entity": "astrocyte",
                "outcome": "progression",
                "relation": "associated_with",
                "effect_direction": "supports",
                "study_type": "observational",
                "source_doi": f"doi_mv_{i}",
                "reliability_score": 0.7,
                "source_reliability_score": 0.7,
                "causal_evidence_type": "observational",
                "sample_size": 40,
                "endpoint_validity": 0.6,
            }
        )

    out_dir = tmp_path / "dataset_min_val"
    manifest = export_finetune_dataset(
        evidence_rows=evidence_rows,
        contradiction_rows=[],
        output_dir=str(out_dir),
        val_ratio=0.0,
        min_val_examples=2,
    )

    assert manifest["val_examples"] >= 2
    assert manifest["qa"]["validation_examples_below_minimum"] is False
