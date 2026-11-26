from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("formations", "0011_alter_formationmodule_location_lengths"),
    ]

    operations = [
        migrations.AddField(
            model_name="formationmodule",
            name="formateur_nom",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Formateur affecté au module (un seul nom)",
                max_length=150,
            ),
        ),
    ]
