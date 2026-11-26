"""
Périmètre d'accès aux formations par utilisateur.

- ADMIN_EDT / DIRECTION_EDT / superuser : voient toutes les formations.
- GESTIONNAIRE_EDT : formations dont il est responsable.
- RUP_EDT : un module du référentiel (matière plateforme) ; voit les formations
  où ce module figure au programme, avec vue filtrée sur ce module.

La génération automatique de planning (salles, formateurs) reste globale dans
``apps.seances.services`` : elle lit toutes les séances en base.
"""

from __future__ import annotations

from typing import Iterable, Optional, Union

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404

ROLE_ADMIN = "ADMIN_EDT"
ROLE_DIRECTION = "DIRECTION_EDT"
ROLE_GESTIONNAIRE = "GESTIONNAIRE_EDT"
ROLE_RUP = "RUP_EDT"
ROLES_VUE_GLOBALE_FORMATIONS = frozenset({ROLE_ADMIN, ROLE_DIRECTION})

UserLike = Union[AbstractBaseUser, AnonymousUser]


def utilisateur_est_rup(user: UserLike) -> bool:
    """True si l'utilisateur appartient au groupe RUP_EDT."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return False
    return user.groups.filter(name=ROLE_RUP).exists()


def utilisateur_est_gestionnaire(user: UserLike) -> bool:
    """True si l'utilisateur appartient au groupe GESTIONNAIRE_EDT."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return False
    return user.groups.filter(name=ROLE_GESTIONNAIRE).exists()


def module_rup_id_pour_utilisateur(user: UserLike) -> Optional[int]:
    """Id du ``referentiels.Module`` dont l'utilisateur est RUP (un seul par utilisateur)."""
    if not user or not getattr(user, "is_authenticated", False):
        return None
    from apps.formations.models import ResponsableUnitePedagogique

    return (
        ResponsableUnitePedagogique.objects.filter(user=user)
        .values_list("module_id", flat=True)
        .first()
    )


def modules_up_ids_pour_utilisateur(user: UserLike) -> frozenset[int]:
    """Ids des modules visibles par le RUP (0 ou 1 module)."""
    module_id = module_rup_id_pour_utilisateur(user)
    if not module_id:
        return frozenset()
    return frozenset({module_id})


def utilisateur_peut_gerer_module_up(user: UserLike, module_id: int) -> bool:
    """True si le module est celui du RUP."""
    if utilisateur_voit_toutes_les_formations(user):
        return True
    if not utilisateur_est_rup(user):
        return False
    return module_rup_id_pour_utilisateur(user) == int(module_id)


def utilisateur_voit_toutes_les_formations(user: UserLike) -> bool:
    """True si l'utilisateur accède à l'ensemble des formations."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name__in=ROLES_VUE_GLOBALE_FORMATIONS).exists()


def _filtre_formations_q(user: UserLike) -> Q | None:
    """
    Filtre Q sur ``Formation`` pour l'utilisateur.
    None = accès global (pas de filtre).
    """
    if utilisateur_voit_toutes_les_formations(user):
        return None
    if not user or not getattr(user, "is_authenticated", False):
        return Q(pk__in=[])

    filtres = Q()
    if utilisateur_est_gestionnaire(user):
        filtres |= Q(responsable=user)
    module_id = module_rup_id_pour_utilisateur(user)
    if utilisateur_est_rup(user) and module_id:
        filtres |= Q(modules__module_id=module_id)
    if not filtres:
        return Q(pk__in=[])
    return filtres


def queryset_formations(user: UserLike, *, base: QuerySet | None = None) -> QuerySet:
    """QuerySet des formations visibles par l'utilisateur."""
    from apps.formations.models import Formation

    qs = base if base is not None else Formation.objects.all()
    qs = qs.select_related("type_formation", "responsable")
    filtre = _filtre_formations_q(user)
    if filtre is None:
        return qs
    return qs.filter(filtre).distinct()


def get_formation_pour_utilisateur(user: UserLike, pk: int, *, queryset: QuerySet | None = None):
    """Retourne la formation ou lève Http404 si hors périmètre."""
    qs = queryset if queryset is not None else queryset_formations(user)
    return get_object_or_404(qs, pk=pk)


