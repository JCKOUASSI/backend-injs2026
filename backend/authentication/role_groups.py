import logging
from contextlib import contextmanager

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

User = get_user_model()
logger = logging.getLogger(__name__)

_bulk_role_sync_depth = 0

# Lot L4b : la compatibilité transitoire `ROLES_LEGACY` / `normalize_role()` a
# été supprimée. L'audit du 26/09/2026 a établi qu'aucun code de production,
# aucune API, aucun client web ou mobile et aucune ligne de base n'utilisait
# encore la chaîne historique `CPFAE_ADMIN` : la conserver n'était qu'un
# contrat avec personne. Le RBAC est désormais verrouillé applicativement
# (`User.Role.choices`) **et** en base (contrainte CHECK, migration
# `authentication.0024`).


def is_bulk_role_sync():
    """True pendant sync_all_users_role_groups (évite les signaux m2m/post_save)."""
    return _bulk_role_sync_depth > 0


@contextmanager
def _bulk_role_sync():
    global _bulk_role_sync_depth
    _bulk_role_sync_depth += 1
    try:
        yield
    finally:
        _bulk_role_sync_depth -= 1


# Rôles pouvant accéder à l'admin Django ET à la plateforme web.
DUAL_ACCESS_ROLES = frozenset({
    User.Role.ADMIN,
    User.Role.CHEF_INJS_ADMIN,
    User.Role.INJS_ADMIN,
})

# Rôles encadrants reconnus pour le badgeage mobile (legacy SUPERVISEUR inclus).
MOBILE_ENCADRANT_ROLES = frozenset({
    User.Role.ENCADRANT,
    User.Role.SUPERVISEUR,
})

# Rôles réservés à l'application mobile (pas de plateforme web ni admin Django).
MOBILE_ONLY_ROLES = frozenset({
    User.Role.AUDITEUR,
    User.Role.FORMATEUR,
})

# Rôles autorisés sur la plateforme web React (sans device_id mobile).
ALLOWED_WEB_ROLES = frozenset({
    *DUAL_ACCESS_ROLES,
    User.Role.DIRECTION,
    User.Role.CHEF_SECRETARIAT,
    User.Role.SECRETARIAT,
    User.Role.FINANCE,
    User.Role.ARCHIVE,
    User.Role.ENCADRANT,
    User.Role.SUPERVISEUR,
})

# Personnel web hors module Finance (badgeage, formations, modules, dashboard opérationnel).
OPERATIONAL_WEB_ROLES = frozenset(ALLOWED_WEB_ROLES - {User.Role.FINANCE})

# Alias sémantique — même ensemble que DUAL_ACCESS_ROLES.
ADMIN_LEVEL_ROLES = DUAL_ACCESS_ROLES

SECRETARIAT_ROLES = frozenset({
    User.Role.CHEF_SECRETARIAT,
    User.Role.SECRETARIAT,
})

# Accès global formations / dashboard (filtre secrétariat optionnel).
GLOBAL_ACCESS_ROLES = frozenset({
    *ADMIN_LEVEL_ROLES,
    User.Role.DIRECTION,
    User.Role.ARCHIVE,
})

DASHBOARD_SECRETARIAT_FILTER_ROLES = GLOBAL_ACCESS_ROLES

PARTICIPANT_LIST_ROLES = frozenset({
    *ADMIN_LEVEL_ROLES,
    User.Role.DIRECTION,
    User.Role.ARCHIVE,
    *SECRETARIAT_ROLES,
    User.Role.ENCADRANT,
})

LISTE_CLASSE_EXPORT_ROLES = frozenset({
    *ADMIN_LEVEL_ROLES,
    User.Role.DIRECTION,
    User.Role.ARCHIVE,
    *SECRETARIAT_ROLES,
    User.Role.ENCADRANT,
})

STATS_ACCESS_ROLES = frozenset({
    *ADMIN_LEVEL_ROLES,
    User.Role.DIRECTION,
    User.Role.ARCHIVE,
    *SECRETARIAT_ROLES,
    User.Role.FINANCE,
    User.Role.ENCADRANT,
})

GLOBAL_STATS_ROLES = frozenset({
    *ADMIN_LEVEL_ROLES,
    User.Role.DIRECTION,
    User.Role.ARCHIVE,
    User.Role.FINANCE,
})

