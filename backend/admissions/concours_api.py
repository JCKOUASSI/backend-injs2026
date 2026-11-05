"""Lot L2 — API des campagnes et du concours/sélection.

Conventions du projet : vues fonctions ``@api_view``, routes ``path()``
explicites, permissions IsSecretariatOrDFRC (écriture et consultation
staff) — même contrat que les autres endpoints de l'app admissions.
"""
from django.core.exceptions import ValidationError
from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsSecretariatOrDFRC
from scolarite.models import JournalScolarite, journaliser

from . import concours_services
from .models import (
    CampagneAdmission,
    Candidature,
    ClassementConcours,
    ConvocationEpreuve,
    Epreuve,
    NoteConcours,
    SurveillanceEpreuve,
)


def _serializer_campagne(campagne):
    return {
        'id': campagne.id,
        'libelle': campagne.libelle,
        'annee_academique_id': campagne.annee_academique_id,
        'annee_academique': campagne.annee_academique.libelle,
        'ref_formation_id': campagne.ref_formation_id,
        'ref_formation': campagne.ref_formation.intitule,
        'parcours_id': campagne.parcours_id,
        'date_ouverture': campagne.date_ouverture,
        'date_fermeture': campagne.date_fermeture,
        'quota_admissibles': campagne.quota_admissibles,
        'quota_admis': campagne.quota_admis,
        'statut': campagne.statut,
        'statut_libelle': campagne.get_statut_display(),
        'nb_candidatures': campagne.candidatures.count(),
        'nb_epreuves': campagne.epreuves.count(),
        'classement_calcule': campagne.classements.exists(),
        'classement_publie': campagne.classements.filter(publie=True).exists(),
    }


def _serializer_epreuve(epreuve):
    return {
        'id': epreuve.id,
        'campagne_id': epreuve.campagne_id,
        'type': epreuve.type,
        'type_libelle': epreuve.get_type_display(),
        'intitule': epreuve.intitule,
        'date': epreuve.date,
        'heure_debut': epreuve.heure_debut,
        'duree_minutes': epreuve.duree_minutes,
        'centre_id': epreuve.centre_id,
        'centre': epreuve.centre.nom if epreuve.centre_id else None,
        'salle_id': epreuve.salle_id,
        'salle': epreuve.salle.nom if epreuve.salle_id else None,
        'coefficient': epreuve.coefficient,
        'verrouillee': epreuve.verrouillee,
        'nb_convocations': epreuve.convocations.count(),
        'surveillants': [s.surveillant_id for s in epreuve.surveillances.all()],
    }


def _get_campagne(pk):
    return CampagneAdmission.objects.filter(pk=pk).first()


def _get_epreuve(pk):
    return Epreuve.objects.select_related('campagne', 'salle').filter(pk=pk).first()




# ── Contrats OpenAPI (campagnes de concours, épreuves, classements) ──


class ConcoursErreurSerializer(serializers.Serializer):
    error = serializers.JSONField()


class CampagneConcoursReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    libelle = serializers.CharField()
    annee_academique_id = serializers.IntegerField()
    annee_academique = serializers.CharField()
    ref_formation_id = serializers.IntegerField()
    ref_formation = serializers.CharField()
    parcours_id = serializers.IntegerField(allow_null=True)
    date_ouverture = serializers.DateField()
    date_fermeture = serializers.DateField()
    quota_admissibles = serializers.IntegerField()
    quota_admis = serializers.IntegerField()
    statut = serializers.CharField()
    statut_libelle = serializers.CharField()
    nb_candidatures = serializers.IntegerField()
    nb_epreuves = serializers.IntegerField()
    classement_calcule = serializers.BooleanField()
    classement_publie = serializers.BooleanField()


class EpreuveReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    campagne_id = serializers.IntegerField()
    type = serializers.CharField()
    type_libelle = serializers.CharField()
    intitule = serializers.CharField()
    date = serializers.DateField()
    heure_debut = serializers.TimeField(allow_null=True)
    duree_minutes = serializers.IntegerField()
    centre_id = serializers.IntegerField(allow_null=True)
    centre = serializers.CharField(allow_null=True)
    salle_id = serializers.IntegerField(allow_null=True)
    salle = serializers.CharField(allow_null=True)
    coefficient = serializers.DecimalField(max_digits=5, decimal_places=2)
    verrouillee = serializers.BooleanField()
    nb_convocations = serializers.IntegerField()
    surveillants = serializers.ListField(child=serializers.IntegerField())


class DetailConcoursSerializer(serializers.Serializer):
    detail = serializers.CharField()


class SurveillanceCreationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    epreuve_id = serializers.IntegerField()


class ConvocationsGenerationSerializer(serializers.Serializer):
    detail = serializers.CharField()
    creees = serializers.IntegerField()


class VerrouillageEpreuveSerializer(serializers.Serializer):
    detail = serializers.CharField()
    verrouillee = serializers.BooleanField()


class NoteEpreuveReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    note = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    absent = serializers.BooleanField()


class ConvocationPresenceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    presente = serializers.BooleanField()


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: CampagneConcoursReponseSerializer(many=True), 201: CampagneConcoursReponseSerializer, 400: OpenApiTypes.OBJECT})
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def campagne_list(request):
    if request.method == 'GET':
        queryset = CampagneAdmission.objects.select_related(
            'annee_academique', 'ref_formation',
        ).prefetch_related('classements')
        for champ in ('statut', 'annee_academique_id', 'ref_formation_id'):
            if champ in request.query_params:
                queryset = queryset.filter(**{champ: request.query_params[champ]})
        recherche = (request.query_params.get('q') or '').strip()
        if recherche:
            queryset = queryset.filter(
                Q(libelle__icontains=recherche)
                | Q(ref_formation__intitule__icontains=recherche)
            )
        # Chargement explicite (demande du 05/11/2026, écran Résultats
        # concours) : si `page_size` est fourni, réponse paginée bornée à
        # 200 lignes — même convention que le « chargement explicite :
        # 200 événements » du hub Présences. Sans `page_size`, tableau
        # complet comme historiquement (consommé tel quel par l'écran
        # Concours & Sélection) : aucun consommateur existant n'est cassé.
        if 'page_size' in request.query_params:
            try:
                page_size = int(request.query_params.get('page_size') or 50)
            except (TypeError, ValueError):
                page_size = 50
            page_size = max(1, min(page_size, 200))
            try:
                page = max(1, int(request.query_params.get('page') or 1))
            except (TypeError, ValueError):
                page = 1
            total = queryset.count()
            debut = (page - 1) * page_size
            lignes = queryset[debut:debut + page_size]
            return Response({
                'count': total,
                'total_pages': max(1, -(-total // page_size)),
                'page': page,
                'page_size': page_size,
                'results': [_serializer_campagne(c) for c in lignes],
            })
        return Response([_serializer_campagne(c) for c in queryset])

    try:
        campagne = CampagneAdmission(
            libelle=request.data.get('libelle', ''),
            annee_academique_id=request.data.get('annee_academique_id'),
            ref_formation_id=request.data.get('ref_formation_id'),
            parcours_id=request.data.get('parcours_id') or None,
            date_ouverture=request.data.get('date_ouverture') or None,
            date_fermeture=request.data.get('date_fermeture') or None,
            quota_admissibles=request.data.get('quota_admissibles') or None,
            quota_admis=request.data.get('quota_admis') or None,
        )
        campagne.full_clean()
        campagne.save()
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
    journaliser(
        JournalScolarite.Action.CAMPAGNE_CREEE,
        objet=campagne,
        acteur=request.user,
        nouvelle_valeur=campagne.statut,
    )
    return Response(_serializer_campagne(campagne), status=201)


@extend_schema(responses={200: OpenApiTypes.OBJECT, 404: ConcoursErreurSerializer})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def campagne_detail(request, pk):
    """Fiche d'une campagne : propriétés + épreuves (avec convocations)."""
    campagne = _get_campagne(pk)
    if campagne is None:
        return Response({'error': 'Introuvable'}, status=404)
    data = _serializer_campagne(campagne)
    data['epreuves'] = [
        _serializer_epreuve(epreuve)
        for epreuve in campagne.epreuves.select_related('centre', 'salle').prefetch_related(
            'convocations', 'surveillances',
        )
    ]
    return Response(data)


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: CampagneConcoursReponseSerializer, 400: OpenApiTypes.OBJECT, 404: ConcoursErreurSerializer, 409: ConcoursErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def campagne_transition(request, pk):
    """Transition de statut contrôlée par la machine à états de campagne."""
    campagne = _get_campagne(pk)
    if campagne is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        concours_services.appliquer_transition_campagne(
            campagne,
            request.data.get('statut'),
            acteur=request.user,
            commentaire=request.data.get('commentaire', ''),
        )
    except ValidationError as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response(_serializer_campagne(campagne))


@extend_schema(request=OpenApiTypes.OBJECT, responses={201: EpreuveReponseSerializer, 400: OpenApiTypes.OBJECT, 404: ConcoursErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def campagne_epreuve_create(request, pk):
    """Création d'une épreuve rattachée à la campagne."""
    campagne = _get_campagne(pk)
    if campagne is None:
        return Response({'error': 'Introuvable'}, status=404)
    if campagne.statut in (campagne.Statut.CLOTUREE, campagne.Statut.ANNULEE, campagne.Statut.ARCHIVEE):
        return Response({'error': 'Campagne clôturée : épreuves non modifiables.'}, status=400)
    try:
        epreuve = Epreuve(
            campagne=campagne,
            type=request.data.get('type'),
            intitule=request.data.get('intitule', ''),
            date=request.data.get('date'),
            heure_debut=request.data.get('heure_debut'),
            duree_minutes=request.data.get('duree_minutes', 60),
            centre_id=request.data.get('centre_id') or None,
            salle_id=request.data.get('salle_id') or None,
            coefficient=request.data.get('coefficient', 1),
        )
        epreuve.full_clean()
        epreuve.save()
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
    return Response(_serializer_epreuve(epreuve), status=201)


@extend_schema(request=OpenApiTypes.OBJECT, responses={201: SurveillanceCreationSerializer, 400: OpenApiTypes.OBJECT, 404: ConcoursErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def epreuve_surveillant_add(request, pk):
    """Affectation d'un surveillant — chevauchement de sessions refusé."""
    epreuve = _get_epreuve(pk)
    if epreuve is None:
        return Response({'error': 'Introuvable'}, status=404)
    surveillant_id = request.data.get('surveillant_id')
    if not surveillant_id:
        return Response({'error': 'surveillant_id requis.'}, status=400)
    surveillance = SurveillanceEpreuve(epreuve=epreuve, surveillant_id=surveillant_id)
    try:
        surveillance.full_clean()
        surveillance.save()
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
    return Response({'id': surveillance.id, 'epreuve_id': epreuve.id}, status=201)


@extend_schema(request=None, responses={200: ConvocationsGenerationSerializer, 404: ConcoursErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def epreuve_convocations_generer(request, pk):
    """Génération des convocations (respect de la capacité de salle)."""
    epreuve = _get_epreuve(pk)
    if epreuve is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        crees = concours_services.generer_convocations(epreuve, utilisateur=request.user)
    except ValidationError as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response({'detail': f'{crees} convocation(s) créée(s).', 'crees': crees})


@extend_schema(request=None, responses={200: VerrouillageEpreuveSerializer, 400: OpenApiTypes.OBJECT, 404: ConcoursErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def epreuve_verrouiller(request, pk):
    """Verrouille les résultats de l'épreuve — les notes ne sont plus modifiables."""
    epreuve = _get_epreuve(pk)
    if epreuve is None:
        return Response({'error': 'Introuvable'}, status=404)
    concours_services.verrouiller_epreuve(epreuve, utilisateur=request.user)
    return Response({'detail': 'Épreuve verrouillée.', 'verrouillee': True})


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT, 201: NoteEpreuveReponseSerializer, 400: OpenApiTypes.OBJECT, 404: ConcoursErreurSerializer})
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def epreuve_notes(request, pk):
    """Consultation et saisie des notes — écriture refusée si épreuve verrouillée."""
    epreuve = _get_epreuve(pk)
    if epreuve is None:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'GET':
        notes = NoteConcours.objects.filter(epreuve=epreuve).select_related('candidature')
        return Response([
            {
                'id': n.id,
                'candidature_id': n.candidature_id,
                'candidature': n.candidature.numero,
                'note': n.note,
                'absent': n.absent,
            }
            for n in notes
        ])
    candidature = Candidature.objects.filter(pk=request.data.get('candidature_id')).first()
    if candidature is None:
        return Response({'error': 'Candidature introuvable.'}, status=400)
    try:
        note = concours_services.enregistrer_note(
            epreuve, candidature,
            utilisateur=request.user,
            note=request.data.get('note'),
            absent=bool(request.data.get('absent')),
        )
    except ValidationError as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response({'id': note.id, 'note': note.note, 'absent': note.absent}, status=201)


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: ConvocationPresenceSerializer, 400: OpenApiTypes.OBJECT, 404: ConcoursErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def convocation_presence(request, pk):
    """Enregistre la présence d'un candidat convoqué."""
    convocation = ConvocationEpreuve.objects.select_related('epreuve').filter(pk=pk).first()
    if convocation is None:
        return Response({'error': 'Introuvable'}, status=404)
    convocation.presente = bool(request.data.get('presente', True))
    convocation.save(update_fields=['presente'])
    return Response({'id': convocation.id, 'presente': convocation.presente})


@extend_schema(responses={200: OpenApiTypes.OBJECT, 404: ConcoursErreurSerializer})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def campagne_classement(request, pk):
    """Liste du classement de la campagne (rang, score, liste)."""
    campagne = _get_campagne(pk)
    if campagne is None:
        return Response({'error': 'Introuvable'}, status=404)
    classement = ClassementConcours.objects.filter(
        campagne=campagne,
    ).select_related('candidature', 'candidature__candidat')
    return Response([
        {
            'rang': c.rang,
            'candidature_id': c.candidature_id,
            'candidature': c.candidature.numero,
            'candidat': c.candidature.candidat.nom_complet,
            'score_total': c.score_total,
            'liste': c.liste,
            'liste_libelle': c.get_liste_display(),
            'publie': c.publie,
        }
        for c in classement
    ])


@extend_schema(request=None, responses={200: DetailConcoursSerializer, 400: ConcoursErreurSerializer, 404: ConcoursErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def campagne_classement_calculer(request, pk):
    """Calcul reproductible du classement (refusé si déjà publié)."""
    campagne = _get_campagne(pk)
    if campagne is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        lignes = concours_services.calculer_classement(campagne, utilisateur=request.user)
    except ValidationError as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response({'detail': f'{len(lignes)} ligne(s) de classement.'}, status=200)


@extend_schema(request=None, responses={200: OpenApiTypes.OBJECT, 400: ConcoursErreurSerializer, 404: ConcoursErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def campagne_classement_publier(request, pk):
    """Publication des listes d'admissibilité — plus de recalcul ensuite."""
    campagne = _get_campagne(pk)
    if campagne is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        concours_services.publier_classement(campagne, utilisateur=request.user)
    except ValidationError as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response({'detail': 'Classement publié.'})
    data['epreuves'] = [_serializer_epreuve(e) for e in campagne.epreuves.all()]
    return Response(data)