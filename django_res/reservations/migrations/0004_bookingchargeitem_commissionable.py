from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0003_exclude_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookingchargeitem",
            name="commissionable",
            field=models.BooleanField(default=True),
        ),
    ]
