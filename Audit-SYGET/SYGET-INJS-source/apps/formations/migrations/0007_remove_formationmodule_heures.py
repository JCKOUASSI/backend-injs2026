from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("formations", "0006_formationmodule_heures"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="formationmodule",
            name="heure_debut",
        ),
        migrations.RemoveField(
            model_name="formationmodule",
            name="heure_fin",
        ),
    ]
