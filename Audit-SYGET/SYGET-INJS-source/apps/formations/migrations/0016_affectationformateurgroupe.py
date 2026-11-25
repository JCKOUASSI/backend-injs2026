from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("groupes", "0001_initial"),
        ("referentiels", "0001_initial"),
        ("formations", "0015_formateurformation"),
    ]

    operations = [
        migrations.CreateModel(
            name="AffectationFormateurGroupe",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "formateur",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="affectations_groupes",
                        to="formations.formateurformation",
                    ),
                ),
                (
                    "groupe",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="affectations_formateurs",
                        to="groupes.groupe",
                    ),
                ),
                (
                    "module",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="affectations_formateurs",
                        to="referentiels.module",
                    ),
                ),
            ],
            options={
                "verbose_name": "Affectation formateur/groupe",
                "verbose_name_plural": "Affectations formateurs/groupes",
                "ordering": ["groupe__nom", "module__titre", "formateur__nom", "formateur__prenom"],
            },
        ),
        migrations.AddConstraint(
            model_name="affectationformateurgroupe",
            constraint=models.UniqueConstraint(
                fields=("groupe", "module", "formateur"),
                name="uniq_affectation_formateur_groupe_module",
            ),
        ),
    ]
