"""Lot L2 — API des campagnes et du concours/sélection.

Conventions du projet : vues fonctions ``@api_view``, routes ``path()``
explicites, permissions IsSecretariatOrDFRC (écriture et consultation
staff) — même contrat que les autres endpoints de l'app admissions.
"""
from django.core.exceptions import ValidationError
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
        'ref_formation_id': campagne.ref_formation_id,
        'parcours_id': campagne.parcours_id,
        'date_ouverture': campagne.date_ouverture,
        'date_fermeture': campagne.date_fermeture,
        'quota_admissibles': campagne.quota_admissibles,
        'quota_admis': campagne.quota_admis,
        'statut': campagne.statut,
        'nb_candidatures': campagne.candidatures.count(),
        'nb_epreuves': campagne.epreuves.count(),
    }


def _serializer_epreuve(epreuve):
    return {
        'id': epreuve.id,
        'campagne_id': epreuve.campagne_id,
        'type': epreuve.type,
        'intitule': epreuve.intitule,
        'date': epreuve.date,
        'heure_debut': epreuve.heure_debut,
        'duree_minutes': epreuve.duree_minutes,
        'centre_id': epreuve.centre_id,
        'salle_id': epreuve.salle_id,
        'coefficient': epreuve.coefficient,
        'verrouillee': epreuve.verrouillee,
        'nb_convocations': epreuve.convocations.count(),
        'surveillants': [s.surveillant_id for s in epreuve.surveillances.all()],
    }


def _get_campagne(pk):
    return CampagneAdmission.objects.filter(pk=pk).first()


def _get_epreuve(pk):
    return Epreuve.objects.select_related('campagne', 'salle').filter(pk=pk).first()


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def campagne_list(request):
    if request.method == 'GET':
        queryset = CampagneAdmission.objects.select_related(
            'annee_academique', 'ref_formation',
        )
        for champ in ('statut', 'annee_academique_id', 'ref_formation_id'):
            if champ in request.query_params:
                queryset = queryset.filter(**{champ: request.query_params[champ]})
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


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def campagne_detail(request, pk):
    campagne = _get_campagne(pk)
    if campagne is None:
        return Response({'error': 'Introuvable'}, status=404)
    data = _serializer_campagne(campagne)


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


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def epreuve_verrouiller(request, pk):
    """Verrouille les résultats de l'épreuve — les notes ne sont plus modifiables."""
    epreuve = _get_epreuve(pk)
    if epreuve is None:
        return Response({'error': 'Introuvable'}, status=404)
    concours_services.verrouiller_epreuve(epreuve, utilisateur=request.user)
    return Response({'detail': 'Épreuve verrouillée.', 'verrouillee': True})


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
            'publie': c.publie,
        }
        for c in classement
    ])


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