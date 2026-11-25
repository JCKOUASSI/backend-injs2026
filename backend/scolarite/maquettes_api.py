"""API d'administration des maquettes : export, import et suppression.

Complète ``scolarite.api_views`` (liste, détail, création, workflow) sans le
dupliquer : les mêmes permissions (``IsSecretariatOrDFRC``) et les mêmes
filtres y sont appliqués. Les routes sont déclarées dans ``scolarite/urls.py``.

Sécurité :

* toute opération est contrôlée **côté serveur** (aucune confiance au front) ;
* l'export ne sort que les maquettes du périmètre filtré et refuse un
  identifiant non numérique (400) ou inconnu (404) ;
* l'import est transactionnel et refuse un fichier invalide en bloc ;
* la suppression respecte les contraintes métier (statut immuable, données
  liées protégées) et renvoie un bilan détaillé.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsSecretariatOrDFRC

from . import maquettes_export, maquettes_import
from .models import Maquette

logger = logging.getLogger(__name__)

CHAMPS_FILTRES_NUMERIQUES = ('annee_academique_id', 'ref_formation_id', 'parcours_id', 'niveau_id')


class ErreurMaquettesSerializer(serializers.Serializer):
    """Erreur métier renvoyée par les routes d'administration des maquettes."""

    error = serializers.CharField()


# ── Périmètre ───────────────────────────────────────────────────────────────
def _queryset_maquettes():
    return (
        Maquette.objects
        .select_related('annee_academique', 'ref_formation', 'parcours', 'niveau')
        .annotate(
            nb_ue=Count('unites_enseignement', distinct=True),
            total_credits=Sum('unites_enseignement__credits'),
        )
        .order_by('-annee_academique__libelle', 'niveau__ordre', '-version')
    )


def _filtrer(queryset, request):
    """Applique les filtres de l'écran ; retourne ``(queryset, erreur)``."""
    for champ in CHAMPS_FILTRES_NUMERIQUES:
        valeur = (request.query_params.get(champ) or '').strip()
        if not valeur:
            continue
        if not valeur.isdigit():
            return None, f'{champ} doit être un identifiant numérique.'
        queryset = queryset.filter(**{champ: int(valeur)})
    statut = (request.query_params.get('statut') or '').strip()
    if statut:
        if statut not in Maquette.Statut.values:
            return None, f'Statut inconnu : {statut}.'
        queryset = queryset.filter(statut=statut)
    return queryset, None


def _ids_demandes(request):
    """Liste d'identifiants passée en ``?ids=1,2,3`` (ou vide)."""
    brut = (request.query_params.get('ids') or '').strip()
    if not brut:
        return [], None
    ids = []
    for morceau in brut.split(','):
        morceau = morceau.strip()
        if not morceau:
            continue
        if not morceau.isdigit():
            return None, f'Identifiant de maquette invalide : « {morceau} ».'
        ids.append(int(morceau))
    return sorted(set(ids)), None


