"""Migration initiale ScenarioSimulation."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ScenarioSimulation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("libelle", models.CharField(max_length=200)),
                ("payload", models.JSONField(help_text="Paramètres du formset (liste de blocs formation).")),
                ("marge_pct", models.PositiveSmallIntegerField(default=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "auteur",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scenarios_simulation",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Scénario de simulation",
                "verbose_name_plural": "Scénarios de simulation",
                "ordering": ["-updated_at"],
            },
        ),
    ]
