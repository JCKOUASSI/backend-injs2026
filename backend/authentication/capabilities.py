"""Capacités explicites de l'utilisateur courant pour l'interface (P00-06).

Ce module ne crée **aucune** logique d'autorisation nouvelle : il projette les
sources de vérité déjà en place sous une forme consommable par l'UI :

* permissions personnalisées ``authentication.*`` (groupes ``ROLE_*`` issus de
  ``ROLE_POLICY``), via ``user.has_perm`` ;
* ensembles de rôles de :mod:`authentication.role_groups`, les mêmes
  constantes que les vues et classes de permission DRF utilisent ;
* classes de permission DRF existantes (``IsSecretariatOrDFRC``…) évaluées sur
  une requête minimale ;
* helpers de :mod:`formations.access` pour les périmètres concrets.

L'API reste la seule autorité : ces capacités servent uniquement à afficher ou
masquer des actions côté interface. Un écart d'affichage ne peut jamais ouvrir
un droit (les vues gardent leurs ``permission_classes``).
"""
from types import SimpleNamespace

from django.contrib.auth import get_user_model

from authentication.permissions import IsSecretariatOrDFRC
from authentication.role_groups import (
    ADMIN_LEVEL_ROLES,
    ALLOWED_WEB_ROLES,
    DASHBOARD_SECRETARIAT_FILTER_ROLES,
    FINANCE_MODULE_ROLES,
    GLOBAL_ACCESS_ROLES,
    GLOBAL_STATS_ROLES,
    LISTE_CLASSE_EXPORT_ROLES,
    OPERATIONAL_WEB_ROLES,
    PARTICIPANT_LIST_ROLES,
    PRESENCE_ACTION_ROLES,
    PRESENCE_VIEW_ROLES,
    ROLE_HIERARCHY,
    STATS_ACCESS_ROLES,
    SUPERVISION_ROLES,
    USER_MUTATION_ROLES,
    USERS_PAGE_ROLES,
    FORMATION_MUTATION_ROLES,
    MODULE_ARCHIVE_ROLES,
    SECRETARIAT_ROLES,
    get_user_role,
    get_user_roles,
    user_in_roles,
    user_role_context,
)

User = get_user_model()

# Niveaux d'accès du vocabulaire cible (README §8). Le moteur exécutable
# niveau × rôle × permission × module × périmètre arrive au P01-05 ; ce
# mapping provisoire est la transcription de la matrice PUBLIÉE au README §8
# (P00-03), dans l'attente de la validation commanditaire du gate G2.
# Il est volontairement isolé ici pour être remplacé par P01-05 sans toucher
# au reste du calcul.
NIVEAU_PROVISOIRE_PAR_ROLE = {
    User.Role.ADMIN: 'N4',
    User.Role.DIRECTION: 'N4',
    User.Role.CHEF_INJS_ADMIN: 'N4',
    User.Role.INJS_ADMIN: 'N4',
    User.Role.CHEF_SECRETARIAT: 'N3',
    User.Role.FINANCE: 'N3',
    User.Role.SECRETARIAT: 'N2',
    User.Role.ENCADRANT: 'N2',
    User.Role.SUPERVISEUR: 'N2',
    User.Role.FORMATEUR: 'N2',
    User.Role.ARCHIVE: 'N1',
    User.Role.AUDITEUR: 'N1',
}
NIVEAUX_ORDRES = ('N0', 'N1', 'N2', 'N3', 'N4')

# Rôles pouvant paramétrer la rémunération des formateurs (vues rôle en dur :
# formations/api_views.py contrôle FINANCE/DIRECTION pour l'écriture des
# réglages finance).
FINANCE_PARAMETRAGE_ROLES = frozenset({User.Role.FINANCE, User.Role.DIRECTION})

# Étiquettes de périmètre du modèle cible.
PERIMETRE_GLOBAL = 'INJS_ENTIER'
PERIMETRE_SERVICE = 'SERVICE'
PERIMETRE_FORMATION = 'FORMATION'
PERIMETRE_GROUPE = 'GROUPE'
PERIMETRE_MODULE = 'MODULE'
PERIMETRE_PROPRE_COMPTE = 'PROPRE_COMPTE'
PERIMETRE_ETUDIANT = 'ETUDIANT'