# ── Export ──────────────────────────────────────────────────────────────────
@extend_schema(
    parameters=[
        OpenApiParameter('ids', OpenApiTypes.STR, description='Identifiants séparés par des virgules.'),
        OpenApiParameter('detail', OpenApiTypes.BOOL, description='Inclure le détail UE/ECUE.'),
        OpenApiParameter('statut', OpenApiTypes.STR, description='Filtrer par statut.'),
        *[
            OpenApiParameter(champ, OpenApiTypes.INT, description='Filtre de périmètre.')
            for champ in CHAMPS_FILTRES_NUMERIQUES
        ],
    ],
    responses={(200, 'application/octet-stream'): OpenApiTypes.BINARY, 400: ErreurMaquettesSerializer},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def maquette_export(request, fmt):
    """Exporte les maquettes sélectionnées — ou toutes celles du périmètre.

    Règle de sélection (identique à l'interface) :

    * aucun identifiant fourni → toutes les maquettes du périmètre filtré ;
    * un ou plusieurs identifiants → uniquement celles-ci.
    """
    if fmt not in maquettes_export.FORMATS:
        return Response(
            {'error': f'Format non pris en charge : {fmt}. '
                      f'Formats disponibles : {", ".join(maquettes_export.FORMATS)}.'},
            status=400,
        )

    queryset = _queryset_maquettes()
    ids, erreur = _ids_demandes(request)
    if erreur:
        return Response({'error': erreur}, status=400)

    if ids:
        trouvees = set(queryset.filter(pk__in=ids).values_list('pk', flat=True))
        manquantes = [identifiant for identifiant in ids if identifiant not in trouvees]
        if manquantes:
            return Response(
                {'error': 'Maquette(s) introuvable(s) : '
                          + ', '.join(str(identifiant) for identifiant in manquantes) + '.'},
                status=404,
            )
        queryset = queryset.filter(pk__in=ids)
    else:
        queryset, erreur = _filtrer(queryset, request)
        if erreur:
            return Response({'error': erreur}, status=400)

    avec_detail = (request.query_params.get('detail') or '').strip().lower() in (
        '1', 'true', 'oui', 'yes',
    )
    try:
        return maquettes_export.reponse_export(queryset, fmt, avec_detail=avec_detail)
    except Exception:  # une erreur de génération ne doit pas produire un 500 muet
        logger.exception('Export des maquettes en %s impossible', fmt)
        return Response(
            {'error': f'La génération du fichier {fmt.upper()} a échoué. '
                      'Réessayez ou choisissez un autre format.'},
            status=500,
        )


@extend_schema(responses={(200, 'application/octet-stream'): OpenApiTypes.BINARY})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def maquette_modele_import(request, fmt):
    """Télécharge le modèle d'import (CSV ou Excel) avec deux lignes d'exemple."""
    if fmt not in ('csv', 'xlsx'):
        return Response({'error': 'Modèle disponible en CSV ou Excel uniquement.'}, status=400)
    contenu = maquettes_import.modele(fmt)
    content_types = {
        'csv': 'text/csv; charset=utf-8',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }
    reponse = HttpResponse(contenu, content_type=content_types[fmt])
    reponse['Content-Disposition'] = f'attachment; filename="modele_maquettes.{fmt}"'
    reponse['Cache-Control'] = 'private, no-store'
    return reponse


# ── Import ──────────────────────────────────────────────────────────────────
@extend_schema(
    request=OpenApiTypes.BINARY,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
@parser_classes([MultiPartParser, FormParser])
def maquette_import(request):
    """Analyse puis intègre un fichier Excel/CSV de maquettes.

    ``mode=apercu`` (défaut) : lecture seule, rapport et prévisualisation.
    ``mode=importer`` : analyse à nouveau puis écriture **transactionnelle**.
    Un fichier comportant une erreur bloquante est refusé dans les deux modes.
    """
    fichier = request.FILES.get('fichier')
    if fichier is None:
        return Response({'error': 'Aucun fichier reçu (champ « fichier »).'}, status=400)

    mode = (request.data.get('mode') or 'apercu').strip().lower()
    if mode not in ('apercu', 'importer'):
        return Response({'error': 'Mode inconnu : utilisez « apercu » ou « importer ».'}, status=400)

    try:
        lignes = maquettes_import.lire(fichier.name, fichier.read())
    except maquettes_import.FichierInvalide as erreur:
        return Response({'error': str(erreur), 'importable': False}, status=400)

    analyse = maquettes_import.analyser(lignes)
    rapport = {cle: valeur for cle, valeur in analyse.items() if cle != 'plan'}
    rapport['fichier'] = fichier.name
    rapport['mode'] = mode

    if mode == 'apercu':
        return Response(rapport)

    if not analyse['importable']:
        rapport['error'] = (
            'Import annulé : le fichier contient '
            f"{len(analyse['erreurs'])} erreur(s). Corrigez-les puis relancez l'analyse."
        )
        return Response(rapport, status=400)

    try:
        bilan = maquettes_import.appliquer(analyse['plan'], request.user)
    except Exception:
        # La transaction a été annulée : aucune donnée partielle n'est laissée.
        logger.exception("Import des maquettes échoué (%s)", fichier.name)
        return Response(
            {'error': "L'import a échoué et a été annulé en bloc : aucune donnée "
                      "n'a été enregistrée. Vérifiez le fichier puis réessayez.",
             'importable': False},
            status=400,
        )

    logger.info(
        'Import maquettes par %s : %s maquette(s), %s UE, %s ECUE (%s)',
        request.user, bilan['maquettes_creees'] + bilan['maquettes_completees'],
        bilan['ue_creees'] + bilan['ue_mises_a_jour'],
        bilan['ecue_creees'] + bilan['ecue_mises_a_jour'], fichier.name,
    )
    rapport['bilan'] = bilan
    rapport['resume']['maquettes_creees'] = bilan['maquettes_creees']
    rapport['resume']['maquettes_completees'] = bilan['maquettes_completees']
    return Response(rapport)


# ── Suppression ─────────────────────────────────────────────────────────────
def _dependances(maquette):
    """Dépendances métier empêchant une suppression (libellé, nombre)."""
    from evaluations.models import Evaluation
    from equivalences.models import DemandeEquivalenceDispense
    from scolarite.models import AffectationPedagogique, InscriptionPedagogique

    listes = [
        ('inscription(s) pédagogique(s)', InscriptionPedagogique.objects.filter(
            ecue__ue__maquette=maquette,
        )),
        ('note(s)/évaluation(s)', Evaluation.objects.filter(ecue__ue__maquette=maquette)),
        ('demande(s) d’équivalence', DemandeEquivalenceDispense.objects.filter(
            Q(ecue__ue__maquette=maquette) | Q(ue__maquette=maquette),
        )),
        ('affectation(s) pédagogique(s)', AffectationPedagogique.objects.filter(
            ecue__ue__maquette=maquette,
        )),
    ]
    dependances = []
    for libelle, queryset in listes:
        nombre = queryset.count()
        if nombre:
            dependances.append(f'{nombre} {libelle}')
    return dependances


def _motif_blocage(maquette):
    """Motif empêchant la suppression, ou ``None`` si elle est possible."""
    if maquette.statut != Maquette.Statut.BROUILLON:
        return (
            f'maquette {maquette.get_statut_display().lower()} : immuable, '
            'archivez-la au lieu de la supprimer (le clonage crée une nouvelle version).'
        )
    dependances = _dependances(maquette)
    if dependances:
        return 'données liées : ' + ', '.join(dependances) + '.'
    return None


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def maquette_supprimer(request):
    """Supprime une ou plusieurs maquettes, avec bilan et blocages détaillés.

    Seules les maquettes en BROUILLON sans donnée liée sont supprimables. Les
    autres sont refusées **individuellement** : le lot partiel reste possible,
    et le bilan indique pour chacune le motif de refus.
    """
    ids = request.data.get('ids')
    if isinstance(ids, str):
        ids = [morceau for morceau in ids.split(',') if morceau.strip()]
    if not isinstance(ids, (list, tuple)) or not ids:
        return Response({'error': 'Fournir une liste « ids » non vide.'}, status=400)
    try:
        ids = sorted({int(identifiant) for identifiant in ids})
    except (TypeError, ValueError):
        return Response({'error': 'Les identifiants doivent être numériques.'}, status=400)

    maquettes = {m.pk: m for m in _queryset_maquettes().filter(pk__in=ids)}
    introuvables = [identifiant for identifiant in ids if identifiant not in maquettes]
    supprimees = []
    bloquees = []

    for identifiant in ids:
        maquette = maquettes.get(identifiant)
        if maquette is None:
            continue
        motif = _motif_blocage(maquette)
        if motif:
            bloquees.append({'id': identifiant, 'libelle': str(maquette), 'motif': motif})
            continue
        # Savepoint par maquette : une contrainte PROTECT oubliée n'annule pas
        # les suppressions déjà validées du lot.
        try:
            with transaction.atomic():
                libelle = str(maquette)
                maquette.delete()
            supprimees.append({'id': identifiant, 'libelle': libelle})
        except ProtectedError:
            bloquees.append({
                'id': identifiant, 'libelle': str(maquette),
                'motif': 'des données liées protégées empêchent la suppression.',
            })

    if supprimees:
        logger.info(
            'Suppression de %s maquette(s) par %s : %s',
            len(supprimees), request.user,
            ', '.join(str(element['id']) for element in supprimees),
        )

    bilan = {
        'supprimees': supprimees,
        'bloquees': bloquees,
        'introuvables': introuvables,
        'resume': {
            'demandees': len(ids),
            'supprimees': len(supprimees),
            'bloquees': len(bloquees),
            'introuvables': len(introuvables),
        },
    }
    if supprimees:
        return Response(bilan)
    # Rien n'a pu être supprimé : conflit métier explicite, pas une erreur 500.
    bilan['error'] = (
        'Aucune maquette supprimée : '
        + ('maquette(s) introuvable(s).' if not bloquees and introuvables else 'toutes sont bloquées.')
    )
    return Response(bilan, status=409)
