"""Fusion de modules dupliqués (même formation, intitulé, grade, groupe, vague)."""

from django.db import transaction
from django.db.models import Count, Max

from .models import (
    Module,
    ModuleFormateur,
    ModuleParticipant,
    NoteModuleColonne,
    NoteModuleSynthese,
    SessionModule,
)

_STATUT_PRIORITY = {
    'EN_COURS': 4,
    'SUSPENDUE': 3,
    'TERMINEE': 2,
    'PLANIFIEE': 1,
}


def module_activity_score(module):
    """Score d'activité : séances démarrées, puis pointages, puis inscriptions."""
    sessions = module.sessions.all()
    started = sessions.filter(demarree_le__isnull=False).count()
    pointages = sum(s.pointages.count() for s in sessions)
    inscriptions = module.module_participants.count()
    return (started, pointages, inscriptions, -module.id)


def pick_keeper_module(modules):
    """Conserve le module le plus « actif », pas le plus récent."""
    return max(modules, key=module_activity_score)


def merge_module_metadata(keeper, source):
    """Enrichit le module conservé avec les métadonnées du doublon si pertinent."""
    updates = []

    if _STATUT_PRIORITY.get(source.statut, 0) > _STATUT_PRIORITY.get(keeper.statut, 0):
        keeper.statut = source.statut
        updates.append('statut')

    for field in (
        'date_debut', 'date_fin', 'superviseur', 'formateur', 'secretariat',
        'site', 'site_legacy', 'batiment', 'salle', 'ref_module',
    ):
        if not getattr(keeper, field) and getattr(source, field):
            setattr(keeper, field, getattr(source, field))
            updates.append(field)

    if (not keeper.duree_prevue_heures or keeper.duree_prevue_heures == 0) and source.duree_prevue_heures:
        keeper.duree_prevue_heures = source.duree_prevue_heures
        updates.append('duree_prevue_heures')

    if updates:
        keeper.save(update_fields=list(dict.fromkeys(updates)))


def _move_or_reconcile_session(session, keeper):
    """Déplace une séance vers le module conservé ; gère les conflits (date, numéro)."""
    conflict = SessionModule.objects.filter(
        module=keeper,
        date_journee=session.date_journee,
        numero=session.numero,
    ).exclude(pk=session.pk).first()

    if not conflict:
        session.module = keeper
        session.save(update_fields=['module'])
        return 'moved'

    source_active = bool(session.demarree_le)
    target_active = bool(conflict.demarree_le)

    if source_active and not target_active:
        conflict.delete()
        session.module = keeper
        session.save(update_fields=['module'])
        return 'replaced_empty'

    if not source_active and target_active:
        session.delete()
        return 'dropped_empty'

    max_num = (
        SessionModule.objects.filter(module=keeper, date_journee=session.date_journee)
        .aggregate(m=Max('numero'))['m'] or 0
    )
    session.numero = max_num + 1
    session.module = keeper
    session.save(update_fields=['module', 'numero'])
    return 'renumbered'


def merge_module_participants(keeper, source):
    moved = 0
    for mp in source.module_participants.select_related('participant'):
        _, created = ModuleParticipant.objects.get_or_create(
            module=keeper,
            participant=mp.participant,
        )
        if created:
            moved += 1
    ModuleParticipant.objects.filter(module=source).delete()
    return moved


def merge_module_formateurs(keeper, source):
    moved = 0
    for mf in source.module_formateurs.select_related('formateur'):
        _, created = ModuleFormateur.objects.get_or_create(
            module=keeper,
            formateur=mf.formateur,
        )
        if created:
            moved += 1
    ModuleFormateur.objects.filter(module=source).delete()
    return moved


def merge_module_sessions(keeper, source):
    stats = {'moved': 0, 'replaced_empty': 0, 'dropped_empty': 0, 'renumbered': 0}
    for session in list(source.sessions.all()):
        action = _move_or_reconcile_session(session, keeper)
        stats[action] = stats.get(action, 0) + 1
    return stats


def merge_module_notes(keeper, source):
    """Fusionne colonnes / synthèses ; les valeurs de notes suivent les colonnes."""
    for col in source.colonnes_notes.all():
        col.module = keeper
        col.save(update_fields=['module'])

    for syn in source.syntheses_notes.all():
        NoteModuleSynthese.objects.update_or_create(
            module=keeper,
            participant=syn.participant,
            defaults={
                'mention': syn.mention,
                'observations': syn.observations,
                'saisie_par': syn.saisie_par,
            },
        )
    NoteModuleSynthese.objects.filter(module=source).delete()


def merge_module_suivi_evaluation(keeper, source):
    try:
        from suiviEvaluation.models import Questionnaire, Epreuve
    except ImportError:
        return

    Questionnaire.objects.filter(module=source).update(module=keeper)
    Epreuve.objects.filter(module=source).update(module=keeper)


@transaction.atomic
def merge_module_into(keeper, source):
    """
    Fusionne ``source`` dans ``keeper`` puis supprime ``source``.
    Retourne un dict récapitulatif.
    """
    if keeper.pk == source.pk:
        raise ValueError('Impossible de fusionner un module avec lui-même.')

    merge_module_metadata(keeper, source)
    participants = merge_module_participants(keeper, source)
    formateurs = merge_module_formateurs(keeper, source)
    sessions = merge_module_sessions(keeper, source)
    merge_module_notes(keeper, source)
    merge_module_suivi_evaluation(keeper, source)

    source_id = source.pk
    source.delete()

    return {
        'keeper_id': keeper.pk,
        'source_id': source_id,
        'participants_merged': participants,
        'formateurs_merged': formateurs,
        'sessions': sessions,
    }


def find_duplicate_module_groups():
    """Groupes de modules partageant (formation, intitulé, grade, groupe, vague)."""
    dup_keys = (
        Module.objects.values(
            'formation_id', 'intitule', 'grade', 'groupe', 'vague',
        )
        .annotate(n=Count('id'))
        .filter(n__gt=1)
    )
    groups = []
    for key in dup_keys:
        modules = list(
            Module.objects.filter(**{k: key[k] for k in key if k != 'n'})
            .select_related('formation')
            .prefetch_related('sessions')
        )
        groups.append(modules)
    return groups
