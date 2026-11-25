from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("seances", "0006_seance_formateur_details"),
    ]

    operations = [
        migrations.AddField(
            model_name="seance",
            name="formateur_organisation",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="seance",
            name="formateur_telephone",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
    ]