USERS_PAGE_ROLES = frozenset({
    *ADMIN_LEVEL_ROLES,
    User.Role.DIRECTION,
    *SECRETARIAT_ROLES,
})

USER_MUTATION_ROLES = frozenset({
    *ADMIN_LEVEL_ROLES,
    *SECRETARIAT_ROLES,
})

BADGE_ACCOUNT_ROLES = MOBILE_ONLY_ROLES

USER_MANAGEABLE_ROLES = frozenset({
    User.Role.DIRECTION,
    User.Role.CHEF_INJS_ADMIN,
    User.Role.INJS_ADMIN,
    *SECRETARIAT_ROLES,
    User.Role.FINANCE,
    User.Role.ARCHIVE,
    User.Role.ENCADRANT,
    User.Role.SUPERVISEUR,
    *MOBILE_ONLY_ROLES,
})

FINANCE_MODULE_ROLES = frozenset({
    User.Role.FINANCE,
    User.Role.DIRECTION,
    User.Role.ARCHIVE,
})

FORMATION_MUTATION_ROLES = frozenset({
    *ADMIN_LEVEL_ROLES,
    *SECRETARIAT_ROLES,
})

MODULE_ARCHIVE_ROLES = frozenset({
    *FORMATION_MUTATION_ROLES,
    User.Role.DIRECTION,
})

PRESENCE_VIEW_ROLES = frozenset({
    *ADMIN_LEVEL_ROLES,
    User.Role.DIRECTION,
    User.Role.ARCHIVE,
    *SECRETARIAT_ROLES,
    User.Role.ENCADRANT,
})

PRESENCE_ACTION_ROLES = frozenset({
    *ADMIN_LEVEL_ROLES,
    User.Role.ENCADRANT,
    *SECRETARIAT_ROLES,
})

SUPERVISION_ROLES = frozenset({
    *ADMIN_LEVEL_ROLES,
    User.Role.ENCADRANT,
    *SECRETARIAT_ROLES,
})

IMPORT_ROLES = FORMATION_MUTATION_ROLES

# Combinaisons multi-rôles autorisées (phase de migration progressive).
# Un seul rôle : toujours autorisé (sauf mobile + autre, voir validate_role_combination).
ALLOWED_MULTI_ROLE_COMBINATIONS = frozenset({
    frozenset({User.Role.CHEF_SECRETARIAT, User.Role.ENCADRANT}),
    frozenset({User.Role.SECRETARIAT, User.Role.ENCADRANT}),
    frozenset({User.Role.CHEF_SECRETARIAT, User.Role.SUPERVISEUR}),
    frozenset({User.Role.SECRETARIAT, User.Role.SUPERVISEUR}),
    frozenset({User.Role.ENCADRANT, User.Role.SUPERVISEUR}),
})

# Hiérarchie stricte : index bas = rang élevé.
ROLE_HIERARCHY = [
    User.Role.ADMIN,
    User.Role.DIRECTION,
    User.Role.CHEF_INJS_ADMIN,
    User.Role.INJS_ADMIN,
    User.Role.CHEF_SECRETARIAT,
    User.Role.SECRETARIAT,
    User.Role.FINANCE,
    User.Role.ARCHIVE,
    User.Role.ENCADRANT,
    User.Role.SUPERVISEUR,
    User.Role.FORMATEUR,
    User.Role.AUDITEUR,
]

ROLE_LABELS = {value: str(label) for value, label in User.Role.choices}

ROLE_GROUP_NAMES = {
    User.Role.ADMIN: "ROLE_ADMIN",
    User.Role.DIRECTION: "ROLE_DIRECTION",
    User.Role.CHEF_INJS_ADMIN: "ROLE_CHEF_INJS_ADMIN",
    User.Role.INJS_ADMIN: "ROLE_INJS_ADMIN",
    User.Role.CHEF_SECRETARIAT: "ROLE_CHEF_SECRETARIAT",
    User.Role.SECRETARIAT: "ROLE_SECRETARIAT",
    User.Role.FINANCE: "ROLE_FINANCE",
    User.Role.ARCHIVE: "ROLE_ARCHIVE",
    User.Role.ENCADRANT: "ROLE_ENCADRANT",
    User.Role.SUPERVISEUR: "ROLE_SUPERVISEUR",
    User.Role.FORMATEUR: "ROLE_FORMATEUR",
    User.Role.AUDITEUR: "ROLE_AUDITEUR",
}

