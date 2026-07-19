from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from als_intel.models import EvidenceRecord
from als_intel.store import EvidenceStore
from als_intel import webui
from als_intel.llm import LocalLLMError
from als_intel.webui import ChatHandler
from http.server import ThreadingHTTPServer


_FAKE_MODEL_CATALOG = {
    "host": "http://localhost:11434",
    "default": "test-model",
    "models": [
        {
            "id": "test-model",
            "name": "test-model",
            "size": 1,
            "tier": "balanced",
            "family": "unknown",
            "display_name": "test-model",
            "installed": True,
        },
        {
            "id": "qwen2.5:14b",
            "name": "qwen2.5:14b",
            "size": 2,
            "tier": "balanced",
            "family": "qwen",
            "display_name": "Qwen3 14B",
            "installed": True,
        },
        {
            "id": "gemma2:2b",
            "name": "gemma2:2b",
            "size": 3,
            "tier": "fast",
            "family": "gemma",
            "display_name": "Gemma 2 2B",
            "installed": True,
        },
    ],
    "recommended": [
        {
            "id": "llama3.3:70b",
            "name": "llama3.3:70b",
            "size": None,
            "tier": "best",
            "family": "llama",
            "display_name": "Llama 3.3 70B",
            "installed": False,
            "ollama_pull": "llama3.3:70b",
        }
    ],
    "error": None,
}


@pytest.fixture(autouse=True)
def _mock_ollama_model_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(webui, "list_ollama_models", lambda **_: dict(_FAKE_MODEL_CATALOG))


def _seed_evidence(_unused: Path | None = None) -> None:
    store = EvidenceStore()
    store.init_db()

    rows = [
        EvidenceRecord(
            claim_id="C1",
            claim_text="Drug A supports outcome X",
            disease="ALS",
            entity="drug-a",
            relation="modulates",
            outcome="outcome-x",
            effect_direction="supports",
            study_type="observational",
            sample_size=120,
            endpoint_validity=0.8,
            replication_count=2,
            peer_reviewed=True,
            year=2022,
            source_title="Study C1",
            source_doi="10.1000/c1",
            causal_evidence_type="observational",
        ),
        EvidenceRecord(
            claim_id="C2",
            claim_text="Drug A also supports outcome X",
            disease="ALS",
            entity="drug-a",
            relation="modulates",
            outcome="outcome-x",
            effect_direction="supports",
            study_type="interventional",
            sample_size=80,
            endpoint_validity=0.75,
            replication_count=1,
            peer_reviewed=True,
            year=2021,
            source_title="Study C2",
            source_doi="10.1000/c2",
            causal_evidence_type="interventional",
        ),
        EvidenceRecord(
            claim_id="C3",
            claim_text="Drug A contradicts outcome X",
            disease="ALS",
            entity="drug-a",
            relation="modulates",
            outcome="outcome-x",
            effect_direction="contradicts",
            study_type="observational",
            sample_size=60,
            endpoint_validity=0.7,
            replication_count=1,
            peer_reviewed=False,
            year=2020,
            source_title="Study C3",
            source_doi="10.1000/c3",
            causal_evidence_type="negative",
        ),
    ]

    for rec in rows:
        store.upsert_evidence(
            rec,
            score_breakdown={
                "study": 0.2,
                "sample": 0.15,
                "replication": 0.1,
                "peer_review": 0.1,
                "endpoint": 0.1,
                "source": 0.15,
                "extraction": 0.1,
                "total": 0.7,
            },
            source_score=0.8,
        )

    store.upsert_evidence_source_metadata(
        claim_id="C1",
        source_name="pubmed",
        source_id="1000",
        abstract_text="Synthetic abstract for C1",
        journal="ALS Journal",
        pubdate="2022 Jan",
        authors=["A. Author", "B. Author"],
        mesh_terms=["Amyotrophic Lateral Sclerosis", "Neuroinflammation"],
        affiliations=["ALS Institute"],
        references=["2000", "3000"],
        metadata={
            "uid": "1000",
            "api_endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
            "query_used": "amyotrophic lateral sclerosis",
            "source_version": "v1",
            "source_license": "open",
            "extracted_at": "2026-07-01T00:00:00+00:00",
        },
    )


def _request_json(
    base_url: str,
    path: str,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    data = None
    req_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body or "{}")


def _request_ndjson(base_url: str, path: str, payload: dict[str, object]) -> tuple[int, list[dict[str, object]]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode("utf-8")
        events = [json.loads(line) for line in body.splitlines() if line.strip()]
        return resp.status, events


def _request_json_with_headers(
    base_url: str,
    path: str,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object], dict[str, str]]:
    data = None
    req_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=req_headers, method=method)
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode("utf-8")
        return resp.status, json.loads(body or "{}"), dict(resp.headers.items())


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request_no_redirect(base_url: str, path: str) -> tuple[int, dict[str, str], str]:
    req = urllib.request.Request(f"{base_url}{path}", method="GET")
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, dict(resp.headers.items()), body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, dict(exc.headers.items()), body


@pytest.fixture
def api_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    db_path = tmp_path / "als.sqlite"
    _seed_evidence(db_path)

    monkeypatch.setenv("ALS_DB_PATH", str(db_path))
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("ALS_AUTH_ENABLED", "0")
    monkeypatch.setattr(webui, "generate_with_ollama", lambda **_: "stubbed answer")

    server = ThreadingHTTPServer(("127.0.0.1", 0), ChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def api_server_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    db_path = tmp_path / "als_auth.sqlite"
    _seed_evidence(db_path)

    monkeypatch.setenv("ALS_DB_PATH", str(db_path))
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("ALS_AUTH_ENABLED", "1")
    monkeypatch.setenv("ALS_MAGIC_LINK_DEV_MODE", "1")
    monkeypatch.setenv("ALS_CSRF_SECRET", "test-csrf-secret")
    monkeypatch.setattr(webui, "generate_with_ollama", lambda **_: "stubbed answer")

    server = ThreadingHTTPServer(("127.0.0.1", 0), ChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_status_filter_search_compare_and_chat_routes(api_server: str) -> None:
    status_code, status_data = _request_json(api_server, "/api/status")
    assert status_code == 200
    assert int(status_data["records_total"]) == 3
    assert "review_flags_count" in status_data
    assert int(status_data["review_flags_count"]) == 0
    assert "source_breakdown" in status_data
    assert "manual_sync" in status_data

    models_code, models_data = _request_json(api_server, "/api/models")
    assert models_code == 200
    assert models_data["default"] == "test-model"
    assert any(row["name"] == "qwen2.5:14b" for row in models_data["models"])
    assert "recommended" in models_data
    assert any(row.get("installed") is False for row in models_data["recommended"])

    filter_code, filter_data = _request_json(
        api_server,
        "/api/evidence/filter",
        method="POST",
        payload={
            "filters": {
                "evidence_types": ["observational"],
                "min_reliability": 0.6,
                "date_window": "all",
            }
        },
    )
    assert filter_code == 200
    assert int(filter_data["total"]) == 1
    assert int(filter_data["limit"]) == 50
    assert int(filter_data["offset"]) == 0
    assert bool(filter_data["has_more"]) is False

    search_code, search_data = _request_json(
        api_server,
        "/api/evidence/search",
        method="POST",
        payload={"query": "C3", "filters": {}},
    )
    assert search_code == 200
    assert any(row["claim_id"] == "C3" for row in search_data["rows"])
    matched = next(row for row in search_data["rows"] if row["claim_id"] == "C3")
    assert matched["source_url"] == "https://doi.org/10.1000/c3"

    lineage_code, lineage_data = _request_json(api_server, "/api/evidence/C1")
    assert lineage_code == 200
    assert lineage_data["claim"]["claim_id"] == "C1"

    compare_code, compare_data = _request_json(
        api_server,
        "/api/evidence/compare",
        method="POST",
        payload={"claim_a": "C1", "claim_b": "C3"},
    )
    assert compare_code == 200
    assert compare_data["claim_a"]["claim_id"] == "C1"
    assert compare_data["claim_b"]["claim_id"] == "C3"
    assert "follow_up_suggestion" in compare_data

    chat_code, chat_data = _request_json(
        api_server,
        "/api/chat",
        method="POST",
        payload={
            "messages": [{"role": "user", "content": "What does the evidence suggest?"}],
            "filters": {},
            "context_limit": 5,
            "temperature": 0.1,
            "timeout_seconds": 10,
        },
    )
    assert chat_code == 200
    assert chat_data["answer"] == "stubbed answer"
    assert "synthesis" in chat_data
    assert chat_data["model"] in {"test-model", "qwen2.5:14b", "gemma2:2b"}

    auto_code, auto_data = _request_json(
        api_server,
        "/api/chat",
        method="POST",
        payload={
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Compare contradictory mechanistic causal pathways and synthesize "
                        "uncertainty with validation next steps across claim trade-offs."
                    ),
                }
            ],
            "model": "auto",
            "filters": {},
            "context_limit": 5,
            "temperature": 0.1,
            "timeout_seconds": 10,
        },
    )
    assert auto_code == 200
    assert auto_data["model"] == "qwen2.5:14b"


