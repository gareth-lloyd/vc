"""`./manage.py bootstrap_wordpress_user` — WP inbound service user + token.

Idempotently converges the WordPress service user
(`settings.WORDPRESS_SERVICE_EMAIL`) to its locked-down shape — active,
non-staff, non-superuser, unusable password — and ensures its DRF authtoken
exists. The token is the only credential; the command prints it once so it can
be copied into the WP host's `wp-config.php` (never the WP database).

`--rotate` replaces the token in place (design: generate new, update
wp-config, old one is gone) — run it if the token ever leaks.

Lives here (not `integrations/services/`) because the service layer is
contractually rest_framework-free and this needs `authtoken.models.Token`.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from rest_framework.authtoken.models import Token

from accounts.models import User

logger = structlog.get_logger(__name__)


def ensure_wordpress_service_user(*, rotate: bool = False) -> tuple[User, Token, bool]:
    """Converge the service user + token; returns (user, token, token_created)."""
    # UserManager normalises emails to lowercase and looks them up iexact;
    # match that here so a mixed-case env value can't mint a case-variant twin.
    email = settings.WORDPRESS_SERVICE_EMAIL.lower()
    user, _ = User.objects.get_or_create(email=email)
    dirty = []
    for field, wanted in (("is_active", True), ("is_staff", False), ("is_superuser", False)):
        if getattr(user, field) != wanted:
            setattr(user, field, wanted)
            dirty.append(field)
    if user.has_usable_password():
        user.set_unusable_password()
        dirty.append("password")
    if dirty:
        user.save(update_fields=dirty)

    with transaction.atomic():
        if rotate:
            Token.objects.filter(user=user).delete()
        token, token_created = Token.objects.get_or_create(user=user)
    if token_created:
        logger.info("integrations.wordpress_token_issued", service_user_id=user.pk, rotated=rotate)
    return user, token, token_created


class Command(BaseCommand):
    help = "Create/repair the WordPress inbound service user and print its API token."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--rotate",
            action="store_true",
            help="Replace the existing token (invalidates the old one immediately).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        user, token, token_created = ensure_wordpress_service_user(rotate=options["rotate"])
        state = "new" if token_created else "existing"
        self.stdout.write(f"Service user: {user.email}")
        self.stdout.write(f"Token ({state}): {token.key}")
        self.stdout.write("Store in wp-config.php as define('VC_RES_API_TOKEN', '<token>').")
