from __future__ import annotations

import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from als_intel.brand import assets_dir

DIST_DIR = assets_dir() / "dist"
REPO_ASSETS_DIR = assets_dir()
SPA_ENTRY = DIST_DIR / "index.html"
VITE_BASE = "/app-assets/"

BRAND_ASSET_PATHS = {
    "/assets/mtvl-ai-logo.svg",
    "/assets/mtvl-ai-logo-lettermark.png",
    "/assets/landing-dashboard-mockup.png",
}


def spa_available() -> bool:
    return SPA_ENTRY.is_file()


def _safe_repo_asset_path(url_path: str) -> Path | None:
    if not url_path.startswith("/assets/"):
        return None
    if url_path.startswith("/assets/dist/"):
        return None
    relative = url_path[len("/assets/") :].lstrip("/")
    if not relative or ".." in Path(relative).parts:
        return None
    candidate = (REPO_ASSETS_DIR / relative).resolve()
    root = REPO_ASSETS_DIR.resolve()
    if candidate.is_file() and root in candidate.parents:
        return candidate
    return None


def serve_repo_asset(handler: BaseHTTPRequestHandler, path: str) -> bool:
    """Serve static files from the repo assets/ directory at /assets/*."""
    asset = _safe_repo_asset_path(path)
    if asset is None:
        return False
    data = asset.read_bytes()
    mime_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", mime_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "public, max-age=86400")
    handler.end_headers()
    handler.wfile.write(data)
    return True


def _safe_dist_path(url_path: str) -> Path | None:
    if url_path in {"/", ""}:
        return SPA_ENTRY

    candidates: list[Path] = []
    if url_path.startswith(VITE_BASE):
        relative = url_path[len(VITE_BASE) :].lstrip("/")
        candidates.append(DIST_DIR / relative)
    if url_path.startswith("/assets/dist/"):
        relative = url_path[len("/assets/dist/") :].lstrip("/")
        candidates.append(DIST_DIR / relative)

    dist_root = DIST_DIR.resolve()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and dist_root in resolved.parents:
            return resolved
    return None


def is_spa_route(path: str) -> bool:
    if path.startswith("/api/"):
        return False
    if path == "/healthz":
        return False
    if path in BRAND_ASSET_PATHS:
        return False
    if path.startswith("/assets/") and not path.startswith("/assets/dist/"):
        return False
    return True


def serve_spa_or_static(handler: BaseHTTPRequestHandler, path: str) -> bool:
    """Serve built frontend assets or SPA index. Returns True when handled."""
    if not spa_available():
        return False

    asset = _safe_dist_path(path)
    if asset is not None and asset.name != "index.html":
        data = asset.read_bytes()
        mime_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", mime_type)
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "public, max-age=86400")
        handler.end_headers()
        handler.wfile.write(data)
        return True

    if is_spa_route(path):
        data = SPA_ENTRY.read_bytes()
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "no-cache")
        handler.end_headers()
        handler.wfile.write(data)
        return True

    return False
