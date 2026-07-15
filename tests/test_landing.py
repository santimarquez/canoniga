from __future__ import annotations

import pytest

from als_intel.static_frontend import spa_available, serve_spa_or_static


@pytest.mark.skipif(not spa_available(), reason="frontend build not present")
def test_spa_serves_landing_route() -> None:
    from http.server import BaseHTTPRequestHandler
    from io import BytesIO
    from unittest.mock import MagicMock

    handler = MagicMock(spec=BaseHTTPRequestHandler)
    handler.wfile = BytesIO()
    assert serve_spa_or_static(handler, "/") is True
    body = handler.wfile.getvalue().decode("utf-8")
    assert 'id="app"' in body


def test_landing_module_still_exports_app_route() -> None:
    from als_intel.landing import APP_ROUTE

    assert APP_ROUTE == "/app"
