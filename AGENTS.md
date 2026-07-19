# AGENTS.md — Cursor guidance for canoniga

This file orients AI agents working in the **canoniga** repository (`als-intel` v0.1.0): a local-first ALS scientific intelligence platform. Runtime deps stay stdlib-only except the Postgres driver (`psycopg`).

## Project purpose

- Ingest, score, and store ALS-related evidence claims in PostgreSQL.
- Detect contradictions, track confidence drift, and rank hypotheses.
- Run deterministic agents (literature, skeptic, debate, graph, repurposing).
- Ground local LLM chat (Ollama) on in-database evidence.
- Expose CLI and a Vue SPA web UI (Vite + TypeScript) backed by a Python REST API.

Design principles: **local-first**, **inspectable heuristics**, **human review gates**, **benchmark-gated model evaluation**.

Governance docs: [docs/MISSION.md](docs/MISSION.md), [docs/ETHICS_AND_OVERSIGHT.md](docs/ETHICS_AND_OVERSIGHT.md), [docs/HUMAN_OVERSIGHT.md](docs/HUMAN_OVERSIGHT.md). Roadmap tracking: [ai/plans/SCIENTIFIC_FIDELITY_ROADMAP.md](ai/plans/SCIENTIFIC_FIDELITY_ROADMAP.md).

## Architecture

```mermaid
flowchart LR
    subgraph inputs [Inputs]
        JSONL[JSONL ingest]
        Sync[Source sync APIs]
    end
    subgraph core [Core]
        Pipeline[pipeline / ingest]
        Scoring[scoring]
        Store[EvidenceStore Postgres]
    end
    subgraph outputs [Outputs]
        CLI[cli.py]
        WebUI[webui.py API + SPA]
        Agents[agents/*]
        LLM[llm.py Ollama]
    end
    JSONL --> Pipeline --> Scoring --> Store
    Sync --> Store
    Store --> CLI
    Store --> WebUI
    Store --> Agents
    Store --> LLM
```

### Module map

| Layer | Path | Role |
|-------|------|------|
| Entry points | `src/als_intel/cli.py`, `__main__.py`, `webui.py` | CLI (38+ subcommands), HTTP API + static SPA |
| Frontend | `frontend/` | Vue 3 + TypeScript investigator UI |
| Static | `src/als_intel/static_frontend.py`, `assets/dist/` | Built SPA assets |
| Domain model | `src/als_intel/models.py` | `EvidenceRecord`, validation constants |
| Persistence | `src/als_intel/store.py`, `db.py` | Postgres queries, auth tables; schema in `migrations/postgres/` |
| Ingestion | `src/als_intel/pipeline.py`, `ingest.py` | JSONL → scored records |
| Scoring | `src/als_intel/scoring.py` | Reliability decomposition |
| Sync | `src/als_intel/sync.py`, `scheduler.py`, `connectors.py` | Incremental source sync |
| Extractors | `src/als_intel/extractors/*` | 15 biomedical source adapters |
| Agents | `src/als_intel/agents/*` | Literature, skeptic, debate, graph, etc. |
| Hypothesis | `src/als_intel/hypothesis.py` | Queue ranking, causal gates |
| LLM / ML | `src/als_intel/llm.py`, `model_catalog.py`, `finetune_data.py`, `training.py`, `evaluation.py`, `benchmark*.py` | Ollama chat, curated model tiers/Auto, fine-tune export, benchmarks |
| Auth | `src/als_intel/auth.py` | Magic-link sessions, CSRF |

### Safe change zones

| Zone | Risk | Guidance |
|------|------|----------|
| `agents/`, `extractors/` | Low | Preferred extension points |
| `cli.py` (new subcommands) | Medium | Follow existing argparse patterns |
| `store.py` (~3.3k lines) | High | Prefer new SQL migrations under `migrations/postgres/` |
| `webui.py` (~3.6k lines) | High | API handlers only; UI in `frontend/` |

