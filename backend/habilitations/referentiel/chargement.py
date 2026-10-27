"""Chargement idempotent du référentiel en base (migration de données U3 et
commande ``charger_referentiel_injs``).

Le chargement est déterministe : il remet les rôles, permissions, la matrice
et les incompatibilités à l'état du catalogue annexé, sans toucher aux
attributions de comptes (aucune en U3). Le retour arrière ne supprime rien :
il désactive les lignes du catalogue (règle S5).
"""
from dataclasses import dataclass, field

from django.apps import apps as django_apps

from .catalogue_modules import (
    JOKER,
    MODULES,
    NIVEAU_VERBE,
    PERMISSIONS_AVEC_MOTIF,
    PERMISSIONS_CRITIQUES,
    PERMISSIONS_USAGERS,
    RESSOURCES,
    VERBES_CANONIQUES,
)
from .catalogue_roles import ROLES
from .catalogue_matrice import (
    CORRESPONDANCE_LEGACY,
    INCOMPATIBILITES,
    NIVEAU_PERMISSION_SURCHARGE,
    NIVEAUX,
    NIVEAUX_EXTRA_PROVISOIRES,
    NIVEAUX_ROLES_CIBLES,
)

ORDRE_NIVEAUX = {'N0': 0, 'N1': 1, 'N2': 2, 'N3': 3, 'N4': 4}


@dataclass
class RapportChargement:
    permissions: int = 0
    roles: int = 0
    liaisons_matrice: int = 0
    couples_incompatibilite: int = 0
    roles_indisponibles: list = field(default_factory=list)
    permissions_orphelines: list = field(default_factory=list)
    roles_sans_permission: list = field(default_factory=list)

    def as_dict(self):
        return {
            'permissions': self.permissions,
            'roles': self.roles,
            'liaisons_matrice': self.liaisons_matrice,
            'couples_incompatibilite': self.couples_incompatibilite,
            'roles_indisponibles': list(self.roles_indisponibles),
            'permissions_orphelines': list(self.permissions_orphelines),
            'roles_sans_permission': list(self.roles_sans_permission),
        }


def deplier_permissions():
    """Retourne la liste complète des permissions du catalogue (annexe A3).

    Chaque élément est un dict prêt à alimenter :class:`PermissionMetier`.
    """
    depliees = []
    vus = set()
    for module, ressources in RESSOURCES.items():
        for ressource, verbes in ressources.items():
            verbes_effectifs = (
                VERBES_CANONIQUES if verbes == JOKER else verbes
            )
            for verbe in verbes_effectifs:
                code = f'{module}.{ressource}.{verbe}'
                if code in vus:
                    continue
                vus.add(code)
                depliees.append({
                    'code': code,
                    'module': module,
                    'ressource': ressource,
                    'action': verbe,
                    'libelle': f'{verbe.replace("_", " ")} {ressource.replace("_", " ")}',
                })
    return depliees


def module_installe(app_label):
    """Vrai si l'application Django requise par un rôle est disponible."""
    if not app_label:
        return True
    try:
        django_apps.get_app_config(app_label)
    except LookupError:
        return False
    return True


def niveaux_du_role(code_role, domaine):
    """Retourne ``(niveaux, origine)`` après fusion d'A2, des cases
    provisoires J2 et des règles dérivées nettes.

    ``origine`` vaut ``'A2'`` pour une case écrite au recueil et ``'J2'``
    pour une case à valider en atelier (module hors A2 ou dérivation).
    """
    niveaux = dict(NIVEAUX.get(code_role, {}))
    origine = {module: 'A2' for module in niveaux}
    for module, niveau in NIVEAUX_EXTRA_PROVISOIRES.get(code_role, {}).items():
        niveaux[module] = niveau
        origine[module] = 'J2'
    # Rôles cibles du prompt module Utilisateurs (2026-09) : cases J2
    # provisoires, valables en sus de l'A2 (inexistante pour ces rôles).
    for module, niveau in NIVEAUX_ROLES_CIBLES.get(code_role, {}).items():
        niveaux[module] = niveau
        origine[module] = 'J2'
    # Les exports courants suivent le niveau statistique ; l'export sensible
    # reste réservé à N4 par la surcharge de niveau de permission.
    if 'exports' not in niveaux and ORDRE_NIVEAUX.get(niveaux.get('statistiques'), -1) >= 1:
        niveaux['exports'] = 'N1'
        origine['exports'] = 'J2'
    # Les référentiels sont nécessaires aux écrans de saisie des rôles
    # internes (jamais aux simples usagers) ; la case reste provisoire J2.
    if domaine != 'DESTINATAIRES' and 'referentiels' not in niveaux and niveaux:
        niveaux['referentiels'] = 'N1'
        origine['referentiels'] = 'J2'
    return niveaux, origine


def _niveaux_du_role(code_role, domaine):
    return niveaux_du_role(code_role, domaine)[0]


