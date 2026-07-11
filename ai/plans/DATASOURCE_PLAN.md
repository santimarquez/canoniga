# DATASOURCE_PLAN

## Purpose
Track implementation status for all requested datasource extractors and keep a single execution ledger for implemented vs pending work.

## Architecture Decisions
- Extractors must be decoupled modules under src/als_intel/extractors.
- Sync orchestration in src/als_intel/sync.py must use registry dispatch (no source-specific if/elif branching).
- Source-specific normalization and enrichment rules must stay inside each extractor module.
- Restricted sources are implemented as explicit stubs until credentials/licenses are configured.

## Implementation Status Summary
- [x] Phase 0: Plan tracking file created and initialized.
- [x] Phase 1: Extractor foundation implemented (base interface, registry, PubMed/ClinicalTrials extractors migrated).
- [x] Phase 2: Per-source extractor_config and stage_config in scheduler plans.
- [x] Phase 3: Public-source onboarding batch A (completed).
- [x] Phase 4: Restricted-source stubs batch (`restricted.py` stubs with `AccessNotConfiguredError`).
- [x] Phase 5: Cross-source reliability/provenance hardening (contract validation + connector retry/backoff policies complete).
- [x] Phase 6: UI/API source visibility extensions for all public sources (provenance fields surfaced in DB explorer API/detail).
- [x] Phase 7: Comprehensive source-by-source test matrix for public sources.

## Source Matrix

### Already Implemented
- [x] PubMed
- [x] ClinicalTrials.gov
- [x] PubMed Central (PMC)
- [x] NCBI Gene
- [x] UniProt
- [x] Gene Ontology (GO)
- [x] Reactome
- [x] GEO (Gene Expression Omnibus)
- [x] ArrayExpress
- [x] KEGG
- [x] Proteomics databases (PRIDE as first concrete target)
- [x] Metabolomics Workbench
- [x] ChEMBL
- [x] Open Targets
- [x] FDA Drug Labels

### Pending Public / Likely Public Access
- none

### Pending Restricted / Credentialed / Agreement-Based
- [ ] DrugBank (license constraints)
- [ ] Project MinE (DAC approval expected)
- [ ] Answer ALS (access approval expected)
- [ ] ALS Therapy Development Institute (access agreement expected)
- [ ] NEALS (access model TBD)
- [ ] ALS Association Research (access model TBD)

## Current Implemented Components
- src/als_intel/extractors/base.py
- src/als_intel/extractors/registry.py
- src/als_intel/extractors/normalization.py
- src/als_intel/extractors/pubmed.py
- src/als_intel/extractors/clinicaltrials.py
- src/als_intel/extractors/pmc.py
- src/als_intel/extractors/ncbi_gene.py
- src/als_intel/extractors/uniprot.py
- src/als_intel/extractors/go.py
- src/als_intel/extractors/reactome.py
- src/als_intel/extractors/geo.py
- src/als_intel/extractors/arrayexpress.py
- src/als_intel/extractors/kegg.py
- src/als_intel/extractors/pride.py
- src/als_intel/extractors/metabolomics_workbench.py
- src/als_intel/extractors/chembl.py
- src/als_intel/extractors/open_targets.py
- src/als_intel/extractors/fda_labels.py
- src/als_intel/extractors/__init__.py
- src/als_intel/sync.py (registry-driven orchestrator)
- src/als_intel/scheduler.py (per-job extractor/stage config pass-through)
- src/als_intel/cli.py (source choices derived from registry + sync config flags)
- src/als_intel/connectors.py (all public-source connectors, including KEGG/PRIDE/Metabolomics Workbench/ChEMBL/Open Targets/FDA Labels)
- examples/pmc_sample.json
- examples/ncbi_gene_sample.json
- examples/uniprot_sample.json
- examples/go_sample.json
- examples/reactome_sample.json
- examples/geo_sample.json
- examples/arrayexpress_sample.json
- examples/kegg_sample.json
- examples/pride_sample.json
- examples/metabolomics_workbench_sample.json
- examples/chembl_sample.json
- examples/open_targets_sample.json
- examples/fda_labels_sample.json
- tests/test_sync.py (all public sources + config regression coverage)
- tests/test_webui_api.py (all public source URL coverage)

## Pending Next 3
1. Implement restricted-source stubs with AccessNotConfigured behavior and capability flags.
2. Extend source-capabilities output to include restricted sources as non-runnable/stubbed entries.
3. Add restricted-source failure-path tests and operator-facing access requirement checklists.

## Risks and Notes
- API rate limits vary by source; per-extractor throttling/backoff will be required.
- Licensing constraints must be checked before enabling live pulls for restricted sources.
- Some sources may require staged ingestion (metadata first, details later).

## Changelog
- 2026-07-01: Created DATASOURCE_PLAN.md and marked Phase 1 foundation as implemented.
- 2026-07-01: Completed Phase 2 config plumbing (extractor_config + stage_config), implemented PMC extractor, and added fixture-backed tests.
- 2026-07-01: Implemented NCBI Gene extractor with connector and fixture-backed tests; added NCBI Gene source URL mapping.
- 2026-07-01: Implemented UniProt extractor with connector and fixture-backed tests; added UniProt source URL mapping.
- 2026-07-01: Implemented GO extractor with QuickGO connector and fixture-backed tests; added GO source URL mapping.
- 2026-07-01: Implemented Reactome extractor with connector and fixture-backed tests; added Reactome source URL mapping.
- 2026-07-01: Implemented GEO extractor with connector and fixture-backed tests; added GEO source URL mapping.
- 2026-07-01: Implemented ArrayExpress extractor with connector and fixture-backed tests; added ArrayExpress source URL mapping.
- 2026-07-01: Implemented KEGG extractor with connector and fixture-backed tests; added KEGG source URL mapping.
- 2026-07-01: Implemented PRIDE extractor as the first public proteomics target with fixture-backed tests; added PRIDE source URL mapping.
- 2026-07-01: Implemented Metabolomics Workbench extractor with fixture-backed tests; added source URL mapping.
- 2026-07-01: Implemented ChEMBL extractor with connector and fixture-backed tests; added source URL mapping.
- 2026-07-01: Implemented Open Targets extractor with GraphQL connector and fixture-backed tests; added source URL mapping.
- 2026-07-01: Implemented FDA Drug Labels extractor with connector and fixture-backed tests; added source URL mapping.
- 2026-07-01: Added cross-source provenance metadata persistence for all sync-ingested records and new mixed-source schedule/provenance tests.
- 2026-07-01: Added CLI source-capabilities command to report runnable registered datasource extractors.
- 2026-07-01: Added DB explorer API/detail provenance field exposure and regression coverage for metadata summary/detail.
- 2026-07-01: Added broader mixed-source schedule regression (public-source family permutation).
- 2026-07-01: Added dedicated CLI regression test for source-capabilities JSON schema/count and expanded provenance regression checks for kegg/open_targets/fda_labels.
- 2026-07-01: Added full all-public schedule cycle regression, source-capabilities plain-text regression, and DB explorer template provenance rendering regression.
- 2026-07-01: Added connector retry/backoff policy map and provenance contract validation in sync flow.