def test_chat_route_applies_evidence_type_filter(api_server: str) -> None:
    base_payload = {
        "messages": [{"role": "user", "content": "What does the evidence suggest?"}],
        "context_limit": 5,
        "temperature": 0.1,
        "timeout_seconds": 10,
    }

    all_code, all_data = _request_json(
        api_server,
        "/api/chat",
        method="POST",
        payload={
            **base_payload,
            "filters": {},
        },
    )
    assert all_code == 200
    assert int(all_data["evidence_count"]) == 3

    observational_code, observational_data = _request_json(
        api_server,
        "/api/chat",
        method="POST",
        payload={
            **base_payload,
            "filters": {
                "evidence_types": ["observational"],
                "date_window": "all",
                "min_reliability": 0.0,
                "highlight_contradictions": False,
            },
        },
    )
    assert observational_code == 200
    assert int(observational_data["evidence_count"]) == 1

    interventional_code, interventional_data = _request_json(
        api_server,
        "/api/chat",
        method="POST",
        payload={
            **base_payload,
            "filters": {
                "evidence_types": ["interventional"],
                "date_window": "all",
                "min_reliability": 0.0,
                "highlight_contradictions": False,
            },
        },
    )
    assert interventional_code == 200
    assert int(interventional_data["evidence_count"]) == 1

    negative_code, negative_data = _request_json(
        api_server,
        "/api/chat",
        method="POST",
        payload={
            **base_payload,
            "filters": {
                "evidence_types": ["negative"],
                "date_window": "all",
                "min_reliability": 0.0,
                "highlight_contradictions": False,
            },
        },
    )
    assert negative_code == 200
    assert int(negative_data["evidence_count"]) == 1


def test_publication_date_filter_affects_chat_and_filter_routes(api_server: str) -> None:
    base_payload = {
        "messages": [{"role": "user", "content": "Summarize the filtered evidence."}],
        "context_limit": 5,
        "temperature": 0.1,
        "timeout_seconds": 10,
        "filters": {
            "evidence_types": ["observational", "interventional", "negative"],
            "min_reliability": 0.0,
            "highlight_contradictions": False,
        },
    }

    all_code, all_data = _request_json(
        api_server,
        "/api/chat",
        method="POST",
        payload={
            **base_payload,
            "filters": {
                **base_payload["filters"],
                "date_window": "all",
            },
        },
    )
    assert all_code == 200
    assert int(all_data["evidence_count"]) == 3

    last5_chat_code, last5_chat_data = _request_json(
        api_server,
        "/api/chat",
        method="POST",
        payload={
            **base_payload,
            "filters": {
                **base_payload["filters"],
                "date_window": "last5",
            },
        },
    )
    assert last5_chat_code == 200
    assert int(last5_chat_data["evidence_count"]) == 2

    all_filter_code, all_filter_data = _request_json(
        api_server,
        "/api/evidence/filter",
        method="POST",
        payload={
            "filters": {
                "evidence_types": ["observational", "interventional", "negative"],
                "date_window": "all",
                "min_reliability": 0.0,
                "highlight_contradictions": False,
            }
        },
    )
    assert all_filter_code == 200
    assert int(all_filter_data["total"]) == 3

    last5_filter_code, last5_filter_data = _request_json(
        api_server,
        "/api/evidence/filter",
        method="POST",
        payload={
            "filters": {
                "evidence_types": ["observational", "interventional", "negative"],
                "date_window": "last5",
                "min_reliability": 0.0,
                "highlight_contradictions": False,
            }
        },
    )
    assert last5_filter_code == 200
    assert int(last5_filter_data["total"]) == 2


def test_highlight_contradictions_affects_filter_order(api_server: str) -> None:
    base_filters = {
        "evidence_types": ["observational", "interventional", "negative"],
        "date_window": "all",
        "min_reliability": 0.0,
    }

    normal_code, normal_data = _request_json(
        api_server,
        "/api/evidence/filter",
        method="POST",
        payload={
            "filters": {
                **base_filters,
                "highlight_contradictions": False,
            }
        },
    )
    assert normal_code == 200
    assert [row["claim_id"] for row in normal_data["rows"]] == ["C1", "C2", "C3"]

    highlighted_code, highlighted_data = _request_json(
        api_server,
        "/api/evidence/filter",
        method="POST",
        payload={
            "filters": {
                **base_filters,
                "highlight_contradictions": True,
            }
        },
    )
    assert highlighted_code == 200
    assert [row["claim_id"] for row in highlighted_data["rows"]] == ["C3", "C1", "C2"]


