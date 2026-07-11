# Scientific Fidelity Roadmap

Track implementation progress for the 6-month Canoniga scientific intelligence roadmap.

## Status Legend
- [ ] Not started
- [~] In progress
- [x] Done

## Phase 1 — Structured claim extraction
- [x] `claim_builder.py` two-stage pipeline for PubMed and ClinicalTrials.gov
- [x] CTGov connector enriched with trial status, phase, enrollment, endpoints
- [x] Extraction provenance stored in `evidence_source_metadata`
- [x] `extraction_fidelity` benchmark family and CI tests

## Phase 2 — Knowledge depth
- [x] Structured failed-trial corpus in Historical Failure Agent
- [x] Systems Biology agent (`systems_biology.py`)
- [x] Default sync plan promoted to all public sources

## Phase 3 — Trust and autonomy
- [x] Runtime claim verification guardrail in web UI responses
- [x] Local trainer script and Makefile train-eval-promote target
- [x] Longitudinal ops runbook for investigation worker tick

## Phase 4 — Platform maturity
- [x] Mission, ethics, and human oversight governance docs
- [x] Restricted datasource stubs with `AccessNotConfiguredError`

## Deferred
- [ ] PostgreSQL migration (trigger on scale pain point)
