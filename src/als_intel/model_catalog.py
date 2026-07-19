from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

ModelTier = Literal["fast", "balanced", "high", "best"]
ModelFamily = Literal["llama", "phi", "qwen", "gemma", "mistral", "unknown"]

TIER_RANK: dict[str, int] = {
    "fast": 0,
    "balanced": 1,
    "high": 2,
    "best": 3,
}

FAMILY_PREF: dict[str, int] = {
    "llama": 0,
    "qwen": 1,
    "mistral": 2,
    "phi": 3,
    "gemma": 4,
    "unknown": 9,
}


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    id: str
    display_name: str
    family: ModelFamily
    tier: ModelTier
    match_patterns: tuple[str, ...]
    ollama_pull: str


# Curated catalog for investigator chat balancing (Ollama tags are best-effort).
CURATED_MODELS: tuple[CatalogEntry, ...] = (
    # Llama
    CatalogEntry("llama-3.2-1b", "Llama 3.2 1B", "llama", "fast", ("llama3.2:1b", "llama3.2-1b"), "llama3.2:1b"),
    CatalogEntry("llama-3.2-3b", "Llama 3.2 3B", "llama", "fast", ("llama3.2:3b", "llama3.2-3b"), "llama3.2:3b"),
    CatalogEntry("llama-3.1-8b", "Llama 3.1 8B", "llama", "balanced", ("llama3.1:8b", "llama3.1-8b"), "llama3.1:8b"),
    CatalogEntry("llama-3.1-70b", "Llama 3.1 70B", "llama", "high", ("llama3.1:70b", "llama3.1-70b"), "llama3.1:70b"),
    CatalogEntry("llama-3.3-70b", "Llama 3.3 70B", "llama", "best", ("llama3.3:70b", "llama3.3-70b"), "llama3.3:70b"),
    # Phi
    CatalogEntry("phi-3-mini", "Phi-3 Mini 3.8B", "phi", "fast", ("phi3:mini", "phi3-mini", "phi-3-mini"), "phi3:mini"),
    CatalogEntry(
        "phi-4-mini-reasoning",
        "Phi-4 Mini Reasoning",
        "phi",
        "balanced",
        ("phi4-mini-reasoning", "phi4:mini-reasoning", "phi-4-mini"),
        "phi4-mini-reasoning",
    ),
    CatalogEntry("phi-4-14b", "Phi-4 14B", "phi", "high", ("phi4:14b", "phi4-14b", "phi-4"), "phi4"),
    CatalogEntry(
        "phi-3.5-mini",
        "Phi-3.5 Mini Instruct",
        "phi",
        "balanced",
        ("phi3.5:mini", "phi3.5-mini", "phi3.5"),
        "phi3.5:mini",
    ),
    CatalogEntry(
        "phi-3.5-moe",
        "Phi-3.5 MoE 42B",
        "phi",
        "best",
        ("phi3.5:moe", "phi3.5-moe", "phi-3.5-moe"),
        "phi3.5:moe",
    ),
    # Qwen
    CatalogEntry("qwen3-14b", "Qwen3 14B", "qwen", "balanced", ("qwen3:14b", "qwen3-14b", "qwen2.5:14b"), "qwen3:14b"),
    CatalogEntry("qwen3-32b", "Qwen3 32B", "qwen", "high", ("qwen3:32b", "qwen3-32b", "qwen2.5:32b"), "qwen3:32b"),
    CatalogEntry(
        "qwen3-30b-a3b",
        "Qwen3 30B-A3B",
        "qwen",
        "best",
        ("qwen3:30b-a3b", "qwen3-30b-a3b", "qwen3:30b"),
        "qwen3:30b-a3b",
    ),
    CatalogEntry(
        "qwen3-235b-a22b",
        "Qwen3 235B-A22B",
        "qwen",
        "best",
        ("qwen3:235b", "qwen3-235b", "qwen3:235b-a22b"),
        "qwen3:235b-a22b",
    ),
    # Gemma
    CatalogEntry("gemma2-2b", "Gemma 2 2B", "gemma", "fast", ("gemma2:2b", "gemma2-2b"), "gemma2:2b"),
    CatalogEntry("gemma2-9b", "Gemma 2 9B", "gemma", "balanced", ("gemma2:9b", "gemma2-9b"), "gemma2:9b"),
    CatalogEntry("gemma2-27b", "Gemma 2 27B", "gemma", "high", ("gemma2:27b", "gemma2-27b"), "gemma2:27b"),
    # Mistral
    CatalogEntry("ministral-3b", "Ministral 3B", "mistral", "fast", ("ministral-3b", "ministral:3b"), "ministral-3b"),
    CatalogEntry("mistral-7b", "Mistral 7B", "mistral", "balanced", ("mistral:7b", "mistral-7b", "mistral:latest"), "mistral:7b"),
    CatalogEntry("ministral-8b", "Ministral 8B", "mistral", "balanced", ("ministral-8b", "ministral:8b"), "ministral-8b"),
    CatalogEntry(
        "mistral-large-2",
        "Mistral Large 2",
        "mistral",
        "best",
        ("mistral-large", "mistral-large2", "mistral-large:latest"),
        "mistral-large",
    ),
)


def curated_pull_tags() -> list[str]:
    """Ollama tags this project hosts (one representative pull tag per curated entry)."""
    tags: list[str] = []
    seen: set[str] = set()
    for entry in CURATED_MODELS:
        tag = str(entry.ollama_pull).strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags


