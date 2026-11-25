from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("seances", "0004_planningauditlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="seance",
            name="formateur_nom",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
    ]
