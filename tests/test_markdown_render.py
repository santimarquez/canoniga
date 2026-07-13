from __future__ import annotations

from als_intel.markdown_render import extract_markdown_title, render_markdown_to_html


def test_render_markdown_headings_lists_and_bold() -> None:
    html = render_markdown_to_html(
        "# Mission\n\n## Objective\n\nAccelerate **ALS** research.\n\n- First item\n- Second item\n"
    )
    assert "<h2" in html
    assert "Objective" in html
    assert "<strong>ALS</strong>" in html
    assert "<ul" in html
    assert "First item" in html
    assert "# Mission" not in html


def test_render_markdown_table() -> None:
    html = render_markdown_to_html(
        "# Ethics\n\n| Role | Behavior |\n|------|----------|\n| Research | Summarize |\n"
    )
    assert "<table" in html
    assert "<th>Role</th>" in html
    assert "<td>Summarize</td>" in html


def test_render_markdown_inline_code_and_links() -> None:
    html = render_markdown_to_html("Use `GET /api/auth/audit` and [docs](/docs/MISSION.md).")
    assert "<code" in html
    assert "GET /api/auth/audit" in html
    assert 'href="/docs/MISSION.md"' in html


def test_extract_markdown_title() -> None:
    assert extract_markdown_title("# MTVL AI / Canoniga Mission\n\n## Objective") == (
        "MTVL AI / Canoniga Mission"
    )