_SIZE_PATTERNS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"(?:^|[:\-_])235b(?:$|[:\-_])", re.I), 235),
    (re.compile(r"(?:^|[:\-_])70b(?:$|[:\-_])", re.I), 70),
    (re.compile(r"(?:^|[:\-_])65b(?:$|[:\-_])", re.I), 65),
    (re.compile(r"(?:^|[:\-_])42b(?:$|[:\-_])", re.I), 42),
    (re.compile(r"(?:^|[:\-_])34b(?:$|[:\-_])", re.I), 34),
    (re.compile(r"(?:^|[:\-_])33b(?:$|[:\-_])", re.I), 33),
    (re.compile(r"(?:^|[:\-_])32b(?:$|[:\-_])", re.I), 32),
    (re.compile(r"(?:^|[:\-_])30b(?:$|[:\-_])", re.I), 30),
    (re.compile(r"(?:^|[:\-_])27b(?:$|[:\-_])", re.I), 27),
    (re.compile(r"(?:^|[:\-_])22b(?:$|[:\-_])", re.I), 22),
    (re.compile(r"(?:^|[:\-_])14b(?:$|[:\-_])", re.I), 14),
    (re.compile(r"(?:^|[:\-_])13b(?:$|[:\-_])", re.I), 13),
    (re.compile(r"(?:^|[:\-_])12b(?:$|[:\-_])", re.I), 12),
    (re.compile(r"(?:^|[:\-_])9b(?:$|[:\-_])", re.I), 9),
    (re.compile(r"(?:^|[:\-_])8b(?:$|[:\-_])", re.I), 8),
    (re.compile(r"(?:^|[:\-_])7b(?:$|[:\-_])", re.I), 7),
    (re.compile(r"(?:^|[:\-_])4b(?:$|[:\-_])", re.I), 4),
    (re.compile(r"(?:^|[:\-_])3\.8b(?:$|[:\-_])", re.I), 4),
    (re.compile(r"(?:^|[:\-_])3b(?:$|[:\-_])", re.I), 3),
    (re.compile(r"(?:^|[:\-_])2b(?:$|[:\-_])", re.I), 2),
    (re.compile(r"(?:^|[:\-_])1b(?:$|[:\-_])", re.I), 1),
)


def normalize_model_name(name: str) -> str:
    return str(name or "").strip().lower()


def infer_model_size_b(name: str) -> int:
    text = normalize_model_name(name)
    for pattern, size in _SIZE_PATTERNS:
        if pattern.search(text):
            return size
    if "gemma2" in text or "gemma-2" in text:
        return 9
    if "gemma" in text:
        return 7
    if "qwen" in text:
        return 7
    if "llama" in text:
        return 8
    if "mistral" in text or "mixtral" in text or "ministral" in text:
        return 7
    if "phi" in text:
        return 3
    return 5


def tier_from_size_b(billions: int) -> ModelTier:
    if billions <= 3:
        return "fast"
    if billions <= 8:
        return "balanced"
    if billions <= 32:
        return "high"
    return "best"


def infer_family(name: str) -> ModelFamily:
    text = normalize_model_name(name)
    if "llama" in text:
        return "llama"
    if "phi" in text:
        return "phi"
    if "qwen" in text:
        return "qwen"
    if "gemma" in text:
        return "gemma"
    if "mistral" in text or "ministral" in text or "mixtral" in text:
        return "mistral"
    return "unknown"


def match_catalog_entry(name: str) -> CatalogEntry | None:
    text = normalize_model_name(name)
    if not text:
        return None
    best: CatalogEntry | None = None
    best_score = -1
    for entry in CURATED_MODELS:
        for pattern in entry.match_patterns:
            needle = pattern.lower()
            if text == needle or text.startswith(needle) or needle in text:
                score = len(needle)
                if score > best_score:
                    best = entry
                    best_score = score
    return best


def annotate_installed_model(name: str, *, size: int | None = None) -> dict[str, object]:
    entry = match_catalog_entry(name)
    if entry is not None:
        return {
            "id": name,
            "name": name,
            "size": size,
            "tier": entry.tier,
            "family": entry.family,
            "display_name": entry.display_name,
            "catalog_id": entry.id,
            "installed": True,
            "ollama_pull": entry.ollama_pull,
        }
    billions = infer_model_size_b(name)
    family = infer_family(name)
    return {
        "id": name,
        "name": name,
        "size": size,
        "tier": tier_from_size_b(billions),
        "family": family,
        "display_name": name,
        "catalog_id": None,
        "installed": True,
        "ollama_pull": name,
    }


def recommended_missing(installed_names: list[str], *, limit: int = 12) -> list[dict[str, object]]:
    installed = {normalize_model_name(n) for n in installed_names}
    matched_catalog_ids: set[str] = set()
    for name in installed_names:
        entry = match_catalog_entry(name)
        if entry is not None:
            matched_catalog_ids.add(entry.id)

    output: list[dict[str, object]] = []
    for entry in CURATED_MODELS:
        if entry.id in matched_catalog_ids:
            continue
        pull = entry.ollama_pull.lower()
        if any(inst == pull or inst.startswith(pull) or pull in inst for inst in installed):
            continue
        output.append(
            {
                "id": entry.ollama_pull,
                "name": entry.ollama_pull,
                "size": None,
                "tier": entry.tier,
                "family": entry.family,
                "display_name": entry.display_name,
                "catalog_id": entry.id,
                "installed": False,
                "ollama_pull": entry.ollama_pull,
            }
        )
        if len(output) >= max(1, int(limit)):
            break
    return output


def tier_rank(tier: str) -> int:
    return TIER_RANK.get(str(tier), 1)


def family_pref(family: str) -> int:
    return FAMILY_PREF.get(str(family), 9)
