"""Sync ``EmailTemplate`` rows from the on-disk seed files.

Idempotent. Discovers every ``<key>.subject.txt`` under
``comms/templates/comms/`` and, for each:

* Creates a ``version=1`` row if no template with that key exists.
* If an active row exists and its content matches the seed, no-op.
* If an active row exists and content differs, deactivates it and creates
  a new row at the next version (preserving the unique-active and
  unique (key, version) constraints).

The same function is called by the data migration in
``comms/migrations/0003_seed_templates.py`` so a fresh DB is fully
populated by ``migrate`` alone — no operator step required.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from comms.compilers import compile_mjml


@dataclass(frozen=True)
class SeedFile:
    key: str
    title: str
    subject: str
    body_mjml: str


def _humanize_key(key: str) -> str:
    """Derive a human-facing title from a dotted key.

    ``booking.confirmation`` -> ``Booking Confirmation``.
    """
    return key.replace(".", " ").replace("_", " ").title()


def _seed_dir(base_dir: Path | None = None) -> Path:
    if base_dir is not None:
        return base_dir
    return Path(__file__).resolve().parents[2] / "templates" / "comms"


def discover_seeds(base_dir: Path | None = None) -> list[SeedFile]:
    """Read every ``<key>.subject.txt`` file in the seed directory.

    The plaintext body is no longer authored — it's derived from the rendered
    HTML at send time — so only the subject and MJML body are read from disk.
    """
    directory = _seed_dir(base_dir)
    seeds: list[SeedFile] = []
    for subject_path in sorted(directory.glob("*.subject.txt")):
        key = subject_path.name.removesuffix(".subject.txt")
        body_mjml_path = directory / f"{key}.body.mjml"
        seeds.append(
            SeedFile(
                key=key,
                title=_humanize_key(key),
                subject=subject_path.read_text().rstrip("\n"),
                body_mjml=body_mjml_path.read_text() if body_mjml_path.exists() else "",
            )
        )
    return seeds


def _content_matches(template: Any, seed: SeedFile, field_names: set[str]) -> bool:
    if template.subject_template != seed.subject:
        return False
    if template.body_template_mjml != seed.body_mjml:
        return False
    # `title` only exists from migration 0011 onward; older frozen schemas (the
    # historical models the seed migrations run against) don't carry it.
    if "title" in field_names and template.title != seed.title:
        return False
    return True


def _seed_defaults(seed: SeedFile, field_names: set[str]) -> dict[str, Any]:
    """Build create() kwargs for whatever schema the model is currently at.

    This runs both as the live management command and from inside the seed data
    migrations, where the frozen historical model may still have the dropped
    ``body_template`` column and may lack ``title``. Historical models also lack
    the ``save()`` override that compiles MJML, so the compiled HTML is set
    explicitly here rather than relying on save().
    """
    defaults: dict[str, Any] = {
        "subject_template": seed.subject,
        "body_template_mjml": seed.body_mjml,
        "is_active": True,
    }
    if "title" in field_names:
        defaults["title"] = seed.title
    if "body_template_html" in field_names:
        defaults["body_template_html"] = compile_mjml(seed.body_mjml)
    if "body_template" in field_names:
        # Dropped from the live model in 0011 but NOT NULL in older frozen
        # schemas; the plaintext is derived at send time, so seed it empty.
        defaults["body_template"] = ""
    return defaults


def _next_version(EmailTemplate: Any, key: str) -> int:
    latest = (
        EmailTemplate.objects.filter(key=key)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
    )
    return (latest or 0) + 1


def sync_templates(base_dir: Path | None = None, model: Any = None) -> dict[str, int]:
    """Apply all seeds. Returns a count of created / updated / unchanged keys.

    Pass ``model`` (a frozen ``apps.get_model`` class) when calling from a data
    migration so reads/writes match the schema at that point in history; the
    live management command leaves it ``None`` and uses the current model.
    """
    EmailTemplate = model or apps.get_model("comms", "EmailTemplate")
    field_names = {f.name for f in EmailTemplate._meta.get_fields()}
    seeds = discover_seeds(base_dir)

    created = 0
    updated = 0
    unchanged = 0

    with transaction.atomic():
        for seed in seeds:
            active = EmailTemplate.objects.filter(key=seed.key, is_active=True).first()
            if active is not None and _content_matches(active, seed, field_names):
                unchanged += 1
                continue
            # Only compile MJML once we know we're writing a row — the unchanged
            # short-circuit above keeps a no-op resync from recompiling everything.
            defaults = _seed_defaults(seed, field_names)
            if active is not None:
                active.is_active = False
                active.save(update_fields=["is_active", "updated_at"])
                updated += 1
            else:
                created += 1
            EmailTemplate.objects.create(
                key=seed.key,
                version=_next_version(EmailTemplate, seed.key),
                **defaults,
            )

    return {"created": created, "updated": updated, "unchanged": unchanged}


class Command(BaseCommand):
    help = "Seed or update EmailTemplate rows from on-disk template files."

    def handle(self, *args: object, **options: object) -> None:
        result = sync_templates()
        self.stdout.write(
            self.style.SUCCESS(
                f"Templates: {result['created']} created, "
                f"{result['updated']} updated, "
                f"{result['unchanged']} unchanged."
            )
        )
