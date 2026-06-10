"""Delete `RateRule.priority`; card order becomes the only rate precedence.

Within-card overlap is now forbidden unconditionally: the per-priority
EXCLUDE constraint (0003) is replaced by `raterule_no_overlap`, which drops
the `priority WITH =` arm. Legacy-loaded rules predate load-time overlap
resolution (they were stamped `priority = legacy_id % 65535` purely to dodge
the old constraint), so they are deleted here and repopulated by re-running
`loadlegacy rate_plan rate_rule` — the loader now resolves overlaps itself.

Postgres-only SQL is vendor-guarded like 0003. Adding the new constraint is
also the safety check — it fails loudly if any overlap survived.
"""

from __future__ import annotations

from django.db import migrations

_OLD_CONSTRAINT_SQL_PG = (
    "ALTER TABLE pricing_raterule "
    "ADD CONSTRAINT raterule_no_overlap_same_priority "
    "EXCLUDE USING gist ("
    "card_id WITH =, "
    "daterange(date_from, date_to, '[]') WITH &&, "
    "int4range(min_party, max_party, '[]') WITH &&, "
    "priority WITH ="
    ");"
)

_NEW_CONSTRAINT_SQL_PG = (
    "ALTER TABLE pricing_raterule "
    "ADD CONSTRAINT raterule_no_overlap "
    "EXCLUDE USING gist ("
    "card_id WITH =, "
    "daterange(date_from, date_to, '[]') WITH &&, "
    "int4range(min_party, max_party, '[]') WITH &&"
    ");"
)


def _delete_legacy_rules(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    """Purge legacy-loaded rules; `loadlegacy rate_rule` repopulates them
    overlap-free. UI-created rules (legacy_id NULL) are kept."""
    rate_rule = apps.get_model("pricing", "RateRule")
    rate_rule.objects.filter(legacy_id__isnull=False).delete()


def _drop_old_constraint(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    # Must run before the column drop: Postgres refuses to drop a column an
    # EXCLUDE constraint uses.
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "ALTER TABLE pricing_raterule DROP CONSTRAINT IF EXISTS raterule_no_overlap_same_priority;"
    )


def _readd_old_constraint(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_OLD_CONSTRAINT_SQL_PG)


def _add_new_constraint(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_NEW_CONSTRAINT_SQL_PG)


def _drop_new_constraint(apps, schema_editor) -> None:  # type: ignore[no-untyped-def]
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "ALTER TABLE pricing_raterule DROP CONSTRAINT IF EXISTS raterule_no_overlap;"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0009_remove_ratecard_changeover_weekday"),
        ("core", "0004_postgres_extensions"),  # btree_gist for the EXCLUDE constraint
    ]

    operations = [
        # Reverse is a no-op: repopulate with `loadlegacy rate_plan rate_rule`.
        migrations.RunPython(_delete_legacy_rules, migrations.RunPython.noop, elidable=False),
        migrations.RunPython(_drop_old_constraint, _readd_old_constraint, elidable=False),
        migrations.AlterModelOptions(
            name="raterule",
            options={"ordering": ["card", "date_from"]},
        ),
        migrations.RemoveIndex(
            model_name="raterule",
            name="pricing_rat_card_id_1c7d67_idx",
        ),
        migrations.RemoveField(
            model_name="raterule",
            name="priority",
        ),
        migrations.RunPython(_add_new_constraint, _drop_new_constraint, elidable=False),
    ]
