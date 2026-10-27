"""
API Views pour le Dashboard Engine INJS-LMD 2026.
Fournit des vues synthétiques consolidées évitant les problèmes N+1.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsDFRC, IsSecretariatOrDFRC
from . import services


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def overview(request):
    """Vue consolidée Direction & Pilotage Général INJS-LMD."""
    data = services.get_direction_overview()
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admissions_dashboard(request):
    """Tableau de bord Concours & Admissions."""
    data = services.get_admissions_dashboard()
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def etudiant_dashboard(request):
    """Tableau de bord Mon Espace Étudiant."""
    data = services.get_etudiant_dashboard(request.user)
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def enseignant_dashboard(request):
    """Tableau de bord Enseignant / Formateur."""
    data = services.get_enseignant_dashboard(request.user)
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def scolarite_dashboard(request):
    """Tableau de bord Scolarité & Admissions."""
    data = services.get_scolarite_dashboard()
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pedagogie_dashboard(request):
    """Tableau de bord Pédagogie, Enseignements & Maquettes."""
    data = services.get_pedagogie_dashboard()
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def presences_dashboard(request):
    """Tableau de bord Assiduité & Présences."""
    data = services.get_presences_dashboard()
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def finances_dashboard(request):
    """Tableau de bord Finances Étudiantes & Recouvrement."""
    data = services.get_finances_dashboard()
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def examens_dashboard(request):
    """Tableau de bord Examens, Jurys LMD & Diplômation."""
    data = services.get_examens_dashboard()
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def logistique_dashboard(request):
    """Tableau de bord Logistique, Patrimoine & Stages."""
    data = services.get_logistique_dashboard()
    return Response(data)

