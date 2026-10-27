from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from formations.models import Module, Participant, Formation
from formations.access import modules_queryset_for_user

from .models import (
    Questionnaire, Question, ChoixQuestion, ReponseQuestionnaire, ReponseQuestion,
)

from .permissions import (
    IsSuperviseur, IsAuditeur,
)
from .access import (
    questionnaires_queryset_for_user,
    titres_dans_perimetre,
    questionnaire_accessible_to_participant,
    _normalize_groupe_value,
)
from .resultats_utils import build_resultats_payload
from .questionnaire_exports import (
    export_questionnaire_groupe_pdf,
    export_questionnaire_groupe_excel,
    export_questionnaire_tous_groupes_excel,
)
from .serializers import (
    QuestionnaireListSerializer,
    QuestionnaireDetailSerializer,
    QuestionWriteSerializer,
    SoumissionSerializer,
)



# ─────────────────────────────────────────────────────────────
# QUESTIONNAIRES — Superviseurs
# ─────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsSuperviseur])
def questionnaire_list_create(request):
    """
    GET  : liste des questionnaires (filtrables par module_id, cible, statut)
    POST : créer un nouveau questionnaire
    """
    if request.method == 'GET':
        qs = questionnaires_queryset_for_user(
            request.user,
            Questionnaire.objects.select_related('module', 'createur'),
        )

        module_id = request.query_params.get('module_id')
        if module_id:
            qs = qs.filter(module_id=module_id)

        cible = request.query_params.get('cible')
        if cible:
            qs = qs.filter(cible__iexact=cible)

        statut = request.query_params.get('statut')
        if statut:
            qs = qs.filter(statut__iexact=statut)

        qs = qs.annotate(_nb_questions=Count('questions', distinct=True)).order_by('-created_at', '-id')

        legacy_array = request.query_params.get('legacy') == '1'
        if legacy_array:
            serializer = QuestionnaireListSerializer(qs, many=True)
            return Response(serializer.data)

        page = max(int(request.query_params.get('page', 1)), 1)
        page_size = min(max(int(request.query_params.get('page_size', 50)), 1), 200)
        total_count = qs.count()
        start = (page - 1) * page_size
        page_qs = qs[start:start + page_size]
        serializer = QuestionnaireListSerializer(page_qs, many=True)
        return Response({
            'results': serializer.data,
            'count': total_count,
            'total_pages': (total_count + page_size - 1) // page_size if total_count else 0,
            'current_page': page,
        })

    # POST
    titres = request.data.get('titres') or []
    if not titres_dans_perimetre(request.user, titres):
        return Response(
            {'detail': 'Un ou plusieurs modules ciblés sont hors de votre périmètre.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    data = request.data.copy()
    data['createur'] = request.user.pk
    serializer = QuestionnaireListSerializer(data=data)
    if serializer.is_valid():
        serializer.save(createur=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsSuperviseur])
def questionnaire_detail(request, pk):
    """Détail, modification ou suppression d'un questionnaire."""
    questionnaire = get_object_or_404(questionnaires_queryset_for_user(request.user), pk=pk)

    if request.method == 'GET':
        serializer = QuestionnaireDetailSerializer(questionnaire)
        return Response(serializer.data)

    if request.method == 'PATCH':
        serializer = QuestionnaireListSerializer(questionnaire, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # DELETE
    if questionnaire.reponses.exists():
        return Response(
            {'detail': 'Impossible de supprimer un questionnaire ayant des réponses.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    questionnaire.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([IsSuperviseur])
def questionnaire_publier(request, pk):
    """Publier ou fermer un questionnaire."""
    questionnaire = get_object_or_404(questionnaires_queryset_for_user(request.user), pk=pk)
    nouveau_statut = request.data.get('statut')
    if nouveau_statut not in (Questionnaire.Statut.PUBLIE, Questionnaire.Statut.FERME, Questionnaire.Statut.BROUILLON):
        return Response({'detail': 'statut invalide.'}, status=status.HTTP_400_BAD_REQUEST)
    questionnaire.statut = nouveau_statut
    questionnaire.save(update_fields=['statut'])
    return Response({'statut': questionnaire.statut})


# ─────────────────────────────────────────────────────────────
# QUESTIONS — Superviseurs
# ─────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsSuperviseur])
def question_create(request, questionnaire_pk):
    """Ajouter une question à un questionnaire."""
    questionnaire = get_object_or_404(questionnaires_queryset_for_user(request.user), pk=questionnaire_pk)
    if questionnaire.statut == Questionnaire.Statut.PUBLIE:
        return Response(
            {'detail': 'Impossible de modifier un questionnaire publié.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    serializer = QuestionWriteSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(questionnaire=questionnaire)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsSuperviseur])
def question_detail(request, questionnaire_pk, pk):
    """Modifier ou supprimer une question."""
    questionnaire = get_object_or_404(questionnaires_queryset_for_user(request.user), pk=questionnaire_pk)
    question = get_object_or_404(Question, pk=pk, questionnaire=questionnaire)

    if questionnaire.statut == Questionnaire.Statut.PUBLIE:
        return Response(
            {'detail': 'Impossible de modifier un questionnaire publié.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if request.method == 'PATCH':
        serializer = QuestionWriteSerializer(question, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # DELETE
    question.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ─────────────────────────────────────────────────────────────
# ÉVALUATION — Auditeurs
# ─────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuditeur])
def questionnaires_disponibles(request):
    """
    Retourne les questionnaires publiés accessibles à l'auditeur connecté
    en fonction de son grade, sa catégorie et son groupe (JSONField categories/grades/groupes).
    Un questionnaire est accessible si :
      - sa liste groupes est vide OU contient le groupe de l'auditeur, ET
      - ses listes categories ET grades sont toutes deux vides (cible tout le monde), OU
      - sa liste categories contient la catégorie de l'auditeur (ex: 'A'), OU
      - sa liste grades contient le grade exact de l'auditeur (ex: 'A3').
    """
    try:
        participant = request.user.participant_profile
    except Exception:
        return Response({'detail': 'Profil étudiant introuvable.'}, status=status.HTTP_404_NOT_FOUND)

    qs = Questionnaire.objects.filter(statut=Questionnaire.Statut.PUBLIE)

    # Exclure ceux déjà soumis
    deja_soumis = ReponseQuestionnaire.objects.filter(
        participant=participant
    ).values_list('questionnaire_id', flat=True)
    qs = qs.exclude(id__in=deja_soumis)

    result = [
        q for q in qs
        if questionnaire_accessible_to_participant(q, participant)
    ]

    serializer = QuestionnaireDetailSerializer(result, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuditeur])
def soumettre_evaluation(request):
    """Soumettre les réponses d'un auditeur à un questionnaire."""
    try:
        participant = request.user.participant_profile
    except Exception:
        return Response({'detail': 'Profil étudiant introuvable.'}, status=status.HTTP_404_NOT_FOUND)

    data = request.data.copy()
    data['participant'] = participant.pk

    serializer = SoumissionSerializer(data=data)
    if serializer.is_valid():
        soumission = serializer.save()
        return Response(
            {'detail': 'Évaluation soumise avec succès.', 'id': soumission.pk},
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────
# RÉSULTATS — Superviseurs
# ─────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsSuperviseur])
def resultats_questionnaire(request, pk):
    """Résultats agrégés d'un questionnaire, ventilés par groupe."""
    questionnaire = get_object_or_404(questionnaires_queryset_for_user(request.user), pk=pk)
    groupe_param = (request.query_params.get('groupe') or '').strip()
    groupe_filtre = _normalize_groupe_value(groupe_param) if groupe_param else ''
    return Response(build_resultats_payload(questionnaire, groupe_filtre))


@api_view(['GET'])
@permission_classes([IsSuperviseur])
def resultats_par_module(request, module_pk):
    """Résultats de tous les questionnaires d'un module."""
    module = get_object_or_404(modules_queryset_for_user(request.user), pk=module_pk)
    questionnaires = Questionnaire.objects.filter(module=module)
    return Response([
        build_resultats_payload(q) for q in questionnaires
    ])


@api_view(['GET'])
@permission_classes([IsSuperviseur])
def analyse_qualitative(request, pk):
    """
    Analyse qualitative complète d'un questionnaire :
    - Méta : nb soumissions, taux de participation par grade/catégorie/groupe
    - Par question : distribution des notes (1-5), verbatims texte, stats choix
    - Score global moyen (questions NOTE uniquement)
    Query param optionnel : groupe (ex. GROUPE 1) pour filtrer les résultats.
    """
    from django.db.models import Avg, Count
    from collections import defaultdict

    questionnaire = get_object_or_404(questionnaires_queryset_for_user(request.user), pk=pk)

    groupe_param = (request.query_params.get('groupe') or '').strip()
    groupe_filtre = _normalize_groupe_value(groupe_param) if groupe_param else ''

    soumissions_qs = questionnaire.reponses.select_related('participant').prefetch_related(
        'reponses_questions__question',
        'reponses_questions__choix',
        'reponses_questions__choix_multiples',
    )
    all_soumissions = list(soumissions_qs)
    if groupe_filtre:
        soumissions = [
            s for s in all_soumissions
            if _normalize_groupe_value(s.participant.groupe) == groupe_filtre
        ]
    else:
        soumissions = all_soumissions

    soumission_ids = {s.id for s in soumissions}
    nb_soumissions = len(soumissions)

    # Distribution par grade, catégorie et groupe (toujours sur l'ensemble des réponses)
    grade_counts = defaultdict(int)
    categorie_counts = defaultdict(int)
    groupe_counts = defaultdict(int)
    for s in all_soumissions:
        grade = (s.participant.grade or '').strip().upper()
        if grade:
            grade_counts[grade] += 1
            cat = grade[0]
            categorie_counts[cat] += 1
        groupe = _normalize_groupe_value(s.participant.groupe)
        if groupe:
            groupe_counts[groupe] += 1

    # Analyse par question (filtrée si groupe sélectionné)
    questions_data = []
    notes_globales = []

    for q in questionnaire.questions.prefetch_related('choix', 'reponses').order_by('ordre'):
        item = {
            'id': q.id,
            'intitule': q.intitule,
            'type_question': q.type_question,
            'ordre': q.ordre,
            'obligatoire': q.obligatoire,
        }

        if q.type_question == 'NOTE':
            reponses_note = q.reponses.filter(
                note__isnull=False,
                soumission_id__in=soumission_ids,
            )
            notes = list(reponses_note.values_list('note', flat=True))
            agg = reponses_note.aggregate(moyenne=Avg('note'), total=Count('id'))
            moyenne = round(agg['moyenne'], 2) if agg['moyenne'] else None
            item['moyenne'] = moyenne
            item['total_reponses'] = agg['total']
            item['distribution'] = {str(i): notes.count(i) for i in range(1, 6)}
            if moyenne:
                notes_globales.append(moyenne)

        elif q.type_question in ('CHOIX_UN', 'CHOIX_MUL'):
            choix_stats = []
            total_rep = 0
            for c in q.choix.all():
                nb_unique = q.reponses.filter(choix=c, soumission_id__in=soumission_ids).count()
                nb_multiple = c.reponses_choix_multiple.filter(
                    soumission__questionnaire=questionnaire,
                    soumission_id__in=soumission_ids,
                ).count()
                nb = nb_unique + nb_multiple
                total_rep += nb
                choix_stats.append({'id': c.id, 'libelle': c.libelle, 'nb_reponses': nb})
            item['choix_stats'] = choix_stats
            item['total_reponses'] = total_rep

        elif q.type_question == 'TEXTE':
            verbatims_qs = q.reponses.exclude(texte='').filter(
                soumission_id__in=soumission_ids,
            ).select_related('soumission__participant')
            verbatims = []
            for r in verbatims_qs:
                grade = (r.soumission.participant.grade or '').strip().upper()
                groupe = _normalize_groupe_value(r.soumission.participant.groupe)
                verbatims.append({
                    'texte': r.texte,
                    'grade': grade,
                    'categorie': grade[0] if grade else '',
                    'groupe': groupe,
                })
            item['verbatims'] = verbatims
            item['nb_reponses_texte'] = len(verbatims)

        questions_data.append(item)

    score_global = round(sum(notes_globales) / len(notes_globales), 2) if notes_globales else None

    def _tendance_soumissions(soums):
        counts = defaultdict(int)
        for s in soums:
            if s.soumis_le:
                counts[s.soumis_le.date().isoformat()] += 1
        return [{'date': d, 'nb': n} for d, n in sorted(counts.items())]

    distribution_notes = defaultdict(int)
    moyennes_par_question = []
    for q in questions_data:
        if q['type_question'] == 'NOTE':
            for k, v in (q.get('distribution') or {}).items():
                distribution_notes[k] += v
            if q.get('moyenne') is not None:
                moyennes_par_question.append({
                    'id': q['id'],
                    'intitule': q['intitule'],
                    'moyenne': q['moyenne'],
                    'total_reponses': q.get('total_reponses') or 0,
                })

    tendance = _tendance_soumissions(soumissions)
    tendance_par_groupe = {
        g: _tendance_soumissions([
            s for s in all_soumissions
            if (_normalize_groupe_value(s.participant.groupe) or '—') == g
        ])
        for g in sorted(set(
            _normalize_groupe_value(s.participant.groupe) or '—'
            for s in all_soumissions
        ))
    }

    comparaison_groupes = []
    par_groupe_payload = build_resultats_payload(questionnaire)['par_groupe']
    for g, block in par_groupe_payload.items():
        note_qs = [
            q for q in block['questions']
            if q['type_question'] == 'NOTE' and q.get('moyenne') is not None
        ]
        g_score = (
            round(sum(q['moyenne'] for q in note_qs) / len(note_qs), 2)
            if note_qs else None
        )
        comparaison_groupes.append({
            'groupe': g,
            'nb_soumissions': block['nb_soumissions'],
            'score_global': g_score,
        })

    return Response({
        'id': questionnaire.pk,
        'titres': questionnaire.titres,
        'cible': questionnaire.cible,
        'statut': questionnaire.statut,
        'categories': questionnaire.categories,
        'grades': questionnaire.grades,
        'groupes': questionnaire.groupes,
        'groupe_filtre': groupe_filtre or None,
        'nb_soumissions': nb_soumissions,
        'nb_soumissions_total': len(all_soumissions),
        'score_global': score_global,
        'distribution_grades': dict(sorted(grade_counts.items())),
        'distribution_categories': dict(sorted(categorie_counts.items())),
        'distribution_groupes': dict(sorted(groupe_counts.items(), key=lambda x: x[0])),
        'distribution_notes': dict(sorted(distribution_notes.items())),
        'moyennes_par_question': moyennes_par_question,
        'tendance': tendance,
        'tendance_par_groupe': tendance_par_groupe,
        'comparaison_groupes': comparaison_groupes,
        'questions': questions_data,
    })


@api_view(['GET'])
@permission_classes([IsSuperviseur])
def export_questionnaire_analyse(request, pk, fmt):
    """
    Export PDF ou Excel de l'analyse par groupe.
    Query param obligatoire : groupe=GROUPE 1
    Query param optionnel : tous=1 (Excel uniquement, une feuille par groupe)
    """
    questionnaire = get_object_or_404(questionnaires_queryset_for_user(request.user), pk=pk)
    fmt = (fmt or '').lower()
    if fmt not in ('pdf', 'excel'):
        return Response({'detail': 'Format invalide (pdf ou excel).'}, status=status.HTTP_400_BAD_REQUEST)

    export_tous = request.query_params.get('tous') in ('1', 'true', 'yes')
    groupe_param = (request.query_params.get('groupe') or '').strip()
    groupe_norm = _normalize_groupe_value(groupe_param) if groupe_param else ''

    try:
        if fmt == 'excel' and export_tous:
            buffer = export_questionnaire_tous_groupes_excel(questionnaire)
            filename = f'evaluation_{pk}_tous_groupes.xlsx'
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            if not groupe_norm:
                return Response(
                    {'detail': 'Précisez le groupe à exporter (paramètre groupe).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            payload = build_resultats_payload(questionnaire)
            if groupe_norm not in payload.get('par_groupe', {}):
                return Response(
                    {'detail': f'Groupe « {groupe_norm} » introuvable pour ce questionnaire.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            safe_groupe = groupe_norm.replace(' ', '_')
            if fmt == 'pdf':
                buffer = export_questionnaire_groupe_pdf(questionnaire, groupe_norm)
                filename = f'evaluation_{pk}_{safe_groupe}.pdf'
                content_type = 'application/pdf'
            else:
                buffer = export_questionnaire_groupe_excel(questionnaire, groupe_norm)
                filename = f'evaluation_{pk}_{safe_groupe}.xlsx'
                content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    except RuntimeError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    response = HttpResponse(buffer.getvalue(), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

