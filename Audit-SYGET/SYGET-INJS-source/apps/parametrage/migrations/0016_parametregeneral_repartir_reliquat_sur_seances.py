from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("parametrage", "0015_parametregeneral_verrouiller_salle_groupe_formation"),
    ]

    operations = [
        migrations.AddField(
            model_name="parametregeneral",
            name="repartir_reliquat_sur_seances",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Génération auto des séances : si des heures n'ont pas pu être planifiées "
                    "sur un module, étendre les séances existantes du module pour absorber le "
                    "reliquat. Maximum +1 h par séance, en commençant par +30 min, puis "
                    "+30 min supplémentaires."
                ),
            ),
        ),
    ]
