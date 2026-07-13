from __future__ import annotations

from als_intel.landing import LANDING_TEMPLATE, render_landing_page


def test_landing_template_is_separate_from_app_page() -> None:
    from als_intel.webui import PAGE_TEMPLATE

    assert LANDING_TEMPLATE.template != PAGE_TEMPLATE.template
    assert "$hero_cta_label" in LANDING_TEMPLATE.template
    assert "failureAtlasList" not in LANDING_TEMPLATE.template


def test_render_landing_page_uses_local_assets_and_login_ctas() -> None:
    body = render_landing_page(auth_enabled=True).decode("utf-8")
    assert "Reduce ALS research uncertainty with traceable, cited intelligence" in body
    assert "/assets/mtvl-ai-logo-lettermark.png" in body
    assert "/assets/landing-dashboard-mockup.png" in body
    assert "googleusercontent.com" not in body
    assert 'href="/login"' in body
    assert "Sign in to investigate" in body
    assert "Not for patient diagnosis or treatment decisions" in body
    assert 'id="database"' in body
    assert 'id="landingDbWidget"' in body
    assert "landingFetchDbStatus" in body


def test_render_landing_page_auth_disabled_links_to_app() -> None:
    body = render_landing_page(auth_enabled=False).decode("utf-8")
    assert 'href="/app"' in body
    assert "Open investigator" in body


def test_render_landing_page_authenticated_links_to_app() -> None:
    body = render_landing_page(auth_enabled=True, authenticated=True).decode("utf-8")
    assert 'href="/app"' in body
    assert "Continue investigating" in body
    assert 'href="/login"' not in body
