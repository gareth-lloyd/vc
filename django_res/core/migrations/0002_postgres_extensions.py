"""Enable the Postgres extensions the schema depends on.

`btree_gist` is required by the EXCLUDE constraints in
`reservations/0003_exclude_constraints` and `pricing/0003_exclude_constraints`
(they mix `=` and `&&` operators on the same gist index — only possible with
btree_gist).

`citext` backs `core.fields.CIEmailField` on Postgres (currently inert — no
column uses citext yet — but kept to match the established DB state).

Both operations subclass `CreateExtension`, which no-ops on non-Postgres
backends, so this migration is safe to run anywhere.
"""

from __future__ import annotations

from django.contrib.postgres.operations import BtreeGistExtension, CITextExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        BtreeGistExtension(),
        CITextExtension(),
    ]
