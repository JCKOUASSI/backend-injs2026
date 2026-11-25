"""API d'administration des UE/ECUE d'une maquette : export, modèle, import.

Ces routes complètent ``api_views`` (liste, création, modification,
suppression) sans les dupliquer : mêmes permissions
(``IsSecretariatOrDFRC``), même maquette cible, mêmes règles de verrouillage.

* l'export ne sort que les UE de la maquette demandée, éventuellement
  restreintes aux identifiants sélectionnés ;
* l'import ne peut toucher qu'à cette maquette, en deux temps, et refuse tout
  fichier comportant une erreur ;
* une maquette qui n'est plus en BROUILLON est refusée avant toute écriture.
"""

from __future__ import annotations

import logging

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsSecretariatOrDFRC

from . import tableaux_export, ues_export, ues_import
from .models import Maquette

logger = logging.getLogger(__name__)


class ErreurUeSerializer(serializers.Serializer):
    """Erreur métier des routes UE/ECUE."""

    error = serializers.CharField()


def _maquette(pk):
    return Maquette.objects.select_related('niveau', 'ref_formation').filter(pk=pk).first()


def _ids_ues(request):
    """``?ids=1,2`` → ``(ids, erreur)``."""
    brut = (request.query_params.get('ids') or '').strip()
    if not brut:
        return [], None
    morceaux = [morceau.strip() for morceau in brut.split(',') if morceau.strip()]
    for morceau in morceaux:
        if not morceau.isdigit():
            return None, f'Identifiant non numérique : {morceau}.'
    return [int(morceau) for morceau in morceaux], None


def _verrou(maquette):
    """Refuse toute écriture sur une maquette qui n'est plus un brouillon."""
    if maquette.statut != Maquette.Statut.BROUILLON:
        return Response(
            {
                'error': f'Maquette {maquette.get_statut_display().lower()} : '
                         'les UE/ECUE ne sont plus modifiables.',
            },
            status=400,
        )
    return None


@extend_schema(
    parameters=[OpenApiParameter('ids', OpenApiTypes.STR, description='Identifiants des UE sélectionnées.')],
    responses={200: OpenApiTypes.BINARY, 400: ErreurUeSerializer, 404: ErreurUeSerializer},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def ues_export_view(request, pk, fmt):
    """Exporte les UE/ECUE de la maquette (CSV, XLSX, DOCX, PDF)."""
    if fmt not in tableaux_export.FORMATS:
        return Response(
            {'error': f'Format inconnu : {fmt}.', 'formats': list(tableaux_export.FORMATS)},
            status=400,
        )
    maquette = _maquette(pk)
    if maquette is None:
        return Response({'error': 'Maquette introuvable'}, status=404)
    ids, erreur = _ids_ues(request)
    if erreur:
        return Response({'error': erreur}, status=400)
    if ids:
        connus = set(
            maquette.unites_enseignement.filter(pk__in=ids).values_list('pk', flat=True),
        )
        inconnus = [identifiant for identifiant in ids if identifiant not in connus]
        if inconnus:
            return Response(
                {'error': 'UE introuvable(s) dans cette maquette : '
                          + ', '.join(map(str, inconnus)) + '.'},
                status=404,
            )
    logger.info(
        'Export UE/ECUE maquette %s (%s) par %s', maquette.pk, fmt, request.user,
    )
    return ues_export.reponse_export(maquette, fmt, ids=ids)


@extend_schema(responses={200: OpenApiTypes.BINARY, 400: ErreurUeSerializer, 404: ErreurUeSerializer})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def ues_modele_view(request, pk, fmt):
    """Fichier modèle d'import des UE/ECUE (CSV ou XLSX)."""
    if fmt not in ('csv', 'xlsx'):
        return Response({'error': 'Le modèle n’existe qu’en CSV ou XLSX.'}, status=400)
    maquette = _maquette(pk)
    if maquette is None:
        return Response({'error': 'Maquette introuvable'}, status=404)
    contenu = ues_import.modele(fmt)
    reponse = HttpResponse(contenu, content_type=ues_import.CONTENT_TYPES[fmt])
    reponse['Content-Disposition'] = f'attachment; filename="modele-ue-ecue-maquette-{maquette.pk}.{fmt}"'
    reponse['Cache-Control'] = 'private, no-store'
    return reponse


@extend_schema(
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: ErreurUeSerializer},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
@parser_classes([MultiPartParser, FormParser])
def ues_import_view(request, pk):
    """Import UE/ECUE en deux temps : ``mode=apercu`` puis ``mode=importer``."""
    maquette = _maquette(pk)
    if maquette is None:
        return Response({'error': 'Maquette introuvable'}, status=404)
    verrou = _verrou(maquette)
    if verrou is not None:
        return verrou

    if 'fichier' not in request.FILES:
        return Response({'error': 'Aucun fichier reçu (champ « fichier »).'}, status=400)
    fichier = request.FILES['fichier']
    mode = (request.data.get('mode') or 'apercu').strip().lower()
    if mode not in ('apercu', 'importer'):
        return Response({'error': 'Mode inconnu : utilisez « apercu » ou « importer ».'}, status=400)

    try:
        lignes = ues_import.lire(fichier.name, fichier.read())
    except ues_import.FichierInvalide as erreur:
        return Response({'error': str(erreur)}, status=400)

    analyse = ues_import.analyser(maquette, lignes)
    if mode == 'apercu':
        return Response(ues_import.rapport(analyse, nom_fichier=fichier.name))

    if not analyse['importable']:
        donnees = ues_import.rapport(analyse, nom_fichier=fichier.name)
        donnees['error'] = (
            f'Import refusé : {analyse["resume"]["rejets"]} ligne(s) invalide(s). '
            'Corrigez le fichier puis relancez l’import.'
        )
        return Response(donnees, status=400)

    from django.db import transaction

    try:
        with transaction.atomic():
            ecrits = ues_import.appliquer(analyse['plan'])
    except Exception as erreur:  # pragma: no cover - contrainte inattendue
        logger.exception('Import UE/ECUE maquette %s échoué', maquette.pk)
        return Response(
            {'error': f'Import annulé, aucune ligne enregistrée : {erreur}'}, status=400,
        )

    logger.info(
        'Import UE/ECUE maquette %s : %s écriture(s) par %s', maquette.pk, len(ecrits), request.user,
    )
    donnees = ues_import.rapport(analyse, ecrits=ecrits, nom_fichier=fichier.name)
    resume = analyse['resume']
    donnees['message'] = (
        f"{resume['ues_creees']} UE créée(s), {resume['ues_mises_a_jour']} mise(s) à jour, "
        f"{resume['ecues_creees']} ECUE créée(s), {resume['ecues_mises_a_jour']} mise(s) à jour."
    )
    return Response(donnees)


__all__ = ['ues_export_view', 'ues_import_view', 'ues_modele_view']
