# Email templates

Branded HTML + plain-text emails for MTVL AI. Stdlib only — no extra dependencies.

## Architecture

```
theme.py          Brand colors, fonts, product copy
layout.py         Base layout + shared HTML helpers
{template}.py     One builder per email type
auth.py / ...     Sender wires EmailContent into EmailMessage
```

Each template returns `EmailContent(subject, plain_text, html)`.

## Brand tokens

Source of truth: [`theme.py`](theme.py). Mirrors the web UI login page.

| Token | Value | Usage |
|-------|-------|-------|
| `PRIMARY_STRONG` | `#003c90` | Accent bar, CTA button |
| `PRIMARY` | `#0f52ba` | Links |
| `BACKGROUND` | `#f8fafc` | Outer background |
| `SURFACE` | `#ffffff` | Card background |
| `BORDER` | `#e2e8f0` | Card border |
| `TEXT` | `#191c1e` | Headings |
| `MUTED` | `#54647a` | Body copy |
| `PRODUCT_NAME` | MTVL AI | Header |
| `PRODUCT_TAGLINE` | Open Source Intelligence | Subtitle |

## How to add a new email

1. Create `src/als_intel/emails/{name}.py`
2. Define `build_{name}_email(...) -> EmailContent` with `subject`, `plain_text`, and `html`
3. Use `render_email_layout()` for HTML; reuse theme constants and layout helpers
4. Write `plain_text` with the same facts as HTML (links, dates, recipient)
5. Export from `emails/__init__.py`
6. Wire the sender in the calling module (e.g. `auth.py`)
7. Add tests in `tests/test_emails.py` (plain text, HTML branding, key content)
8. Preview in Mailpit before merging

## HTML rules

- Table-based layout for email client compatibility
- Inline CSS only — no `<style>` blocks or external stylesheets
- No external images or web fonts (use `FONT_STACK` fallback)
- Max width 600px (`MAX_WIDTH` in theme)
- Always include a plain-text alternative

## Shared helpers

From `layout.py`:

- `render_email_layout(title, preheader, body_html)` — full HTML document
- `render_button(label, url)` — primary CTA button
- `render_paragraph(text)` — body copy paragraph
- `render_link_fallback(url)` — raw URL below CTA
- `paragraph_style()` — inline style string for custom markup

## Template skeleton

```python
from als_intel.emails.layout import render_button, render_email_layout, render_paragraph
from als_intel.emails.types import EmailContent


def build_example_email(*, recipient_email: str, action_url: str) -> EmailContent:
    subject = "Your subject line"
    plain_text = (
        f"Hello,\n\n"
        f"Do the thing:\n{action_url}\n"
    )
    body_html = (
        render_paragraph(f"We have an update for {recipient_email}.")
        + render_button("Do the thing", action_url)
    )
    html = render_email_layout(
        title="Headline shown in email",
        preheader="Short inbox preview line",
        body_html=body_html,
    )
    return EmailContent(subject=subject, plain_text=plain_text, html=html)
```

## Sending pattern

```python
from email.message import EmailMessage

content = build_example_email(recipient_email=email, action_url=url)
msg = EmailMessage()
msg["Subject"] = content.subject
msg["From"] = smtp_from
msg["To"] = email
msg.set_content(content.plain_text)
msg.add_alternative(content.html, subtype="html")
smtp.send_message(msg)
```

## Testing

Required per template:

- Plain text contains key facts (recipient, links, dates)
- HTML contains brand colors, product name, and CTA
- Sender test confirms `multipart/alternative` with both parts

Run tests:

```bash
make test
# or
pytest tests/test_emails.py -q
```

## Preview in Mailpit

```bash
make docker-dev-up
```

1. Request a magic link at http://localhost:8000
2. Open http://localhost:8025 to view the captured HTML email
