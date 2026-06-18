from django.db import migrations


class Migration(migrations.Migration):
    """Rename Contact -> Person (and child tables) in place.

    GAP-045 Unit 1: a pure, reversible identity rename. The autodetector cannot
    infer model renames non-interactively (it would emit DeleteModel +
    CreateModel and drop the data), so the RenameModels are hand-written.
    Django renames the tables and follows the dependent FKs; constraint and
    index names are intentionally left untouched (repo convention).
    """

    # Must run *after* every app that creates a FK to accounts.Contact, so the
    # old name still resolves when those CreateModels render their state. The
    # autodetector adds these automatically for detected renames; this rename is
    # hand-written, so the cross-app deps are pinned by hand. Without them the
    # from-scratch topological sort can place this rename before
    # properties/reservations create their `contact`/`agent` FKs, and
    # 'accounts.contact' no longer resolves (a fresh `migrate` fails even though
    # an incremental one over an existing DB succeeds).
    dependencies = [
        ("accounts", "0005_user_preferred_language"),
        ("properties", "0016_alter_property_options"),
        ("reservations", "0030_enquiry_flexibility_days"),
    ]

    operations = [
        migrations.RenameModel(old_name="Contact", new_name="Person"),
        migrations.RenameModel(old_name="ContactEmail", new_name="PersonEmail"),
        migrations.RenameModel(old_name="ContactPhone", new_name="PersonPhone"),
    ]
