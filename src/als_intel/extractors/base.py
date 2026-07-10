from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from als_intel.models import EvidenceRecord
from als_intel.store import EvidenceStore


class DataSourceExtractor(ABC):
    source_name: str

    @abstractmethod
    def fetch_docs(
        self,
        *,
        query: str,
        max_results: int,
        from_file: str | None,
        last_successful_timestamp: str | None,
        extractor_config: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], str]:
        """Return raw docs and effective query used for fetch."""

    @abstractmethod
    def normalize_doc(self, doc: dict[str, Any]) -> EvidenceRecord:
        """Map raw document to canonical EvidenceRecord."""

    def run_metadata_enrichment(
        self,
        *,
        store: EvidenceStore,
        last_stage_successful_timestamp: str | None,
        source_sync_status: str,
        stage_config: dict[str, Any] | None,
    ) -> tuple[str, str, int]:
        """Return metadata_stage_status, metadata_stage_notes, metadata_enriched_records."""
        if source_sync_status != "ok":
            return "failed", "source_sync_failed", 0
        return "ok", "", 0


class UnsupportedExtractorError(ValueError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
