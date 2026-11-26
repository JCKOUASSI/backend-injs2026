import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("formations", "0020_formateur_specialites_obligatoires"),
    ]

    operations = [
        migrations.AlterField(
            model_name="formationmodule",
            name="volume_horaire",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Volume en heures si fixe ; vide = volume issu du paramétrage (type × module × grade du groupe).",
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
    ]
