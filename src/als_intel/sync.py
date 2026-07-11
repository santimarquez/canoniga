from __future__ import annotations

from datetime import datetime, timezone

# Re-export connector call sites for backward-compatible monkeypatch targets in tests.
from als_intel.connectors import (
    fetch_arrayexpress,
    fetch_chembl,
    fetch_ctgov,
    fetch_fda_labels,
    fetch_geo,
    fetch_go,
    fetch_kegg,
    fetch_metabolomics_workbench,
    fetch_ncbi_gene,
    fetch_open_targets,
    fetch_pmc,
    fetch_pride,
    fetch_pubmed,
    fetch_pubmed_metadata,
    fetch_reactome,
    fetch_uniprot,
)
from als_intel.extractors import register_builtin_extractors
from als_intel.extractors.registry import ExtractorRegistry
from als_intel.scoring import score_components, source_reliability_score
from als_intel.store import EvidenceStore


SOURCE_ENDPOINTS: dict[str, str] = {
    "pubmed": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
    "pmc": "https://www.ebi.ac.uk/europepmc/webservices/rest/",
    "ctgov": "https://clinicaltrials.gov/api/v2/studies",
    "ncbi_gene": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
    "uniprot": "https://rest.uniprot.org/uniprotkb/search",
    "go": "https://www.ebi.ac.uk/QuickGO/services/ontology/go/search",
    "reactome": "https://reactome.org/ContentService/search/query",
    "geo": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
    "arrayexpress": "https://www.ebi.ac.uk/biostudies/api/v1/arrayexpress/search",
    "kegg": "https://rest.kegg.jp/find/pathway/",
    "pride": "https://www.ebi.ac.uk/pride/ws/archive/v2/projects",
    "metabolomics_workbench": "https://www.metabolomicsworkbench.org/rest/",
    "chembl": "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json",
    "open_targets": "https://api.platform.opentargets.org/api/v4/graphql",
    "fda_labels": "https://api.fda.gov/drug/label.json",
}

REQUIRED_PROVENANCE_KEYS = {
    "api_endpoint",
    "query_used",
    "source_version",
    "extracted_at",
    "source_license",
    "ingestion_mode",
}


def _assert_provenance_contract(metadata: dict[str, object]) -> None:
    missing = [key for key in sorted(REQUIRED_PROVENANCE_KEYS) if not str(metadata.get(key, "")).strip()]
    if missing:
        raise ValueError(f"provenance_contract_missing_keys: {', '.join(missing)}")


def _upsert_source_provenance(
    *,
    store: EvidenceStore,
    source_name: str,
    query: str,
    effective_query: str,
    claim_id: str,
    source_id: str,
    source_title: str,
    source_journal: str,
    source_year: int,
    extracted_claim: dict[str, object] | None = None,
    extraction_method: str = "",
) -> None:
    extracted_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "api_endpoint": SOURCE_ENDPOINTS.get(source_name, "unknown"),
        "query_used": effective_query or query,
        "source_version": "live",
        "extracted_at": extracted_at,
        "source_license": "unknown",
        "ingestion_mode": "incremental_sync",
    }
    if extracted_claim:
        metadata["extracted_claim"] = extracted_claim
    if extraction_method:
        metadata["extraction_method"] = extraction_method
    _assert_provenance_contract(metadata)
    store.upsert_evidence_source_metadata(
        claim_id=claim_id,
        source_name=source_name,
        source_id=source_id,
        abstract_text="",
        journal=source_journal,
        pubdate=str(source_year) if source_year > 0 else "",
        authors=[],
        mesh_terms=[],
        affiliations=[],
        references=[],
        metadata=metadata,
    )