def test_highlight_contradictions_affects_chat_prompt_context_order(
    api_server: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(webui, "generate_with_ollama", lambda **kwargs: str(kwargs.get("prompt", "")))

    base_payload = {
        "messages": [{"role": "user", "content": "Summarize evidence."}],
        "context_limit": 5,
        "temperature": 0.1,
        "timeout_seconds": 10,
        "filters": {
            "evidence_types": ["observational", "interventional", "negative"],
            "date_window": "all",
            "min_reliability": 0.0,
        },
    }

    normal_code, normal_data = _request_json(
        api_server,
        "/api/chat",
        method="POST",
        payload={
            **base_payload,
            "filters": {
                **base_payload["filters"],
                "highlight_contradictions": False,
            },
        },
    )
    assert normal_code == 200
    normal_prompt = str(normal_data["answer"])
    normal_c1 = normal_prompt.find("claim_id=C1")
    normal_c3 = normal_prompt.find("claim_id=C3")
    assert normal_c1 != -1
    assert normal_c3 != -1
    assert normal_c1 < normal_c3

    highlighted_code, highlighted_data = _request_json(
        api_server,
        "/api/chat",
        method="POST",
        payload={
            **base_payload,
            "filters": {
                **base_payload["filters"],
                "highlight_contradictions": True,
            },
        },
    )
    assert highlighted_code == 200
    highlighted_prompt = str(highlighted_data["answer"])
    highlighted_c1 = highlighted_prompt.find("claim_id=C1")
    highlighted_c3 = highlighted_prompt.find("claim_id=C3")
    assert highlighted_c1 != -1
    assert highlighted_c3 != -1
    assert highlighted_c3 < highlighted_c1


def test_database_nodes_route_supports_search_and_pagination(api_server: str) -> None:
    page_code, page_data = _request_json(
        api_server,
        "/api/database/nodes",
        method="POST",
        payload={
            "query": "",
            "limit": 1,
            "offset": 1,
        },
    )
    assert page_code == 200
    assert int(page_data["total"]) == 3
    assert int(page_data["limit"]) == 1
    assert int(page_data["offset"]) == 1
    assert bool(page_data["has_more"]) is True
    assert len(page_data["rows"]) == 1
    assert page_data["rows"][0]["claim_id"] == "C2"

    search_code, search_data = _request_json(
        api_server,
        "/api/database/nodes",
        method="POST",
        payload={
            "query": "contradicts",
            "limit": 10,
            "offset": 0,
        },
    )
    assert search_code == 200
    assert int(search_data["total"]) == 1
    assert len(search_data["rows"]) == 1
    row = search_data["rows"][0]
    assert row["claim_id"] == "C3"
    assert row["claim_text"] == "Drug A contradicts outcome X"
    assert "source_doi" in row
    assert row["source_url"] == "https://doi.org/10.1000/c3"


def test_database_nodes_route_includes_metadata_summary(api_server: str) -> None:
    code, data = _request_json(
        api_server,
        "/api/database/nodes",
        method="POST",
        payload={
            "query": "C1",
            "limit": 10,
            "offset": 0,
        },
    )
    assert code == 200
    assert int(data["total"]) == 1
    row = data["rows"][0]
    assert row["claim_id"] == "C1"
    assert "source_metadata" in row
    summary = row["source_metadata"]
    assert summary["journal"] == "ALS Journal"
    assert int(summary["authors_count"]) == 2
    assert int(summary["mesh_terms_count"]) == 2
    assert bool(summary["has_abstract"]) is True
    assert summary["api_endpoint"] == "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    assert summary["query_used"] == "amyotrophic lateral sclerosis"
    assert summary["source_version"] == "v1"
    assert summary["source_license"] == "open"


def test_database_node_metadata_route_returns_detail(api_server: str) -> None:
    code, data = _request_json(
        api_server,
        "/api/database/node/metadata",
        method="POST",
        payload={"claim_id": "C1"},
    )
    assert code == 200
    assert bool(data["found"]) is True
    metadata = data["metadata"]
    assert metadata["claim_id"] == "C1"
    assert metadata["source_name"] == "pubmed"
    assert metadata["journal"] == "ALS Journal"
    assert metadata["authors"] == ["A. Author", "B. Author"]
    assert metadata["metadata"]["api_endpoint"] == "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    assert metadata["metadata"]["query_used"] == "amyotrophic lateral sclerosis"
    assert metadata["metadata"]["source_version"] == "v1"
    assert metadata["metadata"]["source_license"] == "open"

    missing_code, missing_data = _request_json(
        api_server,
        "/api/database/node/metadata",
        method="POST",
        payload={"claim_id": "C2"},
    )
    assert missing_code == 200
    assert bool(missing_data["found"]) is False
    assert missing_data["metadata"] is None


def test_source_url_builder_supports_ncbi_gene() -> None:
    row = {
        "claim_id": "NCBI_GENE_4843",
        "source_doi": "4843",
    }
    assert webui._build_source_url_for_row(row) == "https://www.ncbi.nlm.nih.gov/gene/4843"


def test_source_url_builder_supports_uniprot() -> None:
    row = {
        "claim_id": "UNIPROT_P05067",
        "source_doi": "P05067",
    }
    assert webui._build_source_url_for_row(row) == "https://www.uniprot.org/uniprotkb/P05067"


def test_source_url_builder_supports_go() -> None:
    row = {
        "claim_id": "GO_0006915",
        "source_doi": "GO:0006915",
    }
    assert webui._build_source_url_for_row(row) == "https://www.ebi.ac.uk/QuickGO/term/GO:0006915"


def test_source_url_builder_supports_reactome() -> None:
    row = {
        "claim_id": "REACTOME_R-HSA-109581",
        "source_doi": "R-HSA-109581",
    }
    assert webui._build_source_url_for_row(row) == "https://reactome.org/content/detail/R-HSA-109581"


def test_source_url_builder_supports_geo() -> None:
    row = {
        "claim_id": "GEO_GSE123456",
        "source_doi": "GSE123456",
    }
    assert webui._build_source_url_for_row(row) == "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE123456"


def test_source_url_builder_supports_arrayexpress() -> None:
    row = {
        "claim_id": "ARRAYEXPRESS_E-MTAB-12345",
        "source_doi": "E-MTAB-12345",
    }
    assert webui._build_source_url_for_row(row) == "https://www.ebi.ac.uk/biostudies/arrayexpress/studies/E-MTAB-12345"


def test_source_url_builder_supports_kegg() -> None:
    row = {
        "claim_id": "KEGG_hsa05014",
        "source_doi": "hsa05014",
    }
    assert webui._build_source_url_for_row(row) == "https://www.kegg.jp/entry/hsa05014"


def test_source_url_builder_supports_pride() -> None:
    row = {
        "claim_id": "PRIDE_PXD012345",
        "source_doi": "PXD012345",
    }
    assert webui._build_source_url_for_row(row) == "https://www.ebi.ac.uk/pride/archive/projects/PXD012345"


def test_source_url_builder_supports_metabolomics_workbench() -> None:
    row = {
        "claim_id": "METABOLOMICS_WORKBENCH_ST002001",
        "source_doi": "ST002001",
    }
    assert (
        webui._build_source_url_for_row(row)
        == "https://www.metabolomicsworkbench.org/data/show_study.php?STUDY_ID=ST002001"
    )


def test_source_url_builder_supports_chembl() -> None:
    row = {
        "claim_id": "CHEMBL_CHEMBL25",
        "source_doi": "CHEMBL25",
    }
    assert webui._build_source_url_for_row(row) == "https://www.ebi.ac.uk/chembl/compound_report_card/CHEMBL25/"


def test_source_url_builder_supports_open_targets() -> None:
    row = {
        "claim_id": "OPEN_TARGETS_ENSG00000157764",
        "source_doi": "ENSG00000157764",
    }
    assert webui._build_source_url_for_row(row) == "https://platform.opentargets.org/search?q=ENSG00000157764"


def test_source_url_builder_supports_fda_labels() -> None:
    row = {
        "claim_id": "FDA_LABELS_1234abcd",
        "source_doi": "1234abcd",
    }
    assert webui._build_source_url_for_row(row) == "https://open.fda.gov/apis/drug/label/"


def test_review_queue_routes_flags_decision_and_history(api_server: str) -> None:
    flags_code, flags_data = _request_json(
        api_server,
        "/api/review/flags",
        method="POST",
        payload={},
    )
    assert flags_code == 200
    assert int(flags_data["total"]) >= 1
    first_flag = flags_data["flags"][0]
    assert "claim_id" in first_flag
    claim_id = str(first_flag["claim_id"])

    decision_code, decision_data = _request_json(
        api_server,
        "/api/review/decision",
        method="POST",
        payload={
            "claim_id": claim_id,
            "decision": "approve",
            "reviewer": "reviewer_a",
            "notes": "Looks consistent",
        },
    )
    assert decision_code == 200
    assert bool(decision_data["ok"]) is True
    assert decision_data["claim_id"] == claim_id
    assert decision_data["decision"] == "approve"

    history_code, history_data = _request_json(
        api_server,
        "/api/review/decisions",
        method="POST",
        payload={"claim_id": claim_id, "limit": 10},
    )
    assert history_code == 200
    assert int(history_data["total"]) >= 1
    assert len(history_data["rows"]) >= 1
    latest = history_data["rows"][0]
    assert latest["claim_id"] == claim_id
    assert latest["decision"] == "approve"
    assert latest["reviewer"] == "reviewer_a"


def test_hypothesis_queue_route_respects_signoff_toggle_and_decisions(api_server: str) -> None:
    baseline_code, baseline_data = _request_json(
        api_server,
        "/api/hypothesis/queue",
        method="POST",
        payload={
            "limit": 10,
            "require_review_signoff": False,
            "enforce_causal_gate": False,
        },
    )
    assert baseline_code == 200
    assert int(baseline_data["total"]) >= 1

    gated_code, gated_data = _request_json(
        api_server,
        "/api/hypothesis/queue",
        method="POST",
        payload={
            "limit": 10,
            "require_review_signoff": True,
            "enforce_causal_gate": False,
        },
    )
    assert gated_code == 200
    assert int(gated_data["total"]) == 0
    assert "drug-a" in gated_data["removed_entities"]

    approve_code, approve_data = _request_json(
        api_server,
        "/api/review/decision",
        method="POST",
        payload={
            "claim_id": "C1",
            "decision": "approve",
            "reviewer": "reviewer_a",
            "notes": "approved for promotion",
        },
    )
    assert approve_code == 200
    assert bool(approve_data["ok"]) is True

    post_approval_code, post_approval_data = _request_json(
        api_server,
        "/api/hypothesis/queue",
        method="POST",
        payload={
            "limit": 10,
            "require_review_signoff": True,
            "enforce_causal_gate": False,
        },
    )
    assert post_approval_code == 200
    assert int(post_approval_data["total"]) >= 1
    assert "drug-a" not in post_approval_data["removed_entities"]


def test_session_save_list_and_get_routes(api_server: str) -> None:
    save_code, save_data = _request_json(
        api_server,
        "/api/session/save",
        method="POST",
        payload={
            "session_id": "sess_test_1",
            "title": "Session title",
            "question": "What changed?",
            "messages": [{"role": "user", "content": "Q"}],
            "report": {"answer": "A"},
            "filters": {"min_reliability": 0.6},
            "evidence_claim_ids": ["C1", "C3"],
        },
    )
    assert save_code == 200
    assert save_data["session_id"] == "sess_test_1"

    list_code, list_data = _request_json(api_server, "/api/session/list?limit=1&offset=0")
    assert list_code == 200
    assert any(s["session_id"] == "sess_test_1" for s in list_data["sessions"])
    assert int(list_data["limit"]) == 1
    assert int(list_data["offset"]) == 0
    assert "has_more" in list_data

    get_code, get_data = _request_json(api_server, "/api/session/sess_test_1")
    assert get_code == 200
    assert get_data["session_id"] == "sess_test_1"
    assert get_data["report"]["answer"] == "A"


def test_session_save_requires_session_id(api_server: str) -> None:
    code, data = _request_json(
        api_server,
        "/api/session/save",
        method="POST",
        payload={"messages": []},
    )
    assert code == 400
    assert "session_id is required" in str(data["error"])


def test_export_summary_and_synthesis_routes(api_server: str) -> None:
    synthesis_code, synthesis_data = _request_json(
        api_server,
        "/api/synthesis",
        method="POST",
        payload={"filters": {}},
    )
    assert synthesis_code == 200
    assert int(synthesis_data["evidence_count"]) == 3
    assert "composition" in synthesis_data
    assert "hypothesis_queue" in synthesis_data["composition"]
    assert "debate_report" in synthesis_data["composition"]

    export_code, export_data = _request_json(
        api_server,
        "/api/export/summary",
        method="POST",
        payload={
            "report": {
                "answer": "Test answer",
                "generated_seconds": 0.123,
                "synthesis": {
                    "direct_answer": "Direct",
                    "supporting_claim_ids": ["C1", "C2"],
                    "contradictions_summary": "C1 vs C3",
                    "next_validation_step": "Run trial",
                },
            }
        },
    )
    assert export_code == 200
    assert export_data["json_filename"] == "synthesis_report.json"
    assert export_data["markdown_filename"] == "synthesis_report.md"
    assert "## Direct Answer" in str(export_data["markdown_content"])


def test_chat_payload_includes_transparency_and_guardrail_metadata(api_server: str) -> None:
    chat_code, chat_data = _request_json(
        api_server,
        "/api/chat",
        method="POST",
        payload={
            "messages": [{"role": "user", "content": "Provide a concise synthesis."}],
            "filters": {},
            "context_limit": 5,
            "temperature": 0.1,
            "timeout_seconds": 10,
        },
    )
    assert chat_code == 200
    assert chat_data["response_mode"] == "sync"
    assert isinstance(chat_data["guardrail_flags"], list)
    assert isinstance(chat_data["evidence_rows"], list)
    assert "telemetry" in chat_data
    assert "guardrail_flags" in chat_data["telemetry"]


def test_recent_telemetry_endpoint_returns_recent_traces(api_server: str) -> None:
    _request_json(
        api_server,
        "/api/chat",
        method="POST",
        payload={
            "messages": [{"role": "user", "content": "Generate a brief answer."}],
            "filters": {},
            "context_limit": 5,
            "temperature": 0.1,
            "timeout_seconds": 10,
        },
    )

    code, data = _request_json(api_server, "/api/telemetry/recent?limit=5")
    assert code == 200
    assert int(data["limit"]) == 5
    assert int(data["total"]) >= 1
    assert isinstance(data["traces"], list)
    assert "trace_id" in data["traces"][0]
    assert "phase_seconds" in data["traces"][0]


def test_chat_stream_final_event_includes_transparency_fields(api_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(webui, "generate_with_ollama_stream", lambda **_: iter(["Chunk one. ", "Chunk two."]))

    status, events = _request_ndjson(
        api_server,
        "/api/chat/stream",
        {
            "messages": [{"role": "user", "content": "Stream a concise answer."}],
            "filters": {},
            "context_limit": 5,
            "temperature": 0.1,
            "timeout_seconds": 10,
        },
    )

    assert status == 200
    assert any(event.get("type") == "chunk" for event in events)
    final_event = next(event for event in events if event.get("type") == "final")
    assert final_event["response_mode"] == "stream"
    assert isinstance(final_event["guardrail_flags"], list)
    assert isinstance(final_event["evidence_rows"], list)
    assert "telemetry" in final_event


def test_chat_stream_emits_error_event_when_llm_fails(api_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(**_: object):
        raise LocalLLMError("timed out")

    monkeypatch.setattr(webui, "generate_with_ollama_stream", _raise_timeout)

    status, events = _request_ndjson(
        api_server,
        "/api/chat/stream",
        {
            "messages": [{"role": "user", "content": "Stream a concise answer."}],
            "filters": {},
            "context_limit": 5,
            "temperature": 0.1,
            "timeout_seconds": 10,
        },
    )

    assert status == 200
    error_event = next(event for event in events if event.get("type") == "error")
    assert "timed out" in str(error_event.get("error", ""))
    assert not any(event.get("type") == "final" for event in events)


def test_chat_route_returns_llm_timeout_error(api_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(**_: object):
        raise LocalLLMError("timed out")

    monkeypatch.setattr(webui, "generate_with_ollama", _raise_timeout)

    code, data = _request_json(
        api_server,
        "/api/chat",
        method="POST",
        payload={
            "messages": [{"role": "user", "content": "What is ALS?"}],
            "filters": {},
            "context_limit": 5,
            "temperature": 0.1,
            "timeout_seconds": 10,
        },
    )

    assert code == 502
    assert "timed out" in str(data.get("error", ""))


def test_magic_link_auth_and_user_scoped_sessions(api_server_auth: str) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "analyst@example.com"},
    )
    assert req_code == 200
    assert bool(req_data["ok"]) is True
    magic_link = str(req_data.get("magic_link") or "")
    assert "magic_token=" in magic_link
    token = magic_link.split("magic_token=", 1)[1].split("&", 1)[0]

    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    assert bool(verify_data["authenticated"]) is True
    assert str(verify_data["user"]["email"]) == "analyst@example.com"
    cookie_header = str(verify_headers.get("Set-Cookie") or "")
    assert "als_session=" in cookie_header
    cookie_pair = cookie_header.split(";", 1)[0]
    csrf_token = str(verify_data.get("csrf_token") or "")
    assert len(csrf_token) >= 16

    save_code, _ = _request_json(
        api_server_auth,
        "/api/session/save",
        method="POST",
        headers={"Cookie": cookie_pair, "X-CSRF-Token": csrf_token},
        payload={
            "session_id": "sess_user_a",
            "title": "A",
            "question": "Q",
            "messages": [{"role": "user", "content": "Q"}],
            "report": {"answer": "A"},
            "filters": {},
            "evidence_claim_ids": ["C1"],
        },
    )
    assert save_code == 200

    list_code, list_data = _request_json(
        api_server_auth,
        "/api/session/list?limit=10&offset=0",
        headers={"Cookie": cookie_pair},
    )
    assert list_code == 200
    assert any(s["session_id"] == "sess_user_a" for s in list_data["sessions"])

    req_b_code, req_b_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "other@example.com"},
    )
    assert req_b_code == 200
    magic_link_b = str(req_b_data.get("magic_link") or "")
    token_b = magic_link_b.split("magic_token=", 1)[1].split("&", 1)[0]
    _, _, headers_b = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token_b},
    )
    cookie_pair_b = str(headers_b.get("Set-Cookie") or "").split(";", 1)[0]

    list_b_code, list_b_data = _request_json(
        api_server_auth,
        "/api/session/list?limit=10&offset=0",
        headers={"Cookie": cookie_pair_b},
    )
    assert list_b_code == 200
    assert not any(s["session_id"] == "sess_user_a" for s in list_b_data["sessions"])


