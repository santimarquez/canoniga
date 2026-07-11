"""Branded HTML email templates for MTVL AI.

See README.md in this package for how to add new email templates.
"""

from als_intel.emails.layout import (
    paragraph_style,
    render_button,
    render_email_layout,
    render_link_fallback,
    render_paragraph,
)
from als_intel.emails.magic_link import build_magic_link_email
from als_intel.emails.types import EmailContent

__all__ = [
    "EmailContent",
    "build_magic_link_email",
    "paragraph_style",
    "render_button",
    "render_email_layout",
    "render_link_fallback",
    "render_paragraph",
]
