import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("referentiels", "0003_effectif_et_inscriptions"),
    ]

    operations = [
        migrations.CreateModel(
            name="Specialite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=50, unique=True)),
                ("libelle", models.CharField(max_length=200)),
            ],
            options={
                "verbose_name": "Spécialité",
                "verbose_name_plural": "Spécialités",
                "ordering": ["code"],
            },
        ),
        migrations.AddField(
            model_name="module",
            name="specialite",
            field=models.ForeignKey(
                blank=True,
                help_text="Si renseignée, le planning ne retient que des formateurs ayant cette spécialité.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="modules",
                to="referentiels.specialite",
            ),
        ),
    ]