def test_unauthenticated_root_serves_landing(api_server_auth: str) -> None:
    code, _, body = _request_no_redirect(api_server_auth, "/")
    assert code == 200
    assert 'id="app"' in body
    assert "/app-assets/" in body


def test_unauthenticated_app_assets_serve_javascript(api_server_auth: str) -> None:
    _, _, body = _request_no_redirect(api_server_auth, "/")
    match = re.search(r'src="(/app-assets/[^"]+\.js)"', body)
    if match is None:
        pytest.skip("frontend build not present")
    asset_path = match.group(1)
    code, headers, asset_body = _request_no_redirect(api_server_auth, asset_path)
    assert code == 200
    assert "javascript" in str(headers.get("Content-Type") or "").lower()
    assert asset_body.startswith("(") or "function" in asset_body or "const" in asset_body


def test_unauthenticated_brand_logo_serves_svg(api_server_auth: str) -> None:
    code, headers, body = _request_no_redirect(api_server_auth, "/assets/mtvl-ai-logo.svg")
    assert code == 200
    assert "svg" in str(headers.get("Content-Type") or "").lower()
    assert "<svg" in body.lower()


def test_unauthenticated_app_redirects_to_login(api_server_auth: str) -> None:
    code, headers, _ = _request_no_redirect(api_server_auth, "/app")
    assert code == 302
    location = str(headers.get("Location") or "")
    assert location.startswith("/login")
    assert "next=%2Fapp" in location or "next=/app" in location


def test_authenticated_login_route_redirects_to_app(api_server_auth: str) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "redirect@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, _, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie_pair = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]

    req = urllib.request.Request(f"{api_server_auth}/login", method="GET", headers={"Cookie": cookie_pair})
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(req) as resp:
            status = resp.status
            headers = dict(resp.headers.items())
    except urllib.error.HTTPError as exc:
        status = exc.code
        headers = dict(exc.headers.items())
    assert status == 302
    assert str(headers.get("Location") or "") == "/app"


def test_authenticated_root_serves_landing_with_app_cta(api_server_auth: str) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "root-landing@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, _, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie_pair = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]

    req = urllib.request.Request(f"{api_server_auth}/", method="GET", headers={"Cookie": cookie_pair})
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(req) as resp:
            code = resp.status
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        code = exc.code
        body = exc.read().decode("utf-8")
    assert code == 200
    assert 'id="app"' in body
    assert "/app-assets/" in body


def test_unauthenticated_unknown_page_redirects_to_login(api_server_auth: str) -> None:
    code, headers, _ = _request_no_redirect(api_server_auth, "/workspace")
    assert code == 302
    location = str(headers.get("Location") or "")
    assert location.startswith("/login")
    assert "next=" in location


def test_unauthenticated_magic_link_root_redirects_with_magic_token(api_server_auth: str) -> None:
    code, headers, _ = _request_no_redirect(api_server_auth, "/?magic_token=test-token-123")
    assert code == 302
    location = str(headers.get("Location") or "")
    assert location.startswith("/login")
    assert "magic_token=test-token-123" in location


def test_authenticated_unknown_page_redirects_to_app(api_server_auth: str) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "unknown-route@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, _, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie_pair = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]

    req = urllib.request.Request(f"{api_server_auth}/workspace", method="GET", headers={"Cookie": cookie_pair})
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(req) as resp:
            status = resp.status
            headers = dict(resp.headers.items())
    except urllib.error.HTTPError as exc:
        status = exc.code
        headers = dict(exc.headers.items())
    assert status == 302
    assert str(headers.get("Location") or "") == "/app"


