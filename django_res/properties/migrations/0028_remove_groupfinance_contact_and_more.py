# GAP-070: drop property groups. The freeze migration (0027) resolved the old
# group inheritance into concrete PropertySettings/PropertyFinance values, so
# the group tables carry no live data.
#
# Hand-ordered (not the autodetector's field-stripping form) so the migration
# is cleanly reversible — the MigrationExecutor guard tests roll properties
# back past this point, some (test_migration_0017) with live Property rows.
# The column drop therefore reverses to a NULLABLE group_id at the DB level
# (a NOT NULL re-add would fail on any existing row); the state-level reverse
# keeps the historical non-null field, which is what rows seeded via the
# historical models carry anyway.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0027_freeze_group_inheritance"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="property",
            name="properties__group_i_dfd301_idx",
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(
                    model_name="property",
                    name="group",
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE "properties_property" DROP COLUMN "group_id";',
                    reverse_sql=(
                        'ALTER TABLE "properties_property" '
                        'ADD COLUMN "group_id" bigint NULL '
                        'REFERENCES "properties_propertygroup" ("id") '
                        "DEFERRABLE INITIALLY DEFERRED;"
                    ),
                ),
            ],
        ),
        migrations.DeleteModel(
            name="GroupFinance",
        ),
        migrations.DeleteModel(
            name="GroupSettings",
        ),
        migrations.DeleteModel(
            name="PropertyGroup",
        ),
    ]
