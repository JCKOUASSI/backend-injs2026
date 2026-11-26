from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("formations", "0005_remove_formation_effectif_max"),
    ]

    operations = [
        migrations.AddField(
            model_name="formationmodule",
            name="heure_debut",
            field=models.TimeField(
                blank=True,
                help_text="Heure de début d'enseignement de ce module",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="formationmodule",
            name="heure_fin",
            field=models.TimeField(
                blank=True,
                help_text="Heure de fin d'enseignement de ce module",
                null=True,
            ),
        ),
    ]
