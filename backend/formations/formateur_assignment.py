"""Règles métier pour l'assignation des formateurs aux modules."""
from __future__ import annotations

from datetime import timedelta

from .models import Module, SessionModule


def _module_session_dates(module: Module) -> set:
    dates = set(
        SessionModule.objects.filter(module=module).values_list('date_journee', flat=True)
    )
    if dates:
        return dates
    if module.date_debut and module.date_fin:
        start = module.date_debut
        end = module.date_fin
        if end < start:
            start, end = end, start
        cursor = start
        out = set()
        while cursor <= end:
            out.add(cursor)
            cursor += timedelta(days=1)
        return out
    if module.date_debut:
        return {module.date_debut}
    return set()


def _normalize_groupe(module: Module) -> str:
    return (module.groupe or '').strip()


def _module_label(module: Module) -> str:
    return module.intitule or f'Module #{module.pk}'


def _groupe_label(groupe: str) -> str:
    return groupe or 'groupe non renseigné'


def _format_time_range(session: SessionModule) -> str | None:
    if session.heure_debut_prevue and session.heure_fin_prevue:
        debut = session.heure_debut_prevue.strftime('%H:%M')
        fin = session.heure_fin_prevue.strftime('%H:%M')
        return f'{debut}–{fin}'
    return None


def _sessions_overlap(a: SessionModule, b: SessionModule) -> bool:
    if (
        a.heure_debut_prevue
        and a.heure_fin_prevue
        and b.heure_debut_prevue
        and b.heure_fin_prevue
    ):
        return (
            a.heure_debut_prevue < b.heure_fin_prevue
            and b.heure_debut_prevue < a.heure_fin_prevue
        )
    return True


def check_formateur_groupe_jour_conflict(formateur, target_module: Module) -> str | None:
    """
    Vérifie qu'un formateur peut être assigné à un module :
    - deux groupes différents le même jour → refus ;
    - même groupe le même jour → refus seulement en cas de conflit horaire ;
    - groupe absent sur l'un des modules → refus dès qu'il y a une activité le même jour.

    Retourne un message d'erreur lisible, ou None si l'assignation est autorisée.
    """
    target_dates = _module_session_dates(target_module)
    if not target_dates:
        return None

    formateur_label = str(formateur)
    target_module_label = _module_label(target_module)
    target_groupe = _normalize_groupe(target_module)

    assigned_modules = (
        Module.objects.filter(module_formateurs__formateur=formateur)
        .exclude(pk=target_module.pk)
        .distinct()
    )

    for other in assigned_modules:
        other_dates = _module_session_dates(other)
        common_dates = sorted(target_dates & other_dates)
        if not common_dates:
            continue

        other_groupe = _normalize_groupe(other)
        other_module_label = _module_label(other)
        conflict_date = common_dates[0]
        date_label = conflict_date.strftime('%d/%m/%Y')
        extra_dates = len(common_dates) - 1
        if extra_dates:
            date_label = f'{date_label} (+{extra_dates} autre{"s" if extra_dates > 1 else ""} date{"s" if extra_dates > 1 else ""})'

        if target_groupe and other_groupe and target_groupe != other_groupe:
            return (
                f'{formateur_label} enseigne déjà {_groupe_label(other_groupe)} '
                f'({other_module_label}) le {date_label}. '
                f'Pour l\'assigner à {_groupe_label(target_groupe)} ({target_module_label}), '
                f'retirez-le d\'abord de son module actuel ou modifiez l\'emploi du temps. '
                f'Un formateur ne peut pas enseigner deux groupes différents le même jour.'
            )

        if not target_groupe or not other_groupe:
            return (
                f'{formateur_label} est déjà assigné au module « {other_module_label} » '
                f'le {date_label}. '
                f'Retirez cette assignation ou décalez l\'une des séances avant de l\'assigner '
                f'au module « {target_module_label} ». '
                f'Un formateur ne peut pas enseigner deux cours le même jour.'
            )

        target_sessions = SessionModule.objects.filter(
            module=target_module,
            date_journee=conflict_date,
        )
        other_sessions = SessionModule.objects.filter(
            module=other,
            date_journee=conflict_date,
        )
        for target_session in target_sessions:
            for other_session in other_sessions:
                if _sessions_overlap(target_session, other_session):
                    other_slot = _format_time_range(other_session)
                    target_slot = _format_time_range(target_session)
                    horaire_detail = ''
                    if other_slot and target_slot:
                        horaire_detail = (
                            f' Créneaux en conflit : {other_slot} ({other_module_label}) '
                            f'et {target_slot} ({target_module_label}).'
                        )
                    return (
                        f'{formateur_label} a déjà une séance le {date_label} '
                        f'avec « {other_module_label} » ({_groupe_label(other_groupe)}).'
                        f'{horaire_detail} '
                        f'Modifiez l\'emploi du temps ou retirez l\'assignation existante '
                        f'(conflit horaire le même jour pour le même groupe).'
                    )

    return None
