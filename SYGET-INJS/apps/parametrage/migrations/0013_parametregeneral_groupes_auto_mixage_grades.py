from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("parametrage", "0012_marge_simulation_pct"),
    ]

    operations = [
        migrations.AddField(
            model_name="parametregeneral",
            name="groupes_auto_mixage_grades",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Si activé, la génération automatique des groupes peut regrouper plusieurs grades "
                    "dans un même groupe (répartition tournante). Sinon, un groupe par grade."
                ),
            ),
        ),
    ]
