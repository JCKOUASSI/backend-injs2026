"""API des inscriptions pédagogiques."""

from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsSecretariatOrDFRC

from . import pedagogie_services
from .models import (
    ECUE,
    Groupe,
    InscriptionAdministrative,
    InscriptionPedagogique,
    Semestre,
)


def _serialize_ligne(ligne):
    return {
        'id': ligne.id,
        'inscription_id': ligne.inscription_id,
        'ecue_id': ligne.ecue_id,
        'ecue_code': ligne.ecue.code,
        'ecue_intitule': ligne.ecue.intitule,
        'ue_id': ligne.ecue.ue_id,
        'ue_code': ligne.ecue.ue.code,
        'semestre_id': ligne.semestre_id,
        'semestre': ligne.semestre.libelle,
        'groupe_id': ligne.groupe_id,
        'groupe': ligne.groupe.nom if ligne.groupe else None,
        'type_enseignement': ligne.type_enseignement,
        'credits': ligne.credits,
        'volume_horaire': ligne.volume_horaire,
        'statut': ligne.statut,
        'origine': ligne.origine,
        'ref_module_id': ligne.ecue.ref_module_id,
        'module_participant_id': ligne.module_participant_id,
    }


def _lignes(inscription_id):
    return (
        InscriptionPedagogique.objects
        .filter(inscription_id=inscription_id)
        .select_related('ecue', 'ecue__ue', 'semestre', 'groupe')
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def inscription_pedagogique_list(request, pk):
    """Inscriptions pédagogiques d'une inscription administrative, avec récapitulatif."""
    inscription = InscriptionAdministrative.objects.filter(pk=pk).first()
    if inscription is None:
        return Response({'error': 'Introuvable'}, status=404)
    lignes = _lignes(pk)
    if 'semestre_id' in request.query_params:
        lignes = lignes.filter(semestre_id=request.query_params['semestre_id'])
    return Response({
        'lignes': [_serialize_ligne(ligne) for ligne in lignes],
        'recapitulatif': pedagogie_services.recapitulatif(inscription),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def inscription_pedagogique_generer(request, pk):
    """Génère les inscriptions pédagogiques depuis la maquette applicable."""
    inscription = InscriptionAdministrative.objects.select_related(
        'annee_academique', 'ref_formation', 'niveau', 'parcours', 'etudiant__participant',
    ).filter(pk=pk).first()
    if inscription is None:
        return Response({'error': 'Introuvable'}, status=404)

    semestre = None
    if request.data.get('semestre_id'):
        semestre = Semestre.objects.filter(pk=request.data['semestre_id']).first()
        if semestre is None:
            return Response({'semestre_id': ['Semestre introuvable.']}, status=400)

    groupe = None
    if request.data.get('groupe_id'):
        groupe = Groupe.objects.filter(pk=request.data['groupe_id']).first()
        if groupe is None:
            return Response({'groupe_id': ['Groupe introuvable.']}, status=400)

    try:
        creees = pedagogie_services.generer_inscriptions_pedagogiques(
            inscription, semestre=semestre, groupe=groupe, acteur=request.user,
        )
    except pedagogie_services.PedagogieImpossible as erreur:
        return Response({'error': erreur.messages[0]}, status=409)
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)

    return Response({
        'creees': len(creees),
        'lignes': [_serialize_ligne(ligne) for ligne in _lignes(pk)],
        'recapitulatif': pedagogie_services.recapitulatif(inscription),
    }, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def inscription_pedagogique_ajouter(request, pk):
    """Ajout manuel et exceptionnel d'une ECUE."""
    inscription = InscriptionAdministrative.objects.filter(pk=pk).first()
    if inscription is None:
        return Response({'error': 'Introuvable'}, status=404)
    ecue = ECUE.objects.select_related('ue').filter(pk=request.data.get('ecue_id')).first()
    if ecue is None:
        return Response({'ecue_id': ['ECUE introuvable.']}, status=400)
    groupe = Groupe.objects.filter(pk=request.data.get('groupe_id')).first()

    try:
        ligne = pedagogie_services.ajouter_ecue(
            inscription, ecue, groupe=groupe, acteur=request.user,
            motif=request.data.get('motif', ''),
        )
    except pedagogie_services.PedagogieImpossible as erreur:
        return Response({'error': erreur.messages[0]}, status=409)
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
    return Response(_serialize_ligne(ligne), status=201)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def inscription_pedagogique_detail(request, ligne_id):
    ligne = InscriptionPedagogique.objects.select_related(
        'ecue', 'ecue__ue', 'semestre', 'groupe', 'inscription__etudiant__participant',
    ).filter(pk=ligne_id).first()
    if ligne is None:
        return Response({'error': 'Introuvable'}, status=404)

    if request.method == 'DELETE':
        pedagogie_services.retirer_ecue(
            ligne, acteur=request.user, motif=request.data.get('motif', ''),
        )
        return Response(status=204)

    for champ in ('groupe_id', 'type_enseignement', 'statut'):
        if champ in request.data:
            setattr(ligne, champ, request.data[champ] or None)
    try:
        ligne.full_clean()
    except ValidationError as erreur:
        return Response(erreur.message_dict, status=400)
    ligne.save()
    return Response(_serialize_ligne(ligne))
