"""U5 CURP — drapeaux du cycle de vie, du provisionnement et des imports.

Tous livrés DÉSACTIVÉS (false), conformément au principe de repli de la
fiche U5 : chaque automatisme est un interrupteur indépendant, éteint par
défaut, et aucun compte ne peut être créé ou modifié automatiquement sans
validation humaine (les sondes ne font que déposer des propositions).

* ``flag.curp_provisionnement_auto`` : maître des cinq sondes
  événementielles (doit être ouvert EN PLUS du drapeau de la sonde) ;
* ``flag.curp_declencheur_*`` : les cinq déclencheurs, indépendants ;
* ``flag.curp_suspension_inactivite`` : préavis et mise en file des comptes
  inactifs (jamais de suspension directe) ;
* ``flag.curp_expiration_auto`` : expiration à terme convenu des
  attributions temporaires, dérogations et délégations ;
* ``flag.curp_import_masse`` : écriture transactionnelle et annulation des
  imports en masse (l'aperçu U4 reste disponible sans ce drapeau).
"""
from django.db import migrations

ADMIN_ROLES = '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]'

# (clé, libellé, ordre, description)
DRAPEAUX = [
    (
        'flag.curp_provisionnement_auto',
        'CURP — Maître du provisionnement événementiel (U5)',
        220,
        "Interrupteur maître des sondes qui détectent les événements métier "
        "(admission, inscription, recrutement, affectation enseignant, fin "
        "de relation). N'accorde rien à lui seul : chaque sonde a aussi son "
        "propre drapeau. Désactivé par défaut, extinction immédiate sans "
        "redéploiement.",
    ),
    (
        'flag.curp_declencheur_admission',
        'CURP — Sonde : admission d’un candidat validée',
        221,
        "Dépose en file de validation une proposition de compte étudiant "
        "(rôle ETUDIANT, canal mobile) à chaque admission nouvelle. Aucune "
        "création sans approbation humaine.",
    ),
    (
        'flag.curp_declencheur_inscription',
        'CURP — Sonde : inscription administrative validée',
        222,
        "Propose l'activation du compte étudiant et son rattachement au "
        "périmètre de la formation, du niveau et du groupe.",
    ),
    (
        'flag.curp_declencheur_recrutement',
        'CURP — Sonde : recrutement d’un agent en RH',
        223,
        "Propose la création du compte agent à partir des agents RH actifs "
        "sans compte. Le rôle est à compléter par le valideur si non "
        "déductible de la fonction.",
    ),
    (
        'flag.curp_declencheur_affectation_enseignant',
        'CURP — Sonde : affectation pédagogique d’un enseignant',
        224,
        "Propose le rôle ENSEIGNANT avec les périmètres des ECUE concernés "
        "(canal mobile) à chaque affectation pédagogique nouvelle.",
    ),
    (
        'flag.curp_declencheur_fin_relation',
        'CURP — Sonde : fin d’inscription, départ, fin de contrat',
        225,
        "Après le délai de grâce, propose la suspension du compte (la "
        "désactivation reste un geste administrateur ultérieur).",
    ),
    (
        'flag.curp_suspension_inactivite',
        'CURP — Détection des comptes inactifs (préavis + file)',
        226,
        "Notifie l'agent et son responsable 15 jours avant le seuil de 180 "
        "jours (réglable), puis dépose une proposition de suspension en "
        "file. Jamais de suspension silencieuse directe.",
    ),
    (
        'flag.curp_expiration_auto',
        'CURP — Expiration à terme des attributions, dérogations, délégations',
        227,
        "Applique la date de fin convenue à la création (statut EXPIREE/"
        "TERMINEE) et notifie l'intéressé sept jours avant l'échéance.",
    ),
    (
        'flag.curp_import_masse',
        'CURP — Écriture et annulation des imports en masse (U5)',
        228,
        "Autorise l'exécution transactionnelle d'un import prévisualisé et "
        "son annulation par référence d'exécution. Éteint, seul l'aperçu "
        "sans écriture (U4) est disponible.",
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
        ('parametres', '0005_flag_curp_ui_admin'),
    ]

    operations = [
        migrations.RunPython(seed_flags, reverse_code=unseed_flags),
    ]
