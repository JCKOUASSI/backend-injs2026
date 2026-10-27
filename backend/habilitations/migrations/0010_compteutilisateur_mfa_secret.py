"""LOT 2 (U6) — secret TOTP du MFA sur le compte d'habilitation.

Champ additif vide par défaut : aucun compte existant n'est modifié, et
aucun comportement n'est changé tant que les drapeaux de sécurité de la
connexion (flag.curp_*, livrés éteints) ne sont pas ouverts.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('habilitations', '0009_compteutilisateur_departements_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='compteutilisateur',
            name='mfa_secret',
            field=models.CharField(
                blank=True, default='', max_length=64,
                help_text='Secret TOTP (base32) du MFA ; vide tant que le MFA n’est pas armé.',
            ),
        ),
    ]
