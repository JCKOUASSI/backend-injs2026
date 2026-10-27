"""C1 — API structurelle des évaluations académiques.

Périmètre strictement structurel : création et consultation des sessions,
évaluations, composants, participants, épreuves, émargements, saisie brute
de notes et lecture des résultats. **Aucun calcul, aucune validation,
aucun verrouillage métier, aucun jury** : ces éléments appartiennent à C2
et dépendent des décisions bloquantes (DECISION-1, 2, 3, 5, 6, 10, 15).

Conventions reprises du projet : vues fonctions ``@api_view``, routes
``path()`` explicites, pagination ``PageNumberPagination`` (50 par défaut),
permissions par rôle via ``evaluations.permissions``, erreurs DRF
standard (le handler global ajoute l'en-tête ``X-Error-Code``).
"""
from django.db import transaction
from django.db.models import Count
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from . import permissions as perms
from .services import calcul as services_calcul
from .services import passage as services_passage
from .services import releves as services_releves
from .models import (
    ECUEResult,
    Epreuve,
    Evaluation,
    EvaluationAttendance,
    EvaluationComponent,
    EvaluationGrade,
    EvaluationGradeHistory,
    EvaluationParticipant,
    RegleCalcul,
    ReleveNotes,
    RegleCalculVersion,
    SemesterResult,
    SessionEvaluation,
    TypeEvaluation,
    UEResult,
)
from .serializers import (
    ECUEResultSerializer,
    EpreuveSerializer,
    EvaluationAttendanceSerializer,
    EvaluationComponentSerializer,
    EvaluationGradeHistorySerializer,
    EvaluationGradeSaisieSerializer,
    EvaluationGradeSerializer,
    EvaluationParticipantSerializer,
    EvaluationSerializer,
    PassageNiveauSerializer,
    PreparationSerializer,
    RegleCalculSerializer,
    RegleCalculVersionSerializer,
    ReleveNotesSerializer,
    SemesterResultSerializer,
    SessionEvaluationSerializer,
    TypeEvaluationSerializer,
    UEResultSerializer,
)

TAGS = ['Évaluations académiques']


def _erreur(message, code, http=status.HTTP_400_BAD_REQUEST, extra=None):
    payload = {'detail': message, 'code': code}
    if extra:
        payload.update(extra)
    return Response(payload, status=http)


def _paginer(request, queryset, serializer_class):
    """Pagination explicite (les vues fonctions ne paginent pas d'office)."""
    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        return paginator.get_paginated_response(serializer_class(page, many=True).data)
    return Response(serializer_class(queryset, many=True).data)


def _sessions_visibles(user):
    """Sessions visibles : périmètre ENCADRANT appliqué en base (jamais en UI)."""
    qs = SessionEvaluation.objects.select_related(
        'annee_academique', 'ref_formation', 'niveau', 'semestre', 'maquette',
    ).annotate(nb_evaluations=Count('evaluations', distinct=True))
    affectations = perms.perimetre_affectations(user)
    if affectations.none():
        return qs.none()
    return qs.filter(evaluations__affectation_pedagogique__in=affectations).distinct()


def _evaluations_visibles(user):
    affectations = perms.perimetre_affectations(user)
    if affectations.none():
        return Evaluation.objects.none()
    return Evaluation.objects.filter(
        affectation_pedagogique__in=affectations,
    ).select_related(
        'session', 'ecue', 'type_evaluation', 'affectation_pedagogique',
    ).prefetch_related('components')


def _filtres_sessions(request, qs):
    for champ, parametre in (
        ('annee_academique_id', 'annee_id'),
        ('ref_formation_id', 'ref_formation_id'),
        ('parcours_id', 'parcours_id'),
        ('niveau_id', 'niveau_id'),
        ('semestre_id', 'semestre_id'),
        ('type_session', 'type_session'),
        ('statut', 'statut'),
    ):
        valeur = request.query_params.get(parametre)
        if valeur:
            qs = qs.filter(**{champ: valeur})
    return qs


def _filtres_evaluations(request, qs):
    for champ, parametre in (
        ('session_id', 'session_id'),
        ('ecue_id', 'ecue_id'),
        ('type_evaluation_id', 'type_evaluation_id'),
        ('statut', 'statut'),
    ):
        valeur = request.query_params.get(parametre)
        if valeur:
            qs = qs.filter(**{champ: valeur})
    return qs


