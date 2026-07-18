from __future__ import annotations

import argparse
import json

from als_intel.agents.clinical_trial import build_clinical_trial_analysis
from als_intel.agents.causal_dashboard import build_causal_risk_dashboard
from als_intel.agents.debate import build_debate_report
from als_intel.agents.historical import build_failure_atlas
from als_intel.agents.hypothesis_graph import build_graph_gap_hypotheses
from als_intel.agents.orchestrator import build_agent_report
from als_intel.agents.systems_biology import build_systems_biology_report
from als_intel.extraction_fidelity import evaluate_extraction_fidelity
from als_intel.benchmark import build_benchmark_pack
from als_intel.benchmark_gate import run_benchmark_gate
from als_intel.benchmark_merge import merge_benchmark_templates
from als_intel.benchmark_templates import scaffold_benchmark_templates
from als_intel.benchmark_validation import validate_benchmark_files
from als_intel.evaluation import evaluate_model_candidate
from als_intel.extractors import register_builtin_extractors, supported_sources
from als_intel.finetune_data import export_finetune_dataset
from als_intel.hypothesis import build_hypothesis_queue
from als_intel.llm import LocalLLMError, build_grounded_prompt, generate_with_ollama
from als_intel.metrics import compute_quality_metrics
from als_intel.pipeline import ingest_file
from als_intel.scheduler import run_scheduled_sync
from als_intel.store import EvidenceStore
from als_intel.sync import run_incremental_sync
from als_intel.training import run_training_pipeline


