from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


DEFAULT_HTTP_POLICY = {
    "retries": 2,
    "timeout": 20,
    "backoff_seconds": 0.25,
}

SOURCE_HTTP_POLICIES: dict[str, dict[str, float | int]] = {
    "pubmed": {"retries": 2, "timeout": 20, "backoff_seconds": 0.2},
    "ctgov": {"retries": 2, "timeout": 20, "backoff_seconds": 0.2},
    "pmc": {"retries": 2, "timeout": 25, "backoff_seconds": 0.25},
    "ncbi_gene": {"retries": 2, "timeout": 20, "backoff_seconds": 0.2},
    "uniprot": {"retries": 2, "timeout": 25, "backoff_seconds": 0.25},
    "go": {"retries": 2, "timeout": 25, "backoff_seconds": 0.25},
    "reactome": {"retries": 2, "timeout": 25, "backoff_seconds": 0.25},
    "geo": {"retries": 2, "timeout": 20, "backoff_seconds": 0.2},
    "arrayexpress": {"retries": 2, "timeout": 25, "backoff_seconds": 0.25},
    "kegg": {"retries": 2, "timeout": 20, "backoff_seconds": 0.2},
    "pride": {"retries": 2, "timeout": 25, "backoff_seconds": 0.25},
    "metabolomics_workbench": {"retries": 1, "timeout": 20, "backoff_seconds": 0.2},
    "chembl": {"retries": 2, "timeout": 25, "backoff_seconds": 0.25},
    "open_targets": {"retries": 2, "timeout": 25, "backoff_seconds": 0.25},
    "fda_labels": {"retries": 2, "timeout": 25, "backoff_seconds": 0.25},
}


def _http_policy(source_name: str | None) -> dict[str, float | int]:
    if not source_name:
        return dict(DEFAULT_HTTP_POLICY)
    merged = dict(DEFAULT_HTTP_POLICY)
    merged.update(SOURCE_HTTP_POLICIES.get(source_name, {}))
    return merged


def _http_request_text(
    *,
    url: str,
    source_name: str | None = None,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    policy = _http_policy(source_name)
    retries = int(policy["retries"])
    timeout = int(policy["timeout"])
    backoff = float(policy["backoff_seconds"])
    last_error: Exception | None = None

    request_headers = {"User-Agent": "als-intel/0.1"}
    if headers:
        request_headers.update(headers)

    for attempt in range(retries + 1):
        try:
            req = Request(url, data=body, headers=request_headers, method=method)
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return resp.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))

    assert last_error is not None
    raise last_error


def _http_get_json(url: str, *, source_name: str | None = None) -> dict[str, Any]:
    body = _http_request_text(url=url, source_name=source_name, method="GET")
    return json.loads(body)


