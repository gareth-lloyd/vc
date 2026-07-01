"""SMELL-019: rename the model `RateRule` → `RateBand`.

After GAP-056, `RateRule` carries no dates or card — it is exactly a party band
hanging off a `RatePeriod`. This renames the model (and its table
`pricing_raterule` → `pricing_rateband`), the FK reverse accessor
(`period.rules` → `period.bands`), the three CHECK constraints, the auto-named
`(period, min_party)` index, and — via raw SQL, since it is invisible to the
migration autodetector — the btree_gist EXCLUDE `raterule_bands_no_overlap`
created in 0015. No data moves; this is a pure rename.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0015_drop_ratecard_contract"),
    ]

    operations = [
        # help_text now reads "RateBand" (cosmetic; no DB change).
        migrations.AlterField(
            model_name="rateplan",
            name="fallback_nightly",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text=(
                    "Opt-in nightly rate used when no RateBand covers a night. "
                    "NULL = no fallback (uncovered nights raise NoRateAvailable)."
                ),
                max_digits=12,
                null=True,
            ),
        ),
        # Rename the model + table + FK; repoints the period FK automatically.
        migrations.RenameModel(old_name="RateRule", new_name="RateBand"),
        # The FK reverse accessor changed related_name "rules" -> "bands"
        # (Python-only; recorded so future autodetection stays clean).
        migrations.AlterField(
            model_name="rateband",
            name="period",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="bands",
                to="pricing.rateperiod",
            ),
        ),
        # The auto-named (period, min_party) index keeps its raterule-era name
        # after the table rename; realign it to the rateband auto-name.
        migrations.RenameIndex(
            model_name="rateband",
            old_name="pricing_rat_period__4b935d_idx",
            new_name="pricing_rat_period__49f1f2_idx",
        ),
        # Rename the three CHECK constraints raterule_* -> rateband_*.
        migrations.RemoveConstraint(
            model_name="rateband",
            name="raterule_min_party_lte_max_party",
        ),
        migrations.RemoveConstraint(
            model_name="rateband",
            name="raterule_has_price_or_poa",
        ),
        migrations.RemoveConstraint(
            model_name="rateband",
            name="raterule_poa_excludes_price",
        ),
        migrations.AddConstraint(
            model_name="rateband",
            constraint=models.CheckConstraint(
                condition=models.Q(("min_party__lte", models.F("max_party"))),
                name="rateband_min_party_lte_max_party",
            ),
        ),
        migrations.AddConstraint(
            model_name="rateband",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("nightly__isnull", False),
                    ("weekly__isnull", False),
                    ("is_poa", True),
                    _connector="OR",
                ),
                name="rateband_has_price_or_poa",
            ),
        ),
        migrations.AddConstraint(
            model_name="rateband",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("is_poa", False),
                    models.Q(("nightly__isnull", True), ("weekly__isnull", True)),
                    _connector="OR",
                ),
                name="rateband_poa_excludes_price",
            ),
        ),
        # The btree_gist EXCLUDE was added by raw SQL in 0015 (no migration
        # state), so the autodetector can't see it. Rename it by hand so it no
        # longer contradicts the table it lives on.
        migrations.RunSQL(
            sql=(
                "ALTER TABLE pricing_rateband "
                "RENAME CONSTRAINT raterule_bands_no_overlap "
                "TO rateband_bands_no_overlap;"
            ),
            reverse_sql=(
                "ALTER TABLE pricing_rateband "
                "RENAME CONSTRAINT rateband_bands_no_overlap "
                "TO raterule_bands_no_overlap;"
            ),
        ),
    ]
