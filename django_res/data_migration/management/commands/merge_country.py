"""Merge one Country into another by walking _meta.related_objects.

Same pattern as `accounts.models.contact.Contact.merge`: every FK that
points at the source country is rewritten to point at the target. Once the
source has zero references, it's hard-deleted.

Example:

    manage.py merge_country --from-legacy 24 --to-iso2 GB

Picks the source by `legacy_id='24'`, the target by `iso2='GB'`.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from properties.models.geo import Country


class Command(BaseCommand):
    help = "Merge one Country row into another by rewriting all FK references."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--from-legacy",
            required=True,
            help="legacy_id of the source country to merge",
        )
        parser.add_argument(
            "--to-iso2",
            required=True,
            help="iso2 of the target country",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without applying it.",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        source = Country.objects.filter(legacy_id=opts["from_legacy"]).first()
        if source is None:
            raise CommandError(f"No country with legacy_id={opts['from_legacy']!r}")
        target = Country.objects.filter(iso2=opts["to_iso2"].upper()).first()
        if target is None:
            raise CommandError(f"No country with iso2={opts['to_iso2']!r}")
        if target.pk == source.pk:
            raise CommandError("Source and target are the same row")

        self.stdout.write(
            f"Merging {source.name} (id={source.pk}, legacy={source.legacy_id}) "
            f"→ {target.name} (id={target.pk}, iso2={target.iso2})"
        )

        with transaction.atomic():
            total_rewritten = 0
            for rel in source._meta.related_objects:
                related_model = rel.related_model
                if related_model is None or isinstance(related_model, str):
                    continue
                if rel.many_to_many:
                    continue
                field_name = rel.field.name
                qs = related_model._default_manager.filter(**{field_name: source})
                if opts["dry_run"]:
                    affected = qs.count()
                else:
                    affected = qs.update(**{field_name: target})
                if not affected:
                    continue
                self.stdout.write(
                    f"  {related_model._meta.label}.{field_name}: rewriting {affected} rows"
                )
                total_rewritten += affected

            if opts["dry_run"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"Dry run: would rewrite {total_rewritten} rows then delete source"
                    )
                )
                raise CommandError("Dry run — rolling back")

            source.delete()
            self.stdout.write(
                self.style.SUCCESS(f"Rewrote {total_rewritten} rows and deleted source country.")
            )
