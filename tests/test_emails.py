from __future__ import annotations

from email import policy
from email.parser import BytesParser
from unittest.mock import patch

import pytest

from als_intel.auth import AuthConfig, AuthService
from als_intel.emails import build_magic_link_email, render_email_layout
from als_intel.brand import LOGO_ACCENT_COLOR, LOGO_PRIMARY_COLOR
from als_intel.emails.theme import PRIMARY_STRONG, PRODUCT_NAME


def test_build_magic_link_email_plain_text() -> None:
    content = build_magic_link_email(
        magic_link="http://localhost:8000/?magic_token=abc123",
        expires_minutes=15,
        recipient_email="analyst@example.com",
    )

    assert content.subject == f"Sign in to {PRODUCT_NAME}"
    assert "analyst@example.com" in content.plain_text
    assert "http://localhost:8000/?magic_token=abc123" in content.plain_text
    assert "15 minutes" in content.plain_text
    assert "ignore" in content.plain_text.lower()


def test_build_magic_link_email_spanish() -> None:
    content = build_magic_link_email(
        magic_link="http://localhost:8000/?magic_token=abc123",
        expires_minutes=15,
        recipient_email="analyst@example.com",
        locale="es",
    )

    assert "analyst@example.com" in content.plain_text
    assert "15" in content.plain_text
    assert "ignore" not in content.plain_text.lower()
    assert "ignor" in content.plain_text.lower()


    content = build_magic_link_email(
        magic_link="http://localhost:8000/?magic_token=abc123",
        expires_minutes=15,
        recipient_email="analyst@example.com",
    )

    assert PRIMARY_STRONG in content.html
    assert '<svg' in content.html
    assert LOGO_PRIMARY_COLOR in content.html
    assert LOGO_ACCENT_COLOR in content.html
    assert "Open Source Intelligence" in content.html
    assert "Open sign-in link" in content.html
    assert 'href="http://localhost:8000/?magic_token=abc123"' in content.html
    assert "analyst@example.com" in content.html
    assert '<table role="presentation"' in content.html


def test_render_email_layout_includes_header_footer() -> None:
    html = render_email_layout(
        title="Test headline",
        preheader="Preview line",
        body_html="<p>Body content</p>",
    )

    assert '<svg' in html
    assert LOGO_PRIMARY_COLOR in html
    assert "Test headline" in html
    assert "Preview line" in html
    assert "Body content" in html
    assert "Open source project" in html


def test_send_magic_link_sends_multipart() -> None:
    config = AuthConfig(
        app_base_url="http://localhost:8000",
        magic_link_ttl_seconds=900,
        session_ttl_seconds=28800,
        session_renew_window_seconds=900,
        cookie_name="als_session",
        smtp_host="mailpit",
        smtp_port=1025,
        smtp_user="",
        smtp_password="",
        smtp_from="no-reply@canoniga.local",
        smtp_starttls=False,
        dev_mode=False,
        request_rate_limit_count=0,
        request_rate_limit_window_seconds=0,
        request_rate_limit_ip_count=0,
        cookie_secure=False,
        cookie_same_site="Lax",
        cookie_http_only=True,
        cookie_path="/",
        cookie_domain="",
    )
    service = AuthService(config)
    sent_messages: list[bytes] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int = 10) -> None:
            self.host = host
            self.port = port

        def __enter__(self) -> "FakeSMTP":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def starttls(self) -> None:
            return None

        def login(self, user: str, password: str) -> None:
            return None

        def send_message(self, msg: object) -> None:
            from email.message import EmailMessage

            assert isinstance(msg, EmailMessage)
            sent_messages.append(msg.as_bytes())

    with patch("als_intel.auth.smtplib.SMTP", FakeSMTP):
        result = service.send_magic_link(
            email="analyst@example.com",
            magic_link="http://localhost:8000/?magic_token=abc123",
        )

    assert result == {"sent": True, "mode": "smtp"}
    assert len(sent_messages) == 1

    parsed = BytesParser(policy=policy.default).parsebytes(sent_messages[0])
    assert parsed.get_content_type() == "multipart/alternative"
    parts = list(parsed.walk())
    content_types = {part.get_content_type() for part in parts}
    assert "text/plain" in content_types
    assert "text/html" in content_types

    plain_part = next(part for part in parts if part.get_content_type() == "text/plain")
    html_part = next(part for part in parts if part.get_content_type() == "text/html")
    assert "analyst@example.com" in plain_part.get_content()
    assert PRIMARY_STRONG in html_part.get_content()
    assert "Open sign-in link" in html_part.get_content()