GROUP_NAME_TO_ROLE = {name: role for role, name in ROLE_GROUP_NAMES.items()}

# Permissions métier (modèle User) assignées aux groupes via ROLE_POLICY.
CUSTOM_PERMISSIONS = {
    'access_web': 'authentication.access_web',
    'operational_web': 'authentication.operational_web',
    'mutate_users': 'authentication.mutate_users',
    'global_scope': 'authentication.global_scope',
    'list_participants': 'authentication.list_participants',
    'finance_module': 'authentication.finance_module',
    'manage_questionnaires': 'authentication.manage_questionnaires',
    'manage_notes': 'authentication.manage_notes',
    'validate_decisions': 'authentication.validate_decisions',
    'consult_evaluation': 'authentication.consult_evaluation',
}

CORE_APPS = ("authentication", "formations", "presences", "exports")

ROLE_POLICY = {
    User.Role.ADMIN: {
        "apps": CORE_APPS,
        "actions": ("view", "add", "change", "delete"),
        "custom": (
            "access_web", "operational_web", "mutate_users", "global_scope",
            "list_participants", "manage_questionnaires", "manage_notes",
            "validate_decisions", "consult_evaluation",
        ),
    },
    User.Role.CHEF_INJS_ADMIN: {
        "apps": CORE_APPS,
        "actions": ("view", "add", "change", "delete"),
        "custom": (
            "access_web", "operational_web", "mutate_users", "global_scope",
            "list_participants", "manage_questionnaires", "manage_notes",
            "validate_decisions", "consult_evaluation",
        ),
    },
    User.Role.INJS_ADMIN: {
        "apps": CORE_APPS,
        "actions": ("view", "add", "change", "delete"),
        "custom": (
            "access_web", "operational_web", "mutate_users", "global_scope",
            "list_participants", "manage_questionnaires", "manage_notes",
            "validate_decisions", "consult_evaluation",
        ),
    },
    User.Role.DIRECTION: {
        "apps": CORE_APPS,
        "actions": ("view",),
        "custom": (
            "access_web", "operational_web", "global_scope", "list_participants",
            "manage_notes", "validate_decisions", "consult_evaluation",
        ),
    },
    User.Role.CHEF_SECRETARIAT: {
        "apps": ("formations", "presences", "suiviEvaluation"),
        "actions": ("view", "add", "change", "delete"),
        # Interdit uniquement la création de nouvelles fiches auditeur.
        # Toutes les autres actions (y compris suppression) restent autorisées.
        "exclude_codenames": ("add_participant",),
        "custom": (
            "access_web", "operational_web", "mutate_users", "list_participants",
            "manage_questionnaires", "manage_notes", "validate_decisions",
            "consult_evaluation",
        ),
    },
    User.Role.SECRETARIAT: {
        "apps": ("formations", "presences", "suiviEvaluation"),
        "actions": ("view", "add", "change", "delete"),
        "exclude_codenames": ("add_participant",),
        "custom": (
            "access_web", "operational_web", "mutate_users", "list_participants",
            "manage_questionnaires", "manage_notes", "validate_decisions",
            "consult_evaluation",
        ),
    },
    User.Role.FINANCE: {
        "apps": ("formations", "presences", "exports"),
        "actions": ("view",),
        "custom": ("access_web", "finance_module", "consult_evaluation"),
    },
    User.Role.ARCHIVE: {
        "apps": CORE_APPS + ("suiviEvaluation",),
        "actions": ("view",),
        "custom": (
            "access_web", "operational_web", "global_scope", "list_participants",
            "finance_module", "consult_evaluation",
        ),
    },
    User.Role.ENCADRANT: {
        "apps": ("formations", "presences", "suiviEvaluation"),
        "actions": ("view", "add", "change", "delete"),
        "custom": (
            "access_web", "operational_web", "list_participants",
            "manage_questionnaires", "manage_notes", "validate_decisions",
            "consult_evaluation",
        ),
    },
    User.Role.SUPERVISEUR: {
        "apps": ("suiviEvaluation",),
        "actions": ("view", "add", "change", "delete"),
        "custom": (
            "access_web", "operational_web", "manage_questionnaires",
            "manage_notes", "validate_decisions", "consult_evaluation",
        ),
    },
    User.Role.FORMATEUR: {
        "apps": ("formations", "presences"),
        "actions": ("view",),
        "custom": (),
    },
    User.Role.AUDITEUR: {
        "apps": ("formations", "presences"),
        "actions": ("view",),
        "custom": (),
    },
}


