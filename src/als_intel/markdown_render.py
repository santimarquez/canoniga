from __future__ import annotations

import html
import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_UL_ITEM_RE = re.compile(r"^[-*]\s+")
_OL_ITEM_RE = re.compile(r"^\d+\.\s+")
_TABLE_ROW_RE = re.compile(r"^\|.+\|$")
_TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BLOCK_SEP_RE = re.compile(r"\n\s*\n")


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = _INLINE_CODE_RE.sub(
        r'<code class="doc-inline-code">\1</code>',
        escaped,
    )
    escaped = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    return _LINK_RE.sub(
        r'<a href="\2" class="doc-link">\1</a>',
        escaped,
    )


def _render_heading(line: str) -> str:
    match = _HEADING_RE.match(line.strip())
    if not match:
        return f"<p>{_inline(line)}</p>"
    level = len(match.group(1))
    html_level = min(level, 6)
    return f"<h{html_level} class=\"doc-heading\">{_inline(match.group(2))}</h{html_level}>"


def _render_list(block: str) -> str:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        return ""
    ordered = bool(_OL_ITEM_RE.match(lines[0]))
    tag = "ol" if ordered else "ul"
    class_name = "doc-ol" if ordered else "doc-ul"
    items: list[str] = []
    for line in lines:
        if ordered:
            content = _OL_ITEM_RE.sub("", line, count=1)
        else:
            content = _UL_ITEM_RE.sub("", line, count=1)
        items.append(f"<li>{_inline(content)}</li>")
    return f"<{tag} class=\"{class_name}\">{''.join(items)}</{tag}>"


def _render_table(block: str) -> str:
    rows = [line.strip() for line in block.splitlines() if line.strip()]
    if len(rows) < 2:
        return f"<p>{_inline(block)}</p>"
    header_cells = [cell.strip() for cell in rows[0].strip("|").split("|")]
    body_rows = rows[2:] if _TABLE_SEP_RE.match(rows[1]) else rows[1:]
    thead = "".join(f"<th>{_inline(cell)}</th>" for cell in header_cells)
    tbody_parts: list[str] = []
    for row in body_rows:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        tbody_parts.append(
            "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in cells) + "</tr>"
        )
    return (
        '<div class="doc-table-wrap"><table class="doc-table">'
        f"<thead><tr>{thead}</tr></thead>"
        f"<tbody>{''.join(tbody_parts)}</tbody>"
        "</table></div>"
    )


def _split_blocks(text: str) -> list[str]:
    return [block.strip() for block in _BLOCK_SEP_RE.split(text.strip()) if block.strip()]


def extract_markdown_title(text: str) -> str | None:
    for line in text.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    return None


def render_markdown_to_html(text: str, *, skip_top_heading: bool = True) -> str:
    lines = text.splitlines()
    body_lines = lines
    if skip_top_heading:
        for index, line in enumerate(lines):
            heading_match = _HEADING_RE.match(line.strip())
            if heading_match and len(heading_match.group(1)) == 1:
                body_lines = lines[index + 1 :]
                break

    blocks = _split_blocks("\n".join(body_lines))
    parts: list[str] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        first_line = block.splitlines()[0].strip()
        if _TABLE_ROW_RE.match(first_line):
            table_blocks = [block]
            while index + 1 < len(blocks) and _TABLE_ROW_RE.match(
                blocks[index + 1].splitlines()[0].strip()
            ):
                index += 1
                table_blocks.append(blocks[index])
            parts.append(_render_table("\n".join(table_blocks)))
        elif _HEADING_RE.match(first_line):
            parts.append(_render_heading(first_line))
        elif _UL_ITEM_RE.match(first_line) or _OL_ITEM_RE.match(first_line):
            parts.append(_render_list(block))
        else:
            paragraph = " ".join(line.strip() for line in block.splitlines())
            parts.append(f"<p class=\"doc-paragraph\">{_inline(paragraph)}</p>")
        index += 1
    return "\n".join(parts)
