from __future__ import annotations

from als_intel.emails.layout import (
    render_button,
    render_email_layout,
    render_link_fallback,
    render_paragraph,
)
from als_intel.emails.theme import PRODUCT_NAME
from als_intel.emails.types import EmailContent
from als_intel.i18n import normalize_locale, t as translate


def build_magic_link_email(
    *,
    magic_link: str,
    expires_minutes: int,
    recipient_email: str,
    locale: str = "en",
) -> EmailContent:
    safe_locale = normalize_locale(locale) or "en"
    safe_email = recipient_email.strip()
    subject = translate(
        safe_locale,
        "email.magic_link_subject",
        product=PRODUCT_NAME,
    )
    preheader = translate(
        safe_locale,
        "email.magic_link_preheader",
        minutes=expires_minutes,
    )

    plain_text = (
        translate(safe_locale, "email.magic_link_title", product=PRODUCT_NAME)
        + "\n\n"
        + translate(safe_locale, "email.magic_link_plain_intro", email=safe_email)
        + "\n\n"
        + translate(safe_locale, "email.magic_link_plain_open")
        + f"\n{magic_link}\n\n"
        + translate(safe_locale, "email.magic_link_plain_expiry", minutes=expires_minutes)
        + "\n"
        + translate(safe_locale, "email.magic_link_plain_ignore")
    )

    body_html = (
        render_paragraph(translate(safe_locale, "email.magic_link_intro", email=safe_email))
        + render_paragraph(translate(safe_locale, "email.magic_link_cta_intro"))
        + render_button(translate(safe_locale, "email.magic_link_button"), magic_link)
        + render_link_fallback(magic_link)
        + render_paragraph(
            translate(safe_locale, "email.magic_link_expiry", minutes=expires_minutes)
        )
    )

    html = render_email_layout(
        title=translate(safe_locale, "email.magic_link_title", product=PRODUCT_NAME),
        preheader=preheader,
        body_html=body_html,
    )

    return EmailContent(subject=subject, plain_text=plain_text, html=html)
