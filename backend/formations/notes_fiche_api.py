"""Endpoints d'impression des fiches de notes (module entier ou auditeur seul)."""
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from suiviEvaluation.permissions import IsGestionNotesOrReadOnly

from .api_access import deny_finance_operational_response, module_for_notes_or_response
from .api_views import (
    _batch_resume_module_participants,
    _ensure_colonnes,
    _serialize_colonne,
)
from .models import ModuleParticipant, NoteModule, NoteModuleSynthese
from .notes_fiche_export import (
    build_fiche_auditeur_pdf,
    build_fiche_module_pdf,
    fiche_auditeur_filename,
    fiche_module_filename,
)


def _module_meta(module):
    formateur = module.formateur
    superviseur = module.superviseur
    site = module.site.nom if module.site else (module.site_legacy or '')
    lieu = ' · '.join(part for part in (site, module.batiment, module.salle) if part)

    if module.date_debut and module.date_fin:
        periode = f"{module.date_debut.strftime('%d/%m/%Y')} au {module.date_fin.strftime('%d/%m/%Y')}"
    elif module.date_debut:
        periode = f"à partir du {module.date_debut.strftime('%d/%m/%Y')}"
    else:
        periode = ''

    return {
        'intitule': module.intitule,
        'formation': module.formation.formation if module.formation_id else '',
        'grade': module.grade or '',
        'groupe': module.groupe or '',
        'vague': module.vague or '',
        'secretariat': module.secretariat.nom if module.secretariat_id else '',
        'lieu': lieu,
        'periode': periode,
        'formateur': f'{formateur.nom} {formateur.prenom}'.strip() if formateur else '',
        'encadrant': (superviseur.get_full_name() or superviseur.username) if superviseur else '',
    }


def _normalize_to_20(note, note_max):
    if note is None:
        return None
    maximum = float(note_max or 20) or 20.0
    return round(float(note) * 20.0 / maximum, 2)


def _admis_labels(moyenne, taux, admissible):
    """Un verdict n'est affiché que si la moyenne et l'assiduité sont connues."""
    if moyenne is None or taux is None:
        return '—', 'En attente'
    return ('Oui', 'Admis') if admissible else ('Non', 'Non admis')


def _build_fiche_context(request, module, participant_ids=None):
    """Assemble colonnes, lignes et statistiques d'un module (mêmes calculs que l'API notes)."""
    from suiviEvaluation.services import _get_parametres

    colonnes = _ensure_colonnes(module)
    criteres = _get_parametres(module.formation)

    inscriptions = (
        ModuleParticipant.objects.filter(module=module)
        .select_related('participant')
        .order_by('participant__nom', 'participant__prenom')
    )
    if participant_ids is not None:
        inscriptions = inscriptions.filter(participant_id__in=participant_ids)
    inscriptions_list = list(inscriptions)

    valeurs_map = {}
    for valeur in NoteModule.objects.filter(
        colonne_id__in=[c.id for c in colonnes],
    ).select_related('colonne'):
        valeurs_map.setdefault(valeur.participant_id, {})[valeur.colonne_id] = valeur

    syntheses_map = {
        s.participant_id: s
        for s in NoteModuleSynthese.objects.filter(module=module)
    }
    resumes = _batch_resume_module_participants(module, inscriptions_list, valeurs_map, criteres)

    rows = []
    for inscription in inscriptions_list:
        participant = inscription.participant
        resume = resumes.get(participant.id, {})
        synthese = syntheses_map.get(participant.id)

        notes = {}
        notes_sur_20 = {}
        for colonne in colonnes:
            valeur = valeurs_map.get(participant.id, {}).get(colonne.id)
            note = float(valeur.note) if valeur and valeur.note is not None else None
            notes[colonne.id] = note
            notes_sur_20[colonne.id] = _normalize_to_20(note, colonne.note_max)

        moyenne = resume.get('moyenne')
        taux = resume.get('taux_presence')
        admis_label, admis_label_long = _admis_labels(moyenne, taux, resume.get('admissible'))

        rows.append({
            'participant_id': participant.id,
            'nom': (participant.nom or '').upper(),
            'prenom': participant.prenom or '',
            'matricule': participant.matricule or '',
            'grade': participant.grade or '',
            'notes': notes,
            'notes_sur_20': notes_sur_20,
            'moyenne': moyenne,
            'mention': synthese.mention if synthese else '',
            'observations': synthese.observations if synthese else '',
            'heures_presence': resume.get('heures_presence'),
            'heures_prevues': resume.get('heures_prevues'),
            'taux_presence': taux,
            'admis_label': admis_label,
            'admis_label_long': admis_label_long,
        })

    moyennes = [r['moyenne'] for r in rows if r['moyenne'] is not None]
    stats = {
        'total': len(rows),
        'notes': sum(1 for r in rows if any(v is not None for v in r['notes'].values())),
        'moyenne_classe': round(sum(moyennes) / len(moyennes), 2) if moyennes else None,
        'admis': sum(1 for r in rows if r['admis_label'] == 'Oui'),
        'non_admis': sum(1 for r in rows if r['admis_label'] == 'Non'),
    }

    edite_par = request.user.get_full_name() or request.user.username
    edite_le = timezone.localtime(timezone.now()).strftime('%d/%m/%Y à %H:%M')

    return {
        'module': _module_meta(module),
        'criteres': criteres,
        'colonnes': [_serialize_colonne(c) for c in colonnes],
        'rows': rows,
        'stats': stats,
        'edite_le_label': f'Édité le {edite_le} par {edite_par}.',
    }


def _pdf_response(buffer, filename):
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
@permission_classes([IsGestionNotesOrReadOnly])
def module_notes_fiche_pdf_api(request, formation_pk, module_pk):
    """Fiche de notes imprimable du module : tous les auditeurs inscrits."""
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    _, module, err = module_for_notes_or_response(request.user, formation_pk, module_pk)
    if err:
        return err

    context = _build_fiche_context(request, module)
    try:
        buffer = build_fiche_module_pdf(context)
    except RuntimeError as exc:
        return Response({'detail': str(exc)}, status=503)

    return _pdf_response(buffer, fiche_module_filename(context['module'], module.pk))


@api_view(['GET'])
@permission_classes([IsGestionNotesOrReadOnly])
def module_notes_fiche_auditeur_pdf_api(request, formation_pk, module_pk, participant_pk):
    """Fiche de notes imprimable d'un auditeur pour ce module."""
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    _, module, err = module_for_notes_or_response(request.user, formation_pk, module_pk)
    if err:
        return err

    context = _build_fiche_context(request, module, participant_ids=[participant_pk])
    if not context['rows']:
        return Response({'detail': 'Auditeur non inscrit à ce module.'}, status=404)

    context['row'] = context['rows'][0]
    try:
        buffer = build_fiche_auditeur_pdf(context)
    except RuntimeError as exc:
        return Response({'detail': str(exc)}, status=503)

    return _pdf_response(buffer, fiche_auditeur_filename(context['row'], module.pk))
