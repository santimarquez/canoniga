from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from als_intel.extractors import normalization as norm
from als_intel.models import EvidenceRecord


MESH_ENTITY_MAP = {
    "microglia": "microglial activation",
    "neuroinflammation": "neuroinflammation",
    "mitochondria": "mitochondrial dysfunction",
    "protein aggregation": "protein aggregation",
    "rna splicing": "rna processing",
    "axonal transport": "axonal transport",
    "motor neuron": "motor neuron degeneration",
    "tdp-43": "TDP-43 pathology",
    "sod1": "SOD1",
    "c9orf72": "C9orf72",
}

GENE_PATTERN = re.compile(
    r"\b(SOD1|C9orf72|TARDBP|FUS|TBK1|OPTN|CCNF|NEK1|C21orf2|MATR3|VCP|PFN1|CHCHD10|TUBA4A)\b",
    re.IGNORECASE,
)

NEGATIVE_MARKERS = (
    "no association",
    "did not",
    "failed",
    "negative",
    "no benefit",
    "not effective",
    "terminated",
    "withdrawn",
    "unsuccessful",
)
POSITIVE_MARKERS = (
    "improved",
    "benefit",
    "associated",
    "reduced",
    "effective",
    "slowed",
    "delayed progression",
    "positive",
)
OUTCOME_MARKERS = {
    "alsfrs": "ALS functional rating",
    "survival": "survival",
    "mortality": "mortality",
    "biomarker": "biomarker response",
    "respiratory": "respiratory function",
    "progression": "disease progression",
    "fvc": "forced vital capacity",
}


@dataclass(slots=True)
class BuiltClaim:
    entity: str
    relation: str
    outcome: str
    effect_direction: str
    claim_text: str
    cohort: str
    model_system: str
    endpoint: str
    extraction_method: str
    field_coverage: float
    provenance: dict[str, Any]


def _text_blob(doc: dict[str, Any]) -> str:
    parts = [
        str(doc.get("title", "")),
        str(doc.get("abstract", "") or doc.get("abstract_text", "")),
        str(doc.get("body_text", "") or doc.get("full_text", "")),
        " ".join(str(m) for m in doc.get("mesh_terms", []) if m),
    ]
    return " ".join(p.strip() for p in parts if p.strip()).lower()


def _infer_entity_from_text(text: str, mesh_terms: list[str] | None = None) -> str:
    for term in mesh_terms or []:
        lower = term.lower()
        for key, entity in MESH_ENTITY_MAP.items():
            if key in lower:
                return entity
    gene = GENE_PATTERN.search(text)
    if gene:
        return gene.group(1).upper()
    return norm.infer_entity(text)


def _infer_effect_direction_from_text(text: str, trial_status: str = "") -> str:
    status = trial_status.strip().lower()
    if status in {"terminated", "withdrawn", "suspended"}:
        return "contradicts"
    if any(m in text for m in NEGATIVE_MARKERS):
        return "contradicts"
    if any(m in text for m in POSITIVE_MARKERS):
        return "supports"
    return "neutral"


def _infer_outcome(text: str, primary_endpoint: str = "") -> str:
    endpoint = (primary_endpoint or "").lower()
    combined = f"{text} {endpoint}"
    for token, outcome in OUTCOME_MARKERS.items():
        if token in combined:
            return outcome
    return "disease progression"


def _infer_relation(effect_direction: str, study_type: str, entity: str) -> str:
    if study_type == "interventional":
        return "modulates" if effect_direction == "supports" else "fails_to_modulate"
    if "gene" in entity.lower() or entity.upper() in {"SOD1", "C9ORF72", "TARDBP", "FUS"}:
        return "genetic_association"
    return "associated_with"