def test_magic_link_cannot_be_replayed(api_server_auth: str) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "replay@example.com"},
    )
    assert req_code == 200
    magic_link = str(req_data.get("magic_link") or "")
    token = magic_link.split("magic_token=", 1)[1].split("&", 1)[0]

    first_verify_code, first_verify_data = _request_json(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert first_verify_code == 200
    assert bool(first_verify_data.get("authenticated")) is True

    replay_code, replay_data = _request_json(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert replay_code == 400
    assert "already used" in str(replay_data.get("error", "")).lower()


def test_magic_link_request_rate_limit(api_server_auth: str) -> None:
    email = "limited@example.com"
    for _ in range(3):
        code, data = _request_json(
            api_server_auth,
            "/api/auth/request-link",
            method="POST",
            payload={"email": email},
        )
        assert code == 200
        assert bool(data.get("ok")) is True

    limited_code, limited_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": email},
    )
    assert limited_code == 429
    assert "too many" in str(limited_data.get("error", "")).lower()


def test_protected_post_requires_csrf_token(api_server_auth: str) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "csrf@example.com"},
    )
    assert req_code == 200
    magic_link = str(req_data.get("magic_link") or "")
    token = magic_link.split("magic_token=", 1)[1].split("&", 1)[0]

    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie_pair = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf_token = str(verify_data.get("csrf_token") or "")

    denied_code, denied_data = _request_json(
        api_server_auth,
        "/api/session/save",
        method="POST",
        headers={"Cookie": cookie_pair},
        payload={
            "session_id": "sess_csrf_missing",
            "title": "CSRF",
            "question": "Q",
            "messages": [{"role": "user", "content": "Q"}],
            "report": {"answer": "A"},
            "filters": {},
            "evidence_claim_ids": ["C1"],
        },
    )
    assert denied_code == 403
    assert "csrf" in str(denied_data.get("error", "")).lower()

    ok_code, _ = _request_json(
        api_server_auth,
        "/api/session/save",
        method="POST",
        headers={"Cookie": cookie_pair, "X-CSRF-Token": csrf_token},
        payload={
            "session_id": "sess_csrf_ok",
            "title": "CSRF",
            "question": "Q",
            "messages": [{"role": "user", "content": "Q"}],
            "report": {"answer": "A"},
            "filters": {},
            "evidence_claim_ids": ["C1"],
        },
    )
    assert ok_code == 200


def test_magic_link_request_ip_rate_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "als_auth_ip.sqlite"
    _seed_evidence(db_path)

    monkeypatch.setenv("ALS_DB_PATH", str(db_path))
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("ALS_AUTH_ENABLED", "1")
    monkeypatch.setenv("ALS_MAGIC_LINK_DEV_MODE", "1")
    monkeypatch.setenv("ALS_MAGIC_LINK_RATE_LIMIT_COUNT", "50")
    monkeypatch.setenv("ALS_MAGIC_LINK_RATE_LIMIT_IP_COUNT", "2")
    monkeypatch.setattr(webui, "generate_with_ollama", lambda **_: "stubbed answer")

    server = ThreadingHTTPServer(("127.0.0.1", 0), ChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    try:
        code_a, _ = _request_json(
            base_url,
            "/api/auth/request-link",
            method="POST",
            payload={"email": "ip1@example.com"},
        )
        code_b, _ = _request_json(
            base_url,
            "/api/auth/request-link",
            method="POST",
            payload={"email": "ip2@example.com"},
        )
        limited_code, limited_data = _request_json(
            base_url,
            "/api/auth/request-link",
            method="POST",
            payload={"email": "ip3@example.com"},
        )
        assert code_a == 200
        assert code_b == 200
        assert limited_code == 429
        assert "too many" in str(limited_data.get("error", "")).lower()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_auth_status_rotates_session_near_expiry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "als_auth_rotate.sqlite"
    _seed_evidence(db_path)

    monkeypatch.setenv("ALS_DB_PATH", str(db_path))
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("ALS_AUTH_ENABLED", "1")
    monkeypatch.setenv("ALS_MAGIC_LINK_DEV_MODE", "1")
    monkeypatch.setenv("ALS_CSRF_SECRET", "rotate-secret")
    monkeypatch.setenv("ALS_SESSION_TTL_SECONDS", "120")
    monkeypatch.setenv("ALS_SESSION_RENEW_WINDOW_SECONDS", "900")
    monkeypatch.setattr(webui, "generate_with_ollama", lambda **_: "stubbed answer")

    server = ThreadingHTTPServer(("127.0.0.1", 0), ChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    try:
        req_code, req_data = _request_json(
            base_url,
            "/api/auth/request-link",
            method="POST",
            payload={"email": "rotate@example.com"},
        )
        assert req_code == 200
        magic_link = str(req_data.get("magic_link") or "")
        token = magic_link.split("magic_token=", 1)[1].split("&", 1)[0]

        verify_code, verify_data, verify_headers = _request_json_with_headers(
            base_url,
            "/api/auth/verify-link",
            method="POST",
            payload={"token": token},
        )
        assert verify_code == 200
        first_cookie = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
        first_csrf = str(verify_data.get("csrf_token") or "")
        assert "als_session=" in first_cookie
        assert first_csrf

        status_code, status_data, status_headers = _request_json_with_headers(
            base_url,
            "/api/auth/status",
            headers={"Cookie": first_cookie},
        )
        assert status_code == 200
        rotated_cookie = str(status_headers.get("Set-Cookie") or "").split(";", 1)[0]
        assert rotated_cookie.startswith("als_session=")
        assert rotated_cookie != first_cookie
        rotated_csrf = str(status_data.get("csrf_token") or "")
        assert rotated_csrf

        save_code, _ = _request_json(
            base_url,
            "/api/session/save",
            method="POST",
            headers={"Cookie": rotated_cookie, "X-CSRF-Token": rotated_csrf},
            payload={
                "session_id": "sess_rotated",
                "title": "rotated",
                "question": "Q",
                "messages": [{"role": "user", "content": "Q"}],
                "report": {"answer": "A"},
                "filters": {},
                "evidence_claim_ids": ["C1"],
            },
        )
        assert save_code == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_auth_audit_timeline_is_user_scoped(api_server_auth: str) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "audit-a@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie_a = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf_a = str(verify_data.get("csrf_token") or "")

    save_code, _ = _request_json(
        api_server_auth,
        "/api/session/save",
        method="POST",
        headers={"Cookie": cookie_a, "X-CSRF-Token": csrf_a},
        payload={
            "session_id": "sess_audit_a",
            "title": "audit",
            "question": "Q",
            "messages": [{"role": "user", "content": "Q"}],
            "report": {"answer": "A"},
            "filters": {},
            "evidence_claim_ids": ["C1"],
        },
    )
    assert save_code == 200

    req_b_code, req_b_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "audit-b@example.com"},
    )
    assert req_b_code == 200
    token_b = str(req_b_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_b_code, verify_b_data, verify_b_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token_b},
    )
    assert verify_b_code == 200
    cookie_b = str(verify_b_headers.get("Set-Cookie") or "").split(";", 1)[0]

    audit_a_code, audit_a_data = _request_json(
        api_server_auth,
        "/api/auth/audit?limit=50",
        headers={"Cookie": cookie_a},
    )
    assert audit_a_code == 200
    assert int(audit_a_data["total"]) >= 2
    assert any(str(row.get("activity_type")) == "session_save" for row in audit_a_data["rows"])

    audit_b_code, audit_b_data = _request_json(
        api_server_auth,
        "/api/auth/audit?limit=50",
        headers={"Cookie": cookie_b},
    )
    assert audit_b_code == 200
    assert not any(str(row.get("activity_type")) == "session_save" for row in audit_b_data["rows"])


def test_auth_logout_revokes_session_and_expires_cookie(api_server_auth: str) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "logout@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]

    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie_pair = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf_token = str(verify_data.get("csrf_token") or "")

    logout_code, logout_data, logout_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/logout",
        method="POST",
        headers={"Cookie": cookie_pair, "X-CSRF-Token": csrf_token},
        payload={},
    )
    assert logout_code == 200
    assert bool(logout_data.get("ok")) is True
    expired_cookie = str(logout_headers.get("Set-Cookie") or "")
    assert "Max-Age=0" in expired_cookie

    status_code, status_data = _request_json(
        api_server_auth,
        "/api/auth/status",
        headers={"Cookie": cookie_pair},
    )
    assert status_code == 200
    assert bool(status_data.get("authenticated")) is False


def test_auth_status_includes_profile_summary(api_server_auth: str) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "profile-status@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie_pair = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]

    status_code, status_data = _request_json(
        api_server_auth,
        "/api/auth/status",
        headers={"Cookie": cookie_pair},
    )
    assert status_code == 200
    profile = status_data.get("profile")
    assert isinstance(profile, dict)
    assert "initials" in profile
    assert "display_name" in profile


def test_auth_profile_update_and_avatar_round_trip(api_server_auth: str) -> None:
    import base64

    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "profile-edit@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie_pair = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf_token = str(verify_data.get("csrf_token") or "")
    avatar_bytes = b"fake-image-bytes"
    update_code, update_data = _request_json(
        api_server_auth,
        "/api/auth/profile",
        method="PUT",
        headers={"Cookie": cookie_pair, "X-CSRF-Token": csrf_token},
        payload={
            "display_name": "Profile Editor",
            "title": "Investigator",
            "institution": "ALS Lab",
            "avatar_base64": base64.b64encode(avatar_bytes).decode("ascii"),
            "avatar_mime_type": "image/png",
        },
    )
    assert update_code == 200
    profile = update_data.get("profile")
    assert isinstance(profile, dict)
    assert profile.get("display_name") == "Profile Editor"
    assert profile.get("has_avatar") is True
    assert profile.get("initials") == "PE"

    get_code, get_data = _request_json(
        api_server_auth,
        "/api/auth/profile",
        headers={"Cookie": cookie_pair},
    )
    assert get_code == 200
    assert get_data["profile"]["display_name"] == "Profile Editor"

    avatar_req = urllib.request.Request(
        f"{api_server_auth}/api/auth/profile/avatar",
        method="GET",
        headers={"Cookie": cookie_pair},
    )
    with urllib.request.urlopen(avatar_req) as resp:
        assert resp.status == 200
        assert resp.read() == avatar_bytes


