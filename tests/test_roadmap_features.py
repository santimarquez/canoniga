from __future__ import annotations

import pytest

from als_intel.extractors.claim_builder import build_record_from_doc
from als_intel.extractors.registry import ExtractorRegistry
from als_intel.extractors.restricted import AccessNotConfiguredError
from als_intel.extractors import register_builtin_extractors
from als_intel.agents.systems_biology import build_systems_biology_report
from als_intel.agents.historical import build_failure_atlas


def test_restricted_extractor_raises_access_not_configured() -> None:
    register_builtin_extractors()
    extractor = ExtractorRegistry.create("drugbank")
    with pytest.raises(AccessNotConfiguredError):
        extractor.fetch_docs(query="als", max_results=1, from_file=None, last_successful_timestamp=None, extractor_config=None)


def test_systems_biology_report_returns_pathway_cards() -> None:
    evidence_rows = [
        {
            "entity": "neuroinflammation",
            "source_title": "kegg pathway map",
            "source_doi": "kegg:map05014",
            "effect_direction": "supports",
            "study_type": "observational",
            "claim_text": "pathway signal",
            "sample_size": 100,
            "endpoint_validity": 0.7,
            "cohort": "ALS",
            "reliability_score": 0.8,
        }
    ]
    support_map = [{"entity": "neuroinflammation", "outcome": "disease progression", "supports": 2, "contradicts": 1}]
    report = build_systems_biology_report(
        evidence_rows=evidence_rows,
        support_map_rows=support_map,
        graph_neighbor_rows=[{"entity": "neuroinflammation", "neighbor_entity": "microglial activation"}],
        limit=5,
    )
    assert report["count"] >= 1
    assert "perturbation_priority_score" in report["items"][0]


def test_failure_atlas_counts_structured_trial_failures() -> None:
    rows = [
        {
            "claim_id": "CTGOV_1",
            "entity": "protein aggregation",
            "outcome": "ALS functional rating",
            "source_doi": "NCT1",
            "study_type": "interventional",
            "effect_direction": "contradicts",
            "claim_text": "terminated trial",
            "source_title": "failed trial",
            "sample_size": 90,
            "endpoint_validity": 0.7,
            "cohort": "ALS",
            "reliability_score": 0.6,
            "extraction_provenance": {
                "trial_status": "Terminated",
                "termination_reason": "Lack of efficacy",
                "primary_endpoint": "ALS functional rating scale",
                "phase": "PHASE2",
                "enrollment": 96,
            },
        }
    ]
    atlas = build_failure_atlas(rows)
    assert atlas["total_failed_or_negative_records"] == 1
    assert atlas["structured_trial_failures"] == 1
    assert atlas["entries"][0]["termination_reason"] == "Lack of efficacy"


def test_llm_extraction_flag_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ALS_CLAIM_EXTRACTION_LLM", raising=False)
    from als_intel.extractors.claim_builder import _llm_extraction_enabled

    assert _llm_extraction_enabled() is False


def test_orchestrator_includes_systems_biology_when_support_map_provided() -> None:
    from als_intel.agents.orchestrator import build_agent_report

    report = build_agent_report(
        evidence_rows=[
            {
                "entity": "neuroinflammation",
                "source_title": "kegg pathway map",
                "source_doi": "kegg:map05014",
                "claim_id": "K1",
                "claim_text": "pathway",
                "outcome": "disease progression",
                "effect_direction": "supports",
                "study_type": "observational",
                "reliability_score": 0.8,
                "source_reliability_score": 0.8,
            }
        ],
        contradiction_rows=[],
        support_map_rows=[
            {"entity": "neuroinflammation", "outcome": "disease progression", "supports": 2, "contradicts": 1}
        ],
        graph_neighbor_rows=[
            {
                "entity": "neuroinflammation",
                "neighbor_entity": "microglial activation",
                "edge_type": "affects_outcome",
                "weight": 0.8,
                "polarity": "supports",
            }
        ],
    )
    assert "systems_biology_agent" in report
    assert int(report["systems_biology_agent"]["count"]) >= 1


def test_failure_atlas_uses_primary_endpoint_result() -> None:
    rows = [
        {
            "claim_id": "CTGOV_2",
            "entity": "neuroinflammation",
            "outcome": "ALS functional rating",
            "source_doi": "NCT2",
            "study_type": "interventional",
            "effect_direction": "contradicts",
            "claim_text": "completed trial",
            "source_title": "completed trial",
            "sample_size": 200,
            "endpoint_validity": 0.7,
            "cohort": "ALS",
            "reliability_score": 0.6,
            "extraction_provenance": {
                "trial_status": "Completed",
                "primary_endpoint_result": "No significant difference versus placebo",
            },
        }
    ]
    atlas = build_failure_atlas(rows)
    assert atlas["entries"][0]["primary_endpoint_result"] == "No significant difference versus placebo"
    assert atlas["entries"][0]["root_cause"] == "endpoint_sensitivity"


def test_cli_agent_report_includes_systems_biology_agent(tmp_path) -> None:
    from als_intel.store import EvidenceStore
    from als_intel.agents.orchestrator import build_agent_report
    from als_intel.sync import run_incremental_sync

    db_path = tmp_path / "agent.sqlite"
    run_incremental_sync(
        db_path=str(db_path),
        source="kegg",
        query="als",
        from_file="examples/kegg_sample.json",
    )
    store = EvidenceStore(str(db_path))
    store.rebuild_knowledge_graph()
    support_map = store.graph_support_contradiction_map(limit=10)
    assert support_map
    report = build_agent_report(
        evidence_rows=store.all_evidence(),
        contradiction_rows=store.contradiction_pairs(),
        support_map_rows=support_map,
        graph_neighbor_rows=[],
    )
    assert "systems_biology_agent" in report


def test_failure_atlas_api_payload_includes_endpoint_result() -> None:
    from als_intel.agents.historical import build_failure_atlas

    rows = [
        {
            "claim_id": "CTGOV_API_1",
            "entity": "neuroinflammation",
            "outcome": "ALS functional rating",
            "source_doi": "NCTAPI1",
            "study_type": "interventional",
            "effect_direction": "contradicts",
            "claim_text": "completed trial",
            "source_title": "completed trial",
            "sample_size": 200,
            "endpoint_validity": 0.7,
            "cohort": "ALS",
            "reliability_score": 0.6,
            "extraction_provenance": {
                "trial_status": "Completed",
                "primary_endpoint_result": "No significant difference versus placebo",
            },
        }
    ]
    atlas = build_failure_atlas(rows)
    assert atlas["entries"][0]["primary_endpoint_result"] == "No significant difference versus placebo"


def test_ctgov_sample_fixture_uses_structured_claim_text() -> None:
    record = build_record_from_doc(
        {
            "source": "ctgov",
            "source_id": "NCT99900002",
            "title": "Failed trial of protein aggregation inhibitor in ALS",
            "trial_status": "Terminated",
            "termination_reason": "Lack of efficacy",
            "primary_endpoint": "ALS functional rating scale",
            "intervention_arm": "Protein aggregation inhibitor",
            "year": 2024,
            "journal": "clinicaltrials.gov",
        }
    )
    assert record.effect_direction == "contradicts"
    assert record.claim_text != record.source_title
