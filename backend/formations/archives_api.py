"""Endpoints légers pour l'espace Archives (consultation en lecture seule)."""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from presences.models import Pointage
from .api_access import (
    IsOperationalWebStaff,
    archived_module_or_response,
    deny_finance_operational_response,
)
from .api_cache import get_cached_response, request_cache_key, set_cached_response
from .api_views import (
    _filtered_modules_queryset,
    _module_participant_counts,
    _serialize_module_list_item,
)
from .models import Formateur, ModuleParticipant, Participant
from .access import archived_modules_queryset
from .serializers import ParticipantSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def archives_stats_api(request):
    """Compteurs rapides pour le tableau de bord Archives (sans filter_options)."""
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    cache_key = request_cache_key('archives_stats', request)
    cached = get_cached_response(cache_key)
    if cached is not None:
        return Response(cached)

    modules_qs = archived_modules_queryset()
    participants_qs = Participant.objects.filter(
        modules_inscrits__module__archived=True,
    ).distinct()
    formateurs_qs = Formateur.objects.filter(
        modules_assignes__module__archived=True,
    ).distinct()

    if request.user.is_authenticated and request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
        sec = request.user.secretariat
        modules_qs = modules_qs.filter(secretariat=sec)
        participants_qs = participants_qs.filter(secretariat=sec)
    elif request.user.is_authenticated and request.user.role == 'ENCADRANT':
        modules_qs = modules_qs.filter(superviseur=request.user)
        participant_ids = ModuleParticipant.objects.filter(
            module__superviseur=request.user,
            module__archived=True,
        ).values_list('participant_id', flat=True)
        participants_qs = participants_qs.filter(id__in=participant_ids).distinct()
        formateurs_qs = formateurs_qs.filter(modules_assignes__module__in=modules_qs).distinct()

    payload = {
        'modules': modules_qs.count(),
        'participants': participants_qs.count(),
        'formateurs': formateurs_qs.count(),
    }
    set_cached_response(cache_key, payload, 60)
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def archives_modules_list_api(request):
    """Liste paginée de modules pour l'archiviste (sans annotation nb_presents du jour)."""
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    page = int(request.query_params.get('page', 1))
    page_size = int(request.query_params.get('page_size', 24))

    queryset, err = _filtered_modules_queryset(request, archives_only=True)
    if err:
        return err

    total_count = queryset.count()
    start = (page - 1) * page_size
    modules_page = list(queryset[start:start + page_size])
    participant_counts = _module_participant_counts([m.id for m in modules_page])

    results = [
        _serialize_module_list_item(
            m,
            nb_participants=participant_counts.get(m.id, 0),
        )
        for m in modules_page
    ]

    return Response({
        'results': results,
        'count': total_count,
        'total_pages': (total_count + page_size - 1) // page_size if page_size else 1,
        'current_page': page,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def archives_cahier_appel_api(request, formation_pk, module_pk):
    """Cahier d'appel léger : séances, auditeurs et présences (matrice émargement)."""
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    formation, module, err = archived_module_or_response(request.user, formation_pk, module_pk)
    if err:
        return err

    sessions = list(
        module.sessions.order_by('date_journee', 'numero').values(
            'id', 'numero', 'intitule', 'date_journee',
        )
    )
    sessions_data = [
        {
            'id': s['id'],
            'numero': s['numero'],
            'intitule': s['intitule'] or f"Séance {s['numero']}",
            'date': s['date_journee'].isoformat() if s['date_journee'] else None,
        }
        for s in sessions
    ]

    inscriptions = (
        ModuleParticipant.objects.filter(module=module)
        .select_related('participant')
        .order_by('participant__nom', 'participant__prenom')
    )
    participants = ParticipantSerializer(
        [mp.participant for mp in inscriptions], many=True,
    ).data

    pointages = Pointage.objects.filter(
        session__module=module,
        participant_id__isnull=False,
    ).values('participant_id', 'session_id').distinct()

    presences = [
        {
            'type_personne': 'participant',
            'participant_id': row['participant_id'],
            'session_id': row['session_id'],
        }
        for row in pointages
    ]

    return Response({
        'sessions': sessions_data,
        'participants': participants,
        'presences': presences,
    })