def run_incremental_sync(
    db_path: str,
    source: str,
    query: str,
    max_results: int = 20,
    from_file: str | None = None,
    extractor_config: dict[str, object] | None = None,
    stage_config: dict[str, object] | None = None,
) -> dict[str, object]:
    store = EvidenceStore(db_path)
    store.init_db()
    register_builtin_extractors()

    source_normalized = str(source).strip().lower()
    extractor = ExtractorRegistry.create(source_normalized)

    run_id = store.start_sync_run(source_name=source_normalized, query=query)
    inserted = 0
    updated = 0
    unchanged = 0
    status = "ok"
    notes = ""
    effective_query = str(query)
    metadata_stage = "metadata_enrichment"
    metadata_stage_status = "ok"
    metadata_stage_notes = ""
    metadata_enriched_records = 0
    metadata_stage_state: dict[str, object] | None = None
    docs: list[dict[str, object]] = []

    sync_state = store.get_sync_state(source_normalized)
    previous_metadata_state = store.get_stage_sync_state(source_normalized, metadata_stage)

    try:
        last_successful_timestamp = None
        if isinstance(sync_state, dict):
            raw_last_successful = sync_state.get("last_successful_timestamp")
            if raw_last_successful:
                last_successful_timestamp = str(raw_last_successful)

        docs, effective_query = extractor.fetch_docs(
            query=str(query),
            max_results=max_results,
            from_file=from_file,
            last_successful_timestamp=last_successful_timestamp,
            extractor_config=dict(extractor_config or {}),
        )

        for doc in docs:
            record = extractor.normalize_doc(doc)
            breakdown = score_components(record)
            source_score = source_reliability_score(record)
            action = store.upsert_evidence(record, breakdown, source_score, run_id=run_id, source_name=source_normalized)
            source_id = str(doc.get("source_id", "") or record.source_doi or "").strip()
            from als_intel.extractors.claim_builder import build_structured_claim

            structured = build_structured_claim(doc)
            _upsert_source_provenance(
                store=store,
                source_name=source_normalized,
                query=str(query),
                effective_query=effective_query,
                claim_id=record.claim_id,
                source_id=source_id,
                source_title=record.source_title,
                source_journal=str(doc.get("journal", "") or ""),
                source_year=int(doc.get("year", 0) or 0),
                extracted_claim=structured.provenance if structured is not None else None,
                extraction_method=structured.extraction_method if structured is not None else "",
            )
            if action == "inserted":
                inserted += 1
            elif action == "updated":
                updated += 1
            else:
                unchanged += 1
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        notes = str(exc)
        docs = []
    finally:
        store.finish_sync_run(
            run_id=run_id,
            records_seen=len(docs),
            inserted_count=inserted,
            updated_count=updated,
            unchanged_count=unchanged,
            status=status,
            notes=notes,
        )
        store.update_sync_state(
            source_name=source_normalized,
            run_id=run_id,
            status=status,
        )

        last_stage_successful = None
        if isinstance(previous_metadata_state, dict):
            raw_last_stage_successful = previous_metadata_state.get("last_successful_timestamp")
            if raw_last_stage_successful:
                last_stage_successful = str(raw_last_stage_successful)

        try:
            metadata_stage_status, metadata_stage_notes, metadata_enriched_records = extractor.run_metadata_enrichment(
                store=store,
                last_stage_successful_timestamp=last_stage_successful,
                source_sync_status=status,
                stage_config=dict(stage_config or {}),
            )
        except Exception as stage_exc:  # noqa: BLE001
            metadata_stage_status = "failed"
            metadata_stage_notes = str(stage_exc)
            metadata_enriched_records = 0

        metadata_stage_state = store.update_stage_sync_state(
            source_name=source_normalized,
            stage_name=metadata_stage,
            run_id=run_id,
            status=metadata_stage_status,
        )

    return {
        "run_id": run_id,
        "source": source_normalized,
        "query": query,
        "effective_query": effective_query,
        "records_seen": len(docs),
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "status": status,
        "notes": notes,
        "metadata_stage": metadata_stage,
        "metadata_stage_status": metadata_stage_status,
        "metadata_stage_notes": metadata_stage_notes,
        "metadata_enriched_records": metadata_enriched_records,
        "metadata_stage_last_successful": (
            metadata_stage_state.get("last_successful_timestamp")
            if isinstance(metadata_stage_state, dict)
            else None
        ),
    }
