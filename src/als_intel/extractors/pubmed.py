from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from als_intel.extractors.base import DataSourceExtractor
from als_intel.extractors.claim_builder import build_record_from_doc
from als_intel.store import EvidenceStore


def _normalize_iso_to_pubmed_date(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("timestamp is required")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y/%m/%d")


def build_pubmed_incremental_query(base_query: str, last_successful_timestamp: str | None) -> str:
    base = str(base_query or "").strip()
    if not last_successful_timestamp:
        return base
    since_day = _normalize_iso_to_pubmed_date(last_successful_timestamp)
    now_day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    return f"({base}) AND (\"{since_day}\"[Date - Publication] : \"{now_day}\"[Date - Publication])"


class PubMedExtractor(DataSourceExtractor):
    source_name = "pubmed"

    def fetch_docs(
        self,
        *,
        query: str,
        max_results: int,
        from_file: str | None,
        last_successful_timestamp: str | None,
        extractor_config: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], str]:
        from als_intel import sync as sync_module

        config = extractor_config or {}
        disable_incremental = bool(config.get("disable_incremental", False))

        if from_file:
            effective_query = str(query)
        elif disable_incremental:
            effective_query = str(query)
        else:
            effective_query = build_pubmed_incremental_query(str(query), last_successful_timestamp)
        docs = sync_module.fetch_pubmed(query=effective_query, max_results=max_results, from_file=from_file)
        return docs, effective_query

    def normalize_doc(self, doc: dict[str, Any]):
        return build_record_from_doc(doc)

    def run_metadata_enrichment(
        self,
        *,
        store: EvidenceStore,
        last_stage_successful_timestamp: str | None,
        source_sync_status: str,
        stage_config: dict[str, Any] | None,
    ) -> tuple[str, str, int]:
        from als_intel import sync as sync_module

        config = stage_config or {}
        enabled = bool(config.get("enabled", True))
        metadata_limit = int(config.get("metadata_limit", 250) or 250)

        if not enabled:
            return "ok", "disabled_by_stage_config", 0

        if source_sync_status != "ok":
            return "failed", "source_sync_failed", 0

        candidates = store.list_pubmed_ids_for_enrichment(
            since_timestamp=last_stage_successful_timestamp,
            limit=max(1, min(metadata_limit, 2000)),
        )
        if not candidates:
            return "ok", "", 0

        by_source_id = {
            str(row["source_id"]): str(row["claim_id"])
            for row in candidates
        }
        metadata = sync_module.fetch_pubmed_metadata(list(by_source_id.keys()))

        upserted = 0
        for source_id, claim_id in by_source_id.items():
            payload = metadata.get(source_id, {})
            store.upsert_evidence_source_metadata(
                claim_id=claim_id,
                source_name="pubmed",
                source_id=source_id,
                abstract_text=str(payload.get("abstract_text", "") or ""),
                journal=str(payload.get("journal", "") or ""),
                pubdate=str(payload.get("pubdate", "") or ""),
                authors=[str(a) for a in payload.get("authors", []) if str(a).strip()],
                mesh_terms=[str(m) for m in payload.get("mesh_terms", []) if str(m).strip()],
                affiliations=[str(a) for a in payload.get("affiliations", []) if str(a).strip()],
                references=[str(r) for r in payload.get("references", []) if str(r).strip()],
                metadata=payload.get("raw", {}) if isinstance(payload.get("raw", {}), dict) else {},
            )
            upserted += 1

        return "ok", "", upserted