## Development workflow

### Setup

**Requires Python 3.10+.** macOS Command Line Tools ship Python 3.9, which is too old. Install a newer interpreter first:

```bash
brew install python@3.11
```

Then create a venv and install:

```bash
python3.11 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
docker compose up -d postgres   # or use an existing Postgres matching DB_DSN
make init-db
make ingest-sample
```

Or use `make setup` after activating the venv (Makefile auto-detects `python3.11`, `python3.12`, or `python3.10` on macOS/Linux). Default DSN: `postgresql://als:als@localhost:5432/als_intel` (`ALS_DATABASE_URL`).

**Platform note:** On Windows, the Makefile defaults to `py -3`. On macOS/Linux it picks the first Python 3.10+ binary on `PATH`. Override if needed:

```bash
make PYTHON=python3.11 test
```

### Common commands

| Command | Purpose |
|---------|---------|
| `make test` | Full pytest suite (isolated `als_intel_test` DB) |
| `make init-test-db` | Create/migrate the pytest-only Postgres database |
| `make lint` | Syntax check (`compileall`) |
| `make test-regression-queries` | Canonical chat/guardrail regression |
| `make benchmark-gate` | Validate → merge → evaluate templates |
| `make benchmark-gate-strict` | Curated benchmark gate (CI strict) |
| `make docker-up` | Docker stack + DB bootstrap + curated Ollama model pulls |
| `make docker-dev-up` | Hot-reload dev stack |
| `make docker-pull-models` | Pull the full curated project model set into Compose Ollama |
| `make frontend-build` | Build Vue SPA into `assets/dist/` |
| `make frontend-dev` | Vite dev server on `:5173` (proxies `/api` to `:8000`) |
| `make web-dev` | Run API locally on `:8000` (uses `.venv` Python) |

### Run web UI locally

Production-style (API serves built SPA on `:8000`):

```bash
make frontend-build
make web-dev
```

Frontend hot reload (API on `:8000`, Vite on `:5173` — open `http://localhost:5173/`):

```bash
make web-dev       # terminal 1
make frontend-dev  # terminal 2
```

i18n: source JSON lives in `src/als_intel/i18n/locales/`; sync copies into `frontend/src/i18n/locales/` via `frontend/scripts/sync-locales.mjs`. App keys are prefixed with `app.` in `frontend/src/i18n/index.ts`.

## Coding conventions

- **Stdlib only** for runtime except `psycopg[binary]` — do not add other packages to `[project.dependencies]`.
- `from __future__ import annotations` in all modules.
- `@dataclass(slots=True)` for record types; validate with `VALID_*` sets and `ValueError`.
- Absolute imports: `from als_intel...`.
- Postgres access only through `EvidenceStore` / `als_intel.db` — no ad-hoc DB drivers in feature code. Legacy SQLite import lives in `migrate_sqlite.py` only.
- CLI: add subcommands in `build_parser()`, dispatch in `main()`.

## Data layout

| Path | Contents |
|------|----------|
| `data/` | Models, evals, finetune artifacts, optional legacy `.sqlite` for import (gitignored) |
| `migrations/postgres/` | Versioned Postgres schema SQL |
| `examples/` | Sample JSONL for ingestion |
| `config/` | Sync plans, benchmark gate policy |
| `benchmarks/curated/` | Curated benchmark JSONL for strict CI |
| `tests/fixtures/` | Regression query fixtures |

## Testing

- Framework: **pytest** (installed via `.[dev]`).
- Postgres required: isolated test DB `als_intel_test` via `ALS_TEST_DATABASE_URL` (default `postgresql://als:als@localhost:5432/als_intel_test`). `tests/conftest.py` truncates **only** that database between tests — never the app DB `als_intel`.
- Create/migrate the test DB with `make init-test-db` (also auto-created on first pytest via `ensure_database`).
- Seed via `EvidenceStore()` or inline JSONL. Avoid live network calls in unit tests.
- Web UI tests: `ThreadingHTTPServer` + `urllib.request` (see `tests/test_webui_api.py`).
- Update `tests/fixtures/regression_queries.json` only when changing chat/guardrail behavior.

