from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [
        ("formations", "0030_remove_formation_creneau_mode"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("seances", "0007_seance_formateur_tel_org"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlanningRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(default="best_effort", max_length=32)),
                (
                    "statut",
                    models.CharField(
                        choices=[("running", "En cours"), ("done", "Terminé"), ("error", "Erreur")],
                        default="running",
                        max_length=16,
                    ),
                ),
                ("synthese", models.JSONField(blank=True, default=dict)),
                ("groupes", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="planning_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "formation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="planning_runs",
                        to="formations.formation",
                    ),
                ),
            ],
            options={
                "verbose_name": "Rapport de planning",
                "verbose_name_plural": "Rapports de planning",
                "ordering": ["-created_at"],
            },
        ),
    ]
