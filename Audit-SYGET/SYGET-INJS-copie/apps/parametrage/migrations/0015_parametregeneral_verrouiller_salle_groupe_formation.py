from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("parametrage", "0014_alter_parametregeneral_groupes_auto_mixage_grades_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="parametregeneral",
            name="verrouiller_salle_groupe_formation",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Génération auto des séances : si activé, la première salle attribuée à un "
                    "groupe (premier module planifié) est verrouillée pour TOUS les modules "
                    "suivants de ce groupe, du début à la fin de la formation."
                ),
            ),
        ),
    ]