def _compose_claim_text(
    *,
    title: str,
    entity: str,
    outcome: str,
    effect_direction: str,
    abstract: str,
    trial_status: str,
) -> str:
    direction_phrase = {
        "supports": "supports a beneficial association with",
        "contradicts": "contradicts or fails to support an effect on",
        "neutral": "reports neutral or inconclusive evidence regarding",
    }[effect_direction]
    base = f"{title.strip()}: evidence {direction_phrase} {entity} and {outcome}."
    if trial_status:
        base = f"{base} Trial status: {trial_status}."
    if abstract and len(abstract) > 40:
        snippet = abstract.strip()[:180].rstrip()
        if not snippet.endswith("."):
            snippet += "..."
        return f"{base} Abstract excerpt: {snippet}"
    return base


def _field_coverage(*values: object) -> float:
    filled = sum(1 for value in values if str(value or "").strip())
    return round(filled / max(len(values), 1), 4)


def build_pubmed_claim(doc: dict[str, Any]) -> BuiltClaim:
    title = str(doc.get("title", "")).strip() or "Untitled record"
    abstract = str(doc.get("abstract", "") or doc.get("abstract_text", "")).strip()
    mesh_terms = [str(m) for m in doc.get("mesh_terms", []) if str(m).strip()]
    text = _text_blob(doc)

    study_type = norm.infer_study_type("pubmed", title)
    entity = _infer_entity_from_text(text, mesh_terms)
    effect_direction = _infer_effect_direction_from_text(text)
    outcome = _infer_outcome(text)
    relation = _infer_relation(effect_direction, study_type, entity)
    claim_text = _compose_claim_text(
        title=title,
        entity=entity,
        outcome=outcome,
        effect_direction=effect_direction,
        abstract=abstract,
        trial_status="",
    )
    coverage = _field_coverage(entity, outcome, effect_direction, abstract or title, relation)
    return BuiltClaim(
        entity=entity,
        relation=relation,
        outcome=outcome,
        effect_direction=effect_direction,
        claim_text=claim_text,
        cohort="mixed",
        model_system="human" if study_type != "preclinical" else "preclinical",
        endpoint=outcome,
        extraction_method="pubmed_structured",
        field_coverage=coverage,
        provenance={
            "mesh_terms": mesh_terms,
            "abstract_present": bool(abstract),
            "study_type": study_type,
        },
    )


def build_ctgov_claim(doc: dict[str, Any]) -> BuiltClaim:
    title = str(doc.get("title", "")).strip() or "Untitled trial"
    text = _text_blob(doc)
    trial_status = str(doc.get("trial_status", "")).strip()
    phase = str(doc.get("phase", "")).strip()
    enrollment = doc.get("enrollment")
    primary_endpoint = str(doc.get("primary_endpoint", "")).strip()
    termination_reason = str(doc.get("termination_reason", "")).strip()
    arm = str(doc.get("intervention_arm", "")).strip()

    study_type = "interventional"
    entity = _infer_entity_from_text(text)
    if arm:
        entity = arm if entity == "als mechanism (unspecified)" else entity
    effect_direction = _infer_effect_direction_from_text(f"{text} {termination_reason}", trial_status)
    outcome = _infer_outcome(text, primary_endpoint)
    relation = _infer_relation(effect_direction, study_type, entity)
    claim_text = _compose_claim_text(
        title=title,
        entity=entity,
        outcome=outcome,
        effect_direction=effect_direction,
        abstract=termination_reason,
        trial_status=trial_status,
    )
    cohort = "ALS"
    if enrollment:
        cohort = f"ALS (target n={enrollment})"
    coverage = _field_coverage(
        entity,
        outcome,
        effect_direction,
        trial_status,
        primary_endpoint,
        phase,
    )
    primary_endpoint_result = str(doc.get("primary_endpoint_result", "")).strip()
    adverse_events_summary = str(doc.get("adverse_events_summary", "")).strip()
    return BuiltClaim(
        entity=entity,
        relation=relation,
        outcome=outcome,
        effect_direction=effect_direction,
        claim_text=claim_text,
        cohort=cohort,
        model_system="human",
        endpoint=primary_endpoint or outcome,
        extraction_method="ctgov_structured",
        field_coverage=coverage,
        provenance={
            "trial_status": trial_status,
            "phase": phase,
            "enrollment": enrollment,
            "primary_endpoint": primary_endpoint,
            "primary_endpoint_result": primary_endpoint_result,
            "adverse_events_summary": adverse_events_summary,
            "termination_reason": termination_reason,
            "intervention_arm": arm,
        },
    )