def test_session_save_rejects_cross_user_session_takeover(api_server_auth: str) -> None:
    req_a_code, req_a_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "owner@example.com"},
    )
    assert req_a_code == 200
    token_a = str(req_a_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_a_code, verify_a_data, verify_a_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token_a},
    )
    assert verify_a_code == 200
    cookie_a = str(verify_a_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf_a = str(verify_a_data.get("csrf_token") or "")

    save_a_code, _ = _request_json(
        api_server_auth,
        "/api/session/save",
        method="POST",
        headers={"Cookie": cookie_a, "X-CSRF-Token": csrf_a},
        payload={
            "session_id": "sess_shared",
            "title": "Owner session",
            "question": "Q",
            "messages": [{"role": "user", "content": "Q"}],
            "report": {"answer": "A"},
            "filters": {},
            "evidence_claim_ids": ["C1"],
        },
    )
    assert save_a_code == 200

    req_b_code, req_b_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "attacker@example.com"},
    )
    assert req_b_code == 200
    token_b = str(req_b_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_b_code, verify_b_data, verify_b_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token_b},
    )
    assert verify_b_code == 200
    cookie_b = str(verify_b_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf_b = str(verify_b_data.get("csrf_token") or "")

    save_b_code, save_b_data = _request_json(
        api_server_auth,
        "/api/session/save",
        method="POST",
        headers={"Cookie": cookie_b, "X-CSRF-Token": csrf_b},
        payload={
            "session_id": "sess_shared",
            "title": "Hijacked",
            "question": "Q2",
            "messages": [{"role": "user", "content": "Q2"}],
            "report": {"answer": "B"},
            "filters": {},
            "evidence_claim_ids": ["C2"],
        },
    )
    assert save_b_code == 400
    assert "another user" in str(save_b_data.get("error") or "").lower()

    list_a_code, list_a_data = _request_json(
        api_server_auth,
        "/api/session/list?limit=20&offset=0",
        headers={"Cookie": cookie_a},
    )
    assert list_a_code == 200
    owner_row = next(row for row in list_a_data.get("sessions", []) if str(row.get("session_id")) == "sess_shared")
    assert str(owner_row.get("title")) == "Owner session"


def test_investigation_runs_lifecycle_replay_and_user_scope(api_server_auth: str) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "runs-a@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie_a = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf_a = str(verify_data.get("csrf_token") or "")

    start_code, start_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/start",
        method="POST",
        headers={"Cookie": cookie_a, "X-CSRF-Token": csrf_a},
        payload={
            "objective": "Track contradictions for drug-a",
            "filters": {"entities": ["drug-a"]},
            "require_review_signoff": False,
        },
    )
    assert start_code == 200
    run_id = str(start_data.get("run_id") or "")
    assert run_id
    assert str(start_data.get("status") or "") == "completed"
    assert isinstance(start_data.get("report"), dict)
    assert isinstance(start_data.get("quality_gate"), dict)

    list_code, list_data = _request_json(
        api_server_auth,
        "/api/investigation/runs?limit=20",
        headers={"Cookie": cookie_a},
    )
    assert list_code == 200
    assert any(str(row.get("run_id")) == run_id for row in list_data.get("rows", []))

    detail_code, detail_data = _request_json(
        api_server_auth,
        f"/api/investigation/runs/{run_id}",
        headers={"Cookie": cookie_a},
    )
    assert detail_code == 200
    assert str(detail_data.get("run_id") or "") == run_id

    replay_code, replay_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/replay",
        method="POST",
        headers={"Cookie": cookie_a, "X-CSRF-Token": csrf_a},
        payload={"source_run_id": run_id},
    )
    assert replay_code == 200
    replay_run_id = str(replay_data.get("run_id") or "")
    assert replay_run_id
    assert replay_run_id != run_id
    assert str(replay_data.get("replay_of_run_id") or "") == run_id
    assert isinstance(replay_data.get("replay_diff"), dict)
    replay_diff = replay_data.get("replay_diff") if isinstance(replay_data.get("replay_diff"), dict) else {}
    assert isinstance(replay_diff.get("citation_overlap"), dict)
    assert isinstance(replay_diff.get("contradiction_delta"), dict)
    assert isinstance(replay_diff.get("changed_checks"), list)

    req_b_code, req_b_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "runs-b@example.com"},
    )
    assert req_b_code == 200
    token_b = str(req_b_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_b_code, _, verify_b_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token_b},
    )
    assert verify_b_code == 200
    cookie_b = str(verify_b_headers.get("Set-Cookie") or "").split(";", 1)[0]

    list_b_code, list_b_data = _request_json(
        api_server_auth,
        "/api/investigation/runs?limit=20",
        headers={"Cookie": cookie_b},
    )
    assert list_b_code == 200
    assert not any(str(row.get("run_id")) in {run_id, replay_run_id} for row in list_b_data.get("rows", []))


def test_investigation_run_gate_respects_env_thresholds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "als_gate_thresholds.sqlite"
    _seed_evidence(db_path)

    monkeypatch.setenv("ALS_DB_PATH", str(db_path))
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "test-model")
    monkeypatch.setenv("ALS_AUTH_ENABLED", "1")
    monkeypatch.setenv("ALS_MAGIC_LINK_DEV_MODE", "1")
    monkeypatch.setenv("ALS_CSRF_SECRET", "gate-threshold-secret")
    monkeypatch.setenv("ALS_RUN_GATE_FRESHNESS_WINDOW_YEARS", "1")
    monkeypatch.setenv("ALS_RUN_GATE_REQUIRE_CITATION_INTEGRITY", "1")
    monkeypatch.setattr(webui, "generate_with_ollama", lambda **_: "stubbed answer")

    server = ThreadingHTTPServer(("127.0.0.1", 0), ChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    try:
        req_code, req_data = _request_json(
            base_url,
            "/api/auth/request-link",
            method="POST",
            payload={"email": "gate@example.com"},
        )
        assert req_code == 200
        token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]

        verify_code, verify_data, verify_headers = _request_json_with_headers(
            base_url,
            "/api/auth/verify-link",
            method="POST",
            payload={"token": token},
        )
        assert verify_code == 200
        cookie = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
        csrf = str(verify_data.get("csrf_token") or "")

        run_code, run_data = _request_json(
            base_url,
            "/api/investigation/runs/start",
            method="POST",
            headers={"Cookie": cookie, "X-CSRF-Token": csrf},
            payload={
                "objective": "Gate threshold verification",
                "filters": {"entities": ["drug-a"]},
                "require_review_signoff": False,
            },
        )
        assert run_code == 200
        gate = run_data.get("quality_gate") if isinstance(run_data.get("quality_gate"), dict) else {}
        checks = gate.get("checks") if isinstance(gate.get("checks"), dict) else {}
        freshness = checks.get("freshness") if isinstance(checks.get("freshness"), dict) else {}
        assert freshness.get("window_years") == 1
        assert freshness.get("passed") is False
        assert gate.get("passed") is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_investigation_run_start_idempotency_key_returns_existing_run(api_server_auth: str) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "idempotency@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf = str(verify_data.get("csrf_token") or "")

    payload = {
        "objective": "Idempotent start check",
        "filters": {"entities": ["drug-a"]},
        "require_review_signoff": False,
        "idempotency_key": "start-key-1",
        "max_attempts": 2,
    }
    first_code, first_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/start",
        method="POST",
        headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        payload=payload,
    )
    assert first_code == 200
    run_id_a = str(first_data.get("run_id") or "")
    assert run_id_a

    second_code, second_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/start",
        method="POST",
        headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        payload=payload,
    )
    assert second_code == 200
    run_id_b = str(second_data.get("run_id") or "")
    assert run_id_b == run_id_a


def test_investigation_run_queue_and_execute_due_runs(api_server_auth: str) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "queue-exec@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf = str(verify_data.get("csrf_token") or "")

    queue_code, queue_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/queue",
        method="POST",
        headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        payload={
            "objective": "Queued run objective",
            "filters": {"entities": ["drug-a"]},
            "require_review_signoff": False,
            "idempotency_key": "queue-key-1",
            "delay_seconds": 0,
            "max_attempts": 3,
        },
    )
    assert queue_code == 200
    run_id = str(queue_data.get("run_id") or "")
    assert run_id
    assert str(queue_data.get("status") or "") == "queued"
    assert int(queue_data.get("attempt_count", -1)) == 0

    exec_code, exec_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/queued/execute?limit=5",
        headers={"Cookie": cookie},
    )
    assert exec_code == 200
    rows = exec_data.get("rows") if isinstance(exec_data.get("rows"), list) else []
    assert any(str(row.get("run_id") or "") == run_id for row in rows)

    detail_code, detail_data = _request_json(
        api_server_auth,
        f"/api/investigation/runs/{run_id}",
        headers={"Cookie": cookie},
    )
    assert detail_code == 200
    assert str(detail_data.get("status") or "") == "completed"
    assert int(detail_data.get("attempt_count") or 0) >= 1


