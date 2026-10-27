"""Calcul des impacts d'habilitation (couche IMPACT, strictement additive).

Objectif : dériver — sans dupliquer la logique d'autorisation — ce que
provoque une permission, ce que porte un rôle et ce que peut réellement
faire un utilisateur, à partir des modèles et services CURP existants :

* rôles / comptes : ``RoleMetier``, ``AttributionRole``, ``PermissionAttribuee``
  (dérogations), ``DelegationHabilitation``, ``CompteUtilisateur`` ;
* résolution effective : ``comptes_admin.permissions_effectives`` — AUCUNE
  logique d'accès effectif parallèle n'est introduite ici ;
* catalogues : ``referentiel.catalogue_roles`` (fanion sensible),
  ``referentiel.catalogue_modules`` (libellés des modules, niveau des verbes,
  permissions critiques).

Les fonctions sont pures côté lecture, déterministes et utilisables en dehors
des vues HTTP (tests directs du service). Aucun objet n'est modifié.
"""
from django.db.models import Count
from django.utils import timezone

from ..models import (
    AttributionRole,
    CompteUtilisateur,
    DelegationHabilitation,
    PermissionAttribuee,
    PermissionMetier,
    RoleMetier,
)
from ..referentiel.catalogue_modules import (
    MODULES,
    NIVEAU_VERBE,
    PERMISSIONS_CRITIQUES,
)
from ..referentiel.catalogue_roles import ROLES_PAR_CODE
from .comptes_admin import permissions_effectives

#: Taille maximale des listes de comptes renvoyées par une vue d'impact
#: (les totaux restent exacts ; les listes ne sont qu'un échantillon).
LIMITE_ECHANTILLON = 200


def libelle_module(code):
    """Libellé humain d'un module du catalogue (code brut si inconnu)."""
    entree = MODULES.get(code)
    return entree[0] if entree else code


def niveau_verbe(action):
    """Niveau N0–N4 minimal requis par un verbe (None si non catalogué)."""
    return NIVEAU_VERBE.get(action)


def sensibilite_role(code_role):
    """True si le rôle est marqué sensible dans le catalogue (annexe A1)."""
    ligne = ROLES_PAR_CODE.get(code_role)
    return bool(ligne and ligne[6])


def sensibilite_permission(permission):
    """Sensibilité d'une permission, dérivée du modèle (aucune invention).

    La base porte ``criticite`` (NORMALE / SENSIBLE / CRITIQUE) ; le catalogue
    marquant CRITIQUE les permissions de l'annexe A3, on re-croise avec
    ``PERMISSIONS_CRITIQUES`` pour refléter le référentiel chargé.
    """
    if permission.code in PERMISSIONS_CRITIQUES:
        return 'CRITIQUE'
    if permission.criticite == PermissionMetier.Criticite.SENSIBLE:
        return 'SENSIBLE'
    if permission.criticite == PermissionMetier.Criticite.CRITIQUE:
        return 'CRITIQUE'
    return 'NORMALE'


def _aujourdhui():
    return timezone.localdate()


def _ligne_role(role, nb_comptes=None):
    return {
        'code': role.code,
        'libelle': role.libelle,
        'sensible': bool(role.sensible),
        'disponible': bool(role.disponible),
        'niveau_defaut': role.niveau_defaut,
        'comptes_titulaires': nb_comptes,
    }


def _ligne_compte(compte):
    user = compte.user
    personne = compte.personne
    return {
        'id': compte.pk,
        'user_id': compte.user_id,
        'username': user.get_username() if user else '',
        'nom': getattr(personne, 'nom', '') or '',
        'prenoms': getattr(personne, 'prenoms', '') or '',
        'statut': compte.statut,
    }


def _perimetre(perimetre):
    return {
        'id': perimetre.pk,
        'type': perimetre.type,
        'libelle': perimetre.libelle,
        'object_id': perimetre.object_id,
    }


def _grouper_par_module(codes):
    """Regroupe des codes ``module.ressource.action`` par module (trié)."""
    groupes = {}
    for code in codes:
        module = code.split('.')[0]
        groupes.setdefault(module, []).append(code)
    return [
        {'module': code, 'module_libelle': libelle_module(code),
         'permissions': codes}
        for code, codes in sorted(groupes.items())
    ]


