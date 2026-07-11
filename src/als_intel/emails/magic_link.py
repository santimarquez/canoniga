from __future__ import annotations

from als_intel.emails.layout import (
    render_button,
    render_email_layout,
    render_link_fallback,
    render_paragraph,
)
from als_intel.emails.theme import PRODUCT_NAME
from als_intel.emails.types import EmailContent


def build_magic_link_email(
    *,
    magic_link: str,
    expires_minutes: int,
    recipient_email: str,
) -> EmailContent:
    subject = f"Sign in to {PRODUCT_NAME}"
    preheader = f"Your secure sign-in link expires in {expires_minutes} minutes"
    safe_email = recipient_email.strip()

    plain_text = (
        f"Sign in to {PRODUCT_NAME}\n\n"
        f"We received a request to sign in as {safe_email}.\n\n"
        f"Open this secure link to continue:\n{magic_link}\n\n"
        f"This link expires in {expires_minutes} minutes.\n"
        "If you did not request this email, you can safely ignore it."
    )

    body_html = (
        render_paragraph(f"We received a request to sign in as {safe_email}.")
        + render_paragraph("Click the button below to open your secure sign-in link.")
        + render_button("Open sign-in link", magic_link)
        + render_link_fallback(magic_link)
        + render_paragraph(
            f"This link expires in {expires_minutes} minutes. "
            "If you did not request this email, you can safely ignore it."
        )
    )

    html = render_email_layout(
        title=f"Sign in to {PRODUCT_NAME}",
        preheader=preheader,
        body_html=body_html,
    )

    return EmailContent(subject=subject, plain_text=plain_text, html=html)