def test_automation_templates_dashboard_and_experiments(api_server_auth: str) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "automation-a@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf = str(verify_data.get("csrf_token") or "")

    save_code, save_data = _request_json(
        api_server_auth,
        "/api/investigation/templates/save",
        method="POST",
        headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        payload={
            "name": "Drug A Daily Watch",
            "objective": "Track drug-a contradiction profile",
            "filters": {"entities": ["drug-a"]},
            "require_review_signoff": False,
        },
    )
    assert save_code == 200
    template_id = str(save_data.get("template_id") or "")
    assert template_id

    list_templates_code, list_templates_data = _request_json(
        api_server_auth,
        "/api/investigation/templates?limit=20",
        headers={"Cookie": cookie},
    )
    assert list_templates_code == 200
    template_rows = list_templates_data.get("rows") if isinstance(list_templates_data.get("rows"), list) else []
    assert any(str(row.get("template_id") or "") == template_id for row in template_rows)

    run_from_template_code, run_from_template_data = _request_json(
        api_server_auth,
        "/api/investigation/templates/run",
        method="POST",
        headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        payload={"template_id": template_id, "queue": False},
    )
    assert run_from_template_code == 200
    run_obj = run_from_template_data.get("run") if isinstance(run_from_template_data.get("run"), dict) else {}
    assert str(run_obj.get("status") or "") == "completed"

    dashboard_code, dashboard_data = _request_json(
        api_server_auth,
        "/api/automation/dashboard?days=30",
        headers={"Cookie": cookie},
    )
    assert dashboard_code == 200
    assert int(dashboard_data.get("total_runs") or 0) >= 1
    assert isinstance(dashboard_data.get("status_counts"), dict)
    assert "replay_stability_rate" in dashboard_data
    assert "median_time_to_report_seconds" in dashboard_data
    assert "citation_integrity_pass_rate" in dashboard_data
    assert "evidence_freshness_compliance" in dashboard_data
    review_queue = dashboard_data.get("review_queue") if isinstance(dashboard_data.get("review_queue"), dict) else {}
    assert "pending_total" in review_queue
    assert isinstance(review_queue.get("by_status"), dict)
    assert isinstance(review_queue.get("by_risk"), dict)
    assert isinstance(review_queue.get("top_failed_checks"), list)

    exp_code, exp_data = _request_json(
        api_server_auth,
        "/api/automation/experiments/run",
        method="POST",
        headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        payload={
            "name": "Signoff strategy",
            "objective": "Compare signoff gating strategy",
            "filters": {"entities": ["drug-a"]},
            "variant_a": {"name": "strict", "require_review_signoff": True},
            "variant_b": {"name": "open", "require_review_signoff": False},
        },
    )
    assert exp_code == 200
    assert str(exp_data.get("winner_variant") or "") in {"a", "b"}

    exp_list_code, exp_list_data = _request_json(
        api_server_auth,
        "/api/automation/experiments?limit=20",
        headers={"Cookie": cookie},
    )
    assert exp_list_code == 200
    exp_rows = exp_list_data.get("rows") if isinstance(exp_list_data.get("rows"), list) else []
    assert len(exp_rows) >= 1


def test_automation_approvals_rollback_and_export(api_server_auth: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "automation-b@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf = str(verify_data.get("csrf_token") or "")

    start_code, start_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/start",
        method="POST",
        headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        payload={
            "objective": "Approval and rollback run",
            "filters": {"entities": ["drug-a"]},
            "require_review_signoff": False,
        },
    )
    assert start_code == 200
    source_run_id = str(start_data.get("run_id") or "")
    assert source_run_id

    approve_code, approve_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/approve",
        method="POST",
        headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        payload={"run_id": source_run_id, "decision": "approved", "reviewer": "qa@local"},
    )
    assert approve_code == 200
    assert str(approve_data.get("approval_status") or "") == "approved"

    rollback_code, rollback_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/rollback",
        method="POST",
        headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        payload={"run_id": source_run_id, "queue": True, "delay_seconds": 0, "reason": "stability check"},
    )
    assert rollback_code == 200
    rollback_run = rollback_data.get("rollback_run") if isinstance(rollback_data.get("rollback_run"), dict) else {}
    rollback_run_id = str(rollback_run.get("run_id") or "")
    assert rollback_run_id

    exec_code, _ = _request_json(
        api_server_auth,
        "/api/investigation/runs/queued/execute?limit=10",
        headers={"Cookie": cookie},
    )
    assert exec_code == 200

    rollback_detail_code, rollback_detail_data = _request_json(
        api_server_auth,
        f"/api/investigation/runs/{rollback_run_id}",
        headers={"Cookie": cookie},
    )
    assert rollback_detail_code == 200
    assert str(rollback_detail_data.get("status") or "") in {"completed", "queued", "running"}

    export_dir = tmp_path / "auto-exports"
    monkeypatch.setenv("ALS_AUTOMATION_EXPORT_DIR", str(export_dir))
    export_code, export_data = _request_json(
        api_server_auth,
        "/api/export/automated",
        method="POST",
        headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        payload={"run_id": source_run_id, "channel": "markdown_file"},
    )
    assert export_code == 200
    assert str(export_data.get("status") or "") == "delivered"
    result_obj = export_data.get("result") if isinstance(export_data.get("result"), dict) else {}
    assert str(result_obj.get("file_path") or "").endswith(".md")

    exports_code, exports_data = _request_json(
        api_server_auth,
        "/api/automation/exports?limit=20",
        headers={"Cookie": cookie},
    )
    assert exports_code == 200
    rows = exports_data.get("rows") if isinstance(exports_data.get("rows"), list) else []
    assert any(str(row.get("run_id") or "") == source_run_id for row in rows)


def test_automation_worker_tick_and_freshness_alarms(api_server_auth: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALS_AUTOMATION_WORKER_TOKEN", "worker-secret")

    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "automation-c@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf = str(verify_data.get("csrf_token") or "")

    queue_code, queue_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/queue",
        method="POST",
        headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        payload={
            "objective": "Worker queue route",
            "filters": {"entities": ["drug-a"]},
            "require_review_signoff": False,
            "delay_seconds": 0,
            "max_attempts": 2,
        },
    )
    assert queue_code == 200
    run_id = str(queue_data.get("run_id") or "")
    assert run_id

    worker_code, worker_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/worker/tick?token=worker-secret&limit=10",
    )
    assert worker_code == 200
    assert int(worker_data.get("claimed") or 0) >= 1

    detail_code, detail_data = _request_json(
        api_server_auth,
        f"/api/investigation/runs/{run_id}",
        headers={"Cookie": cookie},
    )
    assert detail_code == 200
    assert str(detail_data.get("status") or "") in {"completed", "queued", "running"}

    db_path = Path(str(os.getenv("ALS_DB_PATH") or ""))
    store = EvidenceStore(db_path)
    store.update_sync_state(
        source_name="pubmed",
        run_id=1,
        status="error",
        sync_timestamp="2020-01-01T00:00:00+00:00",
    )

    alarms_code, alarms_data = _request_json(
        api_server_auth,
        "/api/automation/freshness/alarms?stale_after_hours=1&failure_threshold=1",
        headers={"Cookie": cookie},
    )
    assert alarms_code == 200
    alarms_rows = alarms_data.get("rows") if isinstance(alarms_data.get("rows"), list) else []
    assert any(str(row.get("source_name") or "") == "pubmed" for row in alarms_rows)


def test_automation_handoff_sets_pending_approval_when_gate_fails(
    api_server_auth: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALS_AUTOMATION_HANDOFF_ON_GATE_FAIL", "1")
    monkeypatch.setenv("ALS_RUN_GATE_FRESHNESS_WINDOW_YEARS", "1")

    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "handoff@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf = str(verify_data.get("csrf_token") or "")

    start_code, start_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/start",
        method="POST",
        headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        payload={
            "objective": "Handoff gate fail run",
            "filters": {"entities": ["drug-a"]},
            "require_review_signoff": False,
        },
    )
    assert start_code == 200
    run_id = str(start_data.get("run_id") or "")
    assert run_id
    assert str(start_data.get("approval_status") or "") == "pending"

    queue_code, queue_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/review-queue?limit=20",
        headers={"Cookie": cookie},
    )
    assert queue_code == 200
    rows = queue_data.get("rows") if isinstance(queue_data.get("rows"), list) else []
    matched = [row for row in rows if str(row.get("run_id") or "") == run_id]
    assert matched
    row = matched[0]
    assert str(row.get("approval_status") or "") == "pending"
    assert isinstance(row.get("failed_checks"), list)