def _comptes_des_roles(roles, aujourdhui):
    """Comptes détenant une attribution ACTIVE de l'un des rôles, aujourd'hui.

    Une seule requête principale (join attribution → compte), complétée par
    un comptage distinct par rôle ; la fenêtre de dates (date_debut/date_fin)
    est affinée en mémoire sur les attributions préchargées — même logique
    que ``AttributionRole.est_active``, sans la dupliquer dans le SQL.
    """
    if not roles:
        return [], {}
    qs = (
        CompteUtilisateur.objects
        .filter(
            attributions__statut=AttributionRole.Statut.ACTIVE,
            attributions__role__in=roles,
        )
        .select_related('user', 'personne')
        .prefetch_related('attributions__role')
        .distinct()
    )
    par_role = dict(
        AttributionRole.objects
        .filter(statut=AttributionRole.Statut.ACTIVE, role__in=roles)
        .values('role__code')
        .annotate(total=Count('compte', distinct=True))
        .values_list('role__code', 'total')
    )
    resultats = [
        compte for compte in qs
        if any(
            attribution.est_active(aujourdhui) and attribution.role in roles
            for attribution in compte.attributions.all()
        )
    ]
    return resultats, par_role


def _codes_sensibles_en_base(codes):
    """Codes de ``codes`` portant une criticité non NORMALE en base.

    Source de vérité : la table ``PermissionMetier`` telle que le chargement
    du référentiel l'a peuplée (CRITIQUE pour l'annexe A3), complétée des
    permissions marquées sensibles par l'administration. Aucune intersection
    inventée côté catalogue : c'est le référentiel en base qui décide.
    """
    if not codes:
        return set()
    return set(
        PermissionMetier.objects
        .filter(code__in=codes)
        .exclude(criticite=PermissionMetier.Criticite.NORMALE)
        .values_list('code', flat=True)
    )


def impact_permission(code_permission):
    """Impact d'une permission : module, sensibilité, rôles porteurs, comptes.

    Retourne ``None`` si la permission n'existe pas en base (la vue décidera
    du 404). Un objet vide-partiel signifie « existante mais portée par
    aucun rôle et aucun compte » : la liste des rôles est alors vide.
    """
    permission = PermissionMetier.objects.filter(code=code_permission).first()
    if permission is None:
        return None

    aujourdhui = _aujourdhui()
    roles = list(
        permission.roles_octroyants.filter(actif=True).order_by('domaine', 'ordre')
    )
    comptes, par_role = _comptes_des_roles(roles, aujourdhui)

    # Dérogations OCTROI actives portant cette permission (accès directs).
    derogations = (
        PermissionAttribuee.objects
        .filter(
            permission=permission,
            statut=PermissionAttribuee.Statut.ACTIVE,
            sens=PermissionAttribuee.Sens.OCTROI,
        )
        .select_related('compte', 'compte__user', 'compte__personne')
    )
    comptes_derogation = [
        d.compte for d in derogations if d.est_active(aujourdhui)
    ]
    ids_vus = {c.pk for c in comptes}
    comptes_directs = [c for c in comptes_derogation if c.pk not in ids_vus]

    return {
        'type': 'permission',
        'code': permission.code,
        'module': permission.module,
        'module_libelle': libelle_module(permission.module),
        'ressource': permission.ressource,
        'action': permission.action,
        'niveau': niveau_verbe(permission.action),
        'criticite': sensibilite_permission(permission),
        'sensible': sensibilite_permission(permission) != 'NORMALE',
        'necessite_motif': bool(permission.necessite_motif),
        'necessite_double_validation': bool(permission.necessite_double_validation),
        'journalisee': bool(permission.journalisee),
        'portee_maximale': permission.portee_maximale,
        'roles': [_ligne_role(r, par_role.get(r.code, 0)) for r in roles],
        'total_roles': len(roles),
        'total_comptes_roles': len(comptes),
        'total_comptes_derogation': len(comptes_directs),
        'total_comptes': len(comptes) + len(comptes_directs),
        'comptes_roles': [
            _ligne_compte(c) for c in comptes[:LIMITE_ECHANTILLON]
        ],
        'comptes_derogation': [
            _ligne_compte(c) for c in comptes_directs[:LIMITE_ECHANTILLON]
        ],
    }


def impact_role(code_role):
    """Impact d'un rôle : permissions portées, comptes titulaires, modules.

    Retourne ``None`` si le rôle n'existe pas en base. La sensibilité et le
    domaine viennent du rôle chargé en base (cf. ``catalogue_roles``).
    """
    role = RoleMetier.objects.filter(code=code_role).first()
    if role is None:
        return None

    aujourdhui = _aujourdhui()
    permissions = list(
        role.permissions.order_by('module', 'ressource', 'action')
    )
    attributions = (
        AttributionRole.objects
        .filter(role=role, statut=AttributionRole.Statut.ACTIVE)
        .select_related('compte', 'compte__user', 'compte__personne', 'role')
    )
    titulaires = [
        a.compte for a in attributions if a.est_active(aujourdhui)
    ]

    par_module = {}
    for permission in permissions:
        par_module.setdefault(permission.module, []).append(permission.code)

    return {
        'type': 'role',
        'code': role.code,
        'libelle': role.libelle,
        'description': role.description,
        'domaine': role.domaine,
        'niveau_defaut': role.niveau_defaut,
        'perimetre_defaut': role.perimetre_defaut,
        'canal_impose': role.canal_impose,
        'sensible': bool(role.sensible),
        'disponible': bool(role.disponible),
        'actif': bool(role.actif),
        'cumulable': bool(role.cumulable),
        'date_creation': role.date_creation,
        'date_modification': role.date_modification,
        'total_permissions': len(permissions),
        'permissions_par_module': _grouper_par_module(
            [p.code for p in permissions]
        ),
        'modules_impactes': sorted(par_module.keys()),
        'permissions_sensibles': [
            p.code for p in permissions
            if sensibilite_permission(p) == 'CRITIQUE'
        ],
        'total_titulaires': len(titulaires),
        'titulaires': [
            _ligne_compte(c) for c in titulaires[:LIMITE_ECHANTILLON]
        ],
    }


