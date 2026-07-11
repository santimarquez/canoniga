from __future__ import annotations

from typing import Any

from als_intel.extractors.base import DataSourceExtractor
from als_intel.extractors.claim_builder import build_record_from_doc


class ClinicalTrialsExtractor(DataSourceExtractor):
    source_name = "ctgov"

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

        effective_query = str(query)
        docs = sync_module.fetch_ctgov(query=effective_query, max_results=max_results, from_file=from_file)
        return docs, effective_query

    def normalize_doc(self, doc: dict[str, Any]):
        return build_record_from_doc(doc)
