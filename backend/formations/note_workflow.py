"""Workflow de validation des notes de module (lot L1).

Cycle : ``BROUILLON → SOUMISE → VALIDEE`` (verrouillée).

Une note ``VALIDEE`` (``verrouillee=True``) ne peut plus être modifiée
directement par le bulk de saisie : toute correction passe par
:func:`corriger`, qui exige un motif obligatoire, persiste l'ancienne et la
nouvelle valeur dans ``CorrectionNoteModule`` (append-only, aucune vue de
modification/suppression) et écrit :
  - une entrée ``AuditLog.NOTE_CORRIGEE`` ;
  - une entrée ``JournalScolarite`` (best-effort via ``journaliser``) ;
  - la notification Direction existante (``notifier_modification_note``).

Le design suit le pattern du bulk existant : un ``transaction.atomic`` global,
collecte d'erreurs (``errors``) et compteur de traités (``traites``) sans levée.
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from presences.models import _log_audit
from scolarite.models import journaliser

from .models import (
    CorrectionNoteModule,
    ModuleParticipant,
    NoteModule,
    NoteModuleColonne,
)
from .note_notifications import notifier_modification_note


def _decimal(value, note_max):
    """Convertit une saisie en Decimal 2 décimales, bornée [0, note_max]."""
    if value is None or value == '':
        return None
    try:
        d = Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Note invalide.')
    if d < 0 or d > note_max:
        raise ValueError(f'La note doit être entre 0 et {note_max}.')
    return d


def _audit(action, utilisateur, module, note, col_libelle, extra=None):
    """Écrit une entrée AuditLog (best-effort)."""
    try:
        _log_audit(
            action,
            None,
            cible_type='note_module',
            cible_numero=str(note.pk),
            cible_nom=str(note.participant),
            formation=module.formation,
            extra={'module': module.intitule, 'colonne': col_libelle, **(extra or {})},
        )
    except Exception:  # noqa: BLE001 - l'audit ne doit pas casser une opération métier
        pass


def _journal(action, utilisateur, note, col_libelle, ancienne, nouvelle, motif=''):
    """Écrit une entrée JournalScolarite (best-effort).

    NB : ne PAS passer ``objet_libelle`` — ``journaliser()`` le construit déjà
    via ``str(objet)`` ; le repasser provoquerait une collision de mot-clé
    (TypeError) silencieusement avalée par son best-effort.
    """
    try:
        journaliser(
            action,
            objet=note,
            acteur=utilisateur,
            ancienne_valeur=str(ancienne) if ancienne is not None else '',
            nouvelle_valeur=str(nouvelle) if nouvelle is not None else '',
            commentaire=motif,
            extra={
                'module': note.colonne.module_id,
                'colonne': col_libelle,
                'ancienne': str(ancienne) if ancienne is not None else '',
                'nouvelle': str(nouvelle) if nouvelle is not None else '',
            },
        )
    except Exception:  # noqa: BLE001
        pass


def _get_note(module, colonne_id, participant_id):
    try:
        colonne = NoteModuleColonne.objects.get(pk=colonne_id, module=module)
    except NoteModuleColonne.DoesNotExist:
        return None, None, 'Colonne introuvable.'
    try:
        note = NoteModule.objects.get(
            colonne=colonne, participant_id=participant_id,
        )
    except NoteModule.DoesNotExist:
        return colonne, None, None
    return colonne, note, None


def _get_note_ou_erreur(module, colonne_id, participant_id):
    """Version stricte pour les actions nécessitant une note existante."""
    colonne, note, err = _get_note(module, colonne_id, participant_id)
    if err:
        return colonne, None, err
    if note is None or note.note is None:
        return colonne, None, 'Aucune note enregistrée pour cet auditeur sur cette colonne.'
    return colonne, note, None


def soumettre(module, colonne_id, participant_id, utilisateur):
    """BROUILLON → SOUMISE."""
    colonne, note, err = _get_note_ou_erreur(module, colonne_id, participant_id)
    if err:
        return err
    if note.statut_validation == NoteModule.StatutValidation.SOUMISE:
        return 'Note déjà soumise.'
    if note.statut_validation == NoteModule.StatutValidation.VALIDEE:
        return 'Note déjà validée (verrouillée) : déverrouillage requis avant re-soumission.'
    note.statut_validation = NoteModule.StatutValidation.SOUMISE
    note.save(update_fields=['statut_validation', 'updated_at'])
    _audit('NOTE_SOUMISE', utilisateur, module, note, colonne.libelle)
    return None


def annuler(module, colonne_id, participant_id, utilisateur):
    """SOUMISE → BROUILLON (permis tant que non validée)."""
    colonne, note, err = _get_note_ou_erreur(module, colonne_id, participant_id)
    if err:
        return err
    if note.statut_validation == NoteModule.StatutValidation.VALIDEE:
        return 'Note déjà validée (verrouillée) : déverrouillage requis.'
    if note.statut_validation == NoteModule.StatutValidation.BROUILLON:
        return 'Note déjà en brouillon.'
    note.statut_validation = NoteModule.StatutValidation.BROUILLON
    note.save(update_fields=['statut_validation', 'updated_at'])
    return None


def valider(module, colonne_id, participant_id, utilisateur):
    """→ VALIDEE (verrouillée). Accepte BROUILLON ou SOUMISE."""
    colonne, note, err = _get_note(module, colonne_id, participant_id)
    if err:
        return err
    if note is None or note.note is None:
        return 'Aucune note enregistrée pour cet auditeur sur cette colonne.'
    if note.verrouillee:
        return 'Note déjà verrouillée.'
    with transaction.atomic():
        note.statut_validation = NoteModule.StatutValidation.VALIDEE
        note.verrouillee = True
        note.validation_par = utilisateur
        note.validation_le = timezone.now()
        note.save()
    _audit('NOTE_VALIDEE', utilisateur, module, note, colonne.libelle)
    return None


def deverrouiller(module, colonne_id, participant_id, utilisateur):
    """VALIDEE → SOUMISE (déverrouillage par un gestionnaire)."""
    colonne, note, err = _get_note(module, colonne_id, participant_id)
    if err:
        return err
    if note is None or note.note is None:
        return 'Aucune note enregistrée pour cet auditeur sur cette colonne.'
    if not note.verrouillee:
        return 'Note non verrouillée.'
    with transaction.atomic():
        note.verrouillee = False
        note.statut_validation = NoteModule.StatutValidation.SOUMISE
        note.validation_par = None
        note.validation_le = None
        note.save()
    _audit('NOTE_CORRIGEE', utilisateur, module, note, colonne.libelle,
           extra={'operation': 'DEVERROUILLAGE'})
    return None


def corriger(module, colonne_id, participant_id, nouvelle_note, motif, utilisateur):
    """Correction AUDITÉE d'une note verrouillée (motif obligatoire)."""
    colonne, note, err = _get_note(module, colonne_id, participant_id)
    if err:
        return err
    if note is None or note.note is None:
        return 'Aucune note enregistrée pour cet auditeur sur cette colonne.'
    if not note.verrouillee:
        return 'La note n\'est pas verrouillée : corrigez-la directement en saisie.'
    motif = (motif or '').strip()
    if not motif:
        return 'Le motif de correction est obligatoire.'
    try:
        nouveau = _decimal(nouvelle_note, note.colonne.note_max)
    except ValueError as exc:
        return str(exc)
    if nouveau is None:
        return 'Une correction doit fournir une nouvelle note.'
    if nouveau == note.note:
        return 'La nouvelle valeur est identique à la note actuelle.'

    ancienne = note.note
    with transaction.atomic():
        CorrectionNoteModule.objects.create(
            note=note,
            colonne=colonne,
            module=module,
            participant=note.participant,
            ancienne_valeur=ancienne,
            nouvelle_valeur=nouveau,
            motif=motif,
            auteur=utilisateur,
        )
        note.note = nouveau
        note.saisie_par = utilisateur
        # La note reste verrouillée : seules les métadonnées de correction changent.
        note.save()
    _audit('NOTE_CORRIGEE', utilisateur, module, note, colonne.libelle,
           extra={'ancienne': str(ancienne), 'nouvelle': str(nouveau), 'motif': motif[:200]})
    _journal('NOTE_CORRIGEE', utilisateur, note, colonne.libelle, ancienne, nouveau, motif)
    # Notification Direction (pattern existant) — best-effort interne.
    notifier_modification_note(
        utilisateur, note.participant, module, colonne, ancienne, nouveau,
    )
    return None