def impact_module(code_module):
    """Impact d'un module : permissions, rôles porteurs, comptes titulaires.

    Chaînon manquant de la cartographie intermodules (§28) :
    MODULE → PERMISSIONS → RÔLES → COMPTES. Lecture pure et déterministe,
    dérivée exclusivement de la base : ``PermissionMetier`` (portée
    ``module``), rôles octroyants (M2M), titulaires via ``_comptes_des_roles``.

    Retourne ``None`` si le module n'existe ni dans le catalogue
    (``referentiel.catalogue_modules.MODULES``) ni en base — la vue décidera
    du 404. Un module catalogué mais sans permission en base renvoie un
    objet vide-partiel (totaux à zéro), jamais une erreur.
    """
    code = (code_module or '').strip()
    if not code:
        return None
    connu_catalogue = code in MODULES
    permissions = list(
        PermissionMetier.objects.filter(module=code).order_by(
            'ressource', 'action',
        )
    )
    if not permissions and not connu_catalogue:
        return None

    aujourdhui = _aujourdhui()
    roles = list(
        RoleMetier.objects.filter(
            permissions__in=permissions, actif=True,
        ).distinct().order_by('domaine', 'ordre')
    )
    comptes, par_role = _comptes_des_roles(roles, aujourdhui)

    lignes_permissions = [
        {
            'code': permission.code,
            'ressource': permission.ressource,
            'action': permission.action,
            'niveau': niveau_verbe(permission.action),
            'criticite': sensibilite_permission(permission),
            'sensible': sensibilite_permission(permission) != 'NORMALE',
        }
        for permission in permissions
    ]
    niveaux_criticite = {'NORMALE': 0, 'SENSIBLE': 1, 'CRITIQUE': 2}
    criticite_max = 'NORMALE'
    for ligne in lignes_permissions:
        if niveaux_criticite[ligne['criticite']] > niveaux_criticite[criticite_max]:
            criticite_max = ligne['criticite']

    return {
        'type': 'module',
        'module': code,
        'module_libelle': libelle_module(code),
        'catalogue': connu_catalogue,
        'permissions': lignes_permissions,
        'total_permissions': len(lignes_permissions),
        'roles': [_ligne_role(r, par_role.get(r.code, 0)) for r in roles],
        'total_roles': len(roles),
        'total_comptes': len(comptes),
        'criticite_max': criticite_max,
        'roles_sensibles': [r.code for r in roles if r.sensible],
        'comptes': [
            _ligne_compte(c) for c in comptes[:LIMITE_ECHANTILLON]
        ],
    }