def test_automation_review_queue_filters_and_summary(
    api_server_auth: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALS_AUTOMATION_HANDOFF_ON_GATE_FAIL", "1")
    monkeypatch.setenv("ALS_RUN_GATE_FRESHNESS_WINDOW_YEARS", "1")

    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": "queue-filters@example.com"},
    )
    assert req_code == 200
    token = str(req_data.get("magic_link") or "").split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf = str(verify_data.get("csrf_token") or "")

    failed_run_code, failed_run_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/start",
        method="POST",
        headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        payload={
            "objective": "Review queue failed run",
            "filters": {"entities": ["drug-a"]},
            "require_review_signoff": False,
        },
    )
    assert failed_run_code == 200
    failed_run_id = str(failed_run_data.get("run_id") or "")
    assert failed_run_id

    status_code, status_data = _request_json(
        api_server_auth,
        "/api/auth/status",
        headers={"Cookie": cookie},
    )
    assert status_code == 200
    user = status_data.get("user") if isinstance(status_data.get("user"), dict) else {}
    user_id = str(user.get("user_id") or "")
    assert user_id

    db_path = Path(str(os.getenv("ALS_DB_PATH") or ""))
    store = EvidenceStore(db_path)
    medium_run_id = "run_review_queue_medium"
    store.create_investigation_run(
        run_id=medium_run_id,
        user_id=user_id,
        objective="Review queue medium run",
        filters={"entities": ["drug-a"]},
        require_review_signoff=False,
    )
    store.complete_investigation_run(
        user_id=user_id,
        run_id=medium_run_id,
        status="completed",
        report={"answer": "ok"},
        quality_gate={"passed": True, "checks": {"freshness": {"passed": True}}},
        approval_status="pending",
    )

    explicit_failed_run_id = "run_review_queue_failed_manual"
    store.create_investigation_run(
        run_id=explicit_failed_run_id,
        user_id=user_id,
        objective="Review queue failed manual run",
        filters={"entities": ["drug-a"]},
        require_review_signoff=False,
    )
    store.complete_investigation_run(
        user_id=user_id,
        run_id=explicit_failed_run_id,
        status="failed",
        report={"answer": "retry needed"},
        quality_gate={"passed": False, "checks": {"freshness": {"passed": False}}},
        approval_status="pending",
    )

    filtered_failed_code, filtered_failed_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/review-queue?limit=20&status=failed&risk=high&sort=risk_desc",
        headers={"Cookie": cookie},
    )
    assert filtered_failed_code == 200
    assert str(filtered_failed_data.get("status") or "") == "failed"
    assert str(filtered_failed_data.get("risk") or "") == "high"
    failed_rows = filtered_failed_data.get("rows") if isinstance(filtered_failed_data.get("rows"), list) else []
    assert failed_rows
    assert all(str(row.get("status") or "") == "failed" for row in failed_rows)
    assert all(str(row.get("risk_level") or "") == "high" for row in failed_rows)
    assert any(str(row.get("run_id") or "") == explicit_failed_run_id for row in failed_rows)

    filtered_medium_code, filtered_medium_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/review-queue?limit=20&status=completed&risk=medium&sort=created_asc",
        headers={"Cookie": cookie},
    )
    assert filtered_medium_code == 200
    medium_rows = filtered_medium_data.get("rows") if isinstance(filtered_medium_data.get("rows"), list) else []
    assert any(str(row.get("run_id") or "") == medium_run_id for row in medium_rows)
    assert all(str(row.get("status") or "") == "completed" for row in medium_rows)
    assert all(str(row.get("risk_level") or "") == "medium" for row in medium_rows)

    page_one_code, page_one_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/review-queue?limit=1&offset=0&sort=created_desc",
        headers={"Cookie": cookie},
    )
    assert page_one_code == 200
    assert int(page_one_data.get("limit") or 0) == 1
    assert int(page_one_data.get("offset", -1)) == 0
    assert int(page_one_data.get("total") or 0) >= 2
    assert bool(page_one_data.get("has_more")) is True
    page_one_rows = page_one_data.get("rows") if isinstance(page_one_data.get("rows"), list) else []
    assert len(page_one_rows) == 1

    page_two_code, page_two_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/review-queue?limit=1&offset=1&sort=created_desc",
        headers={"Cookie": cookie},
    )
    assert page_two_code == 200
    assert int(page_two_data.get("limit") or 0) == 1
    assert int(page_two_data.get("offset", -1)) == 1
    assert int(page_two_data.get("total") or 0) >= 2
    page_two_rows = page_two_data.get("rows") if isinstance(page_two_data.get("rows"), list) else []
    assert len(page_two_rows) == 1
    assert str(page_one_rows[0].get("run_id") or "") != str(page_two_rows[0].get("run_id") or "")

    summary_code, summary_data = _request_json(
        api_server_auth,
        "/api/investigation/runs/review-queue/summary",
        headers={"Cookie": cookie},
    )
    assert summary_code == 200
    assert int(summary_data.get("pending_total") or 0) >= 2
    by_status = summary_data.get("by_status") if isinstance(summary_data.get("by_status"), dict) else {}
    by_risk = summary_data.get("by_risk") if isinstance(summary_data.get("by_risk"), dict) else {}
    assert int(by_status.get("failed") or 0) >= 1
    assert int(by_status.get("completed") or 0) >= 1
    assert int(by_risk.get("high") or 0) >= 1
    assert int(by_risk.get("medium") or 0) >= 1

    dashboard_code, dashboard_data = _request_json(
        api_server_auth,
        "/api/automation/dashboard?days=30",
        headers={"Cookie": cookie},
    )
    assert dashboard_code == 200
    dashboard_review_queue = dashboard_data.get("review_queue") if isinstance(dashboard_data.get("review_queue"), dict) else {}
    assert int(dashboard_review_queue.get("pending_total") or 0) >= 2


def _authenticated_session(api_server_auth: str, email: str) -> tuple[str, str]:
    req_code, req_data = _request_json(
        api_server_auth,
        "/api/auth/request-link",
        method="POST",
        payload={"email": email},
    )
    assert req_code == 200
    magic_link = str(req_data.get("magic_link") or "")
    token = magic_link.split("magic_token=", 1)[1].split("&", 1)[0]
    verify_code, verify_data, verify_headers = _request_json_with_headers(
        api_server_auth,
        "/api/auth/verify-link",
        method="POST",
        payload={"token": token},
    )
    assert verify_code == 200
    cookie_pair = str(verify_headers.get("Set-Cookie") or "").split(";", 1)[0]
    csrf_token = str(verify_data.get("csrf_token") or "")
    assert cookie_pair
    assert csrf_token
    return cookie_pair, csrf_token


def test_manual_sync_status_requires_auth(api_server_auth: str) -> None:
    code, data = _request_json(api_server_auth, "/api/sync/manual/status")
    assert code == 401
    assert "auth" in str(data.get("error", "")).lower()


def test_manual_sync_status_returns_sources(api_server_auth: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALS_SYNC_PLAN", "config/sync_plan.smoke_public_sources.json")
    cookie_pair, csrf_token = _authenticated_session(api_server_auth, "sync-status@example.com")
    code, data = _request_json(
        api_server_auth,
        "/api/sync/manual/status",
        headers={"Cookie": cookie_pair, "X-CSRF-Token": csrf_token},
    )
    assert code == 200
    sources = data.get("sources")
    assert isinstance(sources, list)
    assert len(sources) >= 5
    assert "can_trigger_all" in data
    assert "can_trigger" in data
    first_source = sources[0]
    assert "can_trigger" in first_source


def test_manual_sync_trigger_requires_csrf(api_server_auth: str) -> None:
    cookie_pair, _csrf = _authenticated_session(api_server_auth, "sync-csrf@example.com")
    code, data = _request_json(
        api_server_auth,
        "/api/sync/manual/trigger",
        method="POST",
        headers={"Cookie": cookie_pair},
        payload={"source": "pubmed"},
    )
    assert code == 403
    assert "csrf" in str(data.get("error", "")).lower()


def test_manual_sync_trigger_returns_202(api_server_auth: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALS_SYNC_PLAN", "config/sync_plan.smoke_public_sources.json")
    monkeypatch.setattr(
        "als_intel.manual_sync._run_single_job",
        lambda db_path, job: {
            "status": "ok",
            "source": str(job["source"]),
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "notes": "",
        },
    )
    cookie_pair, csrf_token = _authenticated_session(api_server_auth, "sync-trigger@example.com")
    code, data = _request_json(
        api_server_auth,
        "/api/sync/manual/trigger",
        method="POST",
        headers={"Cookie": cookie_pair, "X-CSRF-Token": csrf_token},
        payload={"source": "pubmed"},
    )
    assert code == 202
    assert data.get("status") == "started"
    assert data.get("scope") == "pubmed"


def test_manual_sync_trigger_respects_cooldown(api_server_auth: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALS_SYNC_PLAN", "config/sync_plan.smoke_public_sources.json")
    monkeypatch.setenv("ALS_MANUAL_SYNC_COOLDOWN_HOURS", "6")
    cookie_pair, csrf_token = _authenticated_session(api_server_auth, "sync-cooldown@example.com")

    store = EvidenceStore()
    store.init_db()
    store.record_manual_sync_success("all")
    plan = json.loads(Path("config/sync_plan.smoke_public_sources.json").read_text(encoding="utf-8"))
    for job in plan:
        store.record_manual_sync_success(str(job["source"]))

    code, data = _request_json(
        api_server_auth,
        "/api/sync/manual/trigger",
        method="POST",
        headers={"Cookie": cookie_pair, "X-CSRF-Token": csrf_token},
        payload={"scope": "all"},
    )
    assert code == 429
    assert "cooldown" in str(data.get("error", "")).lower()
