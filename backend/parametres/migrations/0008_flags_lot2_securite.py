"""LOT 2 (U6) — drapeaux de sécurité de la connexion.

Trois interrupteurs indépendants, livrés DÉSACTIVÉS comme tous les
automatismes du dispositif : extinction immédiate sans redéploiement,
pas de passe-droit super-utilisateur (``parametres.flags.is_enabled``).

* ``flag.curp_verrouillage_connexion`` : verrouillage du compte après
  échecs consécutifs d'authentification (seuil et durée issus de
  ``PolitiqueSecurite``), déverrouillage automatique à échéance ou par
  un administrateur ; chaque geste est journalisé au journal CURP.
* ``flag.curp_mfa_active`` : étape MFA TOTP (code 6 chiffres) à la
  connexion pour les comptes avec ``mfa_actif=True`` ; fermé, le flag
  ``mfa_actif`` est ignoré (comportement strictement d'avant).
* ``flag.curp_mfa_obligatoire_sensibles`` : connexion refusée pour un
  compte portant au moins un rôle sensible actif sans MFA activé ; le
  MFA de ces comptes ne peut pas être désactivé.
"""
from django.db import migrations

ADMIN_ROLES = '["ADMIN", "CHEF_CPFAE_ADMIN", "CPFAE_ADMIN"]'

# (clé, libellé, ordre, description)
DRAPEAUX = [
    (
        'flag.curp_verrouillage_connexion',
        'CURP — Verrouillage de compte à la connexion',
        230,
        "Après N échecs consécutifs d'authentification "
        "(PolitiqueSecurite.nombre_echecs_avant_verrouillage, défaut 5), "
        "le compte passe VERROUILLÉ pour "
        "PolitiqueSecurite.duree_verrouillage_minutes (défaut 15 min). "
        "Déverrouillage automatique à l'échéance ou par un administrateur ; "
        "journalisé au journal CURP (COMPTE_VERROUILLE / COMPTE_DEVERROUILLE).",
    ),
    (
        'flag.curp_mfa_active',
        'CURP — MFA TOTP à la connexion',
        231,
        "Demande un code à 6 chiffres de l'application d'authentification "
        "(TOTP) pour les comptes avec mfa_actif=True. Fermé, le flag "
        "mfa_actif est ignoré : aucun changement de comportement.",
    ),
    (
        'flag.curp_mfa_obligatoire_sensibles',
        'CURP — MFA obligatoire pour les rôles sensibles',
        232,
        "Ouvert, la connexion est refusée pour un compte portant au moins "
        "un rôle sensible actif sans MFA activé, et le MFA de ces comptes "
        "ne peut pas être désactivé (rôle sensible = colonne « Sens. » "
        "du catalogue des rôles).",
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
        ('parametres', '0007_flag_curp_declencheur_jury'),
    ]

    operations = [
        migrations.RunPython(seed_flags, unseed_flags),
    ]