def _http_post_json(url: str, payload: dict[str, Any], *, source_name: str | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    response_body = _http_request_text(
        url=url,
        source_name=source_name,
        method="POST",
        body=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    return json.loads(response_body)


def _chunk(values: list[str], size: int) -> list[list[str]]:
    step = max(1, int(size))
    return [values[idx: idx + step] for idx in range(0, len(values), step)]


def _target_limit(max_results: int) -> int | None:
    return int(max_results) if int(max_results) > 0 else None


def _strip_xml_text(xml_text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", xml_text)
    return re.sub(r"\s+", " ", text).strip()


def _fetch_pmc_body_snippet(pmcid: str, *, max_chars: int = 1800) -> str:
    if not pmcid:
        return ""
    source_id = pmcid if pmcid.upper().startswith("PMC") else f"PMC{pmcid}"
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{source_id}/fullTextXML"
    try:
        xml_text = _http_request_text(url=url, source_name="pmc", method="GET")
    except Exception:  # noqa: BLE001
        return ""
    body_match = re.search(r"<body[^>]*>(.*)</body>", xml_text, flags=re.DOTALL | re.IGNORECASE)
    raw_body = body_match.group(1) if body_match else xml_text
    return _strip_xml_text(raw_body)[:max_chars]


def fetch_pubmed(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch PubMed records as simple normalized documents.

    For deterministic local tests, pass from_file with a JSON list payload.
    """
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    target = _target_limit(max_results)
    page_size = 10000
    retstart = 0
    pmids: list[str] = []

    while True:
        if target is None:
            retmax = page_size
        else:
            remaining = target - len(pmids)
            if remaining <= 0:
                break
            retmax = min(page_size, remaining)

        search_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
            + urlencode(
                {
                    "db": "pubmed",
                    "term": query,
                    "retmode": "json",
                    "retmax": str(retmax),
                    "retstart": str(retstart),
                }
            )
        )
        search_payload = _http_get_json(search_url, source_name="pubmed")
        batch = [str(p) for p in search_payload.get("esearchresult", {}).get("idlist", [])]
        if not batch:
            break
        pmids.extend(batch)
        if len(batch) < retmax:
            break
        retstart += len(batch)

    if not pmids:
        return []

    result: dict[str, Any] = {}
    for pmid_batch in _chunk([str(p) for p in pmids], 100):
        summary_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
            + urlencode(
                {
                    "db": "pubmed",
                    "retmode": "json",
                    "id": ",".join(pmid_batch),
                }
            )
        )
        summary_payload = _http_get_json(summary_url, source_name="pubmed")
        batch_result = summary_payload.get("result", {})
        if isinstance(batch_result, dict):
            result.update(batch_result)

    docs: list[dict[str, Any]] = []
    for pmid in pmids:
        row = result.get(pmid, {})
        docs.append(
            {
                "source": "pubmed",
                "source_id": pmid,
                "title": row.get("title", ""),
                "year": int(str(row.get("pubdate", "0"))[:4] or 0),
                "journal": row.get("fulljournalname", ""),
            }
        )
    return docs


def fetch_pubmed_metadata(pmids: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch richer metadata for PubMed IDs using esummary.

    Returns a map keyed by PMID.
    """
    normalized = [str(p).strip() for p in pmids if str(p).strip()]
    if not normalized:
        return {}

    result: dict[str, Any] = {}
    for pmid_batch in _chunk(normalized, 100):
        summary_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
            + urlencode(
                {
                    "db": "pubmed",
                    "retmode": "json",
                    "id": ",".join(pmid_batch),
                }
            )
        )
        summary_payload = _http_get_json(summary_url, source_name="pubmed")
        batch_result = summary_payload.get("result", {})
        if isinstance(batch_result, dict):
            result.update(batch_result)

    output: dict[str, dict[str, Any]] = {}
    for pmid in normalized:
        row = result.get(pmid, {})
        authors = row.get("authors", [])
        author_names = [str(a.get("name", "")).strip() for a in authors if isinstance(a, dict) and a.get("name")]
        mesh_raw = row.get("meshheadinglist", [])
        mesh_terms = [str(m).strip() for m in mesh_raw if str(m).strip()]
        references_raw = row.get("references", [])
        references = [str(r).strip() for r in references_raw if str(r).strip()]

        output[pmid] = {
            "abstract_text": str(row.get("elocationid", "") or ""),
            "journal": str(row.get("fulljournalname", "") or ""),
            "pubdate": str(row.get("pubdate", "") or ""),
            "authors": author_names,
            "mesh_terms": mesh_terms,
            "affiliations": [],
            "references": references,
            "raw": row,
        }
    return output


def fetch_ctgov(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch ClinicalTrials.gov studies as normalized documents."""
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    target = _target_limit(max_results)
    page_size = 1000
    next_page_token = ""
    seen_tokens: set[str] = set()
    studies: list[dict[str, Any]] = []

    while True:
        if target is None:
            current_page_size = page_size
        else:
            remaining = target - len(studies)
            if remaining <= 0:
                break
            current_page_size = min(page_size, remaining)

        params: dict[str, str] = {
            "query.term": query,
            "pageSize": str(current_page_size),
        }
        if next_page_token:
            params["pageToken"] = next_page_token

        url = "https://clinicaltrials.gov/api/v2/studies?" + urlencode(params)
        payload = _http_get_json(url, source_name="ctgov")
        batch = payload.get("studies", [])
        if not isinstance(batch, list) or not batch:
            break
        studies.extend(batch)

        token = str(payload.get("nextPageToken", "") or "")
        if not token or token in seen_tokens:
            break
        seen_tokens.add(token)
        next_page_token = token

    docs: list[dict[str, Any]] = []
    for s in studies:
        protocol = s.get("protocolSection", {})
        id_module = protocol.get("identificationModule", {})
        status_module = protocol.get("statusModule", {})
        design_module = protocol.get("designModule", {})
        outcomes_module = protocol.get("outcomesModule", {})
        arms_module = protocol.get("armsInterventionsModule", {})
        title = id_module.get("briefTitle", "")
        nct_id = id_module.get("nctId", "")
        start_date = status_module.get("startDateStruct", {}).get("date", "0")
        phases = design_module.get("phases", [])
        phase = ", ".join(str(p) for p in phases if str(p).strip())
        enrollment_info = design_module.get("enrollmentInfo", {})
        enrollment = enrollment_info.get("count")
        primary_outcomes = outcomes_module.get("primaryOutcomes", [])
        primary_endpoint = ""
        if isinstance(primary_outcomes, list) and primary_outcomes:
            primary_endpoint = str(primary_outcomes[0].get("measure", "") or "")
        arms = arms_module.get("armGroups", [])
        intervention_arm = ""
        if isinstance(arms, list) and arms:
            intervention_arm = str(arms[0].get("label", "") or arms[0].get("type", "") or "")
        primary_endpoint_result = ""
        adverse_events_summary = ""
        results_section = s.get("resultsSection", {}) if isinstance(s.get("resultsSection"), dict) else {}
        if results_section:
            outcome_module = results_section.get("outcomeMeasuresModule", {})
            if isinstance(outcome_module, dict):
                measures = outcome_module.get("outcomeMeasures", [])
                if isinstance(measures, list):
                    for measure in measures:
                        if not isinstance(measure, dict):
                            continue
                        if str(measure.get("type", "")).upper() == "PRIMARY":
                            groups = measure.get("analyses", []) or measure.get("classes", [])
                            if isinstance(groups, list) and groups:
                                first = groups[0]
                                if isinstance(first, dict):
                                    primary_endpoint_result = str(
                                        first.get("pValue", "")
                                        or first.get("paramValue", "")
                                        or first.get("groupDescription", "")
                                        or first.get("title", "")
                                        or ""
                                    ).strip()
                            if not primary_endpoint_result:
                                primary_endpoint_result = str(measure.get("title", "") or "").strip()
                            break
            adverse_module = results_section.get("adverseEventsModule", {})
            if isinstance(adverse_module, dict):
                freq = adverse_module.get("frequencyThreshold", "")
                desc = adverse_module.get("description", "")
                adverse_events_summary = str(desc or freq or "").strip()

        docs.append(
            {
                "source": "ctgov",
                "source_id": nct_id,
                "title": title,
                "year": int(str(start_date)[:4] or 0),
                "journal": "clinicaltrials.gov",
                "trial_status": str(status_module.get("overallStatus", "") or ""),
                "phase": phase,
                "enrollment": enrollment,
                "primary_endpoint": primary_endpoint,
                "primary_endpoint_result": primary_endpoint_result,
                "adverse_events_summary": adverse_events_summary,
                "termination_reason": str(status_module.get("whyStopped", "") or ""),
                "intervention_arm": intervention_arm,
            }
        )
    return docs


def fetch_pmc(
    query: str,
    max_results: int = 20,
    from_file: str | None = None,
    *,
    fetch_fulltext: bool = False,
) -> list[dict[str, Any]]:
    """Fetch PubMed Central records as normalized documents.

    Uses Europe PMC search API for open-access/PMC indexed records.
    """
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    target = _target_limit(max_results)
    page_size = 1000
    page = 1
    rows: list[dict[str, Any]] = []

    while True:
        if target is None:
            current_page_size = page_size
        else:
            remaining = target - len(rows)
            if remaining <= 0:
                break
            current_page_size = min(page_size, remaining)

        url = (
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
            + urlencode(
                {
                    "query": f"{query} AND HAS_PMC:y",
                    "format": "json",
                    "pageSize": str(current_page_size),
                    "page": str(page),
                    "resultType": "core",
                }
            )
        )
        payload = _http_get_json(url, source_name="pmc")
        batch = payload.get("resultList", {}).get("result", [])
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < current_page_size:
            break
        page += 1

    docs: list[dict[str, Any]] = []
    for row in rows:
        pmcid = str(row.get("pmcid", "")).strip()
        title = str(row.get("title", "") or "")
        journal = str(row.get("journalTitle", "") or "")
        pub_year = int(str(row.get("pubYear", "0") or "0")[:4] or 0)
        abstract = str(row.get("abstractText", "") or row.get("abstract", "") or "").strip()
        body_text = str(row.get("body_text", "") or "").strip()
        should_fetch_body = fetch_fulltext or (target is not None and target <= 25)
        if not body_text and pmcid and should_fetch_body:
            body_text = _fetch_pmc_body_snippet(pmcid)
        docs.append(
            {
                "source": "pmc",
                "source_id": pmcid or str(row.get("id", "") or ""),
                "title": title,
                "year": pub_year,
                "journal": journal,
                "abstract": abstract,
                "body_text": body_text,
            }
        )
    return docs


def fetch_ncbi_gene(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch NCBI Gene records as normalized documents."""
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    target = _target_limit(max_results)
    page_size = 10000
    retstart = 0
    gene_ids: list[str] = []

    while True:
        if target is None:
            retmax = page_size
        else:
            remaining = target - len(gene_ids)
            if remaining <= 0:
                break
            retmax = min(page_size, remaining)

        search_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
            + urlencode(
                {
                    "db": "gene",
                    "term": query,
                    "retmode": "json",
                    "retmax": str(retmax),
                    "retstart": str(retstart),
                }
            )
        )
        search_payload = _http_get_json(search_url, source_name="ncbi_gene")
        batch = [str(g) for g in search_payload.get("esearchresult", {}).get("idlist", [])]
        if not batch:
            break
        gene_ids.extend(batch)
        if len(batch) < retmax:
            break
        retstart += len(batch)

    if not gene_ids:
        return []

    result: dict[str, Any] = {}
    for gene_batch in _chunk([str(gid) for gid in gene_ids], 100):
        summary_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
            + urlencode(
                {
                    "db": "gene",
                    "retmode": "json",
                    "id": ",".join(gene_batch),
                }
            )
        )
        summary_payload = _http_get_json(summary_url, source_name="ncbi_gene")
        batch_result = summary_payload.get("result", {})
        if isinstance(batch_result, dict):
            result.update(batch_result)

    docs: list[dict[str, Any]] = []
    for gene_id in gene_ids:
        row = result.get(gene_id, {})
        title = str(row.get("description", "") or row.get("name", "") or "")
        summary = str(row.get("summary", "") or "")
        if summary:
            title = f"{title}: {summary}" if title else summary
        gene_symbol = str(row.get("name", "") or "").strip()
        if ":" in title:
            gene_symbol = title.split(":", 1)[0].strip() or gene_symbol
        docs.append(
            {
                "source": "ncbi_gene",
                "source_id": str(gene_id),
                "title": title or str(row.get("name", "") or f"Gene {gene_id}"),
                "year": 2000,
                "journal": "NCBI Gene",
                "gene_symbol": gene_symbol,
                "summary": summary,
            }
        )
    return docs


def fetch_uniprot(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch UniProtKB entries as normalized documents."""
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    page_size = max(1, min(int(max_results), 500))
    url = (
        "https://rest.uniprot.org/uniprotkb/search?"
        + urlencode(
            {
                "query": query,
                "format": "json",
                "size": str(page_size),
                "fields": "accession,protein_name,gene_names,organism_name,date_created",
            }
        )
    )
    payload = _http_get_json(url, source_name="uniprot")
    rows = payload.get("results", [])

    docs: list[dict[str, Any]] = []
    for row in rows:
        accession = str(row.get("primaryAccession", "") or "").strip()
        protein_desc = row.get("proteinDescription", {}) if isinstance(row.get("proteinDescription"), dict) else {}
        rec_name = protein_desc.get("recommendedName", {}) if isinstance(protein_desc.get("recommendedName"), dict) else {}
        full_name_obj = rec_name.get("fullName", {}) if isinstance(rec_name.get("fullName"), dict) else {}
        protein_name = str(full_name_obj.get("value", "") or "").strip()

        genes = row.get("genes", [])
        gene_name = ""
        if isinstance(genes, list) and genes:
            first_gene = genes[0] if isinstance(genes[0], dict) else {}
            gene_obj = first_gene.get("geneName", {}) if isinstance(first_gene.get("geneName"), dict) else {}
            gene_name = str(gene_obj.get("value", "") or "").strip()

        organism_obj = row.get("organism", {}) if isinstance(row.get("organism"), dict) else {}
        organism = str(organism_obj.get("scientificName", "") or "").strip()

        created = str(row.get("entryAudit", {}).get("firstPublicDate", "") or "")
        pub_year = int((created[:4] or "0")) if created else 2000
        if pub_year <= 0:
            pub_year = 2000

        title_parts = [part for part in [gene_name, protein_name, organism] if part]
        title = " - ".join(title_parts) if title_parts else f"UniProt entry {accession or 'unknown'}"

        docs.append(
            {
                "source": "uniprot",
                "source_id": accession,
                "title": title,
                "year": pub_year,
                "journal": "UniProtKB",
                "gene_symbol": gene_name,
                "protein_name": protein_name,
            }
        )
    return docs


def fetch_go(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch Gene Ontology terms as normalized documents via QuickGO search."""
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    search_query = _simplify_boolean_query(query)
    target = _target_limit(max_results)
    page_size = 600
    page = 1
    rows: list[dict[str, Any]] = []

    while True:
        if target is None:
            current_page_size = page_size
        else:
            remaining = target - len(rows)
            if remaining <= 0:
                break
            current_page_size = min(page_size, remaining)

        url = (
            "https://www.ebi.ac.uk/QuickGO/services/ontology/go/search?"
            + urlencode(
                {
                    "query": search_query,
                    "limit": str(current_page_size),
                    "page": str(page),
                }
            )
        )
        payload = _http_get_json(url, source_name="go")
        batch = payload.get("results", [])
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < current_page_size:
            break
        page += 1
    docs: list[dict[str, Any]] = []
    for row in rows:
        go_id = str(row.get("id", "") or "").strip()
        name = str(row.get("name", "") or "").strip()
        definition = ""
        definition_obj = row.get("definition", {}) if isinstance(row.get("definition"), dict) else {}
        if definition_obj:
            definition = str(definition_obj.get("text", "") or "").strip()
        title = f"{name}: {definition}" if definition else name
        docs.append(
            {
                "source": "go",
                "source_id": go_id,
                "title": title or f"GO term {go_id}",
                "year": 2000,
                "journal": "Gene Ontology",
                "ontology_term": name,
                "definition": definition,
            }
        )
    return docs


def fetch_reactome(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch Reactome pathways/events as normalized documents."""
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    target = _target_limit(max_results)
    page_size = 1000
    start = 0
    rows: list[dict[str, Any]] = []

    while True:
        if target is None:
            current_page_size = page_size
        else:
            remaining = target - len(rows)
            if remaining <= 0:
                break
            current_page_size = min(page_size, remaining)

        url = (
            "https://reactome.org/ContentService/search/query?"
            + urlencode(
                {
                    "query": query,
                    "species": "Homo sapiens",
                    "types": "Pathway,Reaction",
                    "cluster": "true",
                    "start": str(start),
                    "rows": str(current_page_size),
                }
            )
        )
        payload = _http_get_json(url, source_name="reactome")
        batch = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < current_page_size:
            break
        start += len(batch)

    docs: list[dict[str, Any]] = []
    for row in rows:
        st_id = str(row.get("stId", "") or row.get("id", "")).strip()
        name = str(row.get("name", "") or "").strip()
        exact_type = str(row.get("exactType", "") or "").strip()
        docs.append(
            {
                "source": "reactome",
                "source_id": st_id,
                "title": f"{name} ({exact_type})" if name and exact_type else (name or f"Reactome entry {st_id}"),
                "year": 2000,
                "journal": "Reactome",
                "pathway_name": name,
                "pathway_type": exact_type,
            }
        )
    return docs


def fetch_geo(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch GEO datasets (GDS/GSE-like records) as normalized documents."""
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    target = _target_limit(max_results)
    page_size = 10000
    retstart = 0
    ids: list[str] = []

    while True:
        if target is None:
            retmax = page_size
        else:
            remaining = target - len(ids)
            if remaining <= 0:
                break
            retmax = min(page_size, remaining)

        search_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
            + urlencode(
                {
                    "db": "gds",
                    "term": query,
                    "retmode": "json",
                    "retmax": str(retmax),
                    "retstart": str(retstart),
                }
            )
        )
        search_payload = _http_get_json(search_url, source_name="geo")
        batch = [str(item) for item in search_payload.get("esearchresult", {}).get("idlist", [])]
        if not batch:
            break
        ids.extend(batch)
        if len(batch) < retmax:
            break
        retstart += len(batch)

    if not ids:
        return []

    result: dict[str, Any] = {}
    for id_batch in _chunk([str(item) for item in ids], 100):
        summary_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
            + urlencode(
                {
                    "db": "gds",
                    "retmode": "json",
                    "id": ",".join(id_batch),
                }
            )
        )
        summary_payload = _http_get_json(summary_url, source_name="geo")
        batch_result = summary_payload.get("result", {})
        if isinstance(batch_result, dict):
            result.update(batch_result)

    docs: list[dict[str, Any]] = []
    for geo_id in ids:
        row = result.get(geo_id, {})
        accession = str(row.get("accession", "") or "").strip()
        title = str(row.get("title", "") or "").strip()
        if not title:
            title = f"GEO dataset {accession or geo_id}"
        pd = str(row.get("pdattim", "") or "")
        year = int(pd[:4] or "0") if pd else 2000
        if year <= 0:
            year = 2000
        platform = str(row.get("gpl", "") or row.get("platform", "") or "").strip()
        docs.append(
            {
                "source": "geo",
                "source_id": accession or str(geo_id),
                "title": title,
                "year": year,
                "journal": "GEO",
                "platform": platform,
                "study_type": "transcriptomic",
            }
        )
    return docs


def fetch_arrayexpress(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch ArrayExpress experiments as normalized documents."""
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    target = _target_limit(max_results)
    page_size = 1000
    page = 1
    rows: list[dict[str, Any]] = []

    while True:
        if target is None:
            current_page_size = page_size
        else:
            remaining = target - len(rows)
            if remaining <= 0:
                break
            current_page_size = min(page_size, remaining)

        url = (
            "https://www.ebi.ac.uk/biostudies/api/v1/arrayexpress/search?"
            + urlencode(
                {
                    "query": query,
                    "pageSize": str(current_page_size),
                    "page": str(page),
                }
            )
        )
        payload = _http_get_json(url, source_name="arrayexpress")
        batch = payload.get("hits", []) if isinstance(payload, dict) else []
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < current_page_size:
            break
        page += 1

    docs: list[dict[str, Any]] = []
    for row in rows:
        accession = str(row.get("accession", "") or "").strip()
        title = str(row.get("title", "") or "").strip() or f"ArrayExpress study {accession}"
        release = str(row.get("releaseDate", "") or "")
        year = int(release[:4] or "0") if release else 2000
        if year <= 0:
            year = 2000
        docs.append(
            {
                "source": "arrayexpress",
                "source_id": accession,
                "title": title,
                "year": year,
                "journal": "ArrayExpress",
                "study_type": "transcriptomic",
            }
        )
    return docs


def _simplify_boolean_query(query: str, *, default: str = "als") -> str:
    cleaned = str(query or "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1].strip()
    cleaned = cleaned.replace('"', "")
    parts = [part.strip() for part in re.split(r"\s+OR\s+", cleaned, flags=re.IGNORECASE) if part.strip()]
    if not parts:
        return default
    return max(parts, key=len)


def _kegg_find_query(query: str) -> str:
    return _simplify_boolean_query(query)


def fetch_kegg(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch KEGG pathways via KEGG REST find endpoint."""
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    search_query = _kegg_find_query(query)
    encoded_query = quote(search_query, safe="")
    url = f"https://rest.kegg.jp/find/pathway/{encoded_query}"
    text = _http_request_text(url=url, source_name="kegg", method="GET")

    target = _target_limit(max_results)
    lines = text.splitlines() if target is None else text.splitlines()[:target]

    docs: list[dict[str, Any]] = []
    for line in lines:
        if "\t" not in line:
            continue
        raw_id, raw_title = line.split("\t", 1)
        source_id = raw_id.replace("path:", "").strip()
        title = raw_title.strip()
        docs.append(
            {
                "source": "kegg",
                "source_id": source_id,
                "title": title or f"KEGG pathway {source_id}",
                "year": 2000,
                "journal": "KEGG",
                "pathway_name": title.split(" - ", 1)[0].strip() if " - " in title else title,
            }
        )
    return docs


def fetch_pride(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch PRIDE projects (proteomics) from EBI archive API."""
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    target = _target_limit(max_results)
    page_size = 1000
    page = 0
    rows: list[dict[str, Any]] = []

    while True:
        if target is None:
            current_page_size = page_size
        else:
            remaining = target - len(rows)
            if remaining <= 0:
                break
            current_page_size = min(page_size, remaining)

        url = (
            "https://www.ebi.ac.uk/pride/ws/archive/v2/projects?"
            + urlencode(
                {
                    "keyword": query,
                    "page": str(page),
                    "pageSize": str(current_page_size),
                }
            )
        )
        payload = _http_get_json(url, source_name="pride")
        embedded = payload.get("_embedded", {}) if isinstance(payload, dict) else {}
        batch = embedded.get("projects", []) if isinstance(embedded, dict) else []
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < current_page_size:
            break
        page += 1

    docs: list[dict[str, Any]] = []
    for row in rows:
        accession = str(row.get("accession", "") or "").strip()
        title = str(row.get("title", "") or "").strip() or f"PRIDE project {accession}"
        published = str(row.get("publicationDate", "") or "")
        year = int(published[:4] or "0") if published else 2000
        if year <= 0:
            year = 2000
        docs.append(
            {
                "source": "pride",
                "source_id": accession,
                "title": title,
                "year": year,
                "journal": "PRIDE",
                "study_type": "proteomic",
            }
        )
    return docs


def fetch_metabolomics_workbench(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch Metabolomics Workbench studies.

    The public API surface is heterogeneous; this endpoint is best-effort and returns [] on transport/schema mismatch.
    """
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    try:
        url = f"https://www.metabolomicsworkbench.org/rest/study/query/{query}/json"
        payload = _http_get_json(url, source_name="metabolomics_workbench")
    except Exception:  # noqa: BLE001
        return []

    rows: list[dict[str, Any]]
    if isinstance(payload, dict) and isinstance(payload.get("study"), list):
        rows = payload.get("study", [])
    elif isinstance(payload, dict) and isinstance(payload.get("results"), list):
        rows = payload.get("results", [])
    else:
        rows = []

    target = _target_limit(max_results)
    iter_rows = rows if target is None else rows[:target]

    docs: list[dict[str, Any]] = []
    for row in iter_rows:
        study_id = str(row.get("study_id", "") or row.get("STUDY_ID", "") or "").strip()
        title = str(row.get("title", "") or row.get("study_title", "") or row.get("TITLE", "") or "").strip()
        release = str(row.get("release_date", "") or row.get("RELEASE_DATE", "") or "")
        year = int(release[:4] or "0") if release else 2000
        if year <= 0:
            year = 2000
        docs.append(
            {
                "source": "metabolomics_workbench",
                "source_id": study_id or title[:32] or "mw-study",
                "title": title or f"Metabolomics Workbench study {study_id or 'unknown'}",
                "year": year,
                "journal": "Metabolomics Workbench",
                "study_type": "metabolomic",
            }
        )
    return docs


def fetch_chembl(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch ChEMBL molecules via public API."""
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    target = _target_limit(max_results)
    page_size = 1000
    offset = 0
    rows: list[dict[str, Any]] = []

    while True:
        if target is None:
            current_limit = page_size
        else:
            remaining = target - len(rows)
            if remaining <= 0:
                break
            current_limit = min(page_size, remaining)

        url = (
            "https://www.ebi.ac.uk/chembl/api/data/molecule/search.json?"
            + urlencode(
                {
                    "q": query,
                    "limit": str(current_limit),
                    "offset": str(offset),
                }
            )
        )
        payload = _http_get_json(url, source_name="chembl")
        batch = payload.get("molecules", [])
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < current_limit:
            break
        offset += len(batch)

    docs: list[dict[str, Any]] = []
    for row in rows:
        chembl_id = str(row.get("molecule_chembl_id", "") or "").strip()
        pref_name = str(row.get("pref_name", "") or "").strip()
        year_value = row.get("first_approval")
        year = int(year_value) if isinstance(year_value, int) and year_value > 0 else 2000
        docs.append(
            {
                "source": "chembl",
                "source_id": chembl_id,
                "title": pref_name or f"ChEMBL compound {chembl_id}",
                "year": year,
                "journal": "ChEMBL",
                "drug_name": pref_name,
                "first_approval": year_value if isinstance(year_value, int) else None,
            }
        )
    return docs


def fetch_open_targets(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch Open Targets entities via public GraphQL search."""
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    target = _target_limit(max_results)
    size = 500
    graphql_query = """
        query SearchEntities($queryString: String!, $size: Int!, $index: Int!) {
            search(queryString: $queryString, page: {index: $index, size: $size}) {
        hits {
          id
          entity
          name
          description
        }
      }
    }
    """
    rows: list[dict[str, Any]] = []
    index = 0

    while True:
        if target is None:
            current_size = size
        else:
            remaining = target - len(rows)
            if remaining <= 0:
                break
            current_size = min(size, remaining)

        payload = _http_post_json(
            "https://api.platform.opentargets.org/api/v4/graphql",
            {
                "query": graphql_query,
                "variables": {"queryString": query, "size": current_size, "index": index},
            },
            source_name="open_targets",
        )
        batch = payload.get("data", {}).get("search", {}).get("hits", [])
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < current_size:
            break
        index += 1

    docs: list[dict[str, Any]] = []
    for row in rows:
        entity_id = str(row.get("id", "") or "").strip()
        name = str(row.get("name", "") or "").strip()
        desc = str(row.get("description", "") or "").strip()
        entity = str(row.get("entity", "") or "").strip()
        title = name
        if desc:
            title = f"{name}: {desc}" if name else desc
        if entity:
            title = f"{title} ({entity})" if title else entity
        docs.append(
            {
                "source": "open_targets",
                "source_id": entity_id,
                "title": title or f"Open Targets entity {entity_id}",
                "year": 2000,
                "journal": "Open Targets",
                "target_name": name if entity.lower() == "target" else "",
                "entity_type": entity.lower(),
            }
        )
    return docs


def fetch_fda_labels(query: str, max_results: int = 20, from_file: str | None = None) -> list[dict[str, Any]]:
    """Fetch FDA drug labels from openFDA API."""
    if from_file:
        return json.loads(Path(from_file).read_text(encoding="utf-8"))

    docs: list[dict[str, Any]] = []
    target = _target_limit(max_results)
    page_size = 100
    skip = 0
    seen_ids: set[str] = set()

    while True:
        if target is not None and len(docs) >= target:
            break
        url = (
            "https://api.fda.gov/drug/label.json?"
            + urlencode(
                {
                    "search": query,
                    "limit": str(page_size),
                    "skip": str(skip),
                }
            )
        )
        payload = _http_get_json(url, source_name="fda_labels")
        rows = payload.get("results", [])
        if not isinstance(rows, list) or not rows:
            break

        page_added = 0
        for row in rows:
            set_id = str(row.get("set_id", "") or "").strip()
            if not set_id or set_id in seen_ids:
                continue
            seen_ids.add(set_id)

            openfda = row.get("openfda", {}) if isinstance(row.get("openfda"), dict) else {}
            brand = openfda.get("brand_name", [])
            generic = openfda.get("generic_name", [])
            label_name = ""
            if isinstance(brand, list) and brand:
                label_name = str(brand[0])
            elif isinstance(generic, list) and generic:
                label_name = str(generic[0])
            purpose = row.get("purpose", [])
            purpose_text = str(purpose[0]) if isinstance(purpose, list) and purpose else ""
            title = label_name.strip() or f"FDA label {set_id}"
            if purpose_text.strip():
                title = f"{title}: {purpose_text.strip()}"
            docs.append(
                {
                    "source": "fda_labels",
                    "source_id": set_id,
                    "title": title,
                    "year": 2000,
                    "journal": "openFDA Drug Labels",
                    "drug_name": label_name.strip(),
                    "indication": purpose_text.strip(),
                }
            )
            page_added += 1
            if target is not None and len(docs) >= target:
                break

        if page_added == 0:
            break
        skip += page_size

    return docs
