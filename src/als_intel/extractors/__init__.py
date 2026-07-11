from __future__ import annotations

from als_intel.extractors.arrayexpress import ArrayExpressExtractor
from als_intel.extractors.chembl import ChEMBLExtractor
from als_intel.extractors.clinicaltrials import ClinicalTrialsExtractor
from als_intel.extractors.fda_labels import FDALabelsExtractor
from als_intel.extractors.geo import GEOExtractor
from als_intel.extractors.go import GOExtractor
from als_intel.extractors.kegg import KEGGExtractor
from als_intel.extractors.metabolomics_workbench import MetabolomicsWorkbenchExtractor
from als_intel.extractors.ncbi_gene import NCBIGeneExtractor
from als_intel.extractors.open_targets import OpenTargetsExtractor
from als_intel.extractors.pmc import PMCExtractor
from als_intel.extractors.pride import PRIDEExtractor
from als_intel.extractors.pubmed import PubMedExtractor
from als_intel.extractors.reactome import ReactomeExtractor
from als_intel.extractors.uniprot import UniProtExtractor
from als_intel.extractors.registry import ExtractorRegistry
from als_intel.extractors.restricted import (
    ALSAssociationExtractor,
    ALSTDIExtractor,
    AnswerALSExtractor,
    DrugBankExtractor,
    NEALSExtractor,
    ProjectMinEExtractor,
)


def register_builtin_extractors() -> None:
    # Idempotent registration for CLI and scheduler entry points.
    ExtractorRegistry.register("arrayexpress", ArrayExpressExtractor)
    ExtractorRegistry.register("pubmed", PubMedExtractor)
    ExtractorRegistry.register("ctgov", ClinicalTrialsExtractor)
    ExtractorRegistry.register("pmc", PMCExtractor)
    ExtractorRegistry.register("ncbi_gene", NCBIGeneExtractor)
    ExtractorRegistry.register("uniprot", UniProtExtractor)
    ExtractorRegistry.register("go", GOExtractor)
    ExtractorRegistry.register("reactome", ReactomeExtractor)
    ExtractorRegistry.register("geo", GEOExtractor)
    ExtractorRegistry.register("kegg", KEGGExtractor)
    ExtractorRegistry.register("pride", PRIDEExtractor)
    ExtractorRegistry.register("metabolomics_workbench", MetabolomicsWorkbenchExtractor)
    ExtractorRegistry.register("chembl", ChEMBLExtractor)
    ExtractorRegistry.register("open_targets", OpenTargetsExtractor)
    ExtractorRegistry.register("fda_labels", FDALabelsExtractor)
    ExtractorRegistry.register("drugbank", DrugBankExtractor)
    ExtractorRegistry.register("project_mine", ProjectMinEExtractor)
    ExtractorRegistry.register("answer_als", AnswerALSExtractor)
    ExtractorRegistry.register("als_tdi", ALSTDIExtractor)
    ExtractorRegistry.register("neals", NEALSExtractor)
    ExtractorRegistry.register("als_association", ALSAssociationExtractor)


def supported_sources() -> list[str]:
    return ExtractorRegistry.supported_sources()
