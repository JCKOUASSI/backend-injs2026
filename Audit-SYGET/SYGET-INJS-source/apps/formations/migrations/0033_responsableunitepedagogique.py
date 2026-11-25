from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("referentiels", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("formations", "0032_formationperiode"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResponsableUnitePedagogique",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "module",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="responsables_up",
                        to="referentiels.module",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="unites_pedagogiques_responsables",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Responsable d'unité pédagogique",
                "verbose_name_plural": "Responsables d'unités pédagogiques",
                "ordering": ["module__titre", "user__username"],
            },
        ),
        migrations.AddConstraint(
            model_name="responsableunitepedagogique",
            constraint=models.UniqueConstraint(fields=("user", "module"), name="uniq_rup_user_module"),
        ),
    ]