def impact_utilisateur(user_id):
    """Impact d'un utilisateur : rôles, dérogations, accès effectifs.

    ``user_id`` est l'identifiant du ``User`` Django (source de vérité de
    l'identité) ; le compte CURP est résolu par la relation
    ``profil_habilitation``. Retourne ``None`` si ni compte ni utilisateur
    n'existe (la vue décidera du 404).

    La résolution effective est DÉLÉGUÉE à
    ``comptes_admin.permissions_effectives`` — aucune logique parallèle :
    attributions de rôles actives + dérogations actives, retraits
    prioritaires. L'arbre distingue l'origine de chaque accès (rôle porteur
    ou octroi direct) ; les accès retirés sont listés à part, jamais
    « simulés ».
    """
    compte = (
        CompteUtilisateur.objects
        .filter(user_id=user_id)
        .select_related('user', 'personne')
        .first()
    )
    if compte is None:
        return None

    aujourdhui = _aujourdhui()
    attributions = (
        compte.attributions
        .filter(statut=AttributionRole.Statut.ACTIVE)
        .select_related('role')
        .prefetch_related('perimetres')
    )
    roles_actifs = [
        a for a in attributions
        if a.est_active(aujourdhui) and a.role_id and a.role.actif
    ]

    derogations = list(
        compte.derogations
        .filter(statut=PermissionAttribuee.Statut.ACTIVE)
        .select_related('permission')
    )
    octrois_directs = [
        d for d in derogations
        if d.est_active(aujourdhui) and d.sens == PermissionAttribuee.Sens.OCTROI
    ]
    retraits = [
        d for d in derogations
        if d.est_active(aujourdhui) and d.sens == PermissionAttribuee.Sens.RETRAIT
    ]

    delegations_recues = [
        d for d in DelegationHabilitation.objects
        .filter(delegataire=compte, statut=DelegationHabilitation.Statut.ACTIVE)
        .select_related('delegant', 'delegant__user', 'delegant__personne')
        .prefetch_related('roles', 'permissions')
        if d.est_active(aujourdhui)
    ]

    # Résolution effective : service CURP existant, jamais réinventé ici.
    effectifs = permissions_effectives(compte)

    # Arbre d'accès : rôle → module → permissions (catalogue du rôle).
    arbre_roles = []
    codes_herites = set()
    for attribution in roles_actifs:
        role = attribution.role
        permissions_role = sorted(role.permissions.values_list('code', flat=True))
        codes_herites.update(permissions_role)
        arbre_roles.append({
            'code': role.code,
            'libelle': role.libelle,
            'sensible': bool(role.sensible),
            'niveau_effectif': attribution.niveau_effectif,
            'perimetres': [_perimetre(p) for p in attribution.perimetres.all()],
            'date_debut': attribution.date_debut,
            'date_fin': attribution.date_fin,
            'attribue_par': (
                attribution.attribue_par.get_username()
                if attribution.attribue_par_id else ''
            ),
            'modules': _grouper_par_module(permissions_role),
            'permissions': permissions_role,
        })

    octrois_directs_codes = [d.permission.code for d in octrois_directs]
    codes_retraits = [d.permission.code for d in retraits]
    modules_effectifs = sorted({
        code.split('.')[0] for code in effectifs if '.' in code
    })

    return _charge_utilisateur(
        compte, roles_actifs, arbre_roles, len(roles_actifs),
        octrois_directs, octrois_directs_codes, retraits, codes_retraits,
        len(codes_herites), effectifs, modules_effectifs, delegations_recues,
    )


def _charge_utilisateur(
    compte, roles_actifs, arbre_roles, total_roles,
    octrois_directs, octrois_directs_codes, retraits, codes_retraits,
    total_heritees, effectifs, modules_effectifs, delegations_recues,
):
    """Constitue la charge utile d'impact d'un utilisateur (helper privé)."""
    modules_effectifs_detail = [
        {'module': code, 'module_libelle': libelle_module(code)}
        for code in modules_effectifs
    ]
    return {
        'type': 'utilisateur',
        'user_id': compte.user_id,
        'compte_id': compte.pk,
        'username': compte.user.get_username() if compte.user else '',
        'nom': getattr(compte.personne, 'nom', '') or '',
        'prenoms': getattr(compte.personne, 'prenoms', '') or '',
        'statut': compte.statut,
        'motif_statut': compte.motif_statut,
        'canal': compte.canal,
        'mfa_actif': bool(compte.mfa_actif),
        'date_expiration': compte.date_expiration,
        'derniere_connexion': compte.derniere_connexion,
        'derniere_activite': compte.derniere_activite,
        'roles': arbre_roles,
        'total_roles': total_roles,
        'permissions_directes': [
            {
                'code': d.permission.code,
                'module': d.permission.module,
                'module_libelle': libelle_module(d.permission.module),
                'motif': d.motif,
                'date_fin': d.date_fin,
                'sensible': sensibilite_permission(d.permission) != 'NORMALE',
            }
            for d in octrois_directs
        ],
        'permissions_retraits': [
            {'code': d.permission.code, 'motif': d.motif}
            for d in retraits
        ],
        'total_directes': len(octrois_directs_codes),
        'total_heritees': total_heritees,
        'total_effectives': len(effectifs),
        'total_retraits': len(codes_retraits),
        'modules_effectifs': modules_effectifs_detail,
        'actions_sensibles_effectives': sorted(
            _codes_sensibles_en_base(effectifs)
        ),
        'delegations_recues': [
            {
                'id': d.pk,
                'delegant': _ligne_compte(d.delegant),
                'date_debut': d.date_debut,
                'date_fin': d.date_fin,
                'roles': [r.code for r in d.roles.all()],
                'permissions': [p.code for p in d.permissions.all()],
            }
            for d in delegations_recues
        ],
        # Arbre lisible : Utilisateur → Rôle → Module → Permission, plus les
        # octrois directs. Aucun accès simulé : chaque branche vient des
        # attributions/dérogations effectives du compte.
        'arbre': {
            'roles': arbre_roles,
            'derogations': octrois_directs_codes,
            'retraits': codes_retraits,
        },
        'octrois_directs': octrois_directs_codes,
        'retraits': codes_retraits,
    }
