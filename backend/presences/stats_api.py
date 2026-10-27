"""Lot L1 — API des statistiques de présence et alertes d'absence.

Endpoints sous ``/api/presences/stats/`` : taux par étudiant/groupe/module/
formation, alertes selon ConfigAlerteSeuil, génération de notifications
in-app. Lecture : staff ; génération : IsSecretariatOrDFRC.
"""
from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsSecretariatOrDFRC

from .models import NotificationAbsence
from scolarite.models import AnneeAcademique

from . import stats_services


def _annee(request):
    identifiant = request.query_params.get('annee_id')
    if identifiant:
        return AnneeAcademique.objects.filter(pk=identifiant).first()
    return AnneeAcademique.courante_ou_none()


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def taux(request):
    """Taux de présence — ?par=etudiant|groupe|module|formation&annee_id=…"""
    annee = _annee(request)
    par = request.query_params.get('par', 'etudiant')
    fonctions = {
        'etudiant': stats_services.taux_par_etudiant,
        'groupe': stats_services.taux_par_groupe,
        'module': stats_services.taux_par_module,
        'formation': stats_services.taux_par_formation,
    }
    if par not in fonctions:
        return Response({'error': 'par doit être etudiant|groupe|module|formation.'}, status=400)
    return Response({'annee': annee.libelle if annee else None, 'resultats': fonctions[par](annee)})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def alertes(request):
    """Alertes d'absence selon les seuils ConfigAlerteSeuil."""
    annee = _annee(request)
    return Response({'annee': annee.libelle if annee else None,
                     'alertes': stats_services.alertes_absence(annee)})


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def notifications_recues(request):
    """Cloche de l'utilisateur : alertes d'absence reçues (LMD et legacy).

    GET  → {notifications: […], non_lues: n} — les 50 plus récentes.
    PATCH → {ids: […]} marque lues les notifications du destinataire.
    """
    queryset = (NotificationAbsence.objects
                .filter(destinataire=request.user)
                .select_related('etudiant__participant', 'seance_edt'))
    if request.method == 'GET':
        try:
            limite = min(max(int(request.query_params.get('limit') or 50), 1), 200)
        except ValueError:
            limite = 50
        notifications = [
            {
                'id': notif.id,
                'message': notif.message,
                'niveau': notif.niveau,
                'lu': notif.lue,
                'created_at': notif.cree_le.isoformat(),
                'matricule': (notif.etudiant.participant.matricule
                              if notif.etudiant_id and notif.etudiant.participant_id else ''),
                'seance': str(notif.seance_edt) if notif.seance_edt_id else '',
            }
            for notif in queryset[:limite]
        ]
        return Response({'notifications': notifications,
                         'non_lues': queryset.filter(lue=False).count()})
    if request.data.get('tout'):
        # « Tout marquer lu » de la cloche : même contrat que les autres
        # sources de notifications.
        return Response({'marquees': queryset.update(lue=True)})
    ids = [int(x) for x in (request.data.get('ids') or []) if str(x).isdigit()]
    return Response({'marquees': queryset.filter(id__in=ids).update(lue=True)})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def notifications(request):
    """Génère les notifications in-app d'absence pour l'année ciblée."""
    annee = _annee(request)
    try:
        nb = stats_services.notifier_absences(annee, utilisateur=request.user)
    except ValidationError as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response({'detail': f'{nb} notification(s) créée(s).', 'crees': nb})