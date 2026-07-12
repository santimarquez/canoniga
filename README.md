# ALS Scientific Intelligence (Local-First)

This repository contains the first implementation phase of a local, open-source ALS scientific intelligence platform.

## CI visibility

![Benchmark Gate Smoke](https://github.com/santimarquez/canoniga/actions/workflows/benchmark-gate.yml/badge.svg?branch=master)
![Benchmark Gate Strict](https://github.com/santimarquez/canoniga/actions/workflows/benchmark-gate-strict.yml/badge.svg?branch=master)

Active workflow definitions:

- [Benchmark Gate Smoke](.github/workflows/benchmark-gate.yml)
- [Benchmark Gate Strict](.github/workflows/benchmark-gate-strict.yml)

Latest `master` CI status: [Actions runs](https://github.com/santimarquez/canoniga/actions)

## Phase 1 scope

- Canonical evidence schema for research claims.
- Evidence reliability scoring (explicit, inspectable heuristics).
- JSONL ingestion pipeline for ALS-related studies.
- SQLite evidence store with contradiction detection.
- CLI for initialization, ingestion, summaries, and contradiction reports.

## Phase 1.1 additions

- Provenance extensions: cohort, model system, source type, extraction confidence.
- Score decomposition into interpretable reliability components.
- Separate source reliability score tracked independently from claim reliability.
- Temporal evidence history for confidence drift tracking.
- Richer contradiction typing with suggested follow-up experiments.
- Deterministic initial agents:
	- Literature Analysis Agent (labels: fact, hypothesis, conjecture)
	- Skeptic Agent (falsification-focused contradiction alerts)
	- Causal-risk guardrail that blocks fact labels when contradiction density is high.

## Stage 2 additions (current)

- Incremental source sync for PubMed and ClinicalTrials.gov.
- Sync run tracking with insert/update/unchanged counters.
- Change-log table for traceable updates per sync run.
- Hypothesis queue generator with supporting and contradictory evidence cards.
- Trial-feasibility score in hypothesis ranking (cohort and endpoint compatibility aware).
- Local scheduler runner for repeated incremental sync cycles.
- Automatic review flags for claims with high confidence drift or high contradiction density.
- Human sign-off gate to block hypothesis queue promotion until reviewer approval exists.

## Stage 3 additions (current)

- Historical Failure Agent with root-cause taxonomy and reusable lessons.
- Debate Protocol v1 with challenge and rebuttal rounds over contradictions.
- Consensus timeline report with change rationale tracking.
- Calibration metrics: consensus stability, debate disagreement, and failure recurrence.
- Local biomedical knowledge graph layer with support-vs-contradiction queries.
- Graph-driven specialized agents: Clinical Trial Analysis and Drug Repurposing.
- Graph-driven gap hypothesis generation with explicit why-now signals.
- Causal evidence tagging per claim (observational, interventional, mechanistic, genetic, negative).
- Hypothesis cards now include explicit causal-risk scores.
- Repurposing rankings now use transparent MCDA component scoring.
- Causal dashboard for entity-level promotion blocks based on risk and strong causal support.
- Local LLM chat mode (Ollama-compatible) grounded on in-database ALS evidence.
- Fine-tuning dataset export pipeline (OpenAI-style train/val JSONL + manifest).

## Scientific fidelity additions (current)

- Structured claim extraction pipeline for **all 15 public sources** (`claim_builder.py`).
- Extraction fidelity benchmark gate (`make test-extraction-fidelity`) with **43** gold cases.
- Systems Biology agent for pathway neighborhood hypotheses.
- Runtime claim verification guardrails in web chat/synthesis responses.
- Default scheduler plan uses all 15 public sources (`config/sync_plan.all_public_sources.json`).
- Restricted datasource stubs (DrugBank, Project MinE, Answer ALS, ALS-TDI, NEALS, ALS Association).
- Governance docs in `docs/` and longitudinal ops runbook in `ai/plans/LONGITUDINAL_OPS_RUNBOOK.md`.

## Nightly operations

Run unattended sync, graph rebuild, and worker tick:

```bash
export ALS_AUTOMATION_WORKER_TOKEN="<worker-token>"
make nightly-ops
```

For a bounded live API smoke sync (5 records per source):

```bash
SYNC_ALL_PLAN=config/sync_plan.smoke_public_sources.json make sync-all-sources
make sync-stats
```

## Local training path

`make train-eval-promote` exports finetune data, runs [`scripts/local_trainer.sh`](scripts/local_trainer.sh) (Ollama `create` when available), and evaluates via benchmark gate using the **registered model id** returned by `train-model`. The trainer writes a non-simulated marker (`real-ollama-create` or `real-offline-trainer`) in `data/models/<model_id>/adapter.bin`.

Example smoke run (2026-07-11):

```bash
DB_PATH=data/smoke.sqlite make train-eval-promote
# Registered candidate model: als-20260711224145-dd12ad06
```

## Quick start

**Requires Python 3.10+.** On macOS, install with `brew install python@3.11` if your system `python3` is older.

1. Create and activate a virtual environment with Python 3.10+:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

2. Install in editable mode (includes pytest for development):

```bash
python -m pip install -e ".[dev]"
```

Or use `make setup` (auto-detects Python 3.10+ on macOS/Linux).

For AI-assisted development in Cursor, see [AGENTS.md](AGENTS.md).

3. Initialize the database:

```bash
als-intel init-db --db data/als_intel.sqlite
```

4. Ingest sample evidence:

```bash
als-intel ingest-jsonl --db data/als_intel.sqlite --input examples/sample_evidence.jsonl
```

5. Inspect summary and contradictions:

```bash
als-intel summarize --db data/als_intel.sqlite
als-intel contradictions --db data/als_intel.sqlite
als-intel drift --db data/als_intel.sqlite
als-intel export-finetune-data --db data/als_intel.sqlite --output-dir data/finetune --min-reliability 0.55 --min-source-reliability 0.6 --val-ratio 0.2 --split-strategy entity_outcome_hash --format messages --min-val-examples 20
als-intel train-model --db data/als_intel.sqlite --dataset-manifest data/finetune/manifest.json --base-model llama3.1:8b --output-dir data/models --epochs 3 --batch-size 4
als-intel model-registry --db data/als_intel.sqlite --limit 20
als-intel build-benchmark-pack --dataset-manifest data/finetune/manifest.json --output-dir data/benchmark --min-examples 20 --max-examples 200
als-intel scaffold-benchmark-templates --output-dir data/benchmark_templates
als-intel validate-benchmarks --input-path data/benchmark_templates --report data/benchmark_templates/validation_report.json
als-intel merge-benchmark-templates --input-path data/benchmark_templates --output-dir data/benchmark_curated
als-intel benchmark-gate --db data/als_intel.sqlite --candidate-model-id als-20260624000000-abc12345 --input-path data/benchmark_templates --output-dir data/benchmark_gate --policy-file config/benchmark_gate_policy.json
als-intel evaluate-model --db data/als_intel.sqlite --candidate-model-id als-20260624000000-abc12345 --benchmark-manifest data/benchmark/benchmark_manifest.json --output-dir data/evals --min-overall-score 0.7 --min-benchmark-size 20 --min-family-examples 5 --min-family-grounding-score 0.75 --min-family-contradiction-score 0.65 --min-family-uncertainty-score 0.6 --min-family-actionability-score 0.65
als-intel model-evaluations --db data/als_intel.sqlite --limit 20
als-intel chat --db data/als_intel.sqlite --question "What are the strongest contradictory signals?"
als-intel agent-report --db data/als_intel.sqlite
als-intel agent-report --db data/als_intel.sqlite --require-review-signoff
als-intel lineage --db data/als_intel.sqlite --claim-id C1
als-intel sync-source --db data/als_intel.sqlite --source pubmed --query "amyotrophic lateral sclerosis"
als-intel recent-changes --db data/als_intel.sqlite --limit 20
als-intel hypothesis-queue --db data/als_intel.sqlite --limit 10
als-intel hypothesis-queue --db data/als_intel.sqlite --limit 10 --require-review-signoff
als-intel hypothesis-queue --db data/als_intel.sqlite --limit 10 --enforce-causal-gate
als-intel hypothesis-queue --db data/als_intel.sqlite --limit 10 --enforce-causal-gate --causal-gate-override-entity "microglial activation"
als-intel review-flags --db data/als_intel.sqlite
als-intel schedule-sync --db data/als_intel.sqlite --plan config/sync_plan.all_public_sources.json --cycles 1 --interval-seconds 0
als-intel review-decision --db data/als_intel.sqlite --claim-id PUBMED_40000001 --decision approve --reviewer reviewer_a --notes "sufficient confidence"
als-intel review-log --db data/als_intel.sqlite --limit 20
als-intel failure-atlas --db data/als_intel.sqlite
als-intel debate-report --db data/als_intel.sqlite
als-intel consensus-timeline --db data/als_intel.sqlite --limit 50
als-intel quality-metrics --db data/als_intel.sqlite --limit 200
als-intel causal-dashboard --db data/als_intel.sqlite --limit 50
als-intel graph-build --db data/als_intel.sqlite
als-intel graph-overview --db data/als_intel.sqlite
als-intel graph-support-map --db data/als_intel.sqlite --limit 50
als-intel graph-neighbors --db data/als_intel.sqlite --node-key "entity:microglial activation" --limit 20
als-intel trial-analysis-agent --db data/als_intel.sqlite --limit 50
als-intel repurposing-agent --db data/als_intel.sqlite --limit 50
als-intel graph-gap-hypotheses --db data/als_intel.sqlite --limit 10
als-intel graph-gap-hypotheses --db data/als_intel.sqlite --limit 10 --require-review-signoff
als-intel systems-biology-agent --db data/als_intel.sqlite --limit 10
als-intel extraction-fidelity-gate
make train-eval-promote
```

## Docker web chat

You can run a small browser-based chat UI with Docker and Ollama.

1. Start the stack:

```bash
docker compose up --build
```

2. In a second terminal, pull a local model into the Ollama container once:

```bash
docker compose exec ollama ollama pull llama3.1:8b
```

3. Open the website:

```text
http://localhost:8000
```

The web page talks to the local Ollama service and grounds replies with evidence rows from `data/als_intel.sqlite`. If the database is empty, the chat still works, but without local evidence context.

To bring up the whole project locally with Docker and seed sample evidence, use:

```bash
make docker-up
```

For development with hot reload (no rebuild/restart cycle after each Python change), use:

```bash
make docker-dev-up
```

This command uses `docker-compose.dev.yml` to bind-mount the repository into `/app` and run the web process with file watching. Python edits under `src/`, `config/`, and `examples/` automatically restart only the `web` process inside the container.

To stop that dev stack:

```bash
make docker-dev-down
```

That command starts the Ollama and web containers, initializes the SQLite database inside the web container, ingests `examples/sample_evidence.jsonl`, and pulls the configured model into Ollama.

Compose uses project-scoped container names, so repeated `make docker-up` runs should not collide with prior containers.

By default, Ollama runs **CPU-only** so Docker works on macOS and machines without NVIDIA GPUs. On Linux with the NVIDIA Container Toolkit installed, enable GPU inference with:

```bash
make docker-gpu-up
# or for dev mode:
make docker-dev-gpu-up
```

After startup on NVIDIA hosts, confirm GPU usage with:

```bash
make ollama-ps
make gpu-check
```

`make gpu-check` runs a long generation while sampling `ollama ps` and `nvidia-smi` so you can confirm active GPU utilization during inference.

If you want to run the web UI without Docker, you can use:

```bash
python -m als_intel.webui --db data/als_intel.sqlite --ollama-host http://localhost:11434 --model llama3.1:8b
```

## Authentication and magic-link configuration

The web UI supports email-based magic-link authentication with per-user activity logging and user-scoped saved sessions.

Core auth settings:

- `ALS_AUTH_ENABLED` (default: `1`): enable auth gate and user scoping.
- `ALS_APP_BASE_URL` (default: `http://localhost:8000`): base URL used to generate magic links.
- `ALS_MAGIC_LINK_TTL_SECONDS` (default: `900`): magic-link lifetime.
- `ALS_SESSION_TTL_SECONDS` (default: `28800`): auth session lifetime.
- `ALS_SESSION_RENEW_WINDOW_SECONDS` (default: `900`): when remaining lifetime falls below this threshold, `/api/auth/status` rotates and renews the session token.
- `ALS_AUTH_COOKIE_NAME` (default: `als_session`): session cookie name.

Magic-link delivery:

- `ALS_MAGIC_LINK_DEV_MODE` (default: `1`): when enabled, the API returns the magic link directly for local testing.
- `ALS_SMTP_HOST` (default: empty): SMTP host for production delivery.
- `ALS_SMTP_PORT` (default: `587`): SMTP port.
- `ALS_SMTP_USER` / `ALS_SMTP_PASSWORD` (default: empty): optional SMTP auth credentials.
- `ALS_SMTP_FROM` (default: `no-reply@localhost`): sender email.
- `ALS_SMTP_STARTTLS` (default: `1`): enable STARTTLS.

### Local email testing (Mailpit)

The dev Docker stack (`make docker-dev-up`) includes [Mailpit](https://mailpit.axllent.org/) to capture magic-link emails locally instead of returning them in the API response.

| Service | URL |
|---------|-----|
| Mailpit inbox (view captured emails) | http://localhost:8025 |
| Web UI | http://localhost:8000 |

The dev overlay sets `ALS_MAGIC_LINK_DEV_MODE=0` and routes SMTP to `mailpit:1025`. Request a sign-in link in the web UI, then open Mailpit to read and click the link.

For non-Docker local runs with Mailpit already running (`docker compose up -d mailpit`):

```bash
export ALS_MAGIC_LINK_DEV_MODE=0
export ALS_SMTP_HOST=localhost
export ALS_SMTP_PORT=1025
export ALS_SMTP_STARTTLS=0
```

Rate-limiting:

- `ALS_MAGIC_LINK_RATE_LIMIT_COUNT` (default: `3`): max requests allowed per email in window.
- `ALS_MAGIC_LINK_RATE_LIMIT_WINDOW_SECONDS` (default: `600`): rolling window for request limiting.
- `ALS_MAGIC_LINK_RATE_LIMIT_IP_COUNT` (default: `10`): max requests allowed per source IP in the same rolling window.

CSRF protection:

- `ALS_CSRF_SECRET` (default: `als-csrf-secret-local`): secret used to derive per-session CSRF tokens for authenticated POST endpoints.

Cookie policy controls:

- `ALS_COOKIE_SECURE` (default: `0`): set `Secure` flag.
- `ALS_COOKIE_HTTPONLY` (default: `1`): set `HttpOnly` flag.
- `ALS_COOKIE_SAMESITE` (default: `Lax`): allowed values are `Lax`, `Strict`, `None`.
- `ALS_COOKIE_PATH` (default: `/`): cookie path.
- `ALS_COOKIE_DOMAIN` (default: empty): optional cookie domain.

## Production auth checklist

Before exposing a self-hosted instance on the public internet:

1. Set `ALS_MAGIC_LINK_DEV_MODE=0` so magic links are emailed, not returned in API responses.
2. Configure real SMTP (`ALS_SMTP_HOST`, `ALS_SMTP_PORT`, `ALS_SMTP_USER`, `ALS_SMTP_PASSWORD`, `ALS_SMTP_FROM`). Use Mailpit (`localhost:8025`) only for local development.
3. Set `ALS_COOKIE_SECURE=1` behind an HTTPS reverse proxy (nginx, Caddy, Traefik).
4. Keep default rate limits (`ALS_MAGIC_LINK_RATE_LIMIT_*`) unless you have alternate abuse protection.
5. Set a strong `ALS_CSRF_SECRET` and restrict database file permissions.
6. Create `ALS_AUTOMATION_WORKER_TOKEN` for scheduled `make nightly-ops` / `make docker-nightly-ops` worker ticks.
7. Serve governance docs locally at `/docs/MISSION.md` (no GitHub dependency required).

Production baseline recommendation:

- Set `ALS_MAGIC_LINK_DEV_MODE=0`.
- Configure SMTP variables.
- Set `ALS_COOKIE_SECURE=1` and use HTTPS.
- Consider `ALS_COOKIE_SAMESITE=Strict` when cross-site flows are not required.

## Makefile shortcuts

Use the included [Makefile](Makefile) for shorter local commands:

```bash
make setup
make test
make init-db
make ingest-sample
make web-up
make web-down
make chat
make benchmark-gate
make benchmark-gate-strict
make validate-benchmarks
make merge-benchmarks
make nightly-ops
make docker-nightly-ops
```

`make chat` opens the CLI chat loop. `make web-up` starts the Docker web UI at `http://localhost:8000`.

### Local LLM setup (Ollama)

1. Install and run Ollama.
2. Pull a local model, for example:

```bash
ollama pull llama3.1:8b
```

3. Use one-shot grounded chat:

```bash
als-intel chat --db data/als_intel.sqlite --model llama3.1:8b --question "Which mechanisms are most uncertain and why?"
```

4. Use interactive mode:

```bash
als-intel chat --db data/als_intel.sqlite --model llama3.1:8b --interactive
```

### Fine-tuning data export

Export train/validation files for supervised fine-tuning:

```bash
als-intel export-finetune-data --db data/als_intel.sqlite --output-dir data/finetune --min-reliability 0.55 --min-source-reliability 0.6 --val-ratio 0.2 --split-strategy entity_outcome_hash --format messages --min-val-examples 20
```

Outputs:

- `train.jsonl`
- `val.jsonl`
- `manifest.json`

Manifest includes QA checks for duplicate claim ids, filter drop counts, contradiction coverage, train/validation leakage, and whether validation rows meet required minimum size.

### Model training and registry

Run local training pipeline (simulated by default unless `--trainer-command` is provided):

```bash
als-intel train-model --db data/als_intel.sqlite --dataset-manifest data/finetune/manifest.json --base-model llama3.1:8b --output-dir data/models --epochs 3 --batch-size 4
```

List or inspect registered models:

```bash
als-intel model-registry --db data/als_intel.sqlite --limit 20
als-intel model-registry --db data/als_intel.sqlite --model-id als-20260624000000-abc12345
```

### Model evaluation and promotion gate

Evaluate candidate model versus benchmark with automatic promotion gate checks:

```bash
als-intel build-benchmark-pack --dataset-manifest data/finetune/manifest.json --output-dir data/benchmark --min-examples 20 --max-examples 200
als-intel scaffold-benchmark-templates --output-dir data/benchmark_templates
als-intel validate-benchmarks --input-path data/benchmark_templates --report data/benchmark_templates/validation_report.json
als-intel merge-benchmark-templates --input-path data/benchmark_templates --output-dir data/benchmark_curated
als-intel evaluate-model --db data/als_intel.sqlite --candidate-model-id als-20260624000000-abc12345 --baseline-model-id als-20260623000000-def67890 --benchmark-manifest data/benchmark_curated/benchmark_manifest.json --output-dir data/evals --min-grounding-score 0.65 --max-hallucination-risk 0.35 --min-overall-score 0.70 --min-improvement-over-baseline 0.02 --min-benchmark-size 20 --min-family-examples 5 --min-family-grounding-score 0.75 --min-family-contradiction-score 0.65 --min-family-uncertainty-score 0.6 --min-family-actionability-score 0.65
als-intel benchmark-gate --db data/als_intel.sqlite --candidate-model-id als-20260624000000-abc12345 --baseline-model-id als-20260623000000-def67890 --input-path data/benchmark_templates --output-dir data/benchmark_gate --policy-file config/benchmark_gate_policy.json
```

Benchmark packs include family-specific files under `files.families` for: grounding, contradiction, uncertainty, and actionability.
Use `scaffold-benchmark-templates` to generate starter benchmark rows and authoring guidance.
Use `validate-benchmarks` before build/evaluate to ensure benchmark rows satisfy required fields and types.
Use `merge-benchmark-templates` to normalize curated rows and produce a deduplicated benchmark manifest (`benchmark_manifest.json`) ready for `evaluate-model`.
Use `benchmark-gate` to run validation, merge, and evaluation in one command. Outputs include:

- `validation_report.json`
- `merged/benchmark_manifest.json`
- `eval/<evaluation_id>.json`
- `benchmark_gate_summary.json`

Gate thresholds can be versioned in [config/benchmark_gate_policy.json](config/benchmark_gate_policy.json) and loaded with `--policy-file`.

### CI benchmark gate

GitHub Actions workflow [/.github/workflows/benchmark-gate.yml](.github/workflows/benchmark-gate.yml) runs a deterministic smoke gate:

- full test suite (`pytest -q`)
- deterministic benchmark fixture generation
- one-command gate execution (`benchmark-gate`) using [config/benchmark_gate_policy.json](config/benchmark_gate_policy.json)
- artifact upload for gate outputs

GitHub Actions workflow [/.github/workflows/benchmark-gate-strict.yml](.github/workflows/benchmark-gate-strict.yml) runs a strict curated-data gate:

- validates curated JSONL presence under [benchmarks/curated/README.md](benchmarks/curated/README.md)
- runs one-command gate against repository-curated benchmark files
- uploads strict gate outputs as artifacts

Run locally with equivalent command:

```bash
als-intel benchmark-gate --db data/als_intel.sqlite --candidate-model-id YOUR_MODEL_ID --input-path data/benchmark_templates --output-dir data/benchmark_gate --policy-file config/benchmark_gate_policy.json
```

Run strict local equivalent against curated files:

```bash
als-intel benchmark-gate --db data/als_intel.sqlite --candidate-model-id YOUR_MODEL_ID --input-path benchmarks/curated --output-dir data/benchmark_gate_strict --policy-file config/benchmark_gate_policy.json
```

Query evaluation registry:

```bash
als-intel model-evaluations --db data/als_intel.sqlite --limit 20
als-intel model-evaluations --db data/als_intel.sqlite --evaluation-id eval-20260624000000-abc12345
```

## Data model philosophy

The system separates evidence from conclusions and keeps contradictory findings visible. It is intended for research acceleration, not diagnosis or clinical decision-making.

## Output contract

- Facts: high-confidence evidence statements with traceable provenance.
- Hypotheses: plausible but incomplete evidence patterns requiring validation.
- Conjectures: weak-signal ideas intended for exploratory follow-up only.

When contradiction density is high for an entity, the causal-risk guardrail prevents automatic "fact" labeling even if raw confidence is high.

All high-impact interpretations require human scientific review.
