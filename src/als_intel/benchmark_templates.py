from __future__ import annotations

import json
from pathlib import Path


TEMPLATES: dict[str, list[dict[str, object]]] = {
    "grounding": [
        {
            "prompt": "Summarize the ALS claim using only cited evidence.",
            "expected": {
                "must_include": [
                    "explicit claim id citation",
                    "no unsupported mechanism statements",
                ]
            },
            "metadata": {
                "family": "grounding",
                "claim_id": "REPLACE_WITH_CLAIM_ID",
                "contradiction_count": 0,
                "reliability_score": 0.7,
            },
        }
    ],
    "contradiction": [
        {
            "prompt": "Compare supporting and contradicting ALS evidence and explain disagreement.",
            "expected": {
                "must_include": [
                    "at least one supporting citation",
                    "at least one contradicting citation",
                    "clear conflict explanation",
                ]
            },
            "metadata": {
                "family": "contradiction",
                "claim_id": "REPLACE_WITH_CLAIM_ID",
                "contradiction_count": 1,
                "reliability_score": 0.65,
            },
        }
    ],
    "uncertainty": [
        {
            "prompt": "State confidence limits and unresolved uncertainties for this ALS finding.",
            "expected": {
                "must_include": [
                    "explicit uncertainty statement",
                    "confidence caveat",
                    "next validation step",
                ]
            },
            "metadata": {
                "family": "uncertainty",
                "claim_id": "REPLACE_WITH_CLAIM_ID",
                "contradiction_count": 1,
                "reliability_score": 0.5,
            },
        }
    ],
    "actionability": [
        {
            "prompt": "Propose a testable next experiment for this ALS hypothesis.",
            "expected": {
                "must_include": [
                    "specific experiment design",
                    "endpoint definition",
                    "go/no-go criterion",
                ]
            },
            "metadata": {
                "family": "actionability",
                "claim_id": "REPLACE_WITH_CLAIM_ID",
                "contradiction_count": 0,
                "reliability_score": 0.75,
            },
        }
    ],
}


def scaffold_benchmark_templates(output_dir: str) -> dict[str, object]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}
    counts: dict[str, int] = {}

    for family_name, rows in TEMPLATES.items():
        family_path = out / f"template_{family_name}.jsonl"
        family_path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=True) for row in rows),
            encoding="utf-8",
        )
        files[family_name] = str(family_path)
        counts[family_name] = len(rows)

    guide_path = out / "benchmark_authoring_guide.md"
    guide_path.write_text(
        "\n".join(
            [
                "# Benchmark Authoring Guide",
                "",
                "Create JSONL benchmark rows per family using the provided templates.",
                "",
                "Required metadata fields:",
                "- family",
                "- claim_id",
                "- contradiction_count",
                "- reliability_score",
                "",
                "After authoring, merge rows into dataset export and run build-benchmark-pack.",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "output_dir": str(out),
        "template_counts": counts,
        "files": {
            "families": files,
            "guide": str(guide_path),
        },
    }