def _roles(*role_sets):
    """Union d'ensembles de rôles."""
    resultat = set()
    for ensemble in role_sets:
        resultat.update(ensemble)
    return frozenset(resultat)


# Descripteurs des capacités : {module: {action: source}}.
#  * ('roles', ensemble)          → appartenance à l'un des rôles ;
#  * ('perm', 'app.codename')     → permission Django (groupe ROLE_*) ;
#  * ('permclass', Classe, verbe) → classe DRF évaluée avec le verbe HTTP ;
#  * ('callable', fonction)       → helper métier recevant l'utilisateur.
# Ajouter un module = ajouter une entrée ; aucune autre logique ici.
CAPACITES_DESCRIPTEURS = {
    'web': {
        'acceder': ('roles', ALLOWED_WEB_ROLES),
        'operationnel': ('roles', OPERATIONAL_WEB_ROLES),
    },
    'utilisateurs': {
        'voir': ('roles', USERS_PAGE_ROLES),
        'gerer': ('roles', USER_MUTATION_ROLES),
    },
    'participants': {
        'lister': ('roles', PARTICIPANT_LIST_ROLES),
        'creer': ('roles', ADMIN_LEVEL_ROLES),
        'gerer': ('roles', FORMATION_MUTATION_ROLES),
    },
    'modules': {
        'archiver': ('callable', 'formations.access.can_archive_module'),
    },
    'presences': {
        'voir': ('roles', PRESENCE_VIEW_ROLES),
        'agir': ('roles', PRESENCE_ACTION_ROLES),
        'superviser': ('roles', SUPERVISION_ROLES),
    },
    'finance': {
        'voir': ('roles', FINANCE_MODULE_ROLES),
        'exporter': ('roles', FINANCE_MODULE_ROLES),
        'parametrer': ('roles', FINANCE_PARAMETRAGE_ROLES),
    },
    'statistiques': {
        'voir': ('roles', STATS_ACCESS_ROLES),
        'voir_globales': ('roles', GLOBAL_STATS_ROLES),
    },
    'evaluations': {
        'gerer_questionnaires': ('perm', 'authentication.manage_questionnaires'),
        'consulter': ('perm', 'authentication.consult_evaluation'),
    },
    'notes': {
        'gerer': ('perm', 'authentication.manage_notes'),
        'valider_decisions': ('perm', 'authentication.validate_decisions'),
    },
    'scolarite': {
        # Réutilise DIRECTEMENT la classe DRF qui garde les vues scolaires :
        # mêmes rôles complets et mêmes rôles en lecture seule.
        'voir': ('permclass', IsSecretariatOrDFRC, 'GET'),
        'agir': ('permclass', IsSecretariatOrDFRC, 'POST'),
    },
    'exports': {
        'liste_classe': ('roles', LISTE_CLASSE_EXPORT_ROLES),
    },
    'dashboard': {
        'filtrer_secretariat': ('roles', DASHBOARD_SECRETARIAT_FILTER_ROLES),
    },
    # CURP U4 — console d'administration des comptes. Source callable pour
    # appliquer le kill-switch même au super-utilisateur (un drapeau éteint
    # reste éteint pour tout le monde, voir parametres.flags).
    'habilitations_admin': {
        'gerer': ('callable', 'authentication.capabilities._peut_gerer_console_curp'),
    },
}


