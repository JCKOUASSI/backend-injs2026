from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("referentiels", "0001_initial"),
        ("formations", "0014_formationmodule_formateur_tel_org"),
    ]

    operations = [
        migrations.CreateModel(
            name="FormateurFormation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.CharField(max_length=30)),
                ("nom", models.CharField(max_length=150)),
                ("prenom", models.CharField(max_length=150)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("telephone", models.CharField(blank=True, default="", max_length=30)),
                ("organisation", models.CharField(blank=True, default="", max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "formation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="formateurs_importes",
                        to="formations.formation",
                    ),
                ),
                (
                    "module",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="formateurs_importes",
                        to="referentiels.module",
                    ),
                ),
            ],
            options={
                "verbose_name": "Formateur importé",
                "verbose_name_plural": "Formateurs importés",
                "ordering": ["nom", "prenom", "module__titre"],
            },
        ),
        migrations.AddConstraint(
            model_name="formateurformation",
            constraint=models.UniqueConstraint(
                fields=("formation", "module", "numero"),
                name="uniq_formateur_importe_par_formation_module_numero",
            ),
        ),
    ]
