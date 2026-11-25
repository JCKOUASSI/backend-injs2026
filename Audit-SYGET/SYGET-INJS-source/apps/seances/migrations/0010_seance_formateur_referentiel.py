"""Ajoute la FK nullable vers formations.Formateur sur Seance."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("formations", "0031_formation_responsable"),
        ("seances", "0009_seance_salle_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="seance",
            name="formateur_referentiel",
            field=models.ForeignKey(
                blank=True,
                help_text="Référence référentiel (collisions fiables) ; les champs nom restent le snapshot export.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="seances_planifiees",
                to="formations.formateur",
            ),
        ),
    ]
