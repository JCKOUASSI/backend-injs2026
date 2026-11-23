"""Périmètre d'accès aux questionnaires d'évaluation."""
import re

from django.db.models import Q

from authentication.role_groups import GLOBAL_ACCESS_ROLES, SECRETARIAT_ROLES, get_user_role
from formations.access import modules_queryset_for_user

from .models import Questionnaire


def _normalize_groupe_value(value):
    """Normalise les variantes de groupe (1, 01, GROUPE 1) vers GROUPE N."""
    if not value:
        return ''
    compact = str(value).strip().upper()
    match = re.fullmatch(r'(?:GROUPE\s*)?0*(\d+)', compact, flags=re.IGNORECASE)
    if match:
        return f"GROUPE {int(match.group(1))}"
    return compact


def questionnaire_accessible_to_participant(questionnaire, participant):
    """
    True si le questionnaire publié est destiné à cet auditeur
    (filtres catégories / grades / groupes).
    """
    grade = (participant.grade or '').strip().upper()
    categorie = grade[0] if grade else ''
    participant_groupe = _normalize_groupe_value(participant.groupe)

    cats = questionnaire.categories or []
    grades = questionnaire.grades or []
    groupes = questionnaire.groupes or []

    if groupes:
        groupes_norm = {_normalize_groupe_value(g) for g in groupes}
        if not participant_groupe or participant_groupe not in groupes_norm:
            return False

    if not cats and not grades:
        return True
    if categorie and categorie in cats:
        return True
    if grade and grade in grades:
        return True
    return False


def _scoped_module_intitules(user):
    return set(modules_queryset_for_user(user).values_list('intitule', flat=True))


def questionnaire_accessible(user, questionnaire):
    """True si l'utilisateur peut consulter / modifier ce questionnaire."""
    if not user or not user.is_authenticated:
        return False
    role = get_user_role(user)
    if role in GLOBAL_ACCESS_ROLES or role == 'SUPERVISEUR':
        return True
    if role in SECRETARIAT_ROLES or role == 'ENCADRANT':
        if questionnaire.module_id:
            return modules_queryset_for_user(user).filter(pk=questionnaire.module_id).exists()
        titres = set(questionnaire.titres or [])
        scoped = _scoped_module_intitules(user)
        if not scoped:
            return False
        if not titres:
            return False
        return bool(titres & scoped)
    return False


def questionnaires_queryset_for_user(user, queryset=None):
    """Questionnaires visibles selon le périmètre opérationnel."""
    qs = queryset if queryset is not None else Questionnaire.objects.all()
    if not user or not user.is_authenticated:
        return qs.none()
    role = get_user_role(user)
    if role in GLOBAL_ACCESS_ROLES or role == 'SUPERVISEUR':
        return qs
    if role in SECRETARIAT_ROLES or role == 'ENCADRANT':
        scoped_modules = modules_queryset_for_user(user)
        module_ids = list(scoped_modules.values_list('pk', flat=True))
        intitules = _scoped_module_intitules(user)
        if not intitules:
            return qs.none()

        scoped = qs.filter(
            Q(module_id__in=module_ids)
            | Q(module__isnull=True)
        )
        null_module_ids = [
            qid for qid, titres in scoped.filter(module__isnull=True).values_list('id', 'titres')
            if set(titres or []) & intitules
        ]
        return qs.filter(
            Q(module_id__in=module_ids)
            | Q(id__in=null_module_ids)
        ).distinct()
    return qs.none()


def titres_dans_perimetre(user, titres):
    """Vérifie que tous les titres ciblés appartiennent au périmètre de l'utilisateur."""
    role = get_user_role(user)
    if role in GLOBAL_ACCESS_ROLES or role == 'SUPERVISEUR':
        return True
    if role in SECRETARIAT_ROLES or role == 'ENCADRANT':
        scoped = _scoped_module_intitules(user)
        if not scoped:
            return False
        return bool(titres) and set(titres).issubset(scoped)
    return False