def _cached_user_groups(user):
    """Noms de groupes Django de l'utilisateur (cache requête).

    Parcourt `groups.all()` afin de réutiliser un éventuel `prefetch_related`
    du queryset appelant ; sinon le cache d'instance limite à une requête.
    """
    if not hasattr(user, '_role_groups_cache'):
        user._role_groups_cache = {group.name for group in user.groups.all()}
    return user._role_groups_cache


def _roles_from_group_names(group_names):
    """Dérive l'ensemble des rôles à partir des noms de groupes ROLE_*."""
    role_groups = set(group_names) & set(ROLE_GROUP_NAMES.values())
    return frozenset(
        GROUP_NAME_TO_ROLE[name]
        for name in role_groups
        if name in GROUP_NAME_TO_ROLE
    )


def _primary_role_from_roles(roles):
    """Rôle principal (le plus élevé dans la hiérarchie) parmi un ensemble de rôles."""
    if not roles:
        return None
    if len(roles) == 1:
        return next(iter(roles))
    for candidate in ROLE_HIERARCHY:
        if candidate in roles:
            return candidate
    return next(iter(roles))


def _role_from_group_names(group_names):
    """Dérive le rôle principal à partir des noms de groupes ROLE_*."""
    return _primary_role_from_roles(_roles_from_group_names(group_names))


def get_user_roles(user):
    """Ensemble des rôles effectifs — source de vérité : groupes Django ROLE_*."""
    if not user or not getattr(user, 'is_authenticated', True):
        return frozenset()
    if not user.pk:
        role = getattr(user, 'role', None)
        return frozenset({role}) if role else frozenset()
    group_names = _cached_user_groups(user)
    roles = _roles_from_group_names(group_names)
    if roles:
        return roles
    if group_names:
        return frozenset()
    role = getattr(user, 'role', None)
    return frozenset({role}) if role else frozenset()


def get_user_role(user):
    """Rôle principal — le plus élevé dans la hiérarchie parmi les groupes ROLE_*.

    Le champ ``User.role`` est une dénormalisation du rôle principal, synchronisée
    automatiquement (voir ``sync_role_from_group`` / ``sync_user_role_group``).
    """
    if not user or not getattr(user, 'is_authenticated', True):
        return None
    if not user.pk:
        return getattr(user, 'role', None)
    roles = get_user_roles(user)
    if roles:
        return _primary_role_from_roles(roles)
    return getattr(user, 'role', None)


def user_in_roles(user, role_set):
    """Vérifie si l'utilisateur possède au moins un des rôles demandés."""
    roles = get_user_roles(user)
    if not roles:
        return False
    return bool(roles & frozenset(role_set))


def user_is_mobile_encadrant(user):
    """True si le compte peut badger en tant qu'encadrant sur l'app mobile."""
    return user_in_roles(user, MOBILE_ENCADRANT_ROLES)


def validate_role_combination(roles):
    """Valide une combinaison de rôles métier.

    Lève ``ValidationError`` si la combinaison n'est pas autorisée.
    """
    from django.core.exceptions import ValidationError

    role_set = frozenset(roles or ())
    if not role_set:
        return

    if len(role_set) == 1:
        return

    if role_set & MOBILE_ONLY_ROLES:
        mobile = ', '.join(ROLE_LABELS.get(r, r) for r in sorted(role_set & MOBILE_ONLY_ROLES))
        raise ValidationError(
            f'Le rôle {mobile} (application mobile) ne peut pas être combiné avec d\'autres rôles.'
        )

    if role_set not in ALLOWED_MULTI_ROLE_COMBINATIONS:
        allowed_labels = [
            ' + '.join(ROLE_LABELS.get(r, r) for r in sorted(combo))
            for combo in sorted(ALLOWED_MULTI_ROLE_COMBINATIONS, key=lambda c: sorted(c))
        ]
        current = ' + '.join(ROLE_LABELS.get(r, r) for r in sorted(role_set))
        raise ValidationError(
            f'Combinaison « {current} » non autorisée. '
            f'Combinaisons multi-rôles acceptées : {" ; ".join(allowed_labels)}.'
        )


