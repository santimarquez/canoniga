from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from als_intel.emails.theme import (
    ACCENT_BAR_WIDTH,
    BACKGROUND,
    BORDER,
    BUTTON_TEXT,
    FONT_STACK,
    MAX_WIDTH,
    MUTED,
    PRIMARY_STRONG,
    PRODUCT_NAME,
    PRODUCT_TAGLINE,
    SURFACE,
    TEXT,
)


def paragraph_style() -> str:
    return (
        f"margin:0 0 16px;font-family:{FONT_STACK};font-size:15px;line-height:1.6;"
        f"color:{MUTED};"
    )


def heading_style() -> str:
    return (
        f"margin:0 0 12px;font-family:{FONT_STACK};font-size:22px;line-height:1.3;"
        f"font-weight:600;color:{TEXT};"
    )


def render_paragraph(text: str) -> str:
    return f'<p style="{paragraph_style()}">{escape(text)}</p>'


def render_button(label: str, url: str) -> str:
    safe_label = escape(label)
    safe_url = escape(url, quote=True)
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:24px 0;">'
        "<tr><td>"
        f'<a href="{safe_url}" style="display:inline-block;padding:12px 24px;'
        f"background:{PRIMARY_STRONG};color:{BUTTON_TEXT};font-family:{FONT_STACK};"
        f'font-size:14px;font-weight:600;text-decoration:none;border-radius:8px;">'
        f"{safe_label}</a>"
        "</td></tr></table>"
    )


def render_link_fallback(url: str) -> str:
    safe_url = escape(url)
    p_style = (
        f"margin:0 0 16px;font-family:{FONT_STACK};font-size:13px;"
        f"line-height:1.5;color:{TEXT};word-break:break-all;"
    )
    return (
        f'<p style="{paragraph_style()}margin-bottom:8px;">Or copy this link:</p>'
        f'<p style="{p_style}">'
        f'<a href="{safe_url}" style="color:{PRIMARY_STRONG};text-decoration:underline;">'
        f"{safe_url}</a></p>"
    )


def render_email_layout(
    *,
    title: str,
    preheader: str,
    body_html: str,
    footer_html: str | None = None,
) -> str:
    year = datetime.now(timezone.utc).year
    default_footer = (
        f'<p style="margin:0;font-family:{FONT_STACK};font-size:12px;line-height:1.5;'
        f'color:{MUTED};">&copy; {year} {escape(PRODUCT_NAME)}. Open source project.</p>'
    )
    footer_block = footer_html if footer_html is not None else default_footer
    safe_title = escape(title)
    safe_preheader = escape(preheader)
    safe_product = escape(PRODUCT_NAME)
    safe_tagline = escape(PRODUCT_TAGLINE)

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{safe_title}</title>
  </head>
  <body style="margin:0;padding:0;background:{BACKGROUND};">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
      {safe_preheader}
    </div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
      style="background:{BACKGROUND};padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
            style="max-width:{MAX_WIDTH};background:{SURFACE};border:1px solid {BORDER};
            border-radius:8px;overflow:hidden;">
            <tr>
              <td width="{ACCENT_BAR_WIDTH}" style="background:{PRIMARY_STRONG};font-size:0;line-height:0;">
                &nbsp;
              </td>
              <td style="padding:32px 28px;">
                <p style="margin:0 0 4px;font-family:{FONT_STACK};font-size:20px;font-weight:600;
                  color:{TEXT};">{safe_product}</p>
                <p style="margin:0 0 24px;font-family:{FONT_STACK};font-size:11px;font-weight:600;
                  letter-spacing:0.12em;text-transform:uppercase;color:{PRIMARY_STRONG};">
                  {safe_tagline}
                </p>
                <h1 style="{heading_style()}">{safe_title}</h1>
                {body_html}
                <div style="margin-top:32px;padding-top:20px;border-top:1px solid {BORDER};">
                  {footer_block}
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
