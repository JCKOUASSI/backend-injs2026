"""Lot L3/L7 — API des charges pédagogiques des enseignants.

Endpoints sous ``/api/enseignants/`` : résumé de charge, affectations
(création/édition/transition), indisponibilités, anomalies, rapports
d'occupation. Ne touche pas à la paie formateurs (FinanceSettings /
FinanceAjustement).
"""
from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsSecretariatOrDFRC
from formations.models import Formateur

from scolarite import charges_services
from scolarite.models import (
    AffectationPedagogique,
    AnneeAcademique,
    IndisponibiliteEnseignant,
)


def _get_annee(pk):
    if not pk or str(pk).lower() in ('undefined', 'null'):
        return AnneeAcademique.courante_ou_none()
    try:
        return AnneeAcademique.objects.filter(pk=int(pk)).first()
    except (ValueError, TypeError):
        return None


def _get_enseignant(pk):
    return Formateur.objects.filter(pk=pk).first()


def _serializer_affectation(affectation):
    return {
        'id': affectation.id,
        'annee_academique_id': affectation.annee_academique_id,
        'ref_formation_id': affectation.ref_formation_id,
        'parcours_id': affectation.parcours_id,
        'niveau_id': affectation.niveau_id,
        'semestre_id': affectation.semestre_id,
        'ue_id': affectation.ue_id,
        'ecue_id': affectation.ecue_id,
        'ecue': str(affectation.ecue) if affectation.ecue_id else None,
        'groupe_id': affectation.groupe_id,
        'enseignant_id': affectation.enseignant_id,
        'enseignant': str(affectation.enseignant),
        'type_enseignement': affectation.type_enseignement,
        'volume_horaire': affectation.volume_horaire,
        'date_debut': affectation.date_debut,
        'date_fin': affectation.date_fin,
        'statut': affectation.statut,
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def charge_enseignant(request, enseignant_id):
    """Résumé des charges (prévue/affectée/planifiée/réalisée) pour une année."""
    enseignant = _get_enseignant(enseignant_id)
    if enseignant is None:
        return Response({'error': 'Enseignant introuvable.'}, status=404)
    annee = _get_annee(request.query_params.get('annee_id'))
    if annee is None:
        return Response({'error': 'Année académique inconnue (annee_id).'}, status=400)
    return Response(charges_services.charge_enseignant(enseignant, annee))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def affectation_list(request):
    if request.method == 'GET':
        queryset = AffectationPedagogique.objects.select_related(
            'annee_academique', 'ecue__ue__maquette', 'ue', 'groupe', 'enseignant',
        )
        for champ in ('annee_academique_id', 'enseignant_id', 'statut', 'ecue_id'):
            if champ in request.query_params:
                queryset = queryset.filter(**{champ: request.query_params[champ]})
        return Response([_serializer_affectation(a) for a in queryset[:500]])

    try:
        affectation = AffectationPedagogique(
            annee_academique_id=request.data.get('annee_academique_id'),
            ref_formation_id=request.data.get('ref_formation_id'),
            parcours_id=request.data.get('parcours_id') or None,
            niveau_id=request.data.get('niveau_id'),
            semestre_id=request.data.get('semestre_id'),
            ue_id=request.data.get('ue_id') or None,
            ecue_id=request.data.get('ecue_id') or None,
            groupe_id=request.data.get('groupe_id') or None,
            enseignant_id=request.data.get('enseignant_id'),
            type_enseignement=request.data.get('type_enseignement', 'CM'),
            volume_horaire=request.data.get('volume_horaire', 0),
            date_debut=request.data.get('date_debut') or None,
            date_fin=request.data.get('date_fin') or None,
            observations=request.data.get('observations', ''),
        )
        affectation.full_clean()
        affectation.save()
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
    return Response(_serializer_affectation(affectation), status=201)


@api_view(['PATCH', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def affectation_detail(request, pk):
    """Édition (non annulée) et transition de statut d'une affectation."""
    affectation = AffectationPedagogique.objects.filter(pk=pk).first()
    if affectation is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        if request.method == 'POST':
            nouveau_statut = request.data.get('statut')
            if nouveau_statut not in AffectationPedagogique.Statut.values:
                return Response({'error': 'Statut inconnu.'}, status=400)
            affectation.statut = nouveau_statut
        else:
            for champ in ('type_enseignement', 'volume_horaire', 'date_debut',
                          'date_fin', 'observations', 'groupe_id'):
                if champ in request.data:
                    setattr(affectation, champ, request.data[champ] or None)
        affectation.full_clean()
        affectation.save()
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
    return Response(_serializer_affectation(affectation))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def indisponibilite_list(request):
    if request.method == 'GET':
        queryset = IndisponibiliteEnseignant.objects.select_related('enseignant')
        if 'enseignant_id' in request.query_params:
            queryset = queryset.filter(enseignant_id=request.query_params['enseignant_id'])
        return Response([
            {
                'id': i.id, 'enseignant_id': i.enseignant_id,
                'enseignant': str(i.enseignant),
                'date_debut': i.date_debut, 'date_fin': i.date_fin, 'motif': i.motif,
            }
            for i in queryset
        ])
    try:
        indisponibilite = IndisponibiliteEnseignant(
            enseignant_id=request.data.get('enseignant_id'),
            date_debut=request.data.get('date_debut'),
            date_fin=request.data.get('date_fin'),
            motif=request.data.get('motif', ''),
        )
        indisponibilite.full_clean()
        indisponibilite.save()
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
    return Response({'id': indisponibilite.id}, status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def anomalies_list(request):
    """Rapport des anomalies de charge pour une année (L3)."""
    annee = _get_annee(request.query_params.get('annee_id'))
    if annee is None:
        return Response({'error': 'Année académique inconnue (annee_id).'}, status=400)
    return Response({'annee': annee.libelle, 'anomalies': charges_services.anomalies(annee)})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def occupation_report(request):
    """Rapport d'occupation par enseignant pour une année."""
    annee = _get_annee(request.query_params.get('annee_id'))
    if annee is None:
        return Response({'error': 'Année académique inconnue (annee_id).'}, status=400)
    return Response({'annee': annee.libelle,
                     'occupation': charges_services.occupation_par_enseignant(annee)})