def _parse_gene_symbol(doc: dict[str, Any], title: str) -> str:
    explicit = str(doc.get("gene_symbol", "")).strip()
    if explicit:
        return explicit.upper()
    if ":" in title:
        prefix = title.split(":", 1)[0].strip()
        if GENE_PATTERN.fullmatch(prefix) or re.fullmatch(r"[A-Za-z0-9]+", prefix):
            return prefix.upper()
    if " - " in title:
        prefix = title.split(" - ", 1)[0].strip()
        if GENE_PATTERN.search(prefix):
            return GENE_PATTERN.search(prefix).group(1).upper()  # type: ignore[union-attr]
    gene = GENE_PATTERN.search(title)
    return gene.group(1).upper() if gene else ""


def _parse_drug_name(doc: dict[str, Any], title: str) -> str:
    explicit = str(doc.get("drug_name", "")).strip()
    if explicit:
        return explicit
    if ":" in title:
        return title.split(":", 1)[0].strip()
    return title.strip()


def _parse_pathway_name(doc: dict[str, Any], title: str) -> str:
    explicit = str(doc.get("pathway_name", "")).strip()
    if explicit:
        return explicit
    if " - " in title:
        return title.split(" - ", 1)[0].strip()
    if " (" in title:
        return title.split(" (", 1)[0].strip()
    return title.strip()


def _parse_ontology_term(doc: dict[str, Any], title: str) -> str:
    explicit = str(doc.get("ontology_term", "")).strip()
    if explicit:
        return explicit
    if ":" in title:
        return title.split(":", 1)[0].strip()
    return _parse_pathway_name(doc, title)


def _pathway_entity(doc: dict[str, Any], title: str) -> str:
    name = _parse_pathway_name(doc, title)
    lower = f"{name} {title}".lower()
    if "amyotrophic lateral sclerosis" in lower or re.search(r"\bals\b", lower):
        return "amyotrophic lateral sclerosis"
    inferred = _infer_entity_from_text(lower)
    if inferred != "als mechanism (unspecified)":
        return inferred
    return name


def _infer_omics_study_type(source: str, title: str, doc: dict[str, Any]) -> str:
    explicit = str(doc.get("study_type", "")).strip()
    if explicit:
        return explicit
    lower = title.lower()
    if source == "pride" or "proteom" in lower:
        return "proteomic"
    if source == "metabolomics_workbench" or "metabolom" in lower or "metabolic" in lower:
        return "metabolomic"
    if "transcriptom" in lower or source in {"geo", "arrayexpress"}:
        return "transcriptomic"
    return "observational"


def _infer_model_system(text: str, doc: dict[str, Any]) -> str:
    explicit = str(doc.get("model_system", "")).strip()
    if explicit:
        return explicit
    lower = text.lower()
    if any(token in lower for token in ("mouse", "mice", "rat", "zebrafish", "in vitro", "ipsc")):
        return "preclinical"
    if "motor cortex" in lower or "spinal cord" in lower or "csf" in lower or "plasma" in lower:
        return "human tissue"
    return "human"


