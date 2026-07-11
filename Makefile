# Prefer a Python 3.10+ interpreter. Override anytime: make PYTHON=/path/to/python3.11 test
ifeq ($(OS),Windows_NT)
PYTHON ?= py -3
else
PYTHON ?= $(shell (test -x .venv/bin/python && echo .venv/bin/python) || (command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3) 2>/dev/null)
endif
PIP ?= $(PYTHON) -m pip
PYTEST ?= $(PYTHON) -m pytest
ALS ?= $(PYTHON) -m als_intel
DOCKER_COMPOSE ?= docker compose
CONTAINER_PYTHON ?= python
DB_PATH ?= data/als_intel.sqlite
MODEL ?= llama3.1:8b
OLLAMA_HOST ?= http://localhost:11434
WEB_PORT ?= 8000
WEB_DB_PATH ?= /app/data/als_intel.sqlite
WEB_SAMPLE_INPUT ?= /app/examples/sample_evidence.jsonl
SYNC_PLAN ?= config/sync_plan.all_public_sources.json
SYNC_MULTILINGUAL_PLAN ?= config/sync_plan.multilingual_als.json
SYNC_ALL_PLAN ?= config/sync_plan.all_public_sources.json
SYNC_CYCLES ?= 6
SYNC_INTERVAL_SECONDS ?= 900
SYNC_ALL_CYCLES ?= 1
SYNC_ALL_INTERVAL_SECONDS ?= 0
SYNC_STATS_LIMIT ?= 20
HYPOTHESIS_LIMIT ?= 10

.PHONY: help setup test lint init-db ingest-sample chat web-up web-down web-logs docker-up docker-down docker-bootstrap docker-pull-model docker-reset ollama-ps gpu-check docker-gpu-up docker-dev-gpu-up sync-loop sync-all-sources sync-stats hypothesis-check docker-sync-loop docker-sync-all-sources docker-sync-stats docker-hypothesis-check benchmark-gate benchmark-gate-strict validate-benchmarks merge-benchmarks test-regression-queries test-extraction-fidelity train-eval-promote nightly-ops

