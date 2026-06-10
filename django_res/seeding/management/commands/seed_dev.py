"""`./manage.py seed_dev` — generate realistic dev/staging data.

Additive by design: every run appends a fresh batch. Uniqueness is carried by
a per-run token + `factory.Sequence`, so re-running never collides on a unique
constraint. The transactional graph (Enquiry -> Quotation -> Booking ->
Payment) is built through the real service layer so statuses, events, holds
and pricing snapshots are production-faithful.

Three profiles are supported via `--profile`:

  happy  — every booking follows the conversion happy path; statuses span the
           five "everything is fine" terminal buckets via a modulo track plus
           an early-cancel bucket. Reproduces the pre-v2 seeder exactly so
           smoke tests stay deterministic.
  mixed  — default. Adds quotation lifecycle (SENT / EXPIRED / CANCELLED
           without booking), expired and declined bookings, concierge items,
           refunds, repeat guests + preferences, property archive/draft
           spread, multi-currency + FX, rooms/features/gallery/nearby/
           contacts/collections/notes/integrations/webhooks variety.
  chaos  — `mixed` with the dials cranked: more pre-approval, more refunds,
           wider repeat-guest pool, more property-status churn.

Hard-blocked unless `settings.SEED_DEV_ALLOWED` is true (False in base/
production, True in dev/test/staging). `--i-understand` does NOT override the
production block — it only documents intent.
"""

from __future__ import annotations

import random
from typing import Any

import factory.random
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.console import render_table
from core.factories import RUN_TOKEN
from seeding import stages as _stages_pkg  # noqa: F401  (registers all stages)
from seeding.context import _PROFILES, _SCALES, Profile, SeedContext
from seeding.registry import STAGES, StageReport
from seeding.runner import run_stages


class Command(BaseCommand):
    help = "Generate realistic dev/staging data (additive, service-driven)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--scale",
            choices=sorted(_SCALES),
            default="small",
            help="Preset batch size (default: small).",
        )
        parser.add_argument(
            "--profile",
            choices=[p.value for p in Profile],
            default=Profile.MIXED.value,
            help=(
                "Data shape: happy (uniform success path), mixed (default — "
                "lifecycle variety, refunds, concierge, preferences), or "
                "chaos (mixed with dials cranked)."
            ),
        )
        parser.add_argument("--properties", type=int, default=None, help="Override property count.")
        parser.add_argument("--bookings", type=int, default=None, help="Override booking count.")
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Faker/factory random seed for reproducible batches.",
        )
        parser.add_argument(
            "--no-dashboard-activity",
            action="store_false",
            dest="dashboard_activity",
            help=(
                "Skip the guaranteed dashboard cohorts (arrivals/departures "
                "today, NEW enquiries, awaiting-balance stays). For consumers "
                "that need the exact legacy output, e.g. exact-count tests."
            ),
        )
        parser.add_argument(
            "--i-understand",
            action="store_true",
            help="Acknowledge this writes fake data. Does NOT bypass the production block.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not getattr(settings, "SEED_DEV_ALLOWED", False):
            raise CommandError(
                "seed_dev is disabled here (SEED_DEV_ALLOWED is False). It is "
                "intentionally never runnable in production."
            )

        seed = options["seed"]
        if seed is not None:
            factory.random.reseed_random(seed)
            random.seed(seed)
            rng = random.Random(seed)
        else:
            rng = random.Random()

        knobs = _PROFILES[Profile(options["profile"])]
        scale = _SCALES[options["scale"]]
        ctx = SeedContext(
            rng=rng,
            knobs=knobs,
            n_properties=(
                options["properties"] if options["properties"] is not None else scale["properties"]
            ),
            n_bookings=(
                options["bookings"] if options["bookings"] is not None else scale["bookings"]
            ),
            n_users=scale["users"],
            dashboard_factor=scale["dashboard"] if options["dashboard_activity"] else 0,
        )

        reports = run_stages(ctx, STAGES)
        self._print_summary(reports, knobs.name)

    def _print_summary(self, reports: list[StageReport], profile_name: str) -> None:
        self.stdout.write(f"profile: {profile_name} (run token: {RUN_TOKEN})")
        header = ("stage", "created", "errors", "duration")
        rows = [(r.stage, r.created, len(r.errors), f"{r.duration_s:.2f}s") for r in reports]
        self.stdout.write(render_table(header, rows))
        for r in reports:
            if r.errors:
                self.stdout.write(self.style.ERROR(f"\nErrors in {r.stage}:"))
                for message in r.errors:
                    self.stdout.write(f"  {message}")