def _peut_gerer_console_curp(user):
    """Console CURP U4 visible uniquement si le drapeau est ouvert ET que
    l'utilisateur fait partie du trio d'administration de l'habilitation.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    try:
        from parametres.flags import is_enabled
        if not is_enabled('flag.curp_ui_admin', user):
            return False
    except Exception:
        # Application parametres absente ou indisponible : repli fermé.
        return False
    return user_in_roles(
        user, ('ADMIN', 'INJS_ADMIN', 'CHEF_INJS_ADMIN'),
    )


def _evalue_perm_class(permission_class, method, user):
    """Évalue une classe de permission DRF sur une requête minimale."""
    requete = SimpleNamespace(user=user, method=method)
    return permission_class().has_permission(requete, None)


def _evalue_source(user, source):
    """Évalue une source de capacité décrite dans CAPACITES_DESCRIPTEURS."""
    genre = source[0]
    if genre == 'roles':
        return user_in_roles(user, source[1])
    if genre == 'perm':
        return user.has_perm(source[1])
    if genre == 'permclass':
        return _evalue_perm_class(source[1], source[2], user)
    if genre == 'callable':
        chemin = source[1]
        module_path, nom = chemin.rsplit('.', 1)
        import importlib
        fonction = getattr(importlib.import_module(module_path), nom)
        return bool(fonction(user))
    raise ValueError(f'Source de capacité inconnue : {genre!r}')


def _niveau_utilisateur(roles):
    """Niveau le plus élevé parmi les rôles (mapping provisoire P00-06)."""
    niveau = None
    rang = -1
    for role in roles:
        candidat = NIVEAU_PROVISOIRE_PAR_ROLE.get(role)
        if candidat and NIVEAUX_ORDRES.index(candidat) > rang:
            niveau = candidat
            rang = NIVEAUX_ORDRES.index(candidat)
    return niveau


def _identifiants_formations(user, roles):
    """IDs des formations du périmètre concret (hors périmètre global).

    Réutilise les mêmes chemins de relations que
    ``formations.access.modules_queryset_for_user`` /
    ``formation_accessible`` : secrétariat rattaché, modules supervisés,
    inscriptions de l'étudiant lié au compte.
    """
    from formations.models import Module

    qs = Module.objects.none()
    if roles & SECRETARIAT_ROLES and user.secretariat_id:
        qs = qs | Module.objects.filter(secretariat_id=user.secretariat_id)
    if 'ENCADRANT' in roles or 'SUPERVISEUR' in roles:
        qs = qs | Module.objects.filter(superviseur=user)
    if 'AUDITEUR' in roles:
        qs = qs | Module.objects.filter(
            module_participants__participant__user=user
        )
    return sorted(set(qs.values_list('formation_id', flat=True).distinct()))


def _perimetres(user, roles):
    """Étiquettes de périmètre + identifiants concrets (secrétariats, formations, groupes)."""
    if getattr(user, 'is_superuser', False) or roles & GLOBAL_ACCESS_ROLES:
        return {
            'niveaux': [PERIMETRE_GLOBAL],
            'secretariats': '*',
            'formations': '*',
            'groupes': '*',
        }

    niveaux = []
    if User.Role.FINANCE in roles:
        # Périmètre global LIMITÉ au domaine financier (les modules de
        # formation restent hors d'accès, voir formations.access).
        niveaux.append(PERIMETRE_GLOBAL)
    if roles & SECRETARIAT_ROLES:
        niveaux.append(PERIMETRE_SERVICE)
    if 'ENCADRANT' in roles or 'SUPERVISEUR' in roles:
        niveaux.extend([PERIMETRE_FORMATION, PERIMETRE_GROUPE])
    if 'ENCADRANT' in roles:
        niveaux.append(PERIMETRE_MODULE)
    if 'FORMATEUR' in roles:
        niveaux.extend([PERIMETRE_MODULE, PERIMETRE_PROPRE_COMPTE])
    if 'AUDITEUR' in roles:
        niveaux.extend([PERIMETRE_PROPRE_COMPTE, PERIMETRE_ETUDIANT])

    if User.Role.FINANCE in roles:
        secretariats = '*'
    elif roles & SECRETARIAT_ROLES and user.secretariat_id:
        secretariats = [user.secretariat_id]
    else:
        secretariats = []

    formation_ids = _identifiants_formations(user, roles)
    formations = sorted(formation_ids)

    # Groupes LMD rattachés aux cycles (RefFormation) des modules accessibles :
    # Module → ref_module → RefModule.formations (M2M) → Groupe. Ce pont est
    # conservateur (un cycle peut couvrir plusieurs groupes concrets) et sera
    # affiné par le pont Formation ↔ RefFormation attendu au P04-05 (D3).
    groupes = []
    if formation_ids:
        try:
            from formations.models import Module as _Module
            from scolarite.models import Groupe
            ref_formation_ids = (
                _Module.objects
                .filter(formation_id__in=formation_ids, ref_module__isnull=False)
                .values_list('ref_module__formations', flat=True).distinct()
            )
            groupes = sorted(
                Groupe.objects.filter(ref_formation_id__in=list(ref_formation_ids))
                .values_list('id', flat=True).distinct()
            )
        except Exception:  # pragma: no cover - filet défensif (app absente en test ciblé)
            groupes = []

    return {
        'niveaux': sorted(set(niveaux)),
        'secretariats': secretariats,
        'formations': formations,
        'groupes': groupes,
    }


# ---------------------------------------------------------------------------
# Sérialiseurs de documentation OpenAPI (la réponse est dynamique, mais le
# contrat est déclaré pour /api/schema/ et les clients générés).
# ---------------------------------------------------------------------------
from rest_framework import serializers  # noqa: E402


class CapacitesPerimetreSerializer(serializers.Serializer):
    """Périmètre effectif : étiquettes de niveau + identifiants concrets.

    ``secretariats``, ``formations`` et ``groupes`` valent soit ``'*'``
    (périmètre global), soit une liste d'identifiants entiers.
    """

    niveaux = serializers.ListField(child=serializers.CharField(), help_text=(
        "Étiquettes de périmètre : INJS_ENTIER, SERVICE, FORMATION, GROUPE, "
        "MODULE, ETUDIANT, PROPRE_COMPTE."))
    secretariats = serializers.JSONField(help_text="'*' (global) ou liste d'identifiants.")
    formations = serializers.JSONField(help_text="'*' (global) ou liste d'identifiants.")
    groupes = serializers.JSONField(help_text="'*' (global) ou liste d'identifiants.")


class CapabilitiesResponseSerializer(serializers.Serializer):
    """Contrat de GET /api/auth/capabilities/ (P00-06)."""

    version = serializers.IntegerField()
    role = serializers.CharField(allow_null=True, help_text="Rôle principal effectif.")
    roles = serializers.ListField(child=serializers.CharField(), help_text="Tous les rôles effectifs.")
    hierarchie = serializers.ListField(child=serializers.CharField())
    niveau = serializers.CharField(
        allow_null=True,
        help_text="Niveau N0–N4 PROVISOIRE dérivé de la matrice publiée (README §8) ; "
                  "le moteur validé au gate G2 est livré en P01-05.",
    )
    niveau_provisoire = serializers.BooleanField()
    capacites = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField()),
        help_text="{module: [actions]} — source unique de vérité des droits d'affichage UI.",
    )
    perimetres = CapacitesPerimetreSerializer()
    role_context = serializers.JSONField(required=False, help_text="Contexte de rôles déjà servi à /auth/me/.")


def compute_capabilities(user):
    """Projection complète des droits de l'utilisateur pour l'interface.

    Retourne les rôles effectifs, le niveau provisoire N0–N4, le dictionnaire
    ``{module: [actions]``}, les périmètres et le contexte de rôles déjà servi
    à la connexion. Un super-utilisateur obtient toutes les actions.
    """
    roles = get_user_roles(user) if user and getattr(user, 'is_authenticated', False) else frozenset()
    roles = frozenset(roles)

    capacites = {}
    superuser = bool(getattr(user, 'is_superuser', False))
    for module, actions in CAPACITES_DESCRIPTEURS.items():
        if superuser:
            capacites[module] = sorted(actions.keys())
            continue
        capacites[module] = sorted(
            action for action, source in actions.items()
            if _evalue_source(user, source)
        )

    projection = {
        'version': 1,
        'role': get_user_role(user) if roles else getattr(user, 'role', None),
        'roles': sorted(roles),
        'hierarchie': list(ROLE_HIERARCHY),
        'niveau': _niveau_utilisateur(roles),
        'niveau_provisoire': True,
        'capacites': capacites,
        'perimetres': _perimetres(user, roles) if roles else {
            'niveaux': [], 'secretariats': [], 'formations': [], 'groupes': [],
        },
        'role_context': user_role_context(user) if roles else {},
    }
    # CURP U2 — clé additive strictement descriptive (le moteur est en mode
    # observation : cette clé n'accorde ni ne retire aucune action). L'app
    # habilitations est techniquement optionnelle (repli par retrait d'app).
    projection['habilitations'] = _projection_habilitations(user)
    return projection


def _projection_habilitations(user):
    try:
        from habilitations.services.projection import projection_capacites
    except Exception:
        # Repli : application habilitations absente, on l'indique sans casser
        # la capacité.
        return {'gouverne': False, 'mode': 'OFF'}
    try:
        return projection_capacites(user)
    except Exception:
        return {'gouverne': False, 'mode': 'OFF'}