def _make_built_claim(
    *,
    doc: dict[str, Any],
    entity: str,
    relation: str,
    outcome: str,
    effect_direction: str,
    extraction_method: str,
    study_type: str,
    cohort: str,
    model_system: str,
    endpoint: str,
    provenance: dict[str, Any],
    coverage_values: tuple[object, ...],
    abstract: str = "",
    trial_status: str = "",
) -> BuiltClaim:
    title = str(doc.get("title", "")).strip() or "Untitled record"
    claim_text = _compose_claim_text(
        title=title,
        entity=entity,
        outcome=outcome,
        effect_direction=effect_direction,
        abstract=abstract,
        trial_status=trial_status,
    )
    return BuiltClaim(
        entity=entity,
        relation=relation,
        outcome=outcome,
        effect_direction=effect_direction,
        claim_text=claim_text,
        cohort=cohort,
        model_system=model_system,
        endpoint=endpoint,
        extraction_method=extraction_method,
        field_coverage=_field_coverage(*coverage_values),
        provenance={**provenance, "study_type": study_type},
    )


def build_pmc_claim(doc: dict[str, Any]) -> BuiltClaim:
    title = str(doc.get("title", "")).strip() or "Untitled record"
    abstract = str(doc.get("abstract", "") or doc.get("abstract_text", "")).strip()
    mesh_terms = [str(m) for m in doc.get("mesh_terms", []) if str(m).strip()]
    text = _text_blob(doc)
    study_type = norm.infer_study_type("pmc", title)
    entity = _infer_entity_from_text(text, mesh_terms)
    effect_direction = _infer_effect_direction_from_text(text)
    outcome = _infer_outcome(text)
    relation = _infer_relation(effect_direction, study_type, entity)
    return _make_built_claim(
        doc=doc,
        entity=entity,
        relation=relation,
        outcome=outcome,
        effect_direction=effect_direction,
        extraction_method="pmc_structured",
        study_type=study_type,
        cohort="mixed",
        model_system=_infer_model_system(text, doc),
        endpoint=outcome,
        provenance={
            "mesh_terms": mesh_terms,
            "abstract_present": bool(abstract),
            "body_text_present": bool(str(doc.get("body_text", "")).strip()),
        },
        coverage_values=(entity, outcome, effect_direction, abstract or str(doc.get("body_text", "")) or title, relation),
        abstract=abstract,
    )


def build_chembl_claim(doc: dict[str, Any]) -> BuiltClaim:
    title = str(doc.get("title", "")).strip() or "Untitled compound"
    text = _text_blob(doc)
    drug_name = _parse_drug_name(doc, title)
    entity = drug_name or _infer_entity_from_text(text)
    effect_direction = "supports" if doc.get("first_approval") or "als" in text else "neutral"
    outcome = "disease progression"
    relation = "modulates"
    return _make_built_claim(
        doc=doc,
        entity=entity,
        relation=relation,
        outcome=outcome,
        effect_direction=effect_direction,
        extraction_method="chembl_structured",
        study_type="mechanistic",
        cohort="ALS",
        model_system="human",
        endpoint=outcome,
        provenance={"drug_name": drug_name, "target_name": doc.get("target_name", "")},
        coverage_values=(entity, drug_name, outcome, relation),
    )


def build_open_targets_claim(doc: dict[str, Any]) -> BuiltClaim:
    title = str(doc.get("title", "")).strip() or "Untitled target"
    text = _text_blob(doc)
    entity = (
        str(doc.get("target_name", "")).strip()
        or _parse_gene_symbol(doc, title)
        or _infer_entity_from_text(text)
    )
    entity_type = str(doc.get("entity_type", "")).strip().lower()
    if not entity_type and "(target)" in title.lower():
        entity_type = "target"
    relation = "genetic_association" if entity_type == "target" or _parse_gene_symbol(doc, title) else "associated_with"
    effect_direction = _infer_effect_direction_from_text(text) or "supports"
    return _make_built_claim(
        doc=doc,
        entity=entity,
        relation=relation,
        outcome="disease progression",
        effect_direction=effect_direction,
        extraction_method="open_targets_structured",
        study_type="genetic",
        cohort="ALS",
        model_system="human",
        endpoint="disease progression",
        provenance={"entity_type": entity_type, "target_name": doc.get("target_name", "")},
        coverage_values=(entity, relation, entity_type),
    )


