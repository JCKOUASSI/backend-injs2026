from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("referentiels", "0001_initial"),
        ("auditeurs", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Formation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "type_formation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="formations",
                        to="referentiels.typeformation",
                    ),
                ),
                ("intitule", models.CharField(max_length=200)),
                ("vague", models.CharField(blank=True, max_length=50)),
                ("date_debut", models.DateField()),
                ("date_fin", models.DateField()),
                (
                    "effectif_max",
                    models.PositiveIntegerField(default=100, validators=[django.core.validators.MinValueValidator(1)]),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Formation",
                "verbose_name_plural": "Formations",
                "ordering": ["-date_debut", "intitule"],
            },
        ),
        migrations.CreateModel(
            name="FormationModule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "formation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="modules", to="formations.formation"
                    ),
                ),
                (
                    "module",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="formation_associations",
                        to="referentiels.module",
                    ),
                ),
                (
                    "volume_horaire",
                    models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)]),
                ),
            ],
            options={
                "verbose_name": "Module de formation",
                "verbose_name_plural": "Modules de formation",
                "ordering": ["module__titre"],
                "unique_together": {("formation", "module")},
            },
        ),
        migrations.CreateModel(
            name="Inscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "formation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inscriptions",
                        to="formations.formation",
                    ),
                ),
                (
                    "auditeur",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inscriptions",
                        to="auditeurs.auditeur",
                    ),
                ),
                ("date_inscription", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Inscription",
                "verbose_name_plural": "Inscriptions",
                "unique_together": {("formation", "auditeur")},
            },
        ),
    ]
