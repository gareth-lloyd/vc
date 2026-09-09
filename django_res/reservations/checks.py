"""System checks for the contract pipeline's environment (GAP-094 retro).

`auto_generate_contract` swallows every failure and only logs; there is no
worker and no alerting. So an environment fault — WeasyPrint's native
toolchain missing from the image — would silently mean no guest gets a
contract. This check makes the fault loud on every `manage.py` command that
keeps the default `requires_system_checks`: `migrate` (Render's pre-deploy,
which fails the deploy on an `Error`), `makemigrations`, `runserver` (each
autoreload) and every custom command. Not `shell`/`dbshell` (they opt out),
not `collectstatic` (staticfiles tag only), and never the web or worker
processes, which run no checks.

It runs on every `runserver` reload, so it must stay an import probe — never
a render.

Why there is no storage check: every shipped non-DEBUG settings module binds
the `documents` alias to S3 unconditionally and refuses to import without
`DOCUMENTS_S3_BUCKET` (`settings/production.py`), which is the fail-fast; a
check on the resolved storage class could only ever fire under the test
settings.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Warning, register

from core.pdf import native_toolchain_error

TAG = "reservations"

_NATIVE_HINT = (
    "WeasyPrint needs Pango/HarfBuzz and a font. macOS: `brew install pango "
    "harfbuzz libffi` (settings seed DYLD_FALLBACK_LIBRARY_PATH with the Homebrew "
    "lib dir; export it yourself to override). Debian/Render image: "
    "`libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core` — "
    "see django_res/CLAUDE.md."
)


@register(TAG)
def check_pdf_toolchain(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """E001 / W001 — the PDF renderer's native libraries (and a font) load.

    An `Error` outside DEBUG so a deploy without them fails at `migrate`
    instead of every confirmation silently producing no contract; only a
    `Warning` under DEBUG so a pango-less dev is not locked out of
    `runserver`.
    """
    failure = native_toolchain_error()
    if failure is None:
        return []
    msg = (
        f"WeasyPrint cannot load its native toolchain ({failure}); booking contracts cannot render."
    )
    if settings.DEBUG:
        return [Warning(msg, hint=_NATIVE_HINT, id="reservations.W001")]
    return [Error(msg, hint=_NATIVE_HINT, id="reservations.E001")]
