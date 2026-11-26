from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("referentiels", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Grade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("libelle", models.CharField(max_length=20, unique=True)),
                ("ordre", models.PositiveIntegerField(default=0, help_text="Ordre d'affichage et de tri")),
                ("actif", models.BooleanField(default=True)),
            ],
            options={"verbose_name": "Grade", "verbose_name_plural": "Grades", "ordering": ["ordre", "libelle"]},
        ),
        migrations.CreateModel(
            name="Vague",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("libelle", models.CharField(max_length=50, unique=True)),
                ("actif", models.BooleanField(default=True)),
            ],
            options={"verbose_name": "Vague", "verbose_name_plural": "Vagues", "ordering": ["libelle"]},
        ),
        migrations.CreateModel(
            name="ParametreGeneral",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "max_auditeurs_groupe_defaut",
                    models.PositiveIntegerField(default=25, validators=[django.core.validators.MinValueValidator(1)]),
                ),
                ("matin_heure_debut_defaut", models.TimeField(default="08:00")),
                ("matin_heure_fin_defaut", models.TimeField(default="12:00")),
                ("soir_heure_debut_defaut", models.TimeField(default="13:00")),
                ("soir_heure_fin_defaut", models.TimeField(default="17:00")),
                (
                    "jours_defaut",
                    models.JSONField(default=list, help_text="Liste des entiers 0-6 (0=lundi). Ex: [0,1,2,3,4]"),
                ),
            ],
            options={"verbose_name": "Paramètre général", "verbose_name_plural": "Paramètres généraux"},
        ),
        migrations.CreateModel(
            name="ModuleTypeFormation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "module",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="type_associations",
                        to="referentiels.module",
                    ),
                ),
                (
                    "type_formation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="module_associations",
                        to="referentiels.typeformation",
                    ),
                ),
                (
                    "volume_horaire_defaut",
                    models.PositiveIntegerField(
                        help_text="Volume horaire par défaut en heures pour ce type de formation",
                        validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
            ],
            options={
                "verbose_name": "Association module / type",
                "verbose_name_plural": "Associations modules / types",
                "unique_together": {("module", "type_formation")},
            },
        ),
    ]