# action → callable renvoyant None (succès) ou un message d'erreur
_ACTIONS = {
    'soumettre': soumettre,
    'annuler': annuler,
    'valider': valider,
    'deverrouiller': deverrouiller,
}


def appliquer_workflow(module, action, items, utilisateur):
    """Point d'entrée de l'endpoint : traite une liste d'items.

    Retourne ``{'traites': n, 'errors': [...]}`` — mêmes conventions que le
    bulk de saisie existant.
    """
    if not isinstance(items, list):
        return {'traites': 0, 'errors': [{'index': None, 'detail': 'Le champ "items" (liste) est requis.'}]}

    inscrits = set(
        ModuleParticipant.objects.filter(module=module).values_list('participant_id', flat=True)
    )
    traites = 0
    errors = []

    with transaction.atomic():
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append({'index': idx, 'detail': 'Entrée invalide.'})
                continue

            participant_id = item.get('participant_id')
            colonne_id = item.get('colonne_id')
            if not participant_id or not colonne_id:
                errors.append({'index': idx, 'detail': 'participant_id et colonne_id requis.'})
                continue
            try:
                participant_id = int(participant_id)
                colonne_id = int(colonne_id)
            except (TypeError, ValueError):
                errors.append({'index': idx, 'detail': 'participant_id ou colonne_id invalide.'})
                continue

            if participant_id not in inscrits:
                errors.append({'index': idx, 'detail': 'Étudiant non inscrit à ce module.'})
                continue

            if action == 'corriger':
                err = corriger(
                    module, colonne_id, participant_id,
                    item.get('note'), item.get('motif'), utilisateur,
                )
            else:
                err = _ACTIONS[action](module, colonne_id, participant_id, utilisateur)
            if err:
                errors.append({'index': idx, 'detail': err})
            else:
                traites += 1

    return {'traites': traites, 'errors': errors}


def actions_valides():
    return tuple(_ACTIONS) + ('corriger',)