## CI gates

Two GitHub Actions workflows must stay green:

- `.github/workflows/benchmark-gate.yml` — full pytest + regression queries + benchmark gate smoke
- `.github/workflows/benchmark-gate-strict.yml` — curated benchmark validation + strict gate

Do not break regression queries or benchmark gates when modifying chat, guardrails, or evaluation logic.

## Environment variables (web/auth)

Key variables (full list in README):

- `ALS_DATABASE_URL` (or `ALS_PG_*`), `OLLAMA_HOST`, `OLLAMA_MODEL` — DB DSN and LLM
- `ALS_TEST_DATABASE_URL` — pytest-only DB (default `…/als_intel_test`); must not point at the app DB
- Optional `ALS_OLLAMA_MODELS` — comma allowlist for `GET /api/models` / Auto picker
- Model balancing: curated catalog in `model_catalog.py` is the **project-hosted model set** (`curated_pull_tags()`). `make docker-pull-models` / `docker-bootstrap` pulls every curated tag into Compose Ollama (large download; per-tag failures skipped). Catalog enriches installed tags with `tier` / `family` / `display_name`; `GET /api/models` also returns `recommended` for any still-missing curated tags. Auto (`resolve_chat_model`) maps question complexity to tier floors (complex → High/Best when installed; never Fast if a higher tier exists).
- Chat evidence candidates default to `max(context_limit * 10, 200)` (cap 20000). Override with `ALS_CHAT_EVIDENCE_MAX_ROWS` or request `evidence_max_rows` (>0). Non-positive no longer means unbounded for chat.
- Legacy one-shot import: `als-intel migrate-from-sqlite --sqlite path/to/als_intel.sqlite`
- Rollback: there is no dual-engine toggle; restore a prior release plus a SQLite/Postgres backup as appropriate.
- `ALS_AUTH_ENABLED`, `ALS_MAGIC_LINK_DEV_MODE` — auth gate (dev mode returns link in API)
- `ALS_CSRF_SECRET` — CSRF for authenticated POST endpoints
- SMTP: `ALS_SMTP_HOST`, `ALS_SMTP_USER`, `ALS_SMTP_PASSWORD` — never commit credentials
- Local email testing: `make docker-dev-up` wires SMTP to Mailpit at http://localhost:8025 (magic links sent as real emails, not returned in API)

## Roadmap and plans

Before large features, read the relevant plan in `ai/plans/`:

| Plan | Topic |
|------|-------|
| `PLATFORM_NEXT_STEPS_PLAN.md` | Telemetry, guardrails, regression, ranking |
| `AUTOMATION_FIRST_ROADMAP_PLAN.md` | Autonomous investigation runs |
| `AUTH_SESSION_PLAN.md` | Auth/session hardening |
| `DATASOURCE_PLAN.md` | New data source integration |
| `POSTGRES_MIGRATION_PLAN.md` | Postgres cutover (local/CI done; prod is ops) |

## Cursor rules

File-specific guidance lives in `.cursor/rules/`:

- `project-core.mdc` — always-on project standards
- `python-conventions.mdc` — Python patterns
- `testing.mdc` — test conventions
- `webui.mdc` — Vue frontend + Python API guidance
- `extractors-agents.mdc` — agent and extractor extension patterns
- `emails.mdc` — email template conventions

## Email templates

Branded HTML emails live in [`src/als_intel/emails/`](src/als_intel/emails/). Read [`src/als_intel/emails/README.md`](src/als_intel/emails/README.md) before adding or changing templates. Always ship HTML + plain-text multipart messages; preview locally in Mailpit at http://localhost:8025 (`make docker-dev-up`).