def _verbe_autorise(code_permission, verbe, niveau_num):
    surcharge = NIVEAU_PERMISSION_SURCHARGE.get(code_permission)
    requis = surcharge if surcharge is not None else NIVEAU_VERBE.get(verbe, 4)
    return requis <= niveau_num


def charger_referentiel(dry_run=False):
    """Charge (ou simule si ``dry_run``) tout le référentiel. Retourne un
    :class:`RapportChargement`.
    """
    from ..models import PermissionMetier, RoleMetier
    rapport = RapportChargement()

    # 1) Permissions atomiques (A3).
    definitions = deplier_permissions()
    permissions_par_code = {}
    for definition in definitions:
        code = definition['code']
        critique = code in PERMISSIONS_CRITIQUES
        avec_motif = critique or code in PERMISSIONS_AVEC_MOTIF
        valeurs = {
            'module': definition['module'],
            'ressource': definition['ressource'],
            'action': definition['action'],
            'libelle': definition['libelle'],
            'criticite': 'CRITIQUE' if critique else 'NORMALE',
            'necessite_motif': avec_motif,
            'necessite_double_validation': critique,
            'journalisee': definition['action'] != 'consulter',
            'actif': True,
        }
        if not dry_run:
            objet, _ = PermissionMetier.objects.update_or_create(
                code=code, defaults=valeurs,
            )
        else:
            objet = type('P', (), {'code': code})()
        permissions_par_code[code] = objet
    rapport.permissions = len(permissions_par_code)

    # 2) Rôles (A1) et disponibilité conditionnelle par module.
    roles_par_code = {}
    for (code, libelle, domaine, niveau, perimetre, module_requis,
         sensible, canal, ordre, description) in ROLES:
        disponible = module_installe(module_requis)
        if not disponible:
            rapport.roles_indisponibles.append(code)
        valeurs = {
            'libelle': libelle,
            'libelle_court': libelle,
            'description': description,
            'domaine': domaine,
            'niveau_defaut': niveau,
            'perimetre_defaut': perimetre,
            'module_requis': module_requis,
            'disponible': disponible,
            'sensible': sensible,
            'cumulable': True,
            'canal_impose': canal,
            'ordre': ordre,
            'actif': True,
        }
        if not dry_run:
            objet, _ = RoleMetier.objects.update_or_create(
                code=code, defaults=valeurs,
            )
        else:
            objet = type('R', (), {'code': code})()
        roles_par_code[code] = objet
    rapport.roles = len(roles_par_code)

    # 3) Matrice rôle × permissions (dérivation de l'annexe A2).
    permissions_par_role = {code: set() for code in roles_par_code}
    for (code, _lib, domaine, _niv, _per, _mod, _sens, _canal,
         _ordre, _desc) in ROLES:
        niveaux = _niveaux_du_role(code, domaine)
        for module, niveau in niveaux.items():
            niveau_num = ORDRE_NIVEAUX.get(niveau, 0)
            for definition in definitions:
                if definition['module'] != module:
                    continue
                if _verbe_autorise(
                    definition['code'], definition['action'], niveau_num
                ):
                    permissions_par_role[code].add(definition['code'])
        # Actes d'auto-démarche des usagers sur leur propre dossier.
        for code_perm in PERMISSIONS_USAGERS.get(code, ()):
            permissions_par_role[code].add(code_perm)

    for code, codes_perm in permissions_par_role.items():
        if not codes_perm:
            rapport.roles_sans_permission.append(code)
        if not dry_run:
            role = roles_par_code[code]
            role.permissions.set([
                permissions_par_code[c] for c in sorted(codes_perm)
            ])
        rapport.liaisons_matrice += len(codes_perm)

    # Une permission est orpheline si aucun rôle ne la détient.
    accordees = set()
    for codes in permissions_par_role.values():
        accordees.update(codes)
    rapport.permissions_orphelines = sorted(
        c for c in permissions_par_code if c not in accordees
    )

    # 4) Incompatibilités bilatérales (J5).
    paires = set()
    for code_a, code_b in INCOMPATIBILITES:
        paires.add(tuple(sorted((code_a, code_b))))
    if not dry_run:
        for code_a, code_b in paires:
            roles_par_code[code_a].incompatible_avec.add(roles_par_code[code_b])
            roles_par_code[code_b].incompatible_avec.add(roles_par_code[code_a])
    rapport.couples_incompatibilite = len(paires)
    return rapport


def desactiver_referentiel():
    """Retour arrière non destructif : inactive les lignes du catalogue."""
    from ..models import PermissionMetier, RoleMetier
    codes_roles = [ligne[0] for ligne in ROLES]
    codes_perms = [d['code'] for d in deplier_permissions()]
    RoleMetier.objects.filter(code__in=codes_roles).update(actif=False)
    PermissionMetier.objects.filter(code__in=codes_perms).update(actif=False)


def correspondance_legacy():
    """Vue exposable/testable de la table A6 (rôle legacy → codes métier)."""
    return dict(CORRESPONDANCE_LEGACY)
