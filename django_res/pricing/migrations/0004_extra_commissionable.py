from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pricing", "0003_exclude_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="extra",
            name="commissionable",
            field=models.BooleanField(default=True),
        ),
    ]
