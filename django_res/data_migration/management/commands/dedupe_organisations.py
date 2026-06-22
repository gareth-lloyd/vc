"""Report near-duplicate organisations for human review (GAP-046).

The company→Organisation backfill (`organisation_for_company_name`) dedupes only
EXACT matches after case/whitespace normalisation. Genuine near-duplicates —
"Dune Travel" vs "Dune Travel Ltd", a typo, a trailing "(old)" — are deliberately
left for a human to fold via `POST /organisations/{id}:merge`. This command
surfaces those clusters using stdlib fuzzy matching.

It is **read-only**: it never merges, never writes. There is no `--apply` —
auto-merging companies is exactly what the GAP-046 owner forbade.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from django.core.management.base import BaseCommand

from accounts.models import Organisation

_DEFAULT_THRESHOLD = 0.85


class Command(BaseCommand):
    help = "Report clusters of near-duplicate organisations (read-only; never merges)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--threshold",
            type=float,
            default=_DEFAULT_THRESHOLD,
            help=f"Similarity ratio 0-1 to cluster two names (default {_DEFAULT_THRESHOLD}).",
        )
        parser.add_argument(
            "--org-type",
            default=None,
            help="Restrict to one org_type (e.g. agency); default compares all.",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        qs = Organisation.objects.all().order_by("name")
        if opts["org_type"]:
            qs = qs.filter(org_type=opts["org_type"])
        orgs = list(qs.values_list("pk", "name"))

        clusters = self._cluster(orgs, opts["threshold"])
        if not clusters:
            self.stdout.write(self.style.SUCCESS("No near-duplicate organisations found."))
            return

        for cluster in clusters:
            self.stdout.write("Possible duplicates:")
            for pk, name in cluster:
                self.stdout.write(f"  #{pk}  {name}")
            self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                f"{len(clusters)} cluster(s) of possible duplicates. Review and fold with "
                "`POST /organisations/<id>:merge`. This command wrote nothing."
            )
        )

    @staticmethod
    def _cluster(orgs: list[tuple[int, str]], threshold: float) -> list[list[tuple[int, str]]]:
        """Greedy union-find over pairwise name similarity (case-insensitive).

        O(n²) — fine for the few thousand orgs a backfill produces. Returns only
        clusters with more than one member, each sorted by name.
        """
        parent = {pk: pk for pk, _ in orgs}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            parent[find(a)] = find(b)

        for i in range(len(orgs)):
            pk_i, name_i = orgs[i]
            key_i = name_i.casefold()
            for j in range(i + 1, len(orgs)):
                pk_j, name_j = orgs[j]
                if SequenceMatcher(None, key_i, name_j.casefold()).ratio() >= threshold:
                    union(pk_i, pk_j)

        groups: dict[int, list[tuple[int, str]]] = {}
        for pk, name in orgs:
            groups.setdefault(find(pk), []).append((pk, name))
        return [sorted(g, key=lambda t: t[1]) for g in groups.values() if len(g) > 1]