@extend_schema(tags=TAGS, responses=SessionEvaluationSerializer(many=True),
                parameters=[
    OpenApiParameter('annee_id', int), OpenApiParameter('ref_formation_id', int),
    OpenApiParameter('parcours_id', int), OpenApiParameter('niveau_id', int),
    OpenApiParameter('semestre_id', int), OpenApiParameter('type_session', str),
    OpenApiParameter('statut', str),
])
@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def sessions_list(request):
    """Sessions d'évaluation du périmètre autorisé."""
    qs = _filtres_sessions(request, _sessions_visibles(request.user))
    return _paginer(request, qs, SessionEvaluationSerializer)


@extend_schema(tags=TAGS, request=SessionEvaluationSerializer,
                responses={201: SessionEvaluationSerializer})
@api_view(['POST'])
@permission_classes([perms.EstGestionEvaluations])
def sessions_create(request):
    """Création d'une session (structurelle, statut BROUILLON)."""
    serializer = SessionEvaluationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        session = serializer.save(creee_par=request.user)
    return Response(
        SessionEvaluationSerializer(session).data, status=status.HTTP_201_CREATED,
    )


@extend_schema(tags=TAGS, methods=['GET'],
                responses=SessionEvaluationSerializer)
@extend_schema(tags=TAGS, methods=['PATCH'], request=SessionEvaluationSerializer,
                responses=SessionEvaluationSerializer)
