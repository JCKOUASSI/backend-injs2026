"""Phase 5 : façade HTTP expérimentale, isolée des routes GET-INJS historiques.

Seules des années BENCHMARK en DEBUG avec flag explicite sont accessibles.
Une requête ne lance jamais le worker et aucune réponse ne publie un EDT.
"""
from dataclasses import asdict

from django.conf import settings
from django.db import IntegrityError
from django.db.models import ObjectDoesNotExist
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from edts.permissions import IsEdtPlanification, IsEdtReadOnlyOrPlanification
from edts.moteur.planification_v2 import TravailSeance


class BesoinBenchSerializer(serializers.Serializer):
    annee_id = serializers.IntegerField(min_value=1)
    groupe_id = serializers.IntegerField(min_value=1)
    ecue_id = serializers.IntegerField(min_value=0)
    type_seance = serializers.ChoiceField(choices=['CM', 'TD', 'TP', 'EXAM'])
    ordinal = serializers.IntegerField(min_value=1)
    duree_minutes = serializers.IntegerField(min_value=1, max_value=1440)
    effectif = serializers.IntegerField(min_value=1)
    formateur_id = serializers.IntegerField(min_value=1)
    revision = serializers.IntegerField(min_value=1)
    # Ne vaut QUE pour une donnée de test : aucune validation institutionnelle.
    source_confirmee = serializers.BooleanField(default=False)
    source_document = serializers.CharField(max_length=255, allow_blank=True, default='')
    jour = serializers.DateField(required=False)
    graine = serializers.IntegerField(default=0, min_value=0, max_value=2**31 - 1)


class PlacementBenchSerializer(BesoinBenchSerializer):
    creneau_id = serializers.IntegerField(min_value=1)
    salle_id = serializers.IntegerField(min_value=1)
    # Le service revalide la décision sous verrou : ce triplet ne fait pas foi.


def annee_a_occurrences_v2(annee_id):
    """Empêche un ancien moteur de remplacer un plan comportant des QR v2."""
    from edts.models import AffectationCreneau
    return AffectationCreneau.objects.filter(
        emploi_du_temps__annee_academique_id=annee_id,
        cle_occurrence_v2__isnull=False).exists()


def _refus(code, http=status.HTTP_409_CONFLICT):
    return Response({'statut': 'A_REVOIR', 'code': code}, status=http)


def _preparer(request, schema):
    from edts.models import RevisionCalendrier
    from scolarite.models import AnneeAcademique, ECUE, Groupe
    data = schema(data=request.data)
    if not data.is_valid():
        return None, Response(data.errors, status=status.HTTP_400_BAD_REQUEST)
    v = data.validated_data
    if not (settings.DEBUG and getattr(settings, 'GETINJS_V2_EXPERIMENTAL_WRITE', False)):
        return None, _refus('BENCH_V2_DESACTIVE', status.HTTP_403_FORBIDDEN)
    annee = AnneeAcademique.objects.filter(pk=v['annee_id'], libelle__startswith='BENCHMARK-').first()
    if not annee:
        return None, _refus('ANNEE_BENCHMARK_REQUISE')
    if (v.get('jour') and not annee.date_debut <= v['jour'] <= annee.date_fin):
        return None, _refus('DATE_HORS_ANNEE', status.HTTP_400_BAD_REQUEST)
    if not Groupe.objects.filter(pk=v['groupe_id'], annee_academique=annee).exists():
        return None, _refus('GROUPE_HORS_ANNEE', status.HTTP_400_BAD_REQUEST)
    if not RevisionCalendrier.objects.filter(annee_academique=annee, numero=v['revision']).exists():
        return None, _refus('REVISION_INCONNUE', status.HTTP_400_BAD_REQUEST)
    intitule = ''
    if v['ecue_id']:
        intitule = ECUE.objects.filter(pk=v['ecue_id']).values_list(
            'intitule', flat=True,
        ).first()
        if intitule is None:
            return None, _refus('ECUE_INCONNU', status.HTTP_400_BAD_REQUEST)
    champs_travail = {key: v[key] for key in (
        'annee_id', 'groupe_id', 'ecue_id', 'type_seance', 'ordinal',
        'duree_minutes', 'effectif', 'formateur_id', 'source_confirmee',
        'source_document',
    )}
    travail = TravailSeance(**champs_travail, intitule=intitule)
    return (travail, v), None


def _sortie(decision):
    return asdict(decision)


@extend_schema(request=BesoinBenchSerializer, responses={200: OpenApiTypes.OBJECT})
@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def simuler_ligne_api(request):
    """Aucune mutation ; alternatives bornées, signalement explicite des sources."""
    contexte, erreur = _preparer(request, BesoinBenchSerializer)
    if erreur is not None:
        return erreur
    travail, v = contexte
    from edts.moteur.application_v2 import proposer_ligne
    decision = proposer_ligne(travail, revision=v['revision'], graine=v['graine'], jour=v.get('jour'))
    return Response({'simulation': True, 'non_officielle': True, 'decision': _sortie(decision)})


