from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("formations", "0021_formationmodule_volume_horaire_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="formation",
            name="planning_union_sites_programme",
            field=models.BooleanField(
                default=False,
                help_text="Si activé, pour chaque module sans liste de salles explicites, le dispatch utilise la réunion des sites déclarés sur tous les modules du programme (pas seulement les sites du module courant). Utile pour dé-saturer un module cantonné à un seul site.",
            ),
        ),
    ]
