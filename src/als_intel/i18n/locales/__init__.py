from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_LOCALES_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _load_json(name: str) -> dict[str, str]:
    path = _LOCALES_DIR / name
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Locale file must be a JSON object: {path}")
    return {str(key): str(value) for key, value in raw.items()}


def _merge_locale(locale: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    for stem in ("app", "landing", "login", "legal", "email", "common"):
        path = _LOCALES_DIR / f"{stem}_{locale}.json"
        if not path.exists():
            continue
        merged.update(_load_json(f"{stem}_{locale}.json"))
    return merged


LOCALE_STRINGS: dict[str, dict[str, str]] = {
    "en": _merge_locale("en"),
    "es": _merge_locale("es"),
}
