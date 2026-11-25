from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("formations", "0001_initial"),
        ("auditeurs", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Groupe",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "formation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="groupes", to="formations.formation"
                    ),
                ),
                ("nom", models.CharField(max_length=100)),
                (
                    "max_auditeurs",
                    models.PositiveIntegerField(default=25, validators=[django.core.validators.MinValueValidator(1)]),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Groupe",
                "verbose_name_plural": "Groupes",
                "ordering": ["formation", "nom"],
                "unique_together": {("formation", "nom")},
            },
        ),
        migrations.CreateModel(
            name="GroupeAuditeur",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "groupe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="membres", to="groupes.groupe"
                    ),
                ),
                (
                    "auditeur",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="groupes", to="auditeurs.auditeur"
                    ),
                ),
            ],
            options={
                "verbose_name": "Membre du groupe",
                "verbose_name_plural": "Membres du groupe",
                "unique_together": {("groupe", "auditeur")},
            },
        ),
        migrations.CreateModel(
            name="ConfigGroupe",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "groupe",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, related_name="config", to="groupes.groupe"
                    ),
                ),
                ("matin_actif", models.BooleanField(default=True)),
                ("matin_heure_debut", models.TimeField(default="08:00")),
                ("matin_heure_fin", models.TimeField(default="12:00")),
                ("soir_actif", models.BooleanField(default=True)),
                ("soir_heure_debut", models.TimeField(default="13:00")),
                ("soir_heure_fin", models.TimeField(default="17:00")),
            ],
            options={"verbose_name": "Configuration du groupe", "verbose_name_plural": "Configurations des groupes"},
        ),
        migrations.CreateModel(
            name="JourCours",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "groupe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="jours_cours", to="groupes.groupe"
                    ),
                ),
                (
                    "jour",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (0, "Lundi"),
                            (1, "Mardi"),
                            (2, "Mercredi"),
                            (3, "Jeudi"),
                            (4, "Vendredi"),
                            (5, "Samedi"),
                            (6, "Dimanche"),
                        ]
                    ),
                ),
            ],
            options={
                "verbose_name": "Jour de cours",
                "verbose_name_plural": "Jours de cours",
                "ordering": ["jour"],
                "unique_together": {("groupe", "jour")},
            },
        ),
    ]
