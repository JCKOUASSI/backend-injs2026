from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("formations", "0013_formationmodule_formateur_details"),
    ]

    operations = [
        migrations.AddField(
            model_name="formationmodule",
            name="formateur_organisation",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Organisation du formateur",
                max_length=150,
            ),
        ),
        migrations.AddField(
            model_name="formationmodule",
            name="formateur_telephone",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Téléphone du formateur",
                max_length=30,
            ),
        ),
    ]
