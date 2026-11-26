from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("formations", "0012_formationmodule_formateur_nom"),
    ]

    operations = [
        migrations.AddField(
            model_name="formationmodule",
            name="formateur_email",
            field=models.EmailField(blank=True, default="", help_text="Email du formateur", max_length=254),
        ),
        migrations.AddField(
            model_name="formationmodule",
            name="formateur_numero",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Numéro de téléphone du formateur",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="formationmodule",
            name="formateur_prenom",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Prénom du formateur affecté au module",
                max_length=150,
            ),
        ),
    ]
