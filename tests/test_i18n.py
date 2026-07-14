from __future__ import annotations

from als_intel.i18n import (
    locale_cookie_header,
    normalize_locale,
    parse_locale_cookie,
    resolve_locale,
    t,
)
from als_intel.i18n.audit import assert_locale_parity, missing_keys
from als_intel.landing import render_landing_page
from als_intel.webui import render_login_page


def test_normalize_locale() -> None:
    assert normalize_locale("en") == "en"
    assert normalize_locale("EN-US") == "en"
    assert normalize_locale("es") == "es"
    assert normalize_locale("es-ES") == "es"
    assert normalize_locale("fr") is None
    assert normalize_locale("") is None
    assert normalize_locale(None) is None


def test_resolve_locale_priority() -> None:
    locale, persist = resolve_locale(
        accept_language="en-US,en;q=0.9",
        cookie_header="als_lang=es",
        query_lang=None,
    )
    assert locale == "es"
    assert persist is False

    locale, persist = resolve_locale(
        accept_language="en-US,en;q=0.9",
        cookie_header="als_lang=es",
        query_lang="en",
    )
    assert locale == "en"
    assert persist is True

    locale, persist = resolve_locale(
        accept_language="es-ES,es;q=0.9",
        cookie_header=None,
        query_lang=None,
    )
    assert locale == "es"
    assert persist is False

    locale, persist = resolve_locale(
        accept_language="en-US,en;q=0.9",
        cookie_header=None,
        query_lang=None,
    )
    assert locale == "en"
    assert persist is False


def test_locale_cookie_helpers() -> None:
    assert parse_locale_cookie("als_lang=en; other=1") == "en"
    assert parse_locale_cookie("als_lang=es") == "es"
    assert parse_locale_cookie("other=1") is None
    header = locale_cookie_header("es")
    assert "als_lang=es" in header
    assert "Path=/" in header
    assert "SameSite=Lax" in header


def test_locale_key_parity() -> None:
    assert_locale_parity()
    assert missing_keys("en", "es") == []
    assert missing_keys("es", "en") == []


def test_translate_with_variables() -> None:
    assert "15" in t("en", "email.magic_link_plain_expiry", minutes=15)
    assert "15" in t("es", "email.magic_link_plain_expiry", minutes=15)


def test_render_landing_page_spanish_smoke() -> None:
    body = render_landing_page(auth_enabled=True, locale="es").decode("utf-8")
    assert 'lang="es"' in body
    assert "Base de datos" in body or "base de datos" in body.lower()
    assert 'href="?lang=es"' in body


def test_render_login_page_spanish_smoke() -> None:
    body = render_login_page(auth_enabled=True, locale="es").decode("utf-8")
    assert 'lang="es"' in body
    assert "Iniciar sesion" in body
    assert 'id="loginEmail"' in body
    assert "Enviar magic link" in body
