from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("formations", "0025_remove_uniq_formateur_par_groupe"),
    ]

    operations = [
        migrations.AddField(
            model_name="formation",
            name="creneau_mode",
            field=models.CharField(
                choices=[
                    ("matin", "Matin uniquement"),
                    ("soir", "Soir uniquement"),
                    ("matin_et_soir", "Matin et soir"),
                ],
                default="matin_et_soir",
                help_text="Définit si la formation se déroule le matin, le soir, ou sur les deux créneaux.",
                max_length=20,
            ),
        ),
    ]