def build_fda_labels_claim(doc: dict[str, Any]) -> BuiltClaim:
    title = str(doc.get("title", "")).strip() or "Untitled label"
    text = _text_blob(doc)
    drug_name = _parse_drug_name(doc, title)
    entity = drug_name or _infer_entity_from_text(text)
    indication = str(doc.get("indication", "")).strip()
    effect_direction = "supports" if "indicated" in text or "treatment" in text or indication else "neutral"
    return _make_built_claim(
        doc=doc,
        entity=entity,
        relation="modulates",
        outcome="disease progression",
        effect_direction=effect_direction,
        extraction_method="fda_labels_structured",
        study_type="interventional",
        cohort="ALS",
        model_system="human",
        endpoint="disease progression",
        provenance={"drug_name": drug_name, "indication": indication or title},
        coverage_values=(entity, drug_name, indication or title),
    )


def build_ncbi_gene_claim(doc: dict[str, Any]) -> BuiltClaim:
    title = str(doc.get("title", "")).strip() or "Untitled gene"
    text = _text_blob(doc)
    gene_symbol = _parse_gene_symbol(doc, title)
    entity = gene_symbol or _infer_entity_from_text(text)
    effect_direction = _infer_effect_direction_from_text(text) or "supports"
    return _make_built_claim(
        doc=doc,
        entity=entity,
        relation="genetic_association",
        outcome="disease progression",
        effect_direction=effect_direction,
        extraction_method="ncbi_gene_structured",
        study_type="genetic",
        cohort="ALS",
        model_system="human",
        endpoint="disease progression",
        provenance={"gene_symbol": gene_symbol, "summary": doc.get("summary", "")},
        coverage_values=(entity, gene_symbol, title),
    )


def build_uniprot_claim(doc: dict[str, Any]) -> BuiltClaim:
    title = str(doc.get("title", "")).strip() or "Untitled protein"
    text = _text_blob(doc)
    gene_symbol = _parse_gene_symbol(doc, title)
    entity = gene_symbol or _infer_entity_from_text(text)
    effect_direction = _infer_effect_direction_from_text(text) or "neutral"
    return _make_built_claim(
        doc=doc,
        entity=entity,
        relation="associated_with",
        outcome="disease progression",
        effect_direction=effect_direction,
        extraction_method="uniprot_structured",
        study_type="mechanistic",
        cohort="ALS",
        model_system="human",
        endpoint="disease progression",
        provenance={"gene_symbol": gene_symbol, "protein_name": doc.get("protein_name", "")},
        coverage_values=(entity, gene_symbol, title),
    )


def build_pathway_claim(doc: dict[str, Any], *, extraction_method: str) -> BuiltClaim:
    title = str(doc.get("title", "")).strip() or "Untitled pathway"
    text = _text_blob(doc)
    entity = _pathway_entity(doc, title)
    effect_direction = _infer_effect_direction_from_text(text) or "neutral"
    return _make_built_claim(
        doc=doc,
        entity=entity,
        relation="associated_with",
        outcome="disease progression",
        effect_direction=effect_direction,
        extraction_method=extraction_method,
        study_type="mechanistic",
        cohort="ALS",
        model_system="human",
        endpoint="disease progression",
        provenance={"pathway_name": _parse_pathway_name(doc, title), "pathway_id": doc.get("source_id", "")},
        coverage_values=(entity, title, doc.get("source_id", "")),
    )