@extend_schema(request=PlacementBenchSerializer, responses={200: OpenApiTypes.OBJECT})
@api_view(['POST'])
@permission_classes([IsEdtPlanification])
def placer_ligne_api(request):
    """Placement manuel BENCH revalidé sous verrou, jamais issu d'une simulation seule."""
    contexte, erreur = _preparer(request, PlacementBenchSerializer)
    if erreur is not None:
        return erreur
    travail, v = contexte
    if not v.get('jour'):
        return _refus('DATE_REQUISE', status.HTTP_400_BAD_REQUEST)
    if not (travail.source_confirmee and travail.source_document.strip()):
        return _refus('VOLUME_NON_CONFIRME')
    from edts.moteur.application_v2 import appliquer_ligne, proposer_ligne
    from edts.moteur.qr_v2 import IntegrationQRBloquee
    from edts.moteur.occupation_v2 import OccupationHeriteeNonResolue
    try:
        from edts.models import AffectationCreneau
        existante = AffectationCreneau.objects.filter(cle_occurrence_v2=travail.cle()).first()
        if existante is not None:
            if not (existante.actif and existante.date_seance == v['jour']
                    and existante.creneau_template_id == v['creneau_id']
                    and existante.salle_id == v['salle_id']):
                return _refus('OCCURRENCE_EXISTANTE_PROTEGEE')
            if existante.formateur_id != travail.formateur_id or existante.revision_calendrier != v['revision']:
                return _refus('ENTREE_MODIFIEE')
            from edts.moteur.occupation_v2 import minute
            slot = existante.creneau_template
            from edts.moteur.planification_v2 import DecisionLigne
            decision = DecisionLigne('PLACEE', 'DEJA_PLACEE', travail.cle(),
                jour=v['jour'], creneau_id=slot.pk, salle_id=v['salle_id'],
                debut=minute(slot.heure_debut), fin=minute(slot.heure_fin))
            resultat = appliquer_ligne(travail, decision, revision=v['revision'], graine=v['graine'])
            return Response({'non_officielle': True, 'decision': _sortie(resultat)})
        decision = proposer_ligne(travail, revision=v['revision'], graine=v['graine'], jour=v['jour'])
        if (decision.statut != 'PLACEE' or (v['jour'], v['creneau_id'], v['salle_id']) not in (
                (decision.jour, decision.creneau_id, decision.salle_id), *decision.alternatives)):
            return _refus('PROPOSITION_EXPIREE', status.HTTP_409_CONFLICT)
        # Une alternative validée emprunte le même chemin d'écriture et sera
        # revérifiée par appliquer_ligne dans sa transaction.
        from dataclasses import replace
        from edts.models import CreneauTemplate
        from edts.moteur.occupation_v2 import minute
        if (v['creneau_id'], v['salle_id']) != (decision.creneau_id, decision.salle_id):
            slot = CreneauTemplate.objects.get(pk=v['creneau_id'])
            decision = replace(decision, creneau_id=slot.pk, salle_id=v['salle_id'],
                               debut=minute(slot.heure_debut), fin=minute(slot.heure_fin))
        resultat = appliquer_ligne(travail, decision, revision=v['revision'], graine=v['graine'])
    except (IntegrationQRBloquee, OccupationHeriteeNonResolue, IntegrityError,
            PermissionError, ValueError, ObjectDoesNotExist):
        return _refus('PLACEMENT_PROTEGE_OU_OBSOLETE')
    return Response({'non_officielle': True, 'decision': _sortie(resultat)},
                    status=status.HTTP_200_OK if resultat.statut == 'PLACEE' else status.HTTP_409_CONFLICT)


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsEdtReadOnlyOrPlanification])
def execution_etat_api(request, pk):
    """Suivi borné et agrégé ; ne lance ni worker ni publication."""
    from edts.models import ExecutionCampagne
    if not (settings.DEBUG and getattr(settings, 'GETINJS_V2_EXPERIMENTAL_WRITE', False)):
        return _refus('BENCH_V2_DESACTIVE', status.HTTP_403_FORBIDDEN)
    execution = (ExecutionCampagne.objects.select_related('campagne__annee_academique')
                 .filter(pk=pk, campagne__annee_academique__libelle__startswith='BENCHMARK-').first())
    if not execution or not execution.statistiques.get('moteur_v2') and execution.version_calendrier is None:
        return _refus('EXECUTION_V2_INTROUVABLE', status.HTTP_404_NOT_FOUND)
    return Response({'id': execution.pk, 'statut': execution.statut,
        'version_calendrier': execution.version_calendrier,
        'lignes_lues': execution.lignes_lues, 'lignes_traitees': execution.lignes_traitees,
        'lignes_placees': execution.lignes_placees, 'lignes_a_revoir': execution.lignes_a_revoir,
        'lignes_echec': execution.lignes_echec, 'heartbeat_le': execution.heartbeat_le,
        'lease_jusqua': execution.lease_jusqua, 'anomalies': execution.anomalies[:100],
        'non_publiable_sans_rapprochement_qr': True})
