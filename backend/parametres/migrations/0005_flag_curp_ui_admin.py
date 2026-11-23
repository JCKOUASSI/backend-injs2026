"""U4 CURP — drapeau de repli de la nouvelle console d'administration.

``flag.curp_ui_admin`` est livré DÉSACTIVÉ (false) : tant qu'il n'est pas
ouvert par un administrateur via l'écran Paramètres/Feature flags, les
nouveaux écrans CURP et leurs endpoints sont inaccessibles et
l'administration Django (ainsi que l'écran Utilisateurs existant) reste la
seule voie, conformément au plan de repli de la fiche U4.
"""
from django.db import migrations

CLE = 'flag.curp_ui_admin'
ADMIN_ROLES = '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]'


def seed_flag(apps, schema_editor):
    Parametre = apps.get_model('parametres', 'Parametre')
    Parametre.objects.get_or_create(
        cle=CLE,
        defaults={
            'libelle': 'CURP — Console web d\u2019administration des comptes (U4)',
            'description': (
                'Active les écrans /administration/comptes (nouveau dispositif '
                'd\u2019habilitation). Désactivé par défaut : la désactivation '
                'rend la main à l\u2019administration Django. N\u2019accorde aucun '
                'droit : il faut en plus être administrateur de l\u2019habilitation.'
            ),
            'categorie': 'flags',
            'ordre': 210,
            'type': 'bool',
            'valeur': 'false',
            'valeur_defaut': 'false',
            'choices_json': '',
            'regex_validation': '',
            'modifiable': True,
            'modifiable_par_roles': ADMIN_ROLES,
            'lecturable_par_roles': ADMIN_ROLES,
            'actif': True,
        },
    )


def unseed_flag(apps, schema_editor):
    Parametre = apps.get_model('parametres', 'Parametre')
    Parametre.objects.filter(cle=CLE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('parametres', '0004_feature_flags_seed'),
    ]

    operations = [
        migrations.RunPython(seed_flag, reverse_code=unseed_flag),
    ]
