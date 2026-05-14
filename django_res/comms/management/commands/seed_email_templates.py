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


@dataclass(frozen=True)
class SeedFile:
    key: str
    subject: str
    body_text: str
    body_mjml: str


def _seed_dir(base_dir: Path | None = None) -> Path:
    if base_dir is not None:
        return base_dir
    return Path(__file__).resolve().parents[2] / "templates" / "comms"


def discover_seeds(base_dir: Path | None = None) -> list[SeedFile]:
    """Read every ``<key>.subject.txt`` file in the seed directory."""
    directory = _seed_dir(base_dir)
    seeds: list[SeedFile] = []
    for subject_path in sorted(directory.glob("*.subject.txt")):
        key = subject_path.name.removesuffix(".subject.txt")
        body_text_path = directory / f"{key}.body.txt"
        body_mjml_path = directory / f"{key}.body.mjml"
        seeds.append(
            SeedFile(
                key=key,
                subject=subject_path.read_text().rstrip("\n"),
                body_text=body_text_path.read_text() if body_text_path.exists() else "",
                body_mjml=body_mjml_path.read_text() if body_mjml_path.exists() else "",
            )
        )
    return seeds


def _content_matches(template: Any, seed: SeedFile) -> bool:
    return (
        template.subject_template == seed.subject
        and template.body_template == seed.body_text
        and template.body_template_mjml == seed.body_mjml
    )


def _next_version(EmailTemplate: Any, key: str) -> int:
    latest = (
        EmailTemplate.objects.filter(key=key)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
    )
    return (latest or 0) + 1


def sync_templates(base_dir: Path | None = None) -> dict[str, int]:
    """Apply all seeds. Returns a count of created / updated / unchanged keys."""
    EmailTemplate = apps.get_model("comms", "EmailTemplate")
    seeds = discover_seeds(base_dir)

    created = 0
    updated = 0
    unchanged = 0

    with transaction.atomic():
        for seed in seeds:
            active = EmailTemplate.objects.filter(key=seed.key, is_active=True).first()
            if active is None:
                EmailTemplate.objects.create(
                    key=seed.key,
                    version=_next_version(EmailTemplate, seed.key),
                    subject_template=seed.subject,
                    body_template=seed.body_text,
                    body_template_mjml=seed.body_mjml,
                    is_active=True,
                )
                created += 1
                continue
            if _content_matches(active, seed):
                unchanged += 1
                continue
            active.is_active = False
            active.save(update_fields=["is_active", "updated_at"])
            EmailTemplate.objects.create(
                key=seed.key,
                version=_next_version(EmailTemplate, seed.key),
                subject_template=seed.subject,
                body_template=seed.body_text,
                body_template_mjml=seed.body_mjml,
                is_active=True,
            )
            updated += 1

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