DOCKER_DEV_COMPOSE = $(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml
DOCKER_GPU_COMPOSE = $(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.gpu.yml
DOCKER_DEV_GPU_COMPOSE = $(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml

help:
	@echo "Available targets:"
	@echo "  setup                 Install the project in editable mode"
	@echo "  test                  Run the full test suite"
	@echo "  init-db               Create the SQLite evidence database"
	@echo "  ingest-sample         Ingest the sample evidence JSONL file"
	@echo "  chat                  Run grounded chat from the CLI"
	@echo "  web-up                Start the Docker web chat stack"
	@echo "  web-down              Stop the Docker web chat stack"
	@echo "  web-logs              Follow web chat container logs"
	@echo "  docker-up             Start Docker stack and bootstrap sample evidence"
	@echo "  docker-dev-up         Start Docker dev stack with bind mounts and auto-reload"
	@echo "                        Mailpit UI at http://localhost:8025 (SMTP magic links)"
	@echo "  docker-gpu-up         Start Docker stack with NVIDIA GPU for Ollama (Linux only)"
	@echo "  docker-dev-gpu-up     Start Docker dev stack with NVIDIA GPU (Linux only)"
	@echo "  docker-bootstrap       Init DB, ingest sample evidence, and pull model in Docker"
	@echo "  docker-pull-model      Pull the Ollama model inside Docker"
	@echo "  ollama-ps             Show active Ollama model processor usage"
	@echo "  gpu-check             Run a long generation and sample GPU + Ollama processor status"
	@echo "  docker-down            Stop the Docker stack"
	@echo "  docker-dev-down       Stop Docker dev stack"
	@echo "  docker-reset          Stop Docker stack and remove the persisted data volume"
	@echo "  sync-loop             Run scheduled sync cycles locally (plan/cycles/interval vars)"
	@echo "  sync-all-sources      Run one full sync cycle over all public sources"
	@echo "  sync-stats            Show recent sync changes and current evidence summary"
	@echo "  hypothesis-check      Verify promoted hypotheses with signoff + causal gate"
	@echo "  docker-sync-loop      Run scheduled sync cycles inside web container"
	@echo "  docker-sync-all-sources Run one full sync cycle over all public sources inside web container"
	@echo "  docker-sync-stats     Show recent sync changes + summary inside web container"
	@echo "  docker-hypothesis-check Verify promoted hypotheses inside web container"
	@echo "  benchmark-gate        Run validate -> merge -> evaluate for benchmark templates"
	@echo "  benchmark-gate-strict Run the strict curated benchmark gate"
	@echo "  validate-benchmarks   Validate curated benchmark JSONL files"
	@echo "  merge-benchmarks      Merge curated benchmark templates into benchmark-ready files"
	@echo "  test-regression-queries Run canonical regression query assertions"
	@echo "  test-extraction-fidelity Run extraction fidelity pytest + CLI gate"
	@echo "  nightly-ops           Chain sync-all-sources, graph-build, and worker tick"

setup:
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

test:
	$(PYTEST) -q

lint:
	$(PYTHON) -m compileall src tests

init-db:
	$(ALS) init-db --db $(DB_PATH)

ingest-sample:
	$(ALS) ingest-jsonl --db $(DB_PATH) --input examples/sample_evidence.jsonl

chat:
	$(ALS) chat --db $(DB_PATH) --model $(MODEL) --host $(OLLAMA_HOST) --interactive

web-up:
	$(DOCKER_COMPOSE) up --build

web-down:
	$(DOCKER_COMPOSE) down

web-logs:
	$(DOCKER_COMPOSE) logs -f web

docker-up:
	$(DOCKER_COMPOSE) up --build -d ollama web
	$(MAKE) docker-bootstrap

docker-dev-up:
	$(DOCKER_DEV_COMPOSE) up --build -d ollama mailpit web
	$(MAKE) docker-bootstrap

docker-gpu-up:
	$(DOCKER_GPU_COMPOSE) up --build -d ollama web
	$(MAKE) docker-bootstrap DOCKER_COMPOSE="$(DOCKER_GPU_COMPOSE)"

docker-dev-gpu-up:
	$(DOCKER_DEV_GPU_COMPOSE) up --build -d ollama mailpit web
	$(MAKE) docker-bootstrap DOCKER_COMPOSE="$(DOCKER_DEV_GPU_COMPOSE)"

docker-bootstrap:
	$(DOCKER_COMPOSE) exec -T web $(CONTAINER_PYTHON) -m als_intel init-db --db $(WEB_DB_PATH)
	$(DOCKER_COMPOSE) exec -T web $(CONTAINER_PYTHON) -m als_intel ingest-jsonl --db $(WEB_DB_PATH) --input $(WEB_SAMPLE_INPUT)
	$(DOCKER_COMPOSE) exec -T ollama ollama pull $(MODEL)

docker-pull-model:
	$(DOCKER_COMPOSE) exec -T ollama ollama pull $(MODEL)

ollama-ps:
	$(DOCKER_COMPOSE) exec -T ollama ollama ps

gpu-check:
	@echo "Starting long inference on model $(MODEL)..."
	@($(DOCKER_COMPOSE) exec -T ollama ollama run $(MODEL) "Write a detailed 20-point analysis of ALS contradictions, uncertainty, and experimental next steps with technical detail." >/tmp/ollama_gpu_check.out 2>&1 &) ; \
	for i in $$(seq 1 20); do \
	  echo "---- sample $$i ----"; \
	  $(DOCKER_COMPOSE) exec -T ollama ollama ps || true; \
	  nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader || true; \
	  sleep 1; \
	done; \
	echo "If PROCESSOR shows CPU-only, restart stack and re-run."; \
	echo "Last Ollama output snippet:"; \
	tail -n 5 /tmp/ollama_gpu_check.out || true

docker-down:
	$(DOCKER_COMPOSE) down

docker-dev-down:
	$(DOCKER_DEV_COMPOSE) down

docker-reset:
	$(DOCKER_COMPOSE) down -v

sync-loop:
	$(ALS) schedule-sync --db $(DB_PATH) --plan $(SYNC_PLAN) --cycles $(SYNC_CYCLES) --interval-seconds $(SYNC_INTERVAL_SECONDS)

sync-all-sources:
	$(ALS) init-db --db $(DB_PATH)
	$(ALS) schedule-sync --db $(DB_PATH) --plan $(SYNC_ALL_PLAN) --cycles $(SYNC_ALL_CYCLES) --interval-seconds $(SYNC_ALL_INTERVAL_SECONDS)

sync-stats:
	$(ALS) recent-changes --db $(DB_PATH) --limit $(SYNC_STATS_LIMIT)
	$(ALS) summarize --db $(DB_PATH)

hypothesis-check:
	$(ALS) hypothesis-queue --db $(DB_PATH) --limit $(HYPOTHESIS_LIMIT) --require-review-signoff --enforce-causal-gate

docker-sync-loop:
	$(DOCKER_COMPOSE) exec -T web $(CONTAINER_PYTHON) -m als_intel schedule-sync --db $(WEB_DB_PATH) --plan /app/$(SYNC_PLAN) --cycles $(SYNC_CYCLES) --interval-seconds $(SYNC_INTERVAL_SECONDS)

docker-sync-all-sources:
	$(DOCKER_COMPOSE) exec -T web $(CONTAINER_PYTHON) -m als_intel init-db --db $(WEB_DB_PATH)
	$(DOCKER_COMPOSE) exec -T web $(CONTAINER_PYTHON) -m als_intel schedule-sync --db $(WEB_DB_PATH) --plan /app/$(SYNC_ALL_PLAN) --cycles $(SYNC_ALL_CYCLES) --interval-seconds $(SYNC_ALL_INTERVAL_SECONDS)

docker-sync-stats:
	$(DOCKER_COMPOSE) exec -T web $(CONTAINER_PYTHON) -m als_intel recent-changes --db $(WEB_DB_PATH) --limit $(SYNC_STATS_LIMIT)
	$(DOCKER_COMPOSE) exec -T web $(CONTAINER_PYTHON) -m als_intel summarize --db $(WEB_DB_PATH)

docker-hypothesis-check:
	$(DOCKER_COMPOSE) exec -T web $(CONTAINER_PYTHON) -m als_intel hypothesis-queue --db $(WEB_DB_PATH) --limit $(HYPOTHESIS_LIMIT) --require-review-signoff --enforce-causal-gate

benchmark-gate:
	$(ALS) benchmark-gate --db $(DB_PATH) --candidate-model-id $(MODEL) --input-path benchmarks/curated --output-dir data/benchmark_gate --policy-file config/benchmark_gate_policy.json

benchmark-gate-strict:
	$(ALS) benchmark-gate --db $(DB_PATH) --candidate-model-id $(MODEL) --input-path benchmarks/curated --output-dir data/benchmark_gate_strict --policy-file config/benchmark_gate_policy.json

validate-benchmarks:
	$(ALS) validate-benchmarks --input-path benchmarks/curated --report data/curated_validation_report.json

merge-benchmarks:
	$(ALS) merge-benchmark-templates --input-path benchmarks/curated --output-dir data/benchmark_curated

test-regression-queries:
	$(PYTEST) -q tests/test_regression_queries.py

test-extraction-fidelity:
	$(PYTEST) -q tests/test_extraction_fidelity.py
	$(ALS) extraction-fidelity-gate

train-eval-promote:
	$(ALS) export-finetune-data --db $(DB_PATH) --output-dir data/finetune --min-reliability 0.55 --min-source-reliability 0.6 --val-ratio 0.2 --split-strategy entity_outcome_hash --format messages --min-val-examples 5
	@MODEL_ID=$$($(ALS) train-model --db $(DB_PATH) --dataset-manifest data/finetune/manifest.json --base-model $(MODEL) --output-dir data/models --trainer-command "bash scripts/local_trainer.sh {train_file} {val_file} {output_dir} {base_model}" | $(PYTHON) -c "import sys, json; print(json.load(sys.stdin)['model_id'])") && \
		echo "Registered candidate model: $$MODEL_ID" && \
		$(ALS) benchmark-gate --db $(DB_PATH) --candidate-model-id $$MODEL_ID --input-path benchmarks/curated --output-dir data/benchmark_gate --policy-file config/benchmark_gate_policy.json

nightly-ops:
	$(MAKE) sync-all-sources
	$(ALS) graph-build --db $(DB_PATH)
	@if [ -z "$$ALS_AUTOMATION_WORKER_TOKEN" ]; then \
		echo "Skipping worker tick: set ALS_AUTOMATION_WORKER_TOKEN to enable automation worker POST."; \
	else \
		curl -fsS -X POST "http://localhost:8000/api/investigation/runs/worker/tick" \
			-H "Authorization: Bearer $$ALS_AUTOMATION_WORKER_TOKEN" \
			-H "Content-Type: application/json" \
			-d '{}'; \
	fi
