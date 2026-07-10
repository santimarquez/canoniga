# Curated Benchmark Inputs

This folder contains starter curated benchmark JSONL files for strict CI benchmark gate checks.

You do not need ALS domain knowledge to start using them. Each file already contains simple, valid example rows that you can review and edit.

Place additional curated benchmark JSONL files in this directory if needed.

Expected row contract per JSONL line:

- prompt (string) or messages (list)
- expected.must_include (list of strings) when prompt is used
- metadata.family in grounding|contradiction|uncertainty|actionability
- metadata.claim_id non-empty string
- metadata.contradiction_count integer >= 0
- metadata.reliability_score float in [0, 1]

Suggested file naming:

- template_grounding.jsonl
- template_contradiction.jsonl
- template_uncertainty.jsonl
- template_actionability.jsonl

These starter files already exist in this folder.

These files are consumed by benchmark-gate in strict CI:

- validate-benchmarks
- merge-benchmark-templates
- evaluate-model

Policy thresholds are loaded from config/benchmark_gate_policy.json.
