"""API de la passerelle LMD → modules opérationnels."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsSecretariatOrDFRC
from formations.models import Formation

from . import passerelle_services
from .models import InscriptionAdministrative


def _formation_depuis(data):
    return Formation.objects.filter(pk=data.get('formation_id')).first()


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def passerelle_analyser(request, pk):
    """Prévisualise le résultat de la passerelle, sans rien écrire."""
    inscription = InscriptionAdministrative.objects.select_related(
        'etudiant__participant',
    ).filter(pk=pk).first()
    if inscription is None:
        return Response({'error': 'Introuvable'}, status=404)
    formation = _formation_depuis(request.data)
    if formation is None:
        return Response({'formation_id': ['Formation introuvable.']}, status=400)

    analyse = passerelle_services.analyser(inscription, formation)
    return Response({
        'a_creer': [
            {'ecue': ligne.ecue.code, 'module': module.intitule}
            for ligne, module in analyse['a_creer']
        ],
        'existantes': analyse['existantes'],
        'non_rapprochees': analyse['non_rapprochees'],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def passerelle_synchroniser(request, pk):
    """Crée les inscriptions aux modules opérationnels correspondantes."""
    inscription = InscriptionAdministrative.objects.select_related(
        'etudiant__participant',
    ).filter(pk=pk).first()
    if inscription is None:
        return Response({'error': 'Introuvable'}, status=404)
    formation = _formation_depuis(request.data)
    if formation is None:
        return Response({'formation_id': ['Formation introuvable.']}, status=400)

    try:
        resultat = passerelle_services.synchroniser(
            inscription, formation, acteur=request.user,
        )
    except passerelle_services.PasserelleImpossible as erreur:
        return Response({'error': erreur.messages[0]}, status=409)
    return Response(resultat)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def passerelle_lot(request):
    """Synchronise toutes les inscriptions validées d'un périmètre."""
    formation = _formation_depuis(request.data)
    if formation is None:
        return Response({'formation_id': ['Formation introuvable.']}, status=400)

    inscriptions = InscriptionAdministrative.objects.filter(
        statut=InscriptionAdministrative.Statut.VALIDEE,
    ).select_related('etudiant__participant')
    for champ in ('annee_academique_id', 'ref_formation_id', 'niveau_id', 'parcours_id'):
        if request.data.get(champ):
            inscriptions = inscriptions.filter(**{champ: request.data[champ]})
    if request.data.get('groupe_id'):
        inscriptions = inscriptions.filter(
            affectations__groupe_id=request.data['groupe_id'], affectations__active=True,
        )

    resultat = passerelle_services.synchroniser_lot(
        list(inscriptions), formation, acteur=request.user,
    )
    return Response(resultat)
