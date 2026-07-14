from __future__ import annotations

from als_intel.i18n.locales import LOCALE_STRINGS


def missing_keys(locale_a: str, locale_b: str) -> list[str]:
    a = LOCALE_STRINGS[locale_a]
    b = LOCALE_STRINGS[locale_b]
    return sorted(set(a) - set(b))


def extra_keys(locale_a: str, locale_b: str) -> list[str]:
    a = LOCALE_STRINGS[locale_a]
    b = LOCALE_STRINGS[locale_b]
    return sorted(set(b) - set(a))


def assert_locale_parity() -> None:
    missing_en = missing_keys("en", "es")
    missing_es = missing_keys("es", "en")
    if missing_en or missing_es:
        details = []
        if missing_en:
            details.append(f"missing in es: {missing_en[:10]}{'...' if len(missing_en) > 10 else ''}")
        if missing_es:
            details.append(f"missing in en: {missing_es[:10]}{'...' if len(missing_es) > 10 else ''}")
        raise ValueError("Locale key mismatch: " + "; ".join(details))