def build_parser() -> argparse.ArgumentParser:
    register_builtin_extractors()
    parser = argparse.ArgumentParser(
        prog="als-intel",
        description="Local ALS scientific intelligence CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Initialize PostgreSQL evidence database")
    init_db.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")

    ingest = subparsers.add_parser("ingest-jsonl", help="Ingest JSONL evidence records")
    ingest.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    ingest.add_argument("--input", required=True, help="Path to input JSONL file")

    summarize = subparsers.add_parser("summarize", help="Show dataset summary")
    summarize.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")

    contradictions = subparsers.add_parser(
        "contradictions",
        help="List contradictory evidence pairs by entity/outcome",
    )
    contradictions.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")

    drift = subparsers.add_parser(
        "drift",
        help="Show confidence drift over ingestion history",
    )
    drift.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    drift.add_argument("--claim-id", required=False, help="Optional claim id filter")

    chat = subparsers.add_parser(
        "chat",
        help="Ask grounded questions to a local LLM using ALS evidence context",
    )
    chat.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    chat.add_argument("--question", required=False, help="Question for one-shot mode")
    chat.add_argument("--interactive", action="store_true", help="Run interactive chat loop")
    chat.add_argument("--model", required=False, default="llama3.1:8b", help="Local model name")
    chat.add_argument("--host", required=False, default="http://localhost:11434", help="Local LLM host URL")
    chat.add_argument("--context-limit", required=False, type=int, default=20, help="Max evidence rows for grounding")
    chat.add_argument("--temperature", required=False, type=float, default=0.1, help="Sampling temperature")
    chat.add_argument("--timeout-seconds", required=False, type=int, default=60, help="LLM request timeout")

    finetune_export = subparsers.add_parser(
        "export-finetune-data",
        help="Export ALS fine-tuning dataset JSONL files from local evidence",
    )
    finetune_export.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    finetune_export.add_argument("--output-dir", required=True, help="Directory for train/val JSONL files")
    finetune_export.add_argument(
        "--min-reliability",
        required=False,
        type=float,
        default=0.0,
        help="Minimum claim reliability to include in dataset",
    )
    finetune_export.add_argument(
        "--min-source-reliability",
        required=False,
        type=float,
        default=0.0,
        help="Minimum source reliability score to include in dataset",
    )
    finetune_export.add_argument(
        "--val-ratio",
        required=False,
        type=float,
        default=0.2,
        help="Validation split ratio in [0,1)",
    )
    finetune_export.add_argument(
        "--split-strategy",
        required=False,
        choices=["claim_hash", "entity_outcome_hash"],
        default="claim_hash",
        help="Deterministic split strategy",
    )
    finetune_export.add_argument(
        "--format",
        required=False,
        choices=["messages", "completion"],
        default="messages",
        help="Output schema format",
    )
    finetune_export.add_argument(
        "--min-val-examples",
        required=False,
        type=int,
        default=0,
        help="Ensure at least this many validation examples by promoting from train if needed",
    )

    benchmark_pack = subparsers.add_parser(
        "build-benchmark-pack",
        help="Build evaluation benchmark pack from a dataset manifest",
    )
    benchmark_pack.add_argument("--dataset-manifest", required=True, help="Path to dataset manifest")
    benchmark_pack.add_argument("--output-dir", required=True, help="Directory for benchmark pack outputs")
    benchmark_pack.add_argument("--min-examples", required=False, type=int, default=20, help="Minimum benchmark examples")
    benchmark_pack.add_argument("--max-examples", required=False, type=int, default=200, help="Maximum benchmark examples")

    benchmark_templates = subparsers.add_parser(
        "scaffold-benchmark-templates",
        help="Create family-specific benchmark authoring templates",
    )
    benchmark_templates.add_argument("--output-dir", required=True, help="Directory for template files")

    benchmark_validate = subparsers.add_parser(
        "validate-benchmarks",
        help="Validate authored benchmark JSONL rows before pack build/evaluation",
    )
    benchmark_validate.add_argument("--input-path", required=True, help="JSONL file or directory containing JSONL files")
    benchmark_validate.add_argument("--report", required=False, help="Optional output report path")
    benchmark_validate.add_argument(
        "--no-fail-on-error",
        action="store_true",
        help="Return validation report even if errors are present",
    )

    benchmark_merge = subparsers.add_parser(
        "merge-benchmark-templates",
        help="Merge curated benchmark template files into benchmark-ready JSONL + manifest",
    )
    benchmark_merge.add_argument(
        "--input-path",
        required=True,
        help="JSONL file or directory containing curated family template files",
    )
    benchmark_merge.add_argument(
        "--output-dir",
        required=True,
        help="Directory for merged benchmark outputs",
    )

    benchmark_gate = subparsers.add_parser(
        "benchmark-gate",
        help="Run validate -> merge -> evaluate benchmark workflow in one command",
    )
    benchmark_gate.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    benchmark_gate.add_argument("--candidate-model-id", required=True, help="Candidate model id")
    benchmark_gate.add_argument("--input-path", required=True, help="Curated templates JSONL file or directory")
    benchmark_gate.add_argument("--output-dir", required=True, help="Directory for gate workflow outputs")
    benchmark_gate.add_argument(
        "--policy-file",
        required=False,
        help="Optional JSON policy file for gate thresholds",
    )
    benchmark_gate.add_argument("--baseline-model-id", required=False, help="Optional baseline model id")
    benchmark_gate.add_argument(
        "--min-grounding-score",
        required=False,
        type=float,
        default=0.65,
        help="Minimum grounding score gate threshold",
    )
    benchmark_gate.add_argument(
        "--max-hallucination-risk",
        required=False,
        type=float,
        default=0.35,
        help="Maximum hallucination risk gate threshold",
    )
    benchmark_gate.add_argument(
        "--min-overall-score",
        required=False,
        type=float,
        default=0.70,
        help="Minimum overall score gate threshold",
    )
    benchmark_gate.add_argument(
        "--min-improvement-over-baseline",
        required=False,
        type=float,
        default=0.02,
        help="Minimum required score improvement over baseline",
    )
    benchmark_gate.add_argument(
        "--min-benchmark-size",
        required=False,
        type=int,
        default=20,
        help="Minimum benchmark rows required to run gate evaluation",
    )
    benchmark_gate.add_argument(
        "--min-family-examples",
        required=False,
        type=int,
        default=5,
        help="Minimum rows required in each benchmark family",
    )
    benchmark_gate.add_argument(
        "--min-family-grounding-score",
        required=False,
        type=float,
        default=0.75,
        help="Minimum grounding-family score",
    )
    benchmark_gate.add_argument(
        "--min-family-contradiction-score",
        required=False,
        type=float,
        default=0.65,
        help="Minimum contradiction-family score",
    )
    benchmark_gate.add_argument(
        "--min-family-uncertainty-score",
        required=False,
        type=float,
        default=0.60,
        help="Minimum uncertainty-family score",
    )
    benchmark_gate.add_argument(
        "--min-family-actionability-score",
        required=False,
        type=float,
        default=0.65,
        help="Minimum actionability-family score",
    )
    benchmark_gate.add_argument("--notes", required=False, default="", help="Optional evaluation notes")

    train_model = subparsers.add_parser(
        "train-model",
        help="Run local ALS model training pipeline and register model metadata",
    )
    train_model.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    train_model.add_argument("--dataset-manifest", required=True, help="Path to dataset manifest.json")
    train_model.add_argument("--base-model", required=True, help="Base model id/name")
    train_model.add_argument("--output-dir", required=True, help="Directory for training outputs")
    train_model.add_argument("--epochs", required=False, type=int, default=3, help="Training epochs")
    train_model.add_argument("--batch-size", required=False, type=int, default=4, help="Training batch size")
    train_model.add_argument("--learning-rate", required=False, type=float, default=2e-4, help="Learning rate")
    train_model.add_argument("--seed", required=False, type=int, default=42, help="Random seed")
    train_model.add_argument("--model-id", required=False, help="Optional explicit model id")
    train_model.add_argument(
        "--trainer-command",
        required=False,
        help=(
            "Optional shell command to run actual training. "
            "Supports placeholders: {train_file} {val_file} {output_dir} {base_model} "
            "{epochs} {batch_size} {learning_rate} {seed}"
        ),
    )
    train_model.add_argument("--notes", required=False, default="", help="Optional registry notes")

    model_registry = subparsers.add_parser(
        "model-registry",
        help="List registered trained models or fetch a model by id",
    )
    model_registry.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    model_registry.add_argument("--model-id", required=False, help="Optional model id")
    model_registry.add_argument("--limit", required=False, type=int, default=50, help="Max models to list")

    evaluate_model = subparsers.add_parser(
        "evaluate-model",
        help="Evaluate candidate model against benchmark and apply promotion gate",
    )
    evaluate_model.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    evaluate_model.add_argument("--candidate-model-id", required=True, help="Candidate model id")
    evaluate_model.add_argument("--benchmark-manifest", required=True, help="Benchmark manifest path")
    evaluate_model.add_argument("--output-dir", required=True, help="Directory for evaluation reports")
    evaluate_model.add_argument("--baseline-model-id", required=False, help="Optional baseline model id")
    evaluate_model.add_argument(
        "--min-grounding-score",
        required=False,
        type=float,
        default=0.65,
        help="Minimum grounding score gate threshold",
    )
    evaluate_model.add_argument(
        "--max-hallucination-risk",
        required=False,
        type=float,
        default=0.35,
        help="Maximum hallucination risk gate threshold",
    )
    evaluate_model.add_argument(
        "--min-overall-score",
        required=False,
        type=float,
        default=0.70,
        help="Minimum overall score gate threshold",
    )
    evaluate_model.add_argument(
        "--min-improvement-over-baseline",
        required=False,
        type=float,
        default=0.02,
        help="Minimum required score improvement over baseline",
    )
    evaluate_model.add_argument(
        "--min-benchmark-size",
        required=False,
        type=int,
        default=20,
        help="Minimum benchmark rows required to run gate evaluation",
    )
    evaluate_model.add_argument(
        "--min-family-examples",
        required=False,
        type=int,
        default=5,
        help="Minimum rows required in each benchmark family",
    )
    evaluate_model.add_argument(
        "--min-family-grounding-score",
        required=False,
        type=float,
        default=0.75,
        help="Minimum grounding-family score",
    )
    evaluate_model.add_argument(
        "--min-family-contradiction-score",
        required=False,
        type=float,
        default=0.65,
        help="Minimum contradiction-family score",
    )
    evaluate_model.add_argument(
        "--min-family-uncertainty-score",
        required=False,
        type=float,
        default=0.60,
        help="Minimum uncertainty-family score",
    )
    evaluate_model.add_argument(
        "--min-family-actionability-score",
        required=False,
        type=float,
        default=0.65,
        help="Minimum actionability-family score",
    )
    evaluate_model.add_argument("--notes", required=False, default="", help="Optional evaluation notes")

    model_evaluations = subparsers.add_parser(
        "model-evaluations",
        help="List model evaluations or fetch evaluation by id",
    )
    model_evaluations.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    model_evaluations.add_argument("--evaluation-id", required=False, help="Optional evaluation id")
    model_evaluations.add_argument(
        "--candidate-model-id",
        required=False,
        help="Optional candidate model id filter",
    )
    model_evaluations.add_argument("--limit", required=False, type=int, default=50, help="Max evaluations")

    agent_report = subparsers.add_parser(
        "agent-report",
        help="Run deterministic literature and skeptic agent reports",
    )
    agent_report.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    agent_report.add_argument(
        "--require-review-signoff",
        action="store_true",
        help="Withhold high-impact labels until a reviewer approval exists for the claim",
    )

    lineage = subparsers.add_parser(
        "lineage",
        help="Show supporting and contradicting citation lineage for a claim",
    )
    lineage.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    lineage.add_argument("--claim-id", required=True, help="Claim id to inspect")

    sync_cmd = subparsers.add_parser(
        "sync-source",
        help="Run incremental sync from a registered source",
    )
    sync_cmd.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    sync_cmd.add_argument("--source", required=True, choices=supported_sources(), help="Data source")
    sync_cmd.add_argument("--query", required=True, help="Source query term")
    sync_cmd.add_argument("--max-results", required=False, type=int, default=20, help="Maximum records")
    sync_cmd.add_argument("--from-file", required=False, help="Optional local JSON file for deterministic sync")
    sync_cmd.add_argument(
        "--extractor-config",
        required=False,
        default="{}",
        help="Optional JSON object with source-specific extractor settings",
    )
    sync_cmd.add_argument(
        "--stage-config",
        required=False,
        default="{}",
        help="Optional JSON object with stage settings (e.g., metadata enrichment)",
    )

    source_caps = subparsers.add_parser(
        "source-capabilities",
        help="List registered datasource extractors and capability status",
    )
    source_caps.add_argument(
        "--as-json",
        action="store_true",
        help="Output JSON instead of plain text",
    )
    source_caps.add_argument(
        "--only-runnable",
        action="store_true",
        help="Show only runnable sources",
    )
    source_caps.add_argument(
        "--only-public",
        action="store_true",
        help="Show only public (non-restricted) sources",
    )

    changes = subparsers.add_parser(
        "recent-changes",
        help="Show recent change-log entries from incremental sync",
    )
    changes.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    changes.add_argument("--run-id", required=False, type=int, help="Optional sync run id filter")
    changes.add_argument("--limit", required=False, type=int, default=50, help="Max change rows")

    hypotheses = subparsers.add_parser(
        "hypothesis-queue",
        help="Generate hypothesis cards with supporting and contradictory evidence",
    )
    hypotheses.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    hypotheses.add_argument("--limit", required=False, type=int, default=10, help="Max hypothesis cards")
    hypotheses.add_argument(
        "--require-review-signoff",
        action="store_true",
        help="Only include hypotheses with at least one approved supporting claim",
    )
    hypotheses.add_argument(
        "--enforce-causal-gate",
        action="store_true",
        help="Block hypothesis promotion for entities failing causal-risk gate",
    )
    hypotheses.add_argument(
        "--causal-gate-override-entity",
        action="append",
        default=[],
        help="Entity name to override causal gate blocking (repeatable)",
    )
    hypotheses.add_argument(
        "--causal-promotion-risk-threshold",
        required=False,
        type=float,
        default=0.5,
        help="Causal risk threshold for promotion blocking",
    )
    hypotheses.add_argument(
        "--causal-minimum-strong-support-ratio",
        required=False,
        type=float,
        default=0.3,
        help="Minimum interventional/genetic support ratio required for promotion",
    )

    review_flags = subparsers.add_parser(
        "review-flags",
        help="Flag claims for mandatory human review based on drift and contradiction pressure",
    )
    review_flags.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    review_flags.add_argument(
        "--delta-threshold",
        required=False,
        type=float,
        default=0.15,
        help="Absolute confidence delta threshold",
    )
    review_flags.add_argument(
        "--contradiction-density-threshold",
        required=False,
        type=float,
        default=0.34,
        help="Entity contradiction density threshold",
    )

    schedule = subparsers.add_parser(
        "schedule-sync",
        help="Run local scheduled sync cycles from a JSON plan",
    )
    schedule.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    schedule.add_argument("--plan", required=True, help="Path to JSON sync plan")
    schedule.add_argument("--cycles", required=False, type=int, default=1, help="Number of sync cycles")
    schedule.add_argument(
        "--interval-seconds",
        required=False,
        type=int,
        default=3600,
        help="Seconds between cycles",
    )

    decision = subparsers.add_parser(
        "review-decision",
        help="Record a human review decision for a claim",
    )
    decision.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    decision.add_argument("--claim-id", required=True, help="Claim id")
    decision.add_argument(
        "--decision",
        required=True,
        choices=["approve", "reject", "needs_more_evidence"],
        help="Human decision",
    )
    decision.add_argument("--reviewer", required=True, help="Reviewer identifier")
    decision.add_argument("--notes", required=False, default="", help="Decision notes")

    decision_log = subparsers.add_parser(
        "review-log",
        help="List recorded human review decisions",
    )
    decision_log.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    decision_log.add_argument("--claim-id", required=False, help="Optional claim id filter")
    decision_log.add_argument("--limit", required=False, type=int, default=100, help="Max rows")

    failure_atlas = subparsers.add_parser(
        "failure-atlas",
        help="Build historical failure atlas and root-cause distribution",
    )
    failure_atlas.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")

    debate = subparsers.add_parser(
        "debate-report",
        help="Run Debate Protocol v1 over contradiction set",
    )
    debate.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")

    consensus = subparsers.add_parser(
        "consensus-timeline",
        help="Show consensus timeline with change rationale",
    )
    consensus.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    consensus.add_argument("--entity", required=False, help="Optional entity filter")
    consensus.add_argument("--limit", required=False, type=int, default=100, help="Max events")

    metrics = subparsers.add_parser(
        "quality-metrics",
        help="Compute calibration metrics (stability, disagreement, recurrence)",
    )
    metrics.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    metrics.add_argument("--entity", required=False, help="Optional entity filter for timeline stability")
    metrics.add_argument("--limit", required=False, type=int, default=200, help="Max timeline events")

    causal_dash = subparsers.add_parser(
        "causal-dashboard",
        help="Rank entities by causal risk and flag promotion blocks",
    )
    causal_dash.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    causal_dash.add_argument("--entity", required=False, help="Optional entity filter")
    causal_dash.add_argument("--limit", required=False, type=int, default=50, help="Max entities")
    causal_dash.add_argument(
        "--promotion-risk-threshold",
        required=False,
        type=float,
        default=0.5,
        help="Risk threshold above which promotion is blocked when strong support is insufficient",
    )
    causal_dash.add_argument(
        "--minimum-strong-support-ratio",
        required=False,
        type=float,
        default=0.3,
        help="Minimum ratio of interventional/genetic supporting evidence for promotion readiness",
    )

    graph_build = subparsers.add_parser(
        "graph-build",
        help="Rebuild biomedical knowledge graph from current evidence",
    )
    graph_build.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")

    graph_overview = subparsers.add_parser(
        "graph-overview",
        help="Show knowledge graph node/edge counts",
    )
    graph_overview.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")

    graph_map = subparsers.add_parser(
        "graph-support-map",
        help="Show support-vs-contradiction map by entity and outcome",
    )
    graph_map.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    graph_map.add_argument("--entity", required=False, help="Optional entity filter")
    graph_map.add_argument("--limit", required=False, type=int, default=50, help="Max rows")

    graph_neighbors = subparsers.add_parser(
        "graph-neighbors",
        help="Show outbound neighbors for a graph node key",
    )
    graph_neighbors.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    graph_neighbors.add_argument("--node-key", required=True, help="Node key, e.g. entity:microglial activation")
    graph_neighbors.add_argument("--limit", required=False, type=int, default=20, help="Max neighbors")

    trial_agent = subparsers.add_parser(
        "trial-analysis-agent",
        help="Run Clinical Trial Analysis Agent over graph and failure context",
    )
    trial_agent.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    trial_agent.add_argument("--entity", required=False, help="Optional entity filter")
    trial_agent.add_argument("--limit", required=False, type=int, default=50, help="Max rows")

    repurpose_agent = subparsers.add_parser(
        "repurposing-agent",
        help="Run Drug Repurposing Agent over graph and failure context",
    )
    repurpose_agent.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    repurpose_agent.add_argument("--entity", required=False, help="Optional entity filter")
    repurpose_agent.add_argument("--limit", required=False, type=int, default=50, help="Max rows")

    gap_hypotheses = subparsers.add_parser(
        "graph-gap-hypotheses",
        help="Generate graph-driven underexplored gap hypotheses with why-now signals",
    )
    gap_hypotheses.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    gap_hypotheses.add_argument("--entity", required=False, help="Optional entity filter")
    gap_hypotheses.add_argument("--limit", required=False, type=int, default=10, help="Max hypothesis cards")
    gap_hypotheses.add_argument(
        "--require-review-signoff",
        action="store_true",
        help="Only include cards backed by at least one approved supporting claim",
    )

    systems_bio = subparsers.add_parser(
        "systems-biology-agent",
        help="Run Systems Biology Agent over pathway and graph neighborhoods",
    )
    systems_bio.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    systems_bio.add_argument("--entity", required=False, help="Optional entity filter")
    systems_bio.add_argument("--limit", required=False, type=int, default=10, help="Max pathway cards")

    extraction_gate = subparsers.add_parser(
        "extraction-fidelity-gate",
        help="Evaluate structured extraction fidelity against curated gold claims",
    )
    extraction_gate.add_argument(
        "--gold-path",
        required=False,
        help="Optional path to extraction fidelity gold JSON",
    )


    migrate_sqlite = subparsers.add_parser(
        "migrate-from-sqlite",
        help="Import a legacy SQLite database into PostgreSQL",
    )
    migrate_sqlite.add_argument("--sqlite", required=True, help="Path to legacy SQLite file")
    migrate_sqlite.add_argument("--db", required=False, default=None, help="Postgres DSN (default: ALS_DATABASE_URL)")
    migrate_sqlite.add_argument(
        "--no-truncate",
        action="store_true",
        help="Do not truncate Postgres tables before import",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-db":
        store = EvidenceStore(args.db)
        store.init_db()
        print(f"Initialized database: {store.dsn}")
        return

    if args.command == "migrate-from-sqlite":
        from als_intel.migrate_sqlite import format_migration_report, migrate_sqlite_to_postgres

        report = migrate_sqlite_to_postgres(
            sqlite_path=args.sqlite,
            dsn=args.db,
            truncate_first=not args.no_truncate,
        )
        print(format_migration_report(report))
        if not report.get("ok"):
            raise SystemExit(1)
        return

    if args.command == "ingest-jsonl":
        count = ingest_file(args.db, args.input)
        print(f"Ingested records: {count}")
        return

    if args.command == "summarize":
        store = EvidenceStore(args.db)
        print(json.dumps(store.summary(), indent=2))
        return

    if args.command == "contradictions":
        store = EvidenceStore(args.db)
        print(json.dumps(store.contradiction_pairs(), indent=2))
        return

    if args.command == "drift":
        store = EvidenceStore(args.db)
        print(json.dumps(store.confidence_drift(args.claim_id), indent=2))
        return

    if args.command == "chat":
        store = EvidenceStore(args.db)
        evidence = store.all_evidence()

        def ask_once(question: str) -> dict[str, object]:
            prompt = build_grounded_prompt(question, evidence, context_limit=args.context_limit)
            answer = generate_with_ollama(
                prompt=prompt,
                model=args.model,
                host=args.host,
                temperature=args.temperature,
                timeout_seconds=args.timeout_seconds,
            )
            return {
                "question": question,
                "model": args.model,
                "context_rows": min(len(evidence), max(args.context_limit, 1)),
                "answer": answer,
            }

        try:
            if args.interactive:
                print("Interactive local chat started. Type 'exit' to quit.")
                while True:
                    user_q = input("you> ").strip()
                    if not user_q:
                        continue
                    if user_q.lower() in {"exit", "quit"}:
                        print("Session ended.")
                        break
                    result = ask_once(user_q)
                    print(f"assistant> {result['answer']}")
                return

            if not args.question:
                parser.error("--question is required unless --interactive is used")

            print(json.dumps(ask_once(args.question), indent=2))
            return
        except LocalLLMError as exc:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "error": str(exc),
                    },
                    indent=2,
                )
            )
            return

    if args.command == "export-finetune-data":
        store = EvidenceStore(args.db)
        manifest = export_finetune_dataset(
            evidence_rows=store.all_evidence(),
            contradiction_rows=store.contradiction_pairs(),
            output_dir=args.output_dir,
            min_reliability=args.min_reliability,
            min_source_reliability=args.min_source_reliability,
            val_ratio=args.val_ratio,
            split_strategy=args.split_strategy,
            output_format=args.format,
            min_val_examples=args.min_val_examples,
        )
        print(json.dumps(manifest, indent=2))
        return

    if args.command == "build-benchmark-pack":
        result = build_benchmark_pack(
            dataset_manifest_path=args.dataset_manifest,
            output_dir=args.output_dir,
            min_examples=args.min_examples,
            max_examples=args.max_examples,
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "scaffold-benchmark-templates":
        result = scaffold_benchmark_templates(args.output_dir)
        print(json.dumps(result, indent=2))
        return

    if args.command == "validate-benchmarks":
        result = validate_benchmark_files(
            input_path=args.input_path,
            output_report_path=args.report,
            fail_on_error=not args.no_fail_on_error,
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "merge-benchmark-templates":
        result = merge_benchmark_templates(
            input_path=args.input_path,
            output_dir=args.output_dir,
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "benchmark-gate":
        result = run_benchmark_gate(
            db_path=args.db,
            candidate_model_id=args.candidate_model_id,
            input_path=args.input_path,
            output_dir=args.output_dir,
            policy_file=args.policy_file,
            baseline_model_id=args.baseline_model_id,
            min_grounding_score=args.min_grounding_score,
            max_hallucination_risk=args.max_hallucination_risk,
            min_overall_score=args.min_overall_score,
            min_improvement_over_baseline=args.min_improvement_over_baseline,
            min_benchmark_size=args.min_benchmark_size,
            min_family_examples=args.min_family_examples,
            min_family_grounding_score=args.min_family_grounding_score,
            min_family_contradiction_score=args.min_family_contradiction_score,
            min_family_uncertainty_score=args.min_family_uncertainty_score,
            min_family_actionability_score=args.min_family_actionability_score,
            notes=args.notes,
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "train-model":
        result = run_training_pipeline(
            db_path=args.db,
            dataset_manifest_path=args.dataset_manifest,
            base_model=args.base_model,
            output_dir=args.output_dir,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            seed=args.seed,
            trainer_command=args.trainer_command,
            model_id=args.model_id,
            notes=args.notes,
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "model-registry":
        store = EvidenceStore(args.db)
        store.init_db()
        if args.model_id:
            print(json.dumps(store.get_model(args.model_id), indent=2))
        else:
            print(json.dumps(store.list_models(limit=args.limit), indent=2))
        return

    if args.command == "evaluate-model":
        result = evaluate_model_candidate(
            db_path=args.db,
            candidate_model_id=args.candidate_model_id,
            baseline_model_id=args.baseline_model_id,
            benchmark_manifest_path=args.benchmark_manifest,
            output_dir=args.output_dir,
            min_grounding_score=args.min_grounding_score,
            max_hallucination_risk=args.max_hallucination_risk,
            min_overall_score=args.min_overall_score,
            min_improvement_over_baseline=args.min_improvement_over_baseline,
            min_benchmark_size=args.min_benchmark_size,
            min_family_examples=args.min_family_examples,
            min_family_grounding_score=args.min_family_grounding_score,
            min_family_contradiction_score=args.min_family_contradiction_score,
            min_family_uncertainty_score=args.min_family_uncertainty_score,
            min_family_actionability_score=args.min_family_actionability_score,
            notes=args.notes,
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "model-evaluations":
        store = EvidenceStore(args.db)
        store.init_db()
        if args.evaluation_id:
            print(json.dumps(store.get_model_evaluation(args.evaluation_id), indent=2))
        else:
            print(
                json.dumps(
                    store.list_model_evaluations(
                        candidate_model_id=args.candidate_model_id,
                        limit=args.limit,
                    ),
                    indent=2,
                )
            )
        return

    if args.command == "agent-report":
        store = EvidenceStore(args.db)
        approved = store.approved_claim_ids() if args.require_review_signoff else set()
        if store.knowledge_graph_overview()["edges"] == 0:
            store.rebuild_knowledge_graph()
        support_map = store.graph_support_contradiction_map(limit=30)
        neighbor_rows: list[dict[str, object]] = []
        for row in support_map:
            entity = str(row.get("entity", "")).strip()
            if not entity:
                continue
            for neighbor in store.graph_neighbors(entity, limit=6):
                neighbor_rows.append(
                    {
                        "entity": entity,
                        "neighbor_entity": str(neighbor.get("neighbor_label", "")),
                        "neighbor_label": str(neighbor.get("neighbor_label", "")),
                        "edge_type": str(neighbor.get("edge_type", "")),
                        "neighbor_type": str(neighbor.get("neighbor_type", "")),
                        "polarity": str(neighbor.get("polarity", "")),
                        "weight": neighbor.get("weight", 0.0),
                    }
                )
        report = build_agent_report(
            store.all_evidence(),
            store.contradiction_pairs(),
            require_review_signoff=args.require_review_signoff,
            approved_claim_ids=approved,
            support_map_rows=support_map,
            graph_neighbor_rows=neighbor_rows,
            systems_biology_limit=5,
        )
        print(json.dumps(report, indent=2))
        return

    if args.command == "lineage":
        store = EvidenceStore(args.db)
        print(json.dumps(store.claim_lineage(args.claim_id), indent=2))
        return

    if args.command == "sync-source":
        extractor_config = json.loads(args.extractor_config or "{}")
        if not isinstance(extractor_config, dict):
            raise ValueError("extractor-config must be a JSON object")
        stage_config = json.loads(args.stage_config or "{}")
        if not isinstance(stage_config, dict):
            raise ValueError("stage-config must be a JSON object")
        result = run_incremental_sync(
            db_path=args.db,
            source=args.source,
            query=args.query,
            max_results=args.max_results,
            from_file=args.from_file,
            extractor_config=extractor_config,
            stage_config=stage_config,
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "source-capabilities":
        sources = supported_sources()
        rows = [
            {
                "source": source,
                "status": "runnable",
                "stubbed": False,
                "public": True,
                "requires_credentials": False,
                "supports_incremental": True,
                "supports_metadata_stage": source == "pubmed",
                "notes": "",
            }
            for source in sources
        ]
        if args.only_runnable:
            rows = [row for row in rows if str(row["status"]) == "runnable"]
        if args.only_public:
            rows = [row for row in rows if bool(row["public"]) is True]
        payload = {
            "total": len(rows),
            "rows": rows,
        }
        if args.as_json:
            print(json.dumps(payload, indent=2))
            return
        print(f"total: {payload['total']}")
        for row in rows:
            print(
                f"- {row['source']}: {row['status']} "
                f"(public={str(row['public']).lower()}, "
                f"incremental={str(row['supports_incremental']).lower()}, "
                f"metadata_stage={str(row['supports_metadata_stage']).lower()})"
            )
        return

    if args.command == "recent-changes":
        store = EvidenceStore(args.db)
        print(json.dumps(store.recent_changes(run_id=args.run_id, limit=args.limit), indent=2))
        return

    if args.command == "hypothesis-queue":
        store = EvidenceStore(args.db)
        approved = store.approved_claim_ids() if args.require_review_signoff else set()
        cards = build_hypothesis_queue(
            evidence_rows=store.all_evidence(),
            contradiction_rows=store.contradiction_pairs(),
            limit=args.limit,
            require_review_signoff=args.require_review_signoff,
            approved_claim_ids=approved,
            enforce_causal_gate=args.enforce_causal_gate,
            causal_promotion_overrides=set(args.causal_gate_override_entity),
            promotion_risk_threshold=args.causal_promotion_risk_threshold,
            minimum_strong_support_ratio=args.causal_minimum_strong_support_ratio,
        )
        print(json.dumps(cards, indent=2))
        return

    if args.command == "review-flags":
        store = EvidenceStore(args.db)
        flags = store.review_flags(
            delta_threshold=args.delta_threshold,
            contradiction_density_threshold=args.contradiction_density_threshold,
        )
        print(json.dumps(flags, indent=2))
        return

    if args.command == "schedule-sync":
        result = run_scheduled_sync(
            db_path=args.db,
            plan_file=args.plan,
            cycles=args.cycles,
            interval_seconds=args.interval_seconds,
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "review-decision":
        store = EvidenceStore(args.db)
        store.record_review_decision(
            claim_id=args.claim_id,
            decision=args.decision,
            reviewer=args.reviewer,
            notes=args.notes,
        )
        print(
            json.dumps(
                {
                    "claim_id": args.claim_id,
                    "decision": args.decision,
                    "reviewer": args.reviewer,
                    "status": "recorded",
                },
                indent=2,
            )
        )
        return

    if args.command == "review-log":
        store = EvidenceStore(args.db)
        print(json.dumps(store.list_review_decisions(claim_id=args.claim_id, limit=args.limit), indent=2))
        return

    if args.command == "failure-atlas":
        store = EvidenceStore(args.db)
        print(json.dumps(build_failure_atlas(store.all_evidence_with_provenance()), indent=2))
        return

    if args.command == "debate-report":
        store = EvidenceStore(args.db)
        print(json.dumps(build_debate_report(store.all_evidence(), store.contradiction_pairs()), indent=2))
        return

    if args.command == "consensus-timeline":
        store = EvidenceStore(args.db)
        print(json.dumps(store.consensus_timeline(entity=args.entity, limit=args.limit), indent=2))
        return

    if args.command == "quality-metrics":
        store = EvidenceStore(args.db)
        timeline = store.consensus_timeline(entity=args.entity, limit=args.limit)
        debate = build_debate_report(store.all_evidence(), store.contradiction_pairs())
        failure = build_failure_atlas(store.all_evidence_with_provenance())
        metrics = compute_quality_metrics(timeline, debate, failure)
        print(json.dumps(metrics, indent=2))
        return

    if args.command == "causal-dashboard":
        store = EvidenceStore(args.db)
        dashboard = build_causal_risk_dashboard(
            evidence_rows=store.all_evidence(),
            contradiction_rows=store.contradiction_pairs(),
            entity=args.entity,
            limit=args.limit,
            promotion_risk_threshold=args.promotion_risk_threshold,
            minimum_strong_support_ratio=args.minimum_strong_support_ratio,
        )
        print(json.dumps(dashboard, indent=2))
        return

    if args.command == "graph-build":
        store = EvidenceStore(args.db)
        print(json.dumps(store.rebuild_knowledge_graph(), indent=2))
        return

    if args.command == "graph-overview":
        store = EvidenceStore(args.db)
        print(json.dumps(store.knowledge_graph_overview(), indent=2))
        return

    if args.command == "graph-support-map":
        store = EvidenceStore(args.db)
        print(json.dumps(store.graph_support_contradiction_map(entity=args.entity, limit=args.limit), indent=2))
        return

    if args.command == "graph-neighbors":
        store = EvidenceStore(args.db)
        print(json.dumps(store.graph_neighbors(node_key=args.node_key, limit=args.limit), indent=2))
        return

    if args.command == "trial-analysis-agent":
        store = EvidenceStore(args.db)
        if store.knowledge_graph_overview()["edges"] == 0:
            store.rebuild_knowledge_graph()
        support_map = store.graph_support_contradiction_map(entity=args.entity, limit=args.limit)
        failure = build_failure_atlas(store.all_evidence_with_provenance())
        report = build_clinical_trial_analysis(store.all_evidence(), support_map, failure)
        print(json.dumps(report, indent=2))
        return

    if args.command == "repurposing-agent":
        store = EvidenceStore(args.db)
        if store.knowledge_graph_overview()["edges"] == 0:
            store.rebuild_knowledge_graph()
        support_map = store.graph_support_contradiction_map(entity=args.entity, limit=args.limit)
        failure = build_failure_atlas(store.all_evidence_with_provenance())
        report = build_repurposing_report(store.all_evidence(), support_map, failure)
        print(json.dumps(report, indent=2))
        return

    if args.command == "graph-gap-hypotheses":
        store = EvidenceStore(args.db)
        if store.knowledge_graph_overview()["edges"] == 0:
            store.rebuild_knowledge_graph()
        support_map = store.graph_support_contradiction_map(entity=args.entity, limit=max(args.limit * 5, 20))
        approved = store.approved_claim_ids() if args.require_review_signoff else set()
        cards = build_graph_gap_hypotheses(
            evidence_rows=store.all_evidence(),
            support_map_rows=support_map,
            drift_rows=store.confidence_drift(),
            limit=args.limit,
            require_review_signoff=args.require_review_signoff,
            approved_claim_ids=approved,
        )
        print(json.dumps(cards, indent=2))
        return

    if args.command == "systems-biology-agent":
        store = EvidenceStore(args.db)
        if store.knowledge_graph_overview()["edges"] == 0:
            store.rebuild_knowledge_graph()
        support_map = store.graph_support_contradiction_map(entity=args.entity, limit=max(args.limit * 5, 20))
        neighbor_rows: list[dict[str, object]] = []
        for row in support_map:
            entity = str(row.get("entity", "")).strip()
            if not entity:
                continue
            for neighbor in store.graph_neighbors(entity, limit=8):
                neighbor_rows.append(
                    {
                        "entity": entity,
                        "neighbor_entity": str(neighbor.get("neighbor_label", "")),
                    }
                )
        report = build_systems_biology_report(
            evidence_rows=store.all_evidence(),
            support_map_rows=support_map,
            graph_neighbor_rows=neighbor_rows,
            limit=args.limit,
        )
        print(json.dumps(report, indent=2))
        return

    if args.command == "extraction-fidelity-gate":
        report = evaluate_extraction_fidelity(gold_path=getattr(args, "gold_path", None))
        print(json.dumps(report, indent=2))
        if not bool(report.get("passed")):
            raise SystemExit(1)
        return

    parser.error("Unknown command")


if __name__ == "__main__":
    main()
