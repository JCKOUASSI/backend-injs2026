"""Versionnement, comparaison et restauration des rôles métier (Lot B).

Service strictement ADDITIF : il ne modifie aucun chemin d'exécution du
moteur RBAC. Les instantanés :class:`~habilitations.models.RoleVersion`
sont créés explicitement (capture manuelle, restauration) ; la restauration
réapplique les champs versionnés et les relations M2M, et journalise tout
dans le journal immuable.
"""
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from ..models import PermissionMetier, RoleMetier, RoleVersion
from ..models.version_role import CHAMPS_VERSIONNES
from .journalisation import journaliser

#: Version initiale capturée à la première mise sous versionnement.
NUMERO_PREMIERE_VERSION = 1


def instantaner_role(role):
    """Construit le dictionnaire d'instantané d'un rôle (PUR, sans écriture)."""
    return {
        **{champ: getattr(role, champ) for champ in CHAMPS_VERSIONNES},
        'permissions': sorted(role.permissions.values_list('code', flat=True)),
        'incompatible_avec': sorted(
            role.incompatible_avec.values_list('code', flat=True),
        ),
    }


def capturer_version(role, *, auteur=None, motif='',
                     source=RoleVersion.Source.MANUEL):
    """Capture une nouvelle version du rôle et journalise l'événement."""
    auteur_reel = auteur if (auteur and auteur.is_authenticated) else None
    with transaction.atomic():
        numero = (
            RoleVersion.objects.filter(role=role).aggregate(
                dernier=Max('numero'),
            )['dernier'] or (NUMERO_PREMIERE_VERSION - 1)
        ) + 1
        version = RoleVersion.objects.create(
            role=role,
            numero=numero,
            auteur=auteur_reel,
            motif=motif,
            source=source,
            donnees=instantaner_role(role),
        )
    journaliser(
        'ROLE_VERSIONNE',
        acteur=auteur_reel,
        cible=role,
        nouvelle_valeur={'version': numero, 'source': source},
        motif=motif,
    )
    return version


def restaurer_version(role, numero, *, auteur=None, motif=''):
    """Restaure une version antérieure : réapplique champs + M2M.

    L'état courant est capturé AVANT application (source
    ``AVANT_RESTAURATION``) ; l'état restauré est capturé ensuite (source
    ``RESTAURATION``). Chaque étape est journalisée. Le ``code`` du rôle
    n'est jamais restauré (identifiant de référencement stable).
    """
    version = RoleVersion.objects.filter(role=role, numero=numero).first()
    if version is None:
        raise RoleVersion.DoesNotExist(
            f'Version {numero} introuvable pour le rôle {role.code}.'
        )
    donnees = version.donnees
    auteur_reel = auteur if (auteur and auteur.is_authenticated) else None

    with transaction.atomic():
        capturer_version(
            role, auteur=auteur_reel,
            motif=f'Avant restauration de la version {numero} : {motif}',
            source=RoleVersion.Source.AVANT_RESTAURATION,
        )
        for champ in CHAMPS_VERSIONNES:
            setattr(role, champ, donnees.get(champ))
        role.save()
        role.permissions.set(
            PermissionMetier.objects.filter(
                code__in=donnees.get('permissions', []),
            ),
        )
        role.incompatible_avec.set(
            RoleMetier.objects.filter(
                code__in=donnees.get('incompatible_avec', []),
            ),
        )
        version_restauree = capturer_version(
            role, auteur=auteur_reel,
            motif=f'Restauration de la version {numero} : {motif}',
            source=RoleVersion.Source.RESTAURATION,
        )
    journaliser(
        'ROLE_RESTAURE',
        acteur=auteur_reel,
        cible=role,
        ancienne_valeur={'version_restaurée': numero},
        nouvelle_valeur={'version_courante': version_restauree.numero},
        motif=motif,
    )
    return version_restauree


def _diff_entre_snapshots(avant, apres):
    """Diff PUR entre deux instantanés : champs + ensembles de codes."""
    champs = [
        {
            'champ': champ,
            'avant': avant.get(champ),
            'apres': apres.get(champ),
        }
        for champ in CHAMPS_VERSIONNES
        if avant.get(champ) != apres.get(champ)
    ]
    codes_avant = set(avant.get('permissions', []))
    codes_apres = set(apres.get('permissions', []))
    return {
        'champs': champs,
        'permissions_ajoutees': sorted(codes_apres - codes_avant),
        'permissions_retirees': sorted(codes_avant - codes_apres),
        'incompatibilites_ajoutees': sorted(
            set(apres.get('incompatible_avec', []))
            - set(avant.get('incompatible_avec', [])),
        ),
        'incompatibilites_retirees': sorted(
            set(avant.get('incompatible_avec', []))
            - set(apres.get('incompatible_avec', [])),
        ),
    }


def comparer_roles(code_a, code_b):
    """Compare deux rôles du référentiel (champs versionnés + permissions)."""
    role_a = RoleMetier.objects.filter(code=code_a).first()
    role_b = RoleMetier.objects.filter(code=code_b).first()
    if role_a is None or role_b is None:
        return None
    return {
        'role_a': {'code': role_a.code, 'libelle': role_a.libelle},
        'role_b': {'code': role_b.code, 'libelle': role_b.libelle},
        **_diff_entre_snapshots(
            instantaner_role(role_a), instantaner_role(role_b),
        ),
    }


def comparer_versions(role, numero_de, numero_vers):
    """Compare deux versions du même rôle."""
    v_de = RoleVersion.objects.filter(role=role, numero=numero_de).first()
    v_vers = RoleVersion.objects.filter(role=role, numero=numero_vers).first()
    if v_de is None or v_vers is None:
        return None
    return {
        'role': role.code,
        'de': {
            'numero': v_de.numero,
            'instant': timezone.localtime(v_de.instant).isoformat(),
        },
        'vers': {
            'numero': v_vers.numero,
            'instant': timezone.localtime(v_vers.instant).isoformat(),
        },
        **_diff_entre_snapshots(v_de.donnees, v_vers.donnees),
    }
