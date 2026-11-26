from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("parametrage", "0007_moduletypeformation_grade_cible"),
    ]

    operations = [
        migrations.AddField(
            model_name="parametregeneral",
            name="poids_score_ecart_capacite",
            field=models.PositiveIntegerField(
                default=10,
                help_text="Poids du critère de proximité de capacité lors du choix de salle",
            ),
        ),
        migrations.AddField(
            model_name="parametregeneral",
            name="poids_score_equilibrage_global",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Poids du critère d'équilibrage global d'usage des salles",
            ),
        ),
        migrations.AddField(
            model_name="parametregeneral",
            name="poids_score_rotation_module",
            field=models.PositiveIntegerField(
                default=2,
                help_text="Poids du critère de rotation des salles pour un même module",
            ),
        ),
    ]
