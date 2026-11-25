from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("formations", "0018_global_formateur_referentiel"),
        ("referentiels", "0004_specialite_module_specialite"),
    ]

    operations = [
        migrations.AddField(
            model_name="formateur",
            name="specialites",
            field=models.ManyToManyField(
                blank=True,
                help_text="Spécialités du formateur ; utilisées pour le dispatch des séances selon le module.",
                related_name="formateurs",
                to="referentiels.specialite",
            ),
        ),
    ]