def roles_from_group_queryset(groups):
    """Rôles métier dérivés d'un queryset / iterable de groupes Django."""
    names = [g.name for g in groups]
    return _roles_from_group_names(names)


def role_group_names_for_roles(roles):
    """Noms de groupes Django ROLE_* correspondant à une liste de rôles."""
    return [ROLE_GROUP_NAMES[r] for r in roles if r in ROLE_GROUP_NAMES]


def users_with_roles(roles):
    """Utilisateurs appartenant à au moins un groupe ROLE_* des rôles donnés."""
    names = role_group_names_for_roles(roles)
    if not names:
        return User.objects.none()
    return User.objects.filter(groups__name__in=names).distinct()


def users_with_role(role):
    """Utilisateurs appartenant au groupe ROLE_* du rôle donné."""
    name = ROLE_GROUP_NAMES.get(role)
    if not name:
        return User.objects.none()
    return User.objects.filter(groups__name=name).distinct()


def user_has_perm(user, codename):
    """Vérifie une permission Django (modèle ou custom) via les groupes."""
    if not user or not user.is_authenticated:
        return False
    return user.has_perm(codename)


def get_subordinate_roles(role):
    """Retourne les rôles strictement inférieurs au rôle donné."""
    if role not in ROLE_HIERARCHY:
        return []
    idx = ROLE_HIERARCHY.index(role)
    return ROLE_HIERARCHY[idx + 1:]


def get_creatable_roles(role):
    """Retourne les rôles qu'un utilisateur peut créer."""
    subordinates = get_subordinate_roles(role)
    if role == User.Role.CHEF_INJS_ADMIN and User.Role.DIRECTION not in subordinates:
        return [User.Role.DIRECTION, *subordinates]
    return subordinates


def get_manageable_roles(role):
    """Rôles créables visibles dans la page Utilisateurs (hors ADMIN système)."""
    return [r for r in get_creatable_roles(role) if r in USER_MANAGEABLE_ROLES]


def get_staff_filter_roles(role):
    """Rôles proposés dans le filtre personnel de la page Utilisateurs."""
    staff_roles = [r for r in USER_MANAGEABLE_ROLES if r not in BADGE_ACCOUNT_ROLES]
    if role in USER_MUTATION_ROLES:
        manageable = get_manageable_roles(role)
        return [r for r in staff_roles if r in manageable]
    if role in USERS_PAGE_ROLES:
        return staff_roles
    return []


def _aggregate_roles_capability(user, getter):
    """Union des capacités dérivées de chaque rôle de l'utilisateur."""
    aggregated = set()
    for role in get_user_roles(user):
        aggregated.update(getter(role))
    return sorted(aggregated)


def user_role_context(user):
    """Métadonnées rôles pour le frontend (login / auth/me)."""
    roles = get_user_roles(user)
    primary = get_user_role(user)
    return {
        'hierarchy': ROLE_HIERARCHY,
        'labels': ROLE_LABELS,
        'role': primary,
        'roles': sorted(roles),
        'creatable_roles': _aggregate_roles_capability(user, get_creatable_roles),
        'manageable_roles': _aggregate_roles_capability(user, get_manageable_roles),
        'staff_filter_roles': _aggregate_roles_capability(user, get_staff_filter_roles),
        'badge_account_roles': list(BADGE_ACCOUNT_ROLES),
        'can_mutate_users': user_in_roles(user, USER_MUTATION_ROLES),
        'can_archive_modules': user_in_roles(user, MODULE_ARCHIVE_ROLES),
    }


def _permission_codenames(actions, model_name):
    return [f"{action}_{model_name}" for action in actions]


