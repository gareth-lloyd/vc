"""One-shot system foundations: currencies + FX, SMTP profile, email templates,
multiple TermsVersions (one ACTIVE + 2 superseded).

Only fires when `knobs.do_system_setup` is True. The legacy `happy` profile
leaves this off so the deterministic baseline tests stay byte-for-byte
unchanged; mixed/chaos turn it on for the full multi-currency picture.

Where the canonical row already exists (e.g. via a previous run, or a
fixture/test conftest), the stage reuses it via `get_or_create`. Additive
reruns must not collide on a unique constraint.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import cast

from comms.management.commands.seed_email_templates import sync_templates
from comms.models import SmtpProfile
from core.seed.context import SeedContext
from core.seed.registry import Stage, register
from pricing.factories import CurrencyFactory
from pricing.models import FxRate
from reservations.factories import TermsVersionFactory
from reservations.models.terms import TermsVersion

# Cross-rates we want present. Real values are not load-bearing for seeded
# data — operators just need something on every (base, quote) edge.
_FX_MATRIX: tuple[tuple[str, str, str], ...] = (
    ("GBP", "EUR", "1.17"),
    ("GBP", "USD", "1.27"),
    ("EUR", "GBP", "0.86"),
    ("EUR", "USD", "1.08"),
    ("USD", "GBP", "0.79"),
    ("USD", "EUR", "0.92"),
)


def _run(ctx: SeedContext) -> int:
    made = 0

    # Currencies: always ensure GBP exists; if the profile asked for the full
    # setup, also seed EUR / USD so downstream stages can spread across them.
    gbp = CurrencyFactory(spec=("GBP", "Pound sterling", "£"))
    ctx.currencies["GBP"] = gbp
    ctx.default_currency = gbp
    made += 1

    # Always ensure at least one published TermsVersion exists — every booking
    # the seeder opens needs one. Mixed/chaos extend this to three below.
    legacy_terms = cast(TermsVersion, TermsVersionFactory())
    legacy_terms.publish()
    ctx.terms = [legacy_terms]
    made += 1

    if not ctx.knobs.do_system_setup:
        return made

    eur = CurrencyFactory(spec=("EUR", "Euro", "€"))
    usd = CurrencyFactory(spec=("USD", "US dollar", "$"))
    ctx.currencies["EUR"] = eur
    ctx.currencies["USD"] = usd
    made += 2

    # FX matrix: append today's row for every cross-rate. Constraint is
    # (base, quote, as_of) unique — `get_or_create` keeps additive reruns
    # idempotent on the same day.
    for base_code, quote_code, rate in _FX_MATRIX:
        _, created = FxRate.objects.get_or_create(
            base=ctx.currencies[base_code],
            quote=ctx.currencies[quote_code],
            as_of=ctx.today,
            defaults={"rate": Decimal(rate)},
        )
        # Also drop a row a week ago so the "history" tab has > 1 entry.
        _, created_hist = FxRate.objects.get_or_create(
            base=ctx.currencies[base_code],
            quote=ctx.currencies[quote_code],
            as_of=ctx.today - timedelta(days=7),
            defaults={"rate": Decimal(rate)},
        )
        made += int(created) + int(created_hist)

    # SMTP: one system profile, idempotent on the partial unique constraint.
    if not SmtpProfile.objects.filter(scope="system", is_active=True).exists():
        SmtpProfile.objects.create(
            name="System (seeded)",
            scope="system",
            owner=None,
            host="smtp.example.com",
            port=587,
            username="system",
            encrypted_password="seedpw",
            use_tls=True,
            from_email="noreply@villacollective.test",
        )
        made += 1

    # Email templates: sync every on-disk template so the seeder mirrors
    # what `migrate` does on a fresh DB. Idempotent — keys whose active row
    # already matches the seed file are skipped. Earlier this stage seeded
    # a hardcoded subset, which drifted out of sync with the keys the comms
    # signal handlers actually dispatch (e.g. `booking.confirmation`).
    sync_result = sync_templates()
    made += sync_result["created"] + sync_result["updated"]

    # Extra TermsVersions: one freshly-published current + the legacy row
    # demoted to historical. `publish()` flips this row to current and
    # demotes the previous one.
    superseded = cast(TermsVersion, TermsVersionFactory())
    superseded.publish()
    current = cast(TermsVersion, TermsVersionFactory())
    current.publish()
    ctx.terms = [current, superseded, *ctx.terms]
    made += 2
    return made


register(Stage(name="system_setup", run=_run))
