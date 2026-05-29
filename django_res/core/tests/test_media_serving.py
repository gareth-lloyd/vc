"""WhiteNoise-based media serving.

`MediaWhiteNoiseMiddleware` mounts `MEDIA_ROOT` under `MEDIA_URL` so uploaded
and seeded images are served by the same WhiteNoise layer as static assets and
the SPA build — in *every* environment, not just under DEBUG. This is what
makes seeded villa imagery render on staging (`DEBUG=False`), where Django's
dev-only `static()` route is a no-op.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings as django_settings
from django.http import HttpRequest, HttpResponse
from django.test import override_settings

from core.middleware import MediaWhiteNoiseMiddleware


def _noop_response(request: HttpRequest) -> HttpResponse:  # pragma: no cover - unused
    raise AssertionError("media requests must be served by the middleware")


def test_media_middleware_indexes_media_at_boot(tmp_path: Path) -> None:
    """Production-like (DEBUG off, no autorefresh): media present at boot is
    indexed and served under `MEDIA_URL`."""
    media = tmp_path / "media"
    (media / "properties" / "2026" / "05").mkdir(parents=True)
    (media / "properties" / "2026" / "05" / "hero.jpg").write_bytes(b"img")

    with override_settings(MEDIA_ROOT=media, MEDIA_URL="/media/", DEBUG=False):
        mw = MediaWhiteNoiseMiddleware(_noop_response, settings=django_settings)

    assert "/media/properties/2026/05/hero.jpg" in mw.files


def test_media_middleware_autorefresh_serves_runtime_files(tmp_path: Path) -> None:
    """Staging-like (autorefresh on): images written *after* boot — e.g. by a
    live `seed_dev` run — are served without a restart, and a missing file is
    not served (so the SPA fallback can return a real 404)."""
    media = tmp_path / "media"
    media.mkdir()

    with override_settings(
        MEDIA_ROOT=media,
        MEDIA_URL="/media/",
        DEBUG=False,
        WHITENOISE_AUTOREFRESH=True,
    ):
        mw = MediaWhiteNoiseMiddleware(_noop_response, settings=django_settings)
        (media / "late.jpg").write_bytes(b"img")  # written after middleware init

        assert mw.find_file("/media/late.jpg") is not None
        assert mw.find_file("/media/missing.jpg") is None
