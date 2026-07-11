from __future__ import annotations

from typing import Any

from als_intel.extractors.base import DataSourceExtractor


class AccessNotConfiguredError(RuntimeError):
    """Raised when a restricted datasource has no configured credentials or license."""


class RestrictedDataSourceExtractor(DataSourceExtractor):
    source_name = "restricted"
    access_instructions = "Configure credentials before syncing this source."

    def fetch_docs(
        self,
        *,
        query: str,
        max_results: int,
        from_file: str | None,
        last_successful_timestamp: str | None,
        extractor_config: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], str]:
        raise AccessNotConfiguredError(
            f"{self.source_name}: {self.access_instructions}"
        )

    def normalize_doc(self, doc: dict[str, Any]):
        raise AccessNotConfiguredError(
            f"{self.source_name}: normalization unavailable without configured access."
        )


class DrugBankExtractor(RestrictedDataSourceExtractor):
    source_name = "drugbank"
    access_instructions = (
        "Set DRUGBANK_USERNAME and DRUGBANK_PASSWORD after obtaining a DrugBank license."
    )


class ProjectMinEExtractor(RestrictedDataSourceExtractor):
    source_name = "project_mine"
    access_instructions = (
        "Complete Project MinE DAC approval and configure PROJECT_MINE_API_TOKEN."
    )


class AnswerALSExtractor(RestrictedDataSourceExtractor):
    source_name = "answer_als"
    access_instructions = (
        "Request Answer ALS data access approval and configure ANSWER_ALS_API_TOKEN."
    )


class ALSTDIExtractor(RestrictedDataSourceExtractor):
    source_name = "als_tdi"
    access_instructions = (
        "Sign ALS Therapy Development Institute data agreement and configure ALS_TDI_API_TOKEN."
    )


class NEALSExtractor(RestrictedDataSourceExtractor):
    source_name = "neals"
    access_instructions = (
        "Configure NEALS data access credentials once institutional access is granted."
    )


class ALSAssociationExtractor(RestrictedDataSourceExtractor):
    source_name = "als_association"
    access_instructions = (
        "Configure ALS Association research data access once agreement is in place."
    )
