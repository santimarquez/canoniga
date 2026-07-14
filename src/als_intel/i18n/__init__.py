from __future__ import annotations

import json
import re
from http.cookies import SimpleCookie
from typing import Any

from als_intel.i18n.audit import assert_locale_parity
from als_intel.i18n.locales import LOCALE_STRINGS

SUPPORTED_LOCALES = ("en", "es")
DEFAULT_LOCALE = "en"
LOCALE_COOKIE_NAME = "als_lang"
LOCALE_COOKIE_MAX_AGE = 31_536_000  # 1 year


def normalize_locale(value: str | None) -> str | None:
    if value is None:
        return None
    token = str(value).strip().lower()
    if not token:
        return None
    if token.startswith("es"):
        return "es"
    if token.startswith("en"):
        return "en"
    return None


def locale_from_accept_language(header: str | None) -> str:
    if not header:
        return DEFAULT_LOCALE
    for part in header.split(","):
        token = part.split(";")[0].strip().lower()
        resolved = normalize_locale(token)
        if resolved is not None:
            return resolved
    return DEFAULT_LOCALE


def parse_locale_cookie(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None
    jar = SimpleCookie()
    jar.load(cookie_header)
    morsel = jar.get(LOCALE_COOKIE_NAME)
    if morsel is None:
        return None
    return normalize_locale(morsel.value)


def resolve_locale(
    *,
    accept_language: str | None = None,
    cookie_header: str | None = None,
    query_lang: str | None = None,
) -> tuple[str, bool]:
    """Return locale and whether the caller should persist it from the query param."""
    from_query = normalize_locale(query_lang)
    if from_query is not None:
        return from_query, True

    from_cookie = parse_locale_cookie(cookie_header)
    if from_cookie is not None:
        return from_cookie, False

    return locale_from_accept_language(accept_language), False


def locale_cookie_header(locale: str) -> str:
    safe_locale = normalize_locale(locale) or DEFAULT_LOCALE
    return f"{LOCALE_COOKIE_NAME}={safe_locale}; Path=/; Max-Age={LOCALE_COOKIE_MAX_AGE}; SameSite=Lax"


def t(locale: str, key: str, **variables: Any) -> str:
    safe_locale = normalize_locale(locale) or DEFAULT_LOCALE
    bundle = LOCALE_STRINGS.get(safe_locale, LOCALE_STRINGS[DEFAULT_LOCALE])
    fallback = LOCALE_STRINGS[DEFAULT_LOCALE]
    text = bundle.get(key, fallback.get(key, key))
    if variables:
        for name, value in variables.items():
            text = text.replace("{" + str(name) + "}", str(value))
    return text


def client_i18n_json() -> str:
    payload = {locale: dict(strings) for locale, strings in LOCALE_STRINGS.items()}
    return json.dumps(payload, ensure_ascii=True)


def app_client_i18n_json() -> str:
    """Return only keys without dotted namespace prefixes for the investigator app."""
    payload: dict[str, dict[str, str]] = {"en": {}, "es": {}}
    for locale in SUPPORTED_LOCALES:
        for key, value in LOCALE_STRINGS[locale].items():
            if "." not in key:
                payload[locale][key] = value
    return json.dumps(payload, ensure_ascii=True)


def landing_strings(locale: str) -> dict[str, str]:
    safe_locale = normalize_locale(locale) or DEFAULT_LOCALE
    prefix = "landing."
    bundle = LOCALE_STRINGS[safe_locale]
    return {key[len(prefix) :]: value for key, value in bundle.items() if key.startswith(prefix)}


def login_strings(locale: str) -> dict[str, str]:
    safe_locale = normalize_locale(locale) or DEFAULT_LOCALE
    prefix = "login."
    bundle = LOCALE_STRINGS[safe_locale]
    return {key[len(prefix) :]: value for key, value in bundle.items() if key.startswith(prefix)}


def legal_strings(locale: str) -> dict[str, str]:
    safe_locale = normalize_locale(locale) or DEFAULT_LOCALE
    prefix = "legal."
    bundle = LOCALE_STRINGS[safe_locale]
    return {key[len(prefix) :]: value for key, value in bundle.items() if key.startswith(prefix)}


def common_strings(locale: str) -> dict[str, str]:
    safe_locale = normalize_locale(locale) or DEFAULT_LOCALE
    prefix = "common."
    bundle = LOCALE_STRINGS[safe_locale]
    return {key[len(prefix) :]: value for key, value in bundle.items() if key.startswith(prefix)}


def locale_setter_script() -> str:
    return """
function setLocale(lang) {
  const safe = String(lang || '').toLowerCase().startsWith('es') ? 'es' : 'en';
  document.cookie = 'als_lang=' + safe + ';path=/;max-age=31536000;samesite=lax';
  try { window.localStorage.setItem('als_lang', safe); } catch (_) {}
}
function readStoredLocale() {
  try {
    const stored = String(window.localStorage.getItem('als_lang') || '').trim().toLowerCase();
    if (stored.startsWith('es')) return 'es';
    if (stored.startsWith('en')) return 'en';
  } catch (_) {}
  const match = document.cookie.match(/(?:^|;\\s*)als_lang=([^;]+)/);
  if (match) {
    const cookieValue = decodeURIComponent(match[1] || '').trim().toLowerCase();
    if (cookieValue.startsWith('es')) return 'es';
    if (cookieValue.startsWith('en')) return 'en';
  }
  const browser = String(navigator.language || '').toLowerCase();
  return browser.startsWith('es') ? 'es' : 'en';
}
""".strip()


__all__ = [
    "DEFAULT_LOCALE",
    "LOCALE_COOKIE_NAME",
    "SUPPORTED_LOCALES",
    "assert_locale_parity",
    "app_client_i18n_json",
    "client_i18n_json",
    "common_strings",
    "landing_strings",
    "legal_strings",
    "locale_cookie_header",
    "locale_from_accept_language",
    "locale_setter_script",
    "login_strings",
    "normalize_locale",
    "parse_locale_cookie",
    "resolve_locale",
    "t",
]