def _permissions_for_policy(policy):
    exclude = set(policy.get("exclude_codenames", ()))
    permissions = Permission.objects.none()
    for app_label in policy["apps"]:
        for model in apps.get_app_config(app_label).get_models():
            codenames = [
                c for c in _permission_codenames(policy["actions"], model._meta.model_name)
                if c not in exclude
            ]
            if codenames:
                permissions = permissions | Permission.objects.filter(
                    content_type__app_label=app_label,
                    codename__in=codenames,
                )
    custom_keys = policy.get("custom", ())
    if custom_keys:
        custom_codenames = [
            CUSTOM_PERMISSIONS[key].split(".", 1)[1]
            for key in custom_keys
            if key in CUSTOM_PERMISSIONS
        ]
        if custom_codenames:
            permissions = permissions | Permission.objects.filter(
                content_type__app_label="authentication",
                codename__in=custom_codenames,
            )
    return permissions.distinct()


def ensure_role_groups(force_reset=False):
    """Crée les groupes de rôles et initialise leurs permissions.

    Par défaut (force_reset=False) :
        - Si le groupe n'existe pas encore → le crée et lui applique le ROLE_POLICY.
        - Si le groupe existe déjà → on ajoute les permissions de la politique
          encore absentes (nouveaux modèles après la création du groupe).
          Les permissions retirées manuellement dans l'admin ne sont pas ré‑ajoutées
          si elles ne figurent plus dans la politique ; pour un réalignement complet,
          utiliser force_reset=True.

    Avec force_reset=True :
        - Remet les permissions de TOUS les groupes à l'état défini dans ROLE_POLICY,
          écrasant les modifications manuelles éventuelles.
          Utile pour revenir aux valeurs par défaut.
    """
    for role, group_name in ROLE_GROUP_NAMES.items():
        group, created = Group.objects.get_or_create(name=group_name)
        policy = ROLE_POLICY[role]
        permissions = _permissions_for_policy(policy)
        if created or force_reset:
            group.permissions.set(permissions)
        else:
            # Nouvelles permissions (nouveaux modèles / migrations après création du groupe).
            have = set(group.permissions.values_list("id", flat=True))
            want_ids = set(permissions.values_list("id", flat=True))
            missing = want_ids - have
            if missing:
                group.permissions.add(
                    *Permission.objects.filter(pk__in=missing)
                )


def sync_role_from_group(user):
    """Synchronise le champ ``User.role`` depuis le groupe Django ROLE_*."""
    if not user or not user.pk:
        return

    derived = _role_from_group_names(user.groups.values_list('name', flat=True))
    if not derived or derived == user.role:
        return

    User.objects.filter(pk=user.pk).update(role=derived)
    user.role = derived
    if hasattr(user, '_role_groups_cache'):
        del user._role_groups_cache


def sync_user_role_group(user):
    """Assure que le groupe ROLE_* du champ ``user.role`` est présent (sans retirer les autres)."""
    if not user or not user.pk:
        return

    target_group_name = ROLE_GROUP_NAMES.get(user.role)
    if not target_group_name:
        logger.warning(
            'sync_user_role_group_skipped user_id=%s username=%s reason=unknown_role role=%s',
            user.pk,
            getattr(user, 'username', None),
            user.role,
        )
        return

    if user.groups.filter(name=target_group_name).exists():
        return

    target_group = Group.objects.filter(name=target_group_name).first()
    if target_group:
        user.groups.add(target_group)
    else:
        logger.error(
            'sync_user_role_group_failed user_id=%s username=%s role=%s missing_group=%s',
            user.pk,
            getattr(user, 'username', None),
            user.role,
            target_group_name,
        )

    if hasattr(user, '_role_groups_cache'):
        del user._role_groups_cache


def sync_user_staff_status(user):
    """Active is_staff pour les rôles autorisés sur l'admin Django."""
    if not user or not user.pk or user.is_superuser:
        return

    should_be_staff = user_in_roles(user, DUAL_ACCESS_ROLES)
    if user.is_staff != should_be_staff:
        User.objects.filter(pk=user.pk).update(is_staff=should_be_staff)
        user.is_staff = should_be_staff


def sync_all_users_role_groups():
    """Resynchronise tous les utilisateurs (groupes ROLE_* + is_staff).

    Désactive les signaux m2m/post_save pendant l'opération pour éviter une
    cascade coûteuse (notamment lors de ``manage.py migrate``).
    """
    with _bulk_role_sync():
        for user in User.objects.all().only("id", "role", "is_staff", "is_superuser").iterator():
            sync_user_role_group(user)
            sync_user_staff_status(user)
