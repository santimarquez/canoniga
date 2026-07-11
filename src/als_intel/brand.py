from __future__ import annotations

import re
from pathlib import Path

LOGO_ALT = "MTVL AI"
LOGO_FILENAME = "mtvl-ai-logo.svg"
LOGO_URL_PATH = f"/assets/{LOGO_FILENAME}"
LOGO_PRIMARY_COLOR = "#003c90"
LOGO_ACCENT_COLOR = "#0f52ba"


def assets_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "assets"


def logo_path() -> Path:
    return assets_dir() / LOGO_FILENAME


def logo_svg_markup() -> str:
    path = logo_path()
    if not path.is_file():
        raise FileNotFoundError(f"Brand logo not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def logo_bytes() -> bytes:
    return logo_svg_markup().encode("utf-8")


def logo_mime_type() -> str:
    return "image/svg+xml"


def _size_svg(svg: str, *, height_px: int) -> str:
    return re.sub(
        r"<svg\b",
        (
            f'<svg height="{height_px}" width="{height_px}" '
            f'style="display:block;border:0;"'
        ),
        svg,
        count=1,
    )


def render_inline_logo(*, height_px: int) -> str:
    return _size_svg(logo_svg_markup(), height_px=height_px)


def render_email_logo(*, height_px: int = 36) -> str:
    return f'<div style="margin:0 0 4px;line-height:0;">{render_inline_logo(height_px=height_px)}</div>'
