"""Enable the Postgres extensions the schema depends on.

`btree_gist` is required by the EXCLUDE constraints in
`reservations/0002_postgres_exclude_constraints` and
`pricing/0003_raterule_exclude_constraint` (they mix `=` and `&&` operators
on the same index — only possible with gist + btree_gist).

`citext` backs `core.fields.CIEmailField` on Postgres.

Both operations subclass `CreateExtension`, which no-ops on non-Postgres
backends, so this migration is safe to run anywhere.
"""

from __future__ import annotations

from django.contrib.postgres.operations import BtreeGistExtension, CITextExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_systemsettings"),
    ]

    operations = [
        BtreeGistExtension(),
        CITextExtension(),
    ]