def build_go_claim(doc: dict[str, Any]) -> BuiltClaim:
    title = str(doc.get("title", "")).strip() or "Untitled GO term"
    term = _parse_ontology_term(doc, title)
    text = _text_blob(doc)
    entity = term or _infer_entity_from_text(text)
    return _make_built_claim(
        doc=doc,
        entity=entity,
        relation="associated_with",
        outcome="disease progression",
        effect_direction=_infer_effect_direction_from_text(text) or "neutral",
        extraction_method="go_structured",
        study_type="mechanistic",
        cohort="ALS",
        model_system="human",
        endpoint="disease progression",
        provenance={"ontology_term": term, "go_id": doc.get("source_id", "")},
        coverage_values=(entity, term, doc.get("source_id", "")),
    )


def build_omics_claim(doc: dict[str, Any], *, extraction_method: str) -> BuiltClaim:
    title = str(doc.get("title", "")).strip() or "Untitled omics study"
    source = str(doc.get("source", "")).strip().lower()
    text = _text_blob(doc)
    study_type = _infer_omics_study_type(source, title, doc)
    entity = _infer_entity_from_text(text)
    effect_direction = _infer_effect_direction_from_text(text) or "neutral"
    outcome = _infer_outcome(text)
    cohort = str(doc.get("cohort", "")).strip() or "ALS"
    return _make_built_claim(
        doc=doc,
        entity=entity,
        relation="associated_with",
        outcome=outcome,
        effect_direction=effect_direction,
        extraction_method=extraction_method,
        study_type=study_type,
        cohort=cohort,
        model_system=_infer_model_system(text, doc),
        endpoint=str(doc.get("assay_outcome", "")).strip() or outcome,
        provenance={
            "platform": doc.get("platform", ""),
            "study_type": study_type,
            "cohort": cohort,
        },
        coverage_values=(entity, study_type, outcome, doc.get("platform", "")),
    )


_STRUCTURED_BUILDERS = {
    "pubmed": build_pubmed_claim,
    "ctgov": build_ctgov_claim,
    "pmc": build_pmc_claim,
    "chembl": build_chembl_claim,
    "open_targets": build_open_targets_claim,
    "fda_labels": build_fda_labels_claim,
    "ncbi_gene": build_ncbi_gene_claim,
    "uniprot": build_uniprot_claim,
    "kegg": lambda doc: build_pathway_claim(doc, extraction_method="kegg_structured"),
    "reactome": lambda doc: build_pathway_claim(doc, extraction_method="reactome_structured"),
    "go": build_go_claim,
    "geo": lambda doc: build_omics_claim(doc, extraction_method="geo_structured"),
    "arrayexpress": lambda doc: build_omics_claim(doc, extraction_method="arrayexpress_structured"),
    "pride": lambda doc: build_omics_claim(doc, extraction_method="pride_structured"),
    "metabolomics_workbench": lambda doc: build_omics_claim(
        doc, extraction_method="metabolomics_workbench_structured"
    ),
}


def _llm_extraction_enabled() -> bool:
    return os.getenv("ALS_CLAIM_EXTRACTION_LLM", "").strip().lower() in {"1", "true", "yes", "on"}


def _validate_llm_fields(payload: dict[str, Any]) -> dict[str, str] | None:
    required = ("entity", "relation", "outcome", "effect_direction")
    cleaned: dict[str, str] = {}
    for field in required:
        value = str(payload.get(field, "")).strip()
        if not value:
            return None
        cleaned[field] = value
    allowed_directions = {"supports", "contradicts", "neutral"}
    if cleaned["effect_direction"] not in allowed_directions:
        return None
    return cleaned


