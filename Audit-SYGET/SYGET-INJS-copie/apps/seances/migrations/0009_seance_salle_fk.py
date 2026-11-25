"""Ajoute la FK nullable vers parametrage.Salle sur Seance."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("parametrage", "0019_parametre_formation"),
        ("seances", "0008_planningrun"),
    ]

    operations = [
        migrations.AddField(
            model_name="seance",
            name="salle",
            field=models.ForeignKey(
                blank=True,
                help_text="Référence référentiel (collisions fiables) ; les champs nom restent le snapshot export.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="seances",
                to="parametrage.salle",
            ),
        ),
    ]
