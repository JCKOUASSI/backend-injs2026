from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="TypeFormation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=20, unique=True)),
                ("libelle", models.CharField(max_length=100)),
            ],
            options={
                "verbose_name": "Type de formation",
                "verbose_name_plural": "Types de formation",
                "ordering": ["code"],
            },
        ),
        migrations.CreateModel(
            name="Module",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titre", models.CharField(max_length=200, unique=True)),
                ("actif", models.BooleanField(default=True)),
            ],
            options={"verbose_name": "Module", "verbose_name_plural": "Modules", "ordering": ["titre"]},
        ),
    ]
