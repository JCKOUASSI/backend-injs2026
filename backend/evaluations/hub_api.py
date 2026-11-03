"""Hub Évaluations premium (consultation — tâche 34).

Vues de lecture enrichies pour l'écran consolidé du module :
panorama, sessions, évaluations et notes (saisie/contrôle) avec libellés
métier complets. Aucune écriture : la saisie officielle passe par les
flux C1/C2 existants (notes_saisie, validation).
"""
from django.db.models import Count
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import permissions as perms
from .models import (
    Evaluation, EvaluationGrade, EvaluationParticipant, ReleveNotes,
    SessionEvaluation, TypeEvaluation,
)


@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def stats_api(request):
    notes = dict(
        EvaluationGrade.objects.values_list('statut')
        .annotate(n=Count('id')).order_by()
    )
    total_notes = sum(notes.values())
    validees = notes.get('VALIDEE', 0)
    return Response({
        'sessions': SessionEvaluation.objects.count(),
        'sessions_par_statut': dict(
            SessionEvaluation.objects.values_list('statut')
            .annotate(n=Count('id')).order_by()
        ),
        'evaluations': Evaluation.objects.count(),
        'participants': EvaluationParticipant.objects.count(),
        'notes': total_notes,
        'notes_par_statut': notes,
        'avancement_validation': (
            round(100.0 * validees / total_notes, 1) if total_notes else None
        ),
        'releves': ReleveNotes.objects.count(),
        'types_actifs': TypeEvaluation.objects.filter(actif=True).count(),
    })


@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def sessions_hub_api(request):
    qs = (
        SessionEvaluation.objects.select_related(
            'ref_formation', 'niveau', 'semestre', 'annee_academique',
        )
        .annotate(nb_evaluations=Count('evaluations', distinct=True))
        .order_by('-created_at')
    )
    if request.GET.get('statut'):
        qs = qs.filter(statut=request.GET['statut'])
    return Response({'results': [
        {
            'id': s.id, 'libelle': s.libelle,
            'formation': s.ref_formation.intitule,
            'niveau': s.niveau.code,
            'semestre': s.semestre.libelle if s.semestre_id else '',
            'annee': s.annee_academique.libelle,
            'type_session': s.type_session,
            'type_session_display': s.get_type_session_display(),
            'date_debut': s.date_debut.isoformat() if s.date_debut else None,
            'date_fin': s.date_fin.isoformat() if s.date_fin else None,
            'statut': s.statut, 'statut_display': s.get_statut_display(),
            'verrouillee': s.verrouillee,
            'nb_evaluations': s.nb_evaluations,
        } for s in qs
    ]})


@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def evaluations_hub_api(request):
    qs = (
        Evaluation.objects.select_related(
            'ecue', 'type_evaluation', 'session__ref_formation',
            'session__niveau', 'affectation_pedagogique__enseignant',
        )
        .annotate(nb_participants=Count('participants', distinct=True))
        .order_by('session__ref_formation__intitule', 'ecue__code')
    )
    if request.GET.get('statut'):
        qs = qs.filter(statut=request.GET['statut'])
    return Response({'results': [
        {
            'id': e.id, 'libelle': e.libelle,
            'ecue': f'{e.ecue.code} — {e.ecue.intitule}',
            'type': e.type_evaluation.libelle,
            'formation': e.session.ref_formation.intitule,
            'niveau': e.session.niveau.code,
            'enseignant': (
                str(e.affectation_pedagogique.enseignant)
                if e.affectation_pedagogique_id else ''
            ),
            'bareme': float(e.bareme), 'poids': float(e.poids),
            'date_prevue': e.date_prevue.isoformat() if e.date_prevue else None,
            'nb_participants': e.nb_participants,
            'statut': e.statut, 'statut_display': e.get_statut_display(),
        } for e in qs
    ]})


@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def notes_hub_api(request):
    """Notes en consultation (avancement de saisie et contrôle)."""
    qs = EvaluationGrade.objects.select_related(
        'component__evaluation__ecue', 'component__evaluation__session__ref_formation',
        'component__evaluation__session__niveau',
        'evaluation_participant__inscription_pedagogique__inscription__etudiant'
        '__participant',
    ).order_by('-updated_at')
    if request.GET.get('statut'):
        qs = qs.filter(statut=request.GET['statut'])
    results = []
    for g in qs[:2000]:
        dossier = (
            g.evaluation_participant.inscription_pedagogique
            .inscription.etudiant
        )
        evaluation = g.component.evaluation
        results.append({
            'id': g.id,
            'etudiant_id': dossier.id,
            'matricule': dossier.matricule,
            'nom_complet': dossier.nom_complet,
            'ecue': evaluation.ecue.code,
            'evaluation': evaluation.libelle,
            'formation': evaluation.session.ref_formation.intitule,
            'niveau': evaluation.session.niveau.code,
            'valeur': float(g.valeur) if g.valeur is not None else None,
            'bareme': float(g.bareme),
            'statut': g.statut, 'statut_display': g.get_statut_display(),
            'verrouillee': g.verrouillee,
        })
    return Response({'results': results})


@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def releves_hub_api(request):
    """Relevés versionnés émis (métadonnées de conservation)."""
    qs = ReleveNotes.objects.select_related(
        'inscription__etudiant__participant', 'session__ref_formation',
        'session__niveau',
    ).order_by('-genere_le')
    return Response({'results': [
        {
            'id': r.id,
            'etudiant_id': r.inscription.etudiant_id,
            'matricule': r.inscription.etudiant.participant.matricule,
            'nom_complet': r.inscription.etudiant.nom_complet,
            'formation': r.session.ref_formation.intitule,
            'niveau': r.session.niveau.code,
            'version': r.version,
            'sha256': r.sha256[:16] + '…',
            'verrouillee': r.verrouillee,
            'genere_le': r.genere_le.isoformat() if r.genere_le else None,
        } for r in qs
    ]})
