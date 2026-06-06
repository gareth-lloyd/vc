"""Rename OwnerBlockRequest -> OwnerBlock and requested_by -> created_by.

Mechanical rename only: the table and column move, the lifecycle is unchanged.
The CheckConstraint and index names are deliberately left untouched (they are
internal identifiers; renaming them would be churn with no behavioural effect).
"""

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0016_ownerblockrequest"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="OwnerBlockRequest",
            new_name="OwnerBlock",
        ),
        migrations.RenameField(
            model_name="ownerblock",
            old_name="requested_by",
            new_name="created_by",
        ),
    ]
