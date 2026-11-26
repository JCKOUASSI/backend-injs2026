from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("groupes", "0001_initial"),
        ("referentiels", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Seance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "groupe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="seances", to="groupes.groupe"
                    ),
                ),
                (
                    "module",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="seances", to="referentiels.module"
                    ),
                ),
                ("date", models.DateField()),
                ("heure_debut", models.TimeField()),
                ("heure_fin", models.TimeField()),
                (
                    "duree_minutes",
                    models.PositiveIntegerField(
                        help_text="Durée calculée en minutes", validators=[django.core.validators.MinValueValidator(1)]
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "Séance", "verbose_name_plural": "Séances", "ordering": ["date", "heure_debut"]},
        ),
    ]