@api_view(['GET', 'PATCH'])
@permission_classes([perms.EstConsultantEvaluations])
def session_detail(request, pk):
    """Détail / mise à jour partielle d'une session.

    Une session verrouillée refuse toute modification (B.1 §14).
    """
    session = _sessions_visibles(request.user).filter(pk=pk).first()
    if session is None:
        return _erreur('Session introuvable.', 'SESSION_INTROUVABLE',
                       status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        return Response(SessionEvaluationSerializer(session).data)
    if session.verrouillee:
        return _erreur(
            'Session verrouillée : modification interdite.',
            'SESSION_VERROUILLEE', status.HTTP_409_CONFLICT,
        )
    serializer = SessionEvaluationSerializer(session, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@extend_schema(tags=TAGS, responses=EvaluationSerializer(many=True),
                parameters=[
    OpenApiParameter('session_id', int), OpenApiParameter('ecue_id', int),
    OpenApiParameter('type_evaluation_id', int), OpenApiParameter('statut', str),
])
@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def evaluations_list(request):
    """Évaluations du périmètre autorisé."""
    qs = _filtres_evaluations(request, _evaluations_visibles(request.user))
    return _paginer(request, qs, EvaluationSerializer)


@extend_schema(tags=TAGS, request=EvaluationSerializer,
                responses={201: EvaluationSerializer})
@api_view(['POST'])
@permission_classes([perms.EstGestionEvaluations])
def evaluations_create(request):
    """Création d'une évaluation rattachée à une affectation pédagogique."""
    affectation_id = request.data.get('affectation_pedagogique')
    if not affectation_id:
        return _erreur(
            "L'affectation pédagogique est obligatoire (source canonique).",
            'EVALUATION_AFFECTATION_REQUISE',
        )
    affectation = perms.perimetre_affectations(request.user).filter(
        pk=affectation_id,
    ).first()
    if affectation is None:
        return _erreur(
            "Affectation pédagogique hors périmètre ou inconnue.",
            'EVALUATION_AFFECTATION_HORS_PERIMETRE', status.HTTP_403_FORBIDDEN,
        )
    serializer = EvaluationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        evaluation = serializer.save()
    return Response(
        EvaluationSerializer(evaluation).data, status=status.HTTP_201_CREATED,
    )


@extend_schema(tags=TAGS, methods=['GET'], responses=EvaluationSerializer)
@extend_schema(tags=TAGS, methods=['PATCH'], request=EvaluationSerializer,
                responses=EvaluationSerializer)
@api_view(['GET', 'PATCH'])
@permission_classes([perms.EstConsultantEvaluations])
def evaluation_detail(request, pk):
    """Détail d'une évaluation et mise à jour de sa structure.

    La pondération est figée dès ``composition_verrouillee`` (B.1 §5).
    """
    evaluation = _evaluations_visibles(request.user).filter(pk=pk).first()
    if evaluation is None:
        return _erreur('Évaluation introuvable.', 'EVALUATION_INTROUVABLE',
                       status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        return Response(EvaluationSerializer(evaluation).data)
    if evaluation.composition_verrouillee:
        champs = set(request.data or {})
        verrouille = {
            'poids', 'bareme', 'ecue', 'affectation_pedagogique',
            'type_evaluation', 'session',
        }
        if champs & verrouille:
            return _erreur(
                'Composition verrouillée : structure non modifiable.',
                'EVALUATION_COMPOSITION_VERROUILLEE', status.HTTP_409_CONFLICT,
            )
    serializer = EvaluationSerializer(evaluation, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@extend_schema(tags=TAGS, request=EvaluationComponentSerializer,
                responses=EvaluationComponentSerializer(many=True))
@api_view(['GET', 'POST'])
@permission_classes([perms.EstConsultantEvaluations])
def composants_list(request, pk):
    """Composants pondérés d'une évaluation.

    Écriture structurelle uniquement : la somme des poids n'est pas
    normalisée ici (DECISION-5 non arbitrée) et le gel de composition est
    réservé à C2.
    """
    evaluation = _evaluations_visibles(request.user).filter(pk=pk).first()
    if evaluation is None:
        return _erreur('Évaluation introuvable.', 'EVALUATION_INTROUVABLE',
                       status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        return Response(
            EvaluationComponentSerializer(
                evaluation.components.all(), many=True,
            ).data
        )
    if evaluation.composition_verrouillee:
        return _erreur(
            'Composition verrouillée : composants non modifiables.',
            'EVALUATION_COMPOSITION_VERROUILLEE', status.HTTP_409_CONFLICT,
        )
    serializer = EvaluationComponentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        serializer.save(evaluation=evaluation)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=TAGS, request=EvaluationParticipantSerializer,
                responses=EvaluationParticipantSerializer(many=True))
@api_view(['GET', 'POST'])
@permission_classes([perms.EstConsultantEvaluations])
def participants_list(request, pk):
    """Participants d'une évaluation (rattachés par inscription pédagogique).

    La génération automatique depuis les inscriptions fait partie de C2
    (contrat B.1 §12) : C1 n'expose que l'ajout manuel unitaire.
    """
    evaluation = _evaluations_visibles(request.user).filter(pk=pk).first()
    if evaluation is None:
        return _erreur('Évaluation introuvable.', 'EVALUATION_INTROUVABLE',
                       status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        qs = evaluation.participants.select_related(
            'inscription_pedagogique__inscription__etudiant__participant',
            'groupe',
        )
        return Response(EvaluationParticipantSerializer(qs, many=True).data)
    if not perms.peut_gerer(request.user):
        return _erreur('Ajout réservé à la gestion.', 'PARTICIPANT_NON_AUTORISE',
                       status.HTTP_403_FORBIDDEN)
    serializer = EvaluationParticipantSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if EvaluationParticipant.objects.filter(
        evaluation=evaluation,
        inscription_pedagogique=serializer.validated_data['inscription_pedagogique'],
    ).exists():
        return _erreur('Participant déjà inscrit à cette évaluation.',
                       'PARTICIPANT_DOUBLON', status.HTTP_409_CONFLICT)
    with transaction.atomic():
        participant = serializer.save(evaluation=evaluation, source='MANUEL')
    return Response(
        EvaluationParticipantSerializer(participant).data,
        status=status.HTTP_201_CREATED,
    )


@extend_schema(tags=TAGS, request=EpreuveSerializer,
                responses=EpreuveSerializer(many=True))
@api_view(['GET', 'POST'])
@permission_classes([perms.EstConsultantEvaluations])
def epreuves_list(request, pk):
    """Épreuves d'une évaluation (organisation, sans note)."""
    evaluation = _evaluations_visibles(request.user).filter(pk=pk).first()
    if evaluation is None:
        return _erreur('Évaluation introuvable.', 'EVALUATION_INTROUVABLE',
                       status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        qs = evaluation.epreuves.select_related('salle', 'enseignant_responsable')
        return Response(EpreuveSerializer(qs, many=True).data)
    serializer = EpreuveSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        epreuve = serializer.save(evaluation=evaluation)
    return Response(EpreuveSerializer(epreuve).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=TAGS, responses=PreparationSerializer)
@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def preparation_participant(request, pk, participant_pk):
    """Préparation (projection) du résultat d'un participant — C2.

    Lecture seule : rien n'est écrit, aucun résultat n'est persisté. La
    réponse expose les notes collectées, l'instantané de règle et
    l'empreinte, plus la liste des décisions métier bloquantes. La
    moyenne reste ``null`` tant que D1/D2/D5/D6 ne sont pas validées.
    """
    evaluation = _evaluations_visibles(request.user).filter(pk=pk).first()
    if evaluation is None:
        return _erreur('Évaluation introuvable.', 'EVALUATION_INTROUVABLE',
                       status.HTTP_404_NOT_FOUND)
    participant = EvaluationParticipant.objects.filter(
        pk=participant_pk, evaluation=evaluation,
    ).select_related('evaluation', 'evaluation__session').first()
    if participant is None:
        return _erreur('Participant introuvable pour cette évaluation.',
                       'PARTICIPANT_INTROUVABLE', status.HTTP_404_NOT_FOUND)
    preparation = services_calcul.preparer(participant)
    return Response(PreparationSerializer(preparation).data)


@extend_schema(tags=TAGS, request=EvaluationAttendanceSerializer,
                responses=EvaluationAttendanceSerializer(many=True))
@api_view(['GET', 'POST'])
@permission_classes([perms.EstConsultantEvaluations])
def presences_list(request, pk):
    """Émargement d'une épreuve.

    Invariant C1 : un statut d'absence ne crée **aucune** note et ne vaut
    jamais 0 (B.1 §12). La saisie d'émargement ne touche pas aux notes.
    """
    epreuve = Epreuve.objects.filter(
        pk=pk, evaluation__in=_evaluations_visibles(request.user),
    ).select_related('evaluation').first()
    if epreuve is None:
        return _erreur('Épreuve introuvable.', 'EPREUVE_INTROUVABLE',
                       status.HTTP_404_NOT_FOUND)
    if request.method == 'GET':
        qs = epreuve.presences.select_related(
            'evaluation_participant__inscription_pedagogique__inscription__etudiant__participant',
        )
        return Response(EvaluationAttendanceSerializer(qs, many=True).data)
    serializer = EvaluationAttendanceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    participant_id = serializer.validated_data['evaluation_participant'].id
    if EvaluationAttendance.objects.filter(
        epreuve=epreuve, evaluation_participant_id=participant_id,
    ).exists():
        return _erreur('Émargement déjà enregistré pour ce participant.',
                       'PRESENCE_DOUBLON', status.HTTP_409_CONFLICT)
    with transaction.atomic():
        presence = serializer.save(epreuve=epreuve, saisi_par=request.user)
    return Response(
        EvaluationAttendanceSerializer(presence).data, status=status.HTTP_201_CREATED,
    )


@extend_schema(tags=TAGS, request=EvaluationGradeSaisieSerializer(many=True),
                responses=EvaluationGradeSerializer(many=True))
@api_view(['PUT'])
@permission_classes([perms.EstConsultantEvaluations])
def notes_saisie(request, pk):
    """Saisie brute de valeurs pour un composant.

    Périmètre C1 : on écrit la **valeur** et on trace l'historique. Le
    workflow de validation/verrouillage (soumettre → valider → verrouiller)
    appartient à C2. Une note verrouillée n'est jamais écrasée ici.
    """
    component = EvaluationComponent.objects.filter(
        pk=pk, evaluation__in=_evaluations_visibles(request.user),
    ).select_related('evaluation').first()
    if component is None:
        return _erreur('Composant introuvable.', 'COMPOSANT_INTROUVABLE',
                       status.HTTP_404_NOT_FOUND)
    if not perms.peut_saisir_notes(request.user):
        return _erreur('Saisie de notes non autorisée.', 'NOTE_SAISIE_REFUSEE',
                       status.HTTP_403_FORBIDDEN)
    serializer = EvaluationGradeSaisieSerializer(data=request.data, many=True)
    serializer.is_valid(raise_exception=True)
    erreurs = []
    ecrites = []
    with transaction.atomic():
        for ligne in serializer.validated_data:
            participant_id = ligne['evaluation_participant_id']
            valeur = ligne.get('valeur')
            participant = EvaluationParticipant.objects.filter(
                pk=participant_id, evaluation=component.evaluation,
            ).first()
            if participant is None:
                erreurs.append({'evaluation_participant_id': participant_id,
                                'code': 'PARTICIPANT_HORS_EVALUATION'})
                continue
            if valeur is not None:
                if valeur < 0:
                    erreurs.append({'evaluation_participant_id': participant_id,
                                    'code': 'NOTE_NEGATIVE'})
                    continue
                if valeur > component.bareme:
                    erreurs.append({'evaluation_participant_id': participant_id,
                                    'code': 'NOTE_HORS_BAREME',
                                    'bareme': float(component.bareme)})
                    continue
            grade = EvaluationGrade.objects.filter(
                component=component, evaluation_participant=participant,
            ).first()
            if grade is not None and grade.verrouillee:
                erreurs.append({'evaluation_participant_id': participant_id,
                                'code': 'NOTE_VERROUILLEE'})
                continue
            if grade is None:
                grade = EvaluationGrade(
                    component=component, evaluation_participant=participant,
                    bareme=component.bareme,
                )
                action, ancienne = 'SAISIE', None
            else:
                action, ancienne = 'MODIFICATION', grade.valeur
            grade.valeur = valeur
            grade.saisie_par = request.user
            grade.save()
            EvaluationGradeHistory.objects.create(
                grade=grade, action=action, ancienne_valeur=ancienne,
                nouvelle_valeur=valeur, motif='Saisie C1', auteur=request.user,
            )
            ecrites.append(grade)
    if erreurs:
        return _erreur('Saisie refusée.', 'NOTE_SAISIE_INVALIDE',
                       status.HTTP_400_BAD_REQUEST, {'erreurs': erreurs})
    return Response(EvaluationGradeSerializer(ecrites, many=True).data)


@extend_schema(tags=TAGS, responses=EvaluationGradeHistorySerializer(many=True),
                parameters=[
    OpenApiParameter('evaluation_id', int), OpenApiParameter('action', str),
])
@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def notes_historique(request):
    """Historique append-only des notes du périmètre autorisé."""
    qs = EvaluationGradeHistory.objects.filter(
        grade__component__evaluation__in=_evaluations_visibles(request.user),
    ).select_related('grade', 'auteur')
    if request.query_params.get('evaluation_id'):
        qs = qs.filter(grade__component__evaluation_id=request.query_params['evaluation_id'])
    if request.query_params.get('action'):
        qs = qs.filter(action=request.query_params['action'])
    return _paginer(request, qs, EvaluationGradeHistorySerializer)


def _resultats_visibles(user, model, champ_ecue=None):
    qs = model.objects.all().select_related('session')
    affectations = perms.perimetre_affectations(user)
    if champ_ecue:
        qs = qs.filter(
            **{f'{champ_ecue}__in': affectations.values_list('ecue_id', flat=True)},
        )
    else:
        qs = qs.filter(session__in=_sessions_visibles(user))
    return qs


def _inscription_du_perimetre(user, inscription_id):
    """Inscription administrative lisible par l'utilisateur (jamais de fuite).

    Le périmètre est appliqué **en base** : un encadrant ne peut pas
    atteindre une inscription hors de ses affectations.
    """
    from scolarite.models import InscriptionAdministrative

    qs = InscriptionAdministrative.objects.select_related(
        'etudiant__participant', 'ref_formation', 'niveau', 'parcours', 'vague',
    )
    return qs.filter(pk=inscription_id).first() if perms.peut_consulter(user) else None


def _session_du_perimetre(user, session_id):
    """Session d'évaluation lisible par l'utilisateur (même règle)."""
    if not perms.peut_consulter(user):
        return None
    return SessionEvaluation.objects.filter(pk=session_id).first()


@extend_schema(
    tags=TAGS, responses=PassageNiveauSerializer,
    parameters=[
        OpenApiParameter('inscription_id', int, required=True),
        OpenApiParameter('session_id', int, required=True),
        OpenApiParameter('niveau_id', int, required=False),
    ],
)
@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def passage_niveau_calcul(request):
    """Passage de niveau — **calcul technique, en lecture seule**.

    La méthode est volontairement GET : l'appel ne modifie rien et ne
    produit **aucune** décision de jury (D10). La décision officielle reste
    celle de `jurys.DecisionJury`, ici reprise telle quelle dans
    `decision_jury` lorsqu'elle existe.
    """
    inscription_id = request.query_params.get('inscription_id')
    session_id = request.query_params.get('session_id')
    if not inscription_id or not session_id:
        return _erreur(
            'inscription_id et session_id sont obligatoires.',
            'PARAMETRES_MANQUANTS',
        )
    inscription = _inscription_du_perimetre(request.user, inscription_id)
    if inscription is None:
        return _erreur(
            'Inscription introuvable ou hors périmètre.',
            'INSCRIPTION_INTROUVABLE', http=status.HTTP_404_NOT_FOUND,
        )
    session = _session_du_perimetre(request.user, session_id)
    if session is None:
        return _erreur(
            'Session introuvable ou hors périmètre.',
            'SESSION_INTROUVABLE', http=status.HTTP_404_NOT_FOUND,
        )
    niveau = None
    if request.query_params.get('niveau_id'):
        from scolarite.models import Niveau

        niveau = Niveau.objects.filter(
            pk=request.query_params['niveau_id'], actif=True,
        ).first()
        if niveau is None:
            return _erreur(
                'Niveau introuvable.', 'NIVEAU_INTROUVABLE',
                http=status.HTTP_404_NOT_FOUND,
            )
    resultat = services_passage.passage_niveau(inscription, session, niveau)
    return Response(PassageNiveauSerializer(resultat).data)


def _releves_visibles(user, queryset):
    """Relevés restreints aux sessions visibles par l'utilisateur."""
    return queryset.filter(session__in=_sessions_visibles(user))


@extend_schema(
    tags=TAGS, responses=ReleveNotesSerializer(many=True),
    parameters=[OpenApiParameter('session_id', int)],
)
@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def releves_list(request):
    """Relevés de notes — consultation, du plus récent au plus ancien."""
    qs = _releves_visibles(request.user, ReleveNotes.objects.select_related(
        'inscription__etudiant__participant', 'session',
    ))
    if request.query_params.get('session_id'):
        qs = qs.filter(session_id=request.query_params['session_id'])
    if request.query_params.get('inscription_id'):
        qs = qs.filter(inscription_id=request.query_params['inscription_id'])
    return _paginer(request, qs, ReleveNotesSerializer)


@extend_schema(
    tags=TAGS, request=None, responses=ReleveNotesSerializer,
    parameters=[
        OpenApiParameter('inscription_id', int, required=True),
        OpenApiParameter('session_id', int, required=True),
    ],
)
@api_view(['POST'])
@permission_classes([perms.EstGestionEvaluations])
def releves_generer(request):
    """Génère le relevé : **version suivante**, jamais de réécriture.

    La génération est réservée à la gestion (scolarité / encadrement /
    direction) : la consultation reste ouverte aux rôles de lecture.
    """
    inscription_id = request.data.get('inscription_id')
    session_id = request.data.get('session_id')
    if not inscription_id or not session_id:
        return _erreur(
            'inscription_id et session_id sont obligatoires.',
            'PARAMETRES_MANQUANTS',
        )
    inscription = _inscription_du_perimetre(request.user, inscription_id)
    if inscription is None:
        return _erreur(
            'Inscription introuvable ou hors périmètre.',
            'INSCRIPTION_INTROUVABLE', http=status.HTTP_404_NOT_FOUND,
        )
    session = _session_du_perimetre(request.user, session_id)
    if session is None:
        return _erreur(
            'Session introuvable ou hors périmètre.',
            'SESSION_INTROUVABLE', http=status.HTTP_404_NOT_FOUND,
        )
    releve, _charge = services_releves.enregistrer_releve(
        inscription, session, user=request.user,
    )
    releve.refresh_from_db()
    return Response(
        ReleveNotesSerializer(releve).data,
        status=status.HTTP_201_CREATED,
    )


@extend_schema(tags=TAGS, responses=ReleveNotesSerializer)
@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def releves_detail(request, pk):
    """Relevé de notes — détail d'une version, contenu canonique inclus."""
    releve = _releves_visibles(
        request.user,
        ReleveNotes.objects.select_related('inscription__etudiant__participant'),
    ).filter(pk=pk).first()
    if releve is None:
        return _erreur(
            'Relevé introuvable ou hors périmètre.', 'RELEVE_INTROUVABLE',
            http=status.HTTP_404_NOT_FOUND,
        )
    return Response(ReleveNotesSerializer(releve).data)


@extend_schema(tags=TAGS, responses=ECUEResultSerializer(many=True),
                parameters=[OpenApiParameter('session_id', int)])
@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def resultats_ecue_list(request):
    """Résultats ECUE — **lecture seule en C1** (le calcul appartient à C2)."""
    qs = _resultats_visibles(request.user, ECUEResult, 'ecue')
    if request.query_params.get('session_id'):
        qs = qs.filter(session_id=request.query_params['session_id'])
    return _paginer(request, qs, ECUEResultSerializer)


@extend_schema(tags=TAGS, responses=UEResultSerializer(many=True),
                parameters=[OpenApiParameter('session_id', int)])
@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def resultats_ue_list(request):
    """Résultats UE — lecture seule en C1."""
    qs = _resultats_visibles(request.user, UEResult)
    if request.query_params.get('session_id'):
        qs = qs.filter(session_id=request.query_params['session_id'])
    return _paginer(request, qs, UEResultSerializer)


@extend_schema(tags=TAGS, responses=SemesterResultSerializer(many=True),
                parameters=[OpenApiParameter('session_id', int)])
@api_view(['GET'])
@permission_classes([perms.EstConsultantEvaluations])
def resultats_semestre_list(request):
    """Résultats de semestre — lecture seule en C1."""
    qs = _resultats_visibles(request.user, SemesterResult)
    if request.query_params.get('session_id'):
        qs = qs.filter(session_id=request.query_params['session_id'])
    return _paginer(request, qs, SemesterResultSerializer)


@extend_schema(tags=TAGS, request=RegleCalculSerializer,
                responses=RegleCalculSerializer(many=True))
@api_view(['GET', 'POST'])
@permission_classes([perms.EstConsultantEvaluations])
def regles_list(request):
    """Familles de règles (aucun seed en C1) et leurs versions.

    Aucune règle n'est créée par défaut : aucune valeur métier n'est
    inventée tant que DECISION-1 n'est pas arbitrée.
    """
    if request.method == 'POST':
        if not perms.peut_gerer(request.user):
            return _erreur('Création réservée à la gestion.', 'REGLE_NON_AUTORISEE',
                           status.HTTP_403_FORBIDDEN)
        serializer = RegleCalculSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        regle = serializer.save()
        return Response(RegleCalculSerializer(regle).data, status.HTTP_201_CREATED)
    qs = RegleCalcul.objects.prefetch_related('versions')
    return Response(RegleCalculSerializer(qs, many=True).data)


@extend_schema(tags=TAGS, request=RegleCalculVersionSerializer,
                responses=RegleCalculVersionSerializer(many=True))
@api_view(['GET', 'POST'])
@permission_classes([perms.EstConsultantEvaluations])
def regles_versions_list(request):
    """Versions de règles ; une version verrouillée est immuable (B.1 §9)."""
    if request.method == 'POST':
        if not perms.peut_gerer(request.user):
            return _erreur('Création réservée à la gestion.', 'REGLE_NON_AUTORISEE',
                           status.HTTP_403_FORBIDDEN)
        serializer = RegleCalculVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = serializer.save()
        return Response(
            RegleCalculVersionSerializer(version).data, status.HTTP_201_CREATED,
        )
    qs = RegleCalculVersion.objects.select_related('regle')
    if request.query_params.get('code'):
        qs = qs.filter(regle__code=request.query_params['code'])
    return Response(RegleCalculVersionSerializer(qs, many=True).data)


@extend_schema(tags=TAGS, request=TypeEvaluationSerializer,
                responses=TypeEvaluationSerializer(many=True))
@api_view(['GET', 'POST'])
@permission_classes([perms.EstConsultantEvaluations])
def types_evaluation_list(request):
    """Référentiel des types d'évaluation (paramétrable, sans seed)."""
    if request.method == 'POST':
        if not perms.peut_gerer(request.user):
            return _erreur('Création réservée à la gestion.', 'TYPE_NON_AUTORISE',
                           status.HTTP_403_FORBIDDEN)
        serializer = TypeEvaluationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        type_eval = serializer.save()
        return Response(TypeEvaluationSerializer(type_eval).data, status.HTTP_201_CREATED)
    return Response(TypeEvaluationSerializer(TypeEvaluation.objects.all(), many=True).data)