def maybe_llm_refine_claim(doc: dict[str, Any], claim: BuiltClaim | None) -> BuiltClaim | None:
    if not _llm_extraction_enabled() or claim is None:
        return claim
    abstract = str(doc.get("abstract", "") or doc.get("abstract_text", "")).strip()
    if len(abstract) < 40:
        return claim
    try:
        from als_intel.llm import LocalLLMError, generate_with_ollama

        prompt = (
            "Extract ALS evidence fields as strict JSON with keys "
            "entity, relation, outcome, effect_direction. "
            "Use effect_direction in supports|contradicts|neutral only.\n"
            f"Title: {doc.get('title', '')}\nAbstract: {abstract}"
        )
        raw = generate_with_ollama(prompt=prompt, model=os.getenv("ALS_CLAIM_EXTRACTION_MODEL", "llama3.1:8b"))
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return claim
        parsed = json.loads(raw[start : end + 1])
        if not isinstance(parsed, dict):
            return claim
        validated = _validate_llm_fields(parsed)
        if validated is None:
            return claim
        provenance = dict(claim.provenance)
        provenance["llm_assisted"] = True
        return BuiltClaim(
            entity=validated["entity"],
            relation=validated["relation"],
            outcome=validated["outcome"],
            effect_direction=validated["effect_direction"],
            claim_text=claim.claim_text,
            cohort=claim.cohort,
            model_system=claim.model_system,
            endpoint=claim.endpoint,
            extraction_method=f"{claim.extraction_method}+llm",
            field_coverage=claim.field_coverage,
            provenance=provenance,
        )
    except Exception:
        return claim


def build_structured_claim(doc: dict[str, Any]) -> BuiltClaim | None:
    source = str(doc.get("source", "")).strip().lower()
    builder = _STRUCTURED_BUILDERS.get(source)
    if builder is None:
        return None
    return maybe_llm_refine_claim(doc, builder(doc))


def extraction_confidence_from_coverage(base: float, field_coverage: float) -> float:
    return round(max(0.45, min(base * 0.55 + field_coverage * 0.45, 0.98)), 4)


def build_record_from_doc(doc: dict[str, Any]) -> EvidenceRecord:
    source = str(doc.get("source", "unknown"))
    title = str(doc.get("title", "")).strip() or "Untitled record"
    source_id = str(doc.get("source_id", "")).strip()
    journal = str(doc.get("journal", "")).strip()

    structured = build_structured_claim(doc)
    if structured is not None:
        study_type = norm.infer_study_type(source, title)
        year = int(doc.get("year", 0) or 0)
        year = year if year > 0 else 2000
        base_conf = norm.infer_extraction_confidence(source_id, title, journal, year)
        extraction_confidence = extraction_confidence_from_coverage(base_conf, structured.field_coverage)
        peer_reviewed = source == "pubmed" and norm.infer_source_type(source, title, journal) != "preprint"
        return EvidenceRecord(
            claim_id=norm.claim_id(source, source_id, title),
            claim_text=structured.claim_text,
            disease="ALS",
            entity=structured.entity,
            relation=structured.relation,
            outcome=structured.outcome,
            effect_direction=structured.effect_direction,
            study_type=study_type,
            sample_size=norm.infer_sample_size(source, title, study_type),
            endpoint_validity=norm.infer_endpoint_validity(study_type, title, year),
            replication_count=norm.infer_replication_count(title),
            peer_reviewed=peer_reviewed,
            year=year,
            source_title=title,
            source_doi=source_id or str(doc.get("source_id", "unknown")),
            cohort=structured.cohort,
            model_system=structured.model_system,
            source_type=norm.infer_source_type(source, title, journal),
            extraction_confidence=extraction_confidence,
        )

    return norm.record_from_doc_legacy(doc)


def compare_to_gold(doc: dict[str, Any], expected: dict[str, str]) -> dict[str, object]:
    record = build_record_from_doc(doc)
    fields = ("entity", "relation", "outcome", "effect_direction")
    matches = {
        field: str(getattr(record, field)).strip().lower() == str(expected.get(field, "")).strip().lower()
        for field in fields
    }
    claim_text_ok = bool(record.claim_text) and record.claim_text != str(doc.get("title", "")).strip()
    return {
        "claim_id": record.claim_id,
        "matches": matches,
        "field_accuracy": sum(matches.values()) / len(matches),
        "claim_text_structured": claim_text_ok,
        "record": record,
    }