def queryset_groupes(user: UserLike, *, base: QuerySet | None = None) -> QuerySet:
    """QuerySet des groupes dont la formation est accessible par l'utilisateur."""
    from apps.groupes.models import Groupe

    qs = base if base is not None else Groupe.objects.all()
    if utilisateur_voit_toutes_les_formations(user):
        return qs
    if not user or not getattr(user, "is_authenticated", False):
        return qs.none()
    formation_ids = queryset_formations(user).values_list("pk", flat=True)
    return qs.filter(formation_id__in=formation_ids)


def get_groupe_pour_utilisateur(user: UserLike, groupe_pk: int, *, queryset: QuerySet | None = None):
    """Retourne le groupe ou lève Http404 si hors périmètre."""
    qs = queryset if queryset is not None else queryset_groupes(user)
    return get_object_or_404(qs, pk=groupe_pk)


def filter_formation_ids_pour_utilisateur(user: UserLike, formation_ids: list[int]) -> list[int]:
    """Conserve uniquement les ids de formations accessibles, en préservant l'ordre."""
    if not formation_ids:
        return []
    allowed = set(queryset_formations(user).filter(pk__in=formation_ids).values_list("pk", flat=True))
    return [fid for fid in formation_ids if fid in allowed]


def utilisateur_voit_formation_entierement(user: UserLike, formation) -> bool:
    """True si l'utilisateur voit toute la formation (pas seulement son module UP)."""
    if utilisateur_voit_toutes_les_formations(user):
        return True
    if utilisateur_est_gestionnaire(user) and formation.responsable_id == getattr(user, "pk", None):
        return True
    return False


def modules_up_formation_pour_utilisateur(user: UserLike, formation_id: int) -> QuerySet:
    """``FormationModule`` de la formation pour le module RUP de l'utilisateur."""
    from apps.formations.models import FormationModule

    module_id = module_rup_id_pour_utilisateur(user)
    if not module_id:
        return FormationModule.objects.none()
    return (
        FormationModule.objects.filter(formation_id=formation_id, module_id=module_id)
        .select_related("module", "module__specialite", "periode")
        .order_by("date_debut", "module__titre")
    )


def filtrer_seances_selon_perimetre(user: UserLike, formation, seances: Iterable) -> list:
    """Restreint les séances au module UP du RUP si périmètre partiel."""
    if utilisateur_voit_formation_entierement(user, formation):
        return list(seances)
    module_ids = modules_up_ids_pour_utilisateur(user)
    if utilisateur_est_rup(user) and module_ids:
        return [s for s in seances if getattr(s, "module_id", None) in module_ids]
    return list(seances)


def ids_specialites_pour_module(module_id: int) -> frozenset[int]:
    """Spécialités reconnues pour affecter un formateur sur ce module."""
    from apps.referentiels.models import Module

    module = Module.objects.filter(pk=module_id).select_related("specialite").first()
    if not module:
        return frozenset()
    return module.ids_specialites_pour_matching_formateurs()


def formateur_eligible_pour_module(formateur, module_id: int) -> bool:
    """True si le formateur possède une spécialité compatible avec le module."""
    specialite_ids = ids_specialites_pour_module(module_id)
    if not specialite_ids:
        return False
    return formateur.specialites.filter(pk__in=specialite_ids).exists()


def queryset_formateurs_pour_utilisateur(user: UserLike) -> QuerySet:
    """
    Formateurs visibles par l'utilisateur.
    RUP : uniquement ceux ayant une spécialité compatible avec son module.
    """
    from apps.formations.models import Formateur

    qs = Formateur.objects.prefetch_related("specialites").order_by("nom", "prenom")
    if utilisateur_voit_toutes_les_formations(user):
        return qs
    if utilisateur_est_rup(user):
        module_id = module_rup_id_pour_utilisateur(user)
        if module_id:
            specialite_ids = ids_specialites_pour_module(module_id)
            if specialite_ids:
                return qs.filter(specialites__id__in=specialite_ids).distinct()
            return qs.none()
    return qs
