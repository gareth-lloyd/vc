"""The single-origin SPA fallback: Django serves the built frontend.

`spa_index` returns the SPA's `index.html` for any non-API/admin/static
path so client-side routes (deep links, refreshes) resolve. API and admin
routing must be untouched, and a missing build must not 500.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from django.http import StreamingHttpResponse
from django.test import Client, override_settings

_SENTINEL = "<!doctype html><title>VC SPA</title><div id=root></div>"


@pytest.fixture
def spa_root(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text(_SENTINEL, encoding="utf-8")
    return tmp_path


def _body(response: object) -> bytes:
    # spa_index returns a FileResponse (a StreamingHttpResponse); the test
    # client's response type doesn't expose streaming_content in stubs.
    streaming = cast(StreamingHttpResponse, response)
    return b"".join(cast(Iterator[bytes], streaming.streaming_content))


def test_root_serves_spa_index(spa_root: Path) -> None:
    with override_settings(SPA_ROOT=spa_root):
        response = Client().get("/")

    assert response.status_code == 200
    assert _SENTINEL.encode() in _body(response)


def test_client_side_deep_link_serves_spa_index(spa_root: Path) -> None:
    with override_settings(SPA_ROOT=spa_root):
        response = Client().get("/bookings/1")

    assert response.status_code == 200
    assert _SENTINEL.encode() in _body(response)


@pytest.mark.django_db
def test_api_routes_are_not_shadowed_by_spa(spa_root: Path) -> None:
    with override_settings(SPA_ROOT=spa_root):
        ok = Client().get("/api/health/")
        missing = Client().get("/api/does-not-exist")

    assert ok.status_code == 200
    assert ok.json() == {"status": "ok"}
    # An unknown API path stays a real 404 — not the SPA shell.
    assert missing.status_code == 404
    assert _SENTINEL.encode() not in missing.content


def test_missing_build_is_404_not_500(tmp_path: Path) -> None:
    """Local dev has no build (Vite proxy serves the SPA) — must not error."""
    with override_settings(SPA_ROOT=tmp_path / "does-not-exist"):
        response = Client().get("/")

    assert response.status_code == 404


def test_spa_index_sets_csrf_cookie(spa_root: Path) -> None:
    """The SPA shell must prime the `csrftoken` cookie.

    Regression for the double-login bug: without this, the first POST to
    `/auth/login` is rejected by CsrfViewMiddleware (no cookie → no header
    → 403), and only the second submit works because the failed first
    response is what sets the cookie.
    """
    with override_settings(SPA_ROOT=spa_root):
        response = Client().get("/login")

    assert response.status_code == 200
    assert "csrftoken" in response.cookies
