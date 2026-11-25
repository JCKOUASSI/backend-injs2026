from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Auditeur",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("matricule", models.CharField(max_length=30, unique=True)),
                ("nom", models.CharField(max_length=100)),
                ("prenom", models.CharField(max_length=100)),
                ("grade", models.CharField(blank=True, max_length=20)),
                ("email", models.EmailField(blank=True)),
                ("telephone", models.CharField(blank=True, max_length=20)),
                ("service", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "Auditeur", "verbose_name_plural": "Auditeurs", "ordering": ["nom", "prenom"]},
        ),
    ]
