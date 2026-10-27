"""U5 CURP — drapeau de la 6e sonde événementielle : désignation de jury.

Livré DÉSACTIVÉ (false), comme tous les interrupteurs du dispositif :
chaque automatisme est un interrupteur indépendant, éteint par défaut, et
aucun rôle n'est attribué sans validation humaine (la sonde ne dépose que
des propositions en file).
"""
from django.db import migrations

ADMIN_ROLES = '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]'

# (clé, libellé, ordre, description)
DRAPEAUX = [
    (
        'flag.curp_declencheur_jury',
        'CURP — Sonde : désignation d’un membre de jury',
        229,
        "Propose le rôle MEMBRE_JURY (périmètre de la formation de la "
        "session) à chaque membre désigné dans un jury. Sans compte CURP, "
        "propose la création du compte avec le rôle d'accès existant. "
        "Aucune attribution sans approbation humaine.",
    ),
]


def seed_flags(apps, schema_editor):
    Parametre = apps.get_model('parametres', 'Parametre')
    for cle, libelle, ordre, description in DRAPEAUX:
        Parametre.objects.get_or_create(
            cle=cle,
            defaults={
                'libelle': libelle,
                'description': description,
                'categorie': 'flags',
                'ordre': ordre,
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


def unseed_flags(apps, schema_editor):
    Parametre = apps.get_model('parametres', 'Parametre')
    Parametre.objects.filter(cle__in=[c for c, _, _, _ in DRAPEAUX]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('parametres', '0006_flags_u5_cycle_vie'),
    ]

    operations = [
        migrations.RunPython(seed_flags, unseed_flags),
    ]
