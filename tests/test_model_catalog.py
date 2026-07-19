from __future__ import annotations

from als_intel.model_catalog import (
    CURATED_MODELS,
    annotate_installed_model,
    curated_pull_tags,
    match_catalog_entry,
    recommended_missing,
    tier_from_size_b,
)


def test_curated_pull_tags_covers_catalog() -> None:
    tags = curated_pull_tags()
    assert len(tags) == len(CURATED_MODELS)
    assert "llama3.1:8b" in tags
    assert "llama3.3:70b" in tags
    assert "qwen3:14b" in tags
    assert len(tags) == len(set(tags))


def test_match_catalog_entry_known_tags() -> None:
    llama = match_catalog_entry("llama3.1:8b")
    assert llama is not None
    assert llama.tier == "balanced"
    assert llama.family == "llama"

    best = match_catalog_entry("llama3.3:70b")
    assert best is not None
    assert best.tier == "best"

    qwen = match_catalog_entry("qwen2.5:14b")
    assert qwen is not None
    assert qwen.tier == "balanced"
    assert qwen.family == "qwen"


def test_annotate_installed_falls_back_to_size_tier() -> None:
    row = annotate_installed_model("custom-lab:12b", size=100)
    assert row["installed"] is True
    assert row["tier"] == "high"
    assert row["family"] == "unknown"
    assert tier_from_size_b(2) == "fast"
    assert tier_from_size_b(70) == "best"


def test_recommended_missing_excludes_installed() -> None:
    missing = recommended_missing(["llama3.1:8b", "gemma2:2b"], limit=20)
    ids = {str(row["catalog_id"]) for row in missing}
    assert "llama-3.1-8b" not in ids
    assert "gemma2-2b" not in ids
    assert any(row["installed"] is False for row in missing)
    assert any(str(row["ollama_pull"]).startswith("llama") for row in missing)
