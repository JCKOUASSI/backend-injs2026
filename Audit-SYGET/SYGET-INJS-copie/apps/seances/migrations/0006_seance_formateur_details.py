from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("seances", "0005_seance_formateur_nom"),
    ]

    operations = [
        migrations.AddField(
            model_name="seance",
            name="formateur_email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="seance",
            name="formateur_numero",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
        migrations.AddField(
            model_name="seance",
            name="formateur_prenom",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
    ]
