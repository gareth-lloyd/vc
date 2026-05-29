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
from django.conf import settings
from django.http import StreamingHttpResponse
from django.test import Client, override_settings
from whitenoise import WhiteNoise

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


def test_media_urls_are_not_shadowed_by_spa(spa_root: Path) -> None:
    """Uploaded/seeded images live under `MEDIA_URL` and must not be eaten
    by the SPA history fallback.

    Regression for images failing to load in local dev: with `media/` absent
    from the catch-all's negative lookahead, a GET for an image matched the
    SPA fallback and returned the HTML shell (or a 404 once no build is
    present) instead of the file — so no image ever rendered. The media
    prefix must fall through to the media handler, not `spa_index`.
    """
    with override_settings(SPA_ROOT=spa_root):
        response = Client().get("/media/properties/2026/05/missing.jpg")

    # Not the SPA shell. (No build-less 200; a real-but-absent file is a 404.)
    assert response.status_code == 404


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


def test_whitenoise_does_not_serve_the_spa_shell(spa_root: Path) -> None:
    """WhiteNoise must not own the SPA shell — `spa_index` must.

    Recurring double-login regression: with `WHITENOISE_INDEX_FILE` enabled,
    WhiteNoiseMiddleware serves `index.html` for `/` *directly*, short-
    circuiting the view layer so `spa_index`'s `@ensure_csrf_cookie` never
    fires. A fresh visitor landing on `/` then has no `csrftoken` cookie and
    their first login POST is rejected by `CsrfViewMiddleware` — they have to
    submit twice. (The earlier `@ensure_csrf_cookie` fix only ever covered
    history-fallback routes like `/login`, which WhiteNoise has no file for.)

    The shell must flow through `spa_index`; WhiteNoise only serves the hashed
    assets under `WHITENOISE_ROOT`.
    """
    (spa_root / "assets").mkdir()
    (spa_root / "assets" / "app.js").write_text("//", encoding="utf-8")

    # Pin the policy off — re-enabling index serving reintroduces the bug.
    assert settings.WHITENOISE_INDEX_FILE is False

    served = WhiteNoise(
        lambda environ, start_response: [],
        root=str(spa_root),
        index_file=settings.WHITENOISE_INDEX_FILE,
    ).files
    assert "/assets/app.js" in served  # hashed assets: served by WhiteNoise
    assert "/" not in served  # the shell falls through to spa_index
