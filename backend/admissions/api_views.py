"""API des candidatures, pièces justificatives et référentiels d'admission."""

from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsDFRC, IsSecretariatOrDFRC

from . import admission_services, services, workflow
from .models import (
    Admission,
    Candidat,
    Candidature,
    PieceCandidature,
    ReglePiece,
    TypeCandidature,
    TypePiece,
    VoieAcces,
)

REFERENTIEL_FIELDS = {
    'types-candidature': (TypeCandidature, ['id', 'code', 'libelle', 'actif']),
    'voies-acces': (VoieAcces, ['id', 'code', 'libelle', 'actif']),
    'types-piece': (
        TypePiece,
        ['id', 'code', 'libelle', 'obligatoire_par_defaut', 'avec_date_expiration', 'actif'],
    ),
    'regles-pieces': (
        ReglePiece,
        ['id', 'type_piece_id', 'type_formation_id', 'ref_formation_id', 'obligatoire'],
    ),
}


def _payload(fields, data):
    valeurs = {}
    for champ in fields:
        if champ == 'id' or champ not in data:
            continue
        valeur = data[champ]
        valeurs[champ] = None if valeur == '' and champ.endswith('_id') else valeur
    return valeurs




# ── Contrats OpenAPI (candidats, candidatures, admissions) ───────────


class AdmissionErreurSerializer(serializers.Serializer):
    error = serializers.JSONField()


class CandidatReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    uuid = serializers.CharField()
    nom = serializers.CharField()
    prenom = serializers.CharField()
    nom_complet = serializers.CharField()
    sexe = serializers.CharField()
    date_naissance = serializers.DateField(allow_null=True)
    lieu_naissance = serializers.CharField()
    nationalite = serializers.CharField()
    email = serializers.CharField()
    telephone = serializers.CharField()
    telephone2 = serializers.CharField()
    adresse = serializers.CharField()
    participant_id = serializers.IntegerField(allow_null=True)


class PieceReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type_piece_id = serializers.IntegerField()
    type_piece = serializers.CharField()
    obligatoire = serializers.BooleanField()
    statut = serializers.CharField()
    statut_libelle = serializers.CharField()
    a_fichier = serializers.BooleanField()
    numero_document = serializers.CharField()
    date_delivrance = serializers.DateField(allow_null=True)
    date_expiration = serializers.DateField(allow_null=True)
    est_expiree = serializers.BooleanField()
    commentaire = serializers.CharField()
    verifie_par = serializers.CharField(allow_null=True)
    verifie_le = serializers.DateTimeField(allow_null=True)


class CandidatureReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    numero = serializers.CharField()
    candidat_id = serializers.IntegerField()
    candidat = serializers.CharField()
    annee_academique_id = serializers.IntegerField()
    annee_academique = serializers.CharField()
    ref_formation_id = serializers.IntegerField()
    ref_formation = serializers.CharField()
    campagne_id = serializers.IntegerField(allow_null=True)
    campagne = serializers.CharField(allow_null=True)
    parcours_id = serializers.IntegerField(allow_null=True)
    niveau_id = serializers.IntegerField()
    niveau = serializers.CharField()
    statut = serializers.CharField()
    statut_libelle = serializers.CharField()
    date_candidature = serializers.DateTimeField()
    score = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    pieces_validees = serializers.IntegerField()
    pieces_obligatoires = serializers.IntegerField()
    taux_completude = serializers.FloatField()
    dossier_complet = serializers.BooleanField()


class CandidatureDetailSerializer(CandidatureReponseSerializer):
    type_candidature_id = serializers.IntegerField(allow_null=True)
    voie_acces_id = serializers.IntegerField(allow_null=True)
    regime_id = serializers.IntegerField(allow_null=True)
    vague_id = serializers.IntegerField(allow_null=True)
    observations = serializers.CharField()
    date_decision = serializers.DateTimeField(allow_null=True)
    decide_par = serializers.CharField(allow_null=True)
    transitions_possibles = serializers.JSONField()
    pieces = PieceReponseSerializer(many=True)


class PiecesCandidatureSerializer(serializers.Serializer):
    pieces = PieceReponseSerializer(many=True)
    pieces_validees = serializers.IntegerField()
    pieces_obligatoires = serializers.IntegerField()
    taux_completude = serializers.FloatField()
    dossier_complet = serializers.BooleanField()


class AdmissionReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    candidature_id = serializers.IntegerField()
    candidature_numero = serializers.CharField()
    candidat_id = serializers.IntegerField()
    candidat = serializers.CharField()
    annee_academique_id = serializers.IntegerField()
    annee_academique = serializers.CharField()
    ref_formation_id = serializers.IntegerField()
    ref_formation = serializers.CharField()
    parcours_id = serializers.IntegerField(allow_null=True)
    niveau_id = serializers.IntegerField()
    niveau = serializers.CharField()
    vague_id = serializers.IntegerField(allow_null=True)
    categorie_id = serializers.IntegerField(allow_null=True)
    grade_id = serializers.IntegerField(allow_null=True)
    voie_acces_id = serializers.IntegerField(allow_null=True)
    decision = serializers.CharField()
    decision_libelle = serializers.CharField()
    date_decision = serializers.DateTimeField(allow_null=True)
    reference_decision = serializers.CharField()
    date_limite_inscription = serializers.DateField(allow_null=True)
    est_expiree = serializers.BooleanField()
    permet_inscription = serializers.BooleanField()
    observations = serializers.CharField()
    decide_par = serializers.CharField(allow_null=True)
    inscrit = serializers.BooleanField()
    matricule = serializers.CharField(allow_null=True)
    etudiant_id = serializers.IntegerField(allow_null=True)
    inscription_statut = serializers.CharField(allow_null=True)


class StatsRepartitionSerializer(serializers.Serializer):
    total = serializers.IntegerField()


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: AdmissionErreurSerializer})
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def referentiel_list(request, ressource):
    if ressource not in REFERENTIEL_FIELDS:
        return Response({'error': 'Référentiel inconnu'}, status=404)
    model, fields = REFERENTIEL_FIELDS[ressource]
    if request.method == 'GET':
        return Response(list(model.objects.values(*fields)))
    obj = model(**_payload(fields, request.data))
    try:
        obj.full_clean()
    except ValidationError as erreur:
        return Response(erreur.message_dict, status=400)
    obj.save()
    return Response(model.objects.filter(pk=obj.pk).values(*fields).first(), status=201)


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT, 204: None, 400: OpenApiTypes.OBJECT, 404: AdmissionErreurSerializer, 409: AdmissionErreurSerializer})
@api_view(['PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsDFRC])
def referentiel_detail(request, ressource, pk):
    if ressource not in REFERENTIEL_FIELDS:
        return Response({'error': 'Référentiel inconnu'}, status=404)
    model, fields = REFERENTIEL_FIELDS[ressource]
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'DELETE':
        obj.delete()
        return Response(status=204)
    for champ, valeur in _payload(fields, request.data).items():
        setattr(obj, champ, valeur)
    try:
        obj.full_clean()
    except ValidationError as erreur:
        return Response(erreur.message_dict, status=400)
    obj.save()
    return Response(model.objects.filter(pk=obj.pk).values(*fields).first())


# ── Candidats ───────────────────────────────────────────────────────────────

CANDIDAT_FIELDS = [
    'nom', 'prenom', 'sexe', 'date_naissance', 'lieu_naissance', 'nationalite',
    'email', 'telephone', 'telephone2', 'adresse',
]


def _serialize_candidat(candidat):
    return {
        'id': candidat.id,
        'uuid': str(candidat.uuid),
        'nom': candidat.nom,
        'prenom': candidat.prenom,
        'nom_complet': candidat.nom_complet,
        'sexe': candidat.sexe,
        'date_naissance': candidat.date_naissance,
        'lieu_naissance': candidat.lieu_naissance,
        'nationalite': candidat.nationalite,
        'email': candidat.email,
        'telephone': candidat.telephone,
        'telephone2': candidat.telephone2,
        'adresse': candidat.adresse,
        'participant_id': candidat.participant_id,
    }


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: CandidatReponseSerializer(many=True), 201: CandidatReponseSerializer, 400: OpenApiTypes.OBJECT})
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def candidat_list(request):
    if request.method == 'GET':
        queryset = Candidat.objects.all()
        recherche = request.query_params.get('q')
        if recherche:
            queryset = queryset.filter(
                Q(nom__icontains=recherche)
                | Q(prenom__icontains=recherche)
                | Q(email__icontains=recherche)
                | Q(telephone__icontains=recherche)
            )
        return Response([_serialize_candidat(c) for c in queryset[:200]])

    candidat = Candidat(**{k: v for k, v in request.data.items() if k in CANDIDAT_FIELDS})
    try:
        candidat.full_clean()
    except ValidationError as erreur:
        return Response(erreur.message_dict, status=400)
    candidat.save()
    return Response(_serialize_candidat(candidat), status=201)


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: CandidatReponseSerializer, 400: OpenApiTypes.OBJECT, 404: AdmissionErreurSerializer})
@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def candidat_detail(request, pk):
    candidat = Candidat.objects.filter(pk=pk).first()
    if candidat is None:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PATCH':
        for champ in CANDIDAT_FIELDS:
            if champ in request.data:
                setattr(candidat, champ, request.data[champ])
        try:
            candidat.full_clean()
        except ValidationError as erreur:
            return Response(erreur.message_dict, status=400)
        candidat.save()
    return Response(_serialize_candidat(candidat))


# ── Candidatures ────────────────────────────────────────────────────────────

CANDIDATURE_FIELDS = [
    'annee_academique_id', 'ref_formation_id', 'parcours_id', 'niveau_id',
    'type_candidature_id', 'voie_acces_id', 'regime_id', 'vague_id',
    'date_candidature', 'score', 'observations', 'campagne_id',
]


def _serialize_candidature(candidature, detail=False):
    validees, total = candidature.completude
    data = {
        'id': candidature.id,
        'numero': candidature.numero,
        'candidat_id': candidature.candidat_id,
        'candidat': candidature.candidat.nom_complet,
        'annee_academique_id': candidature.annee_academique_id,
        'annee_academique': candidature.annee_academique.libelle,
        'ref_formation_id': candidature.ref_formation_id,
        'ref_formation': candidature.ref_formation.intitule,
        'campagne_id': candidature.campagne_id,
        'campagne': candidature.campagne.libelle if candidature.campagne_id else None,
        'parcours_id': candidature.parcours_id,
        'niveau_id': candidature.niveau_id,
        'niveau': candidature.niveau.code,
        'statut': candidature.statut,
        'statut_libelle': candidature.get_statut_display(),
        'date_candidature': candidature.date_candidature,
        'score': candidature.score,
        'pieces_validees': validees,
        'pieces_obligatoires': total,
        'taux_completude': candidature.taux_completude,
        'dossier_complet': candidature.dossier_complet,
    }
    if detail:
        data.update({
            'type_candidature_id': candidature.type_candidature_id,
            'voie_acces_id': candidature.voie_acces_id,
            'regime_id': candidature.regime_id,
            'vague_id': candidature.vague_id,
            'observations': candidature.observations,
            'date_decision': candidature.date_decision,
            'decide_par': candidature.decide_par.username if candidature.decide_par else None,
            'transitions_possibles': workflow.transitions_possibles(candidature),
            'pieces': [_serialize_piece(p) for p in candidature.pieces.select_related('type_piece')],
        })
    return data


def _candidature_queryset():
    return Candidature.objects.select_related(
        'candidat', 'annee_academique', 'ref_formation', 'niveau', 'decide_par',
    ).prefetch_related('pieces')


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: CandidatureReponseSerializer(many=True), 201: CandidatureDetailSerializer, 400: OpenApiTypes.OBJECT})
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def candidature_list(request):
    if request.method == 'GET':
        queryset = _candidature_queryset()
        for champ in ('statut', 'annee_academique_id', 'ref_formation_id', 'niveau_id', 'candidat_id'):
            if champ in request.query_params:
                queryset = queryset.filter(**{champ: request.query_params[champ]})
        recherche = request.query_params.get('q')
        if recherche:
            queryset = queryset.filter(
                Q(numero__icontains=recherche)
                | Q(candidat__nom__icontains=recherche)
                | Q(candidat__prenom__icontains=recherche)
            )
        # Chargement explicite (extension de la série, 05/11/2026) : si
        # `page_size` est fourni, réponse paginée bornée à 200 lignes —
        # même convention que les écrans Campagnes / Équivalences. Sans
        # `page_size`, tableau complet historique (plafond 500) inchangé.
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
                'results': [_serialize_candidature(c) for c in lignes],
            })
        return Response([_serialize_candidature(c) for c in queryset[:500]])

    candidat = Candidat.objects.filter(pk=request.data.get('candidat_id')).first()
    if candidat is None:
        return Response({'candidat_id': ['Candidat introuvable.']}, status=400)
    try:
        candidature = services.creer_candidature(
            candidat,
            acteur=request.user,
            **{k: v for k, v in request.data.items() if k in CANDIDATURE_FIELDS},
        )
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
    return Response(_serialize_candidature(candidature, detail=True), status=201)


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: CandidatureDetailSerializer, 400: OpenApiTypes.OBJECT, 404: AdmissionErreurSerializer})
@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def candidature_detail(request, pk):
    candidature = _candidature_queryset().filter(pk=pk).first()
    if candidature is None:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PATCH':
        # Le statut ne se modifie que par la machine à états.
        for champ in CANDIDATURE_FIELDS:
            if champ in request.data:
                setattr(candidature, champ, request.data[champ])
        try:
            candidature.full_clean(exclude=['numero'])
        except ValidationError as erreur:
            return Response(erreur.message_dict, status=400)
        candidature.save()
    return Response(_serialize_candidature(candidature, detail=True))


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: CandidatureDetailSerializer, 400: OpenApiTypes.OBJECT, 404: AdmissionErreurSerializer, 409: AdmissionErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def candidature_transition(request, pk):
    """Applique une transition de statut contrôlée par la machine à états."""
    candidature = _candidature_queryset().filter(pk=pk).first()
    if candidature is None:
        return Response({'error': 'Introuvable'}, status=404)
    nouveau_statut = request.data.get('statut')
    if nouveau_statut not in Candidature.Statut.values:
        return Response({'statut': ['Statut inconnu.']}, status=400)
    try:
        workflow.appliquer_transition(
            candidature,
            nouveau_statut,
            acteur=request.user,
            commentaire=request.data.get('commentaire', ''),
            forcer_dossier=bool(request.data.get('forcer_dossier')),
        )
    except workflow.TransitionInterdite as erreur:
        return Response({'error': erreur.messages[0]}, status=409)
    return Response(_serialize_candidature(candidature, detail=True))


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def candidature_stats(request):
    """Répartition des candidatures par statut, pour le tableau de bord scolarité."""
    queryset = Candidature.objects.all()
    if 'annee_academique_id' in request.query_params:
        queryset = queryset.filter(annee_academique_id=request.query_params['annee_academique_id'])
    repartition = {
        ligne['statut']: ligne['total']
        for ligne in queryset.values('statut').annotate(total=Count('id'))
    }
    return Response({
        'total': sum(repartition.values()),
        'par_statut': repartition,
    })


# ── Pièces justificatives ───────────────────────────────────────────────────

def _serialize_piece(piece):
    return {
        'id': piece.id,
        'type_piece_id': piece.type_piece_id,
        'type_piece': piece.type_piece.libelle,
        'obligatoire': piece.obligatoire,
        'statut': piece.statut,
        'statut_libelle': piece.get_statut_display(),
        'a_fichier': bool(piece.fichier),
        'numero_document': piece.numero_document,
        'date_delivrance': piece.date_delivrance,
        'date_expiration': piece.date_expiration,
        'est_expiree': piece.est_expiree,
        'commentaire': piece.commentaire,
        'verifie_par': piece.verifie_par.username if piece.verifie_par else None,
        'verifie_le': piece.verifie_le,
    }


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: PiecesCandidatureSerializer, 201: PieceReponseSerializer, 400: OpenApiTypes.OBJECT, 404: AdmissionErreurSerializer})
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def candidature_pieces(request, pk):
    candidature = Candidature.objects.filter(pk=pk).first()
    if candidature is None:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'POST':
        services.initialiser_pieces(candidature, acteur=request.user)
    services.rafraichir_pieces_expirees(candidature)
    pieces = candidature.pieces.select_related('type_piece', 'verifie_par')
    validees, total = candidature.completude
    return Response({
        'pieces': [_serialize_piece(p) for p in pieces],
        'pieces_validees': validees,
        'pieces_obligatoires': total,
        'taux_completude': candidature.taux_completude,
        'dossier_complet': candidature.dossier_complet,
    })


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: PieceReponseSerializer, 400: OpenApiTypes.OBJECT, 404: AdmissionErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
@parser_classes([MultiPartParser, FormParser])
def piece_deposer(request, piece_id):
    piece = PieceCandidature.objects.select_related('candidature', 'type_piece').filter(pk=piece_id).first()
    if piece is None:
        return Response({'error': 'Introuvable'}, status=404)
    champs = {
        champ: request.data[champ]
        for champ in ('numero_document', 'date_delivrance', 'date_expiration')
        if request.data.get(champ)
    }
    services.deposer_piece(piece, fichier=request.FILES.get('fichier'), acteur=request.user, **champs)
    return Response(_serialize_piece(piece))


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: PieceReponseSerializer, 400: OpenApiTypes.OBJECT, 404: AdmissionErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def piece_verifier(request, piece_id):
    piece = PieceCandidature.objects.select_related('candidature', 'type_piece').filter(pk=piece_id).first()
    if piece is None:
        return Response({'error': 'Introuvable'}, status=404)
    statut = request.data.get('statut')
    if statut not in PieceCandidature.Statut.values:
        return Response({'statut': ['Statut inconnu.']}, status=400)
    services.verifier_piece(
        piece, statut, acteur=request.user, commentaire=request.data.get('commentaire', ''),
    )
    return Response(_serialize_piece(piece))


# ── Admissions ──────────────────────────────────────────────────────────────

ADMISSION_CHAMPS_CREATION = [
    'niveau_id', 'parcours_id', 'vague_id', 'categorie_id', 'grade_id', 'voie_acces_id',
    'reference_decision', 'date_limite_inscription', 'observations',
]


def _serialize_admission(admission):
    data = {
        'id': admission.id,
        'candidature_id': admission.candidature_id,
        'candidature_numero': admission.candidature.numero,
        'candidat_id': admission.candidat_id,
        'candidat': admission.candidat.nom_complet,
        'annee_academique_id': admission.annee_academique_id,
        'annee_academique': admission.annee_academique.libelle,
        'ref_formation_id': admission.ref_formation_id,
        'ref_formation': admission.ref_formation.intitule,
        'parcours_id': admission.parcours_id,
        'niveau_id': admission.niveau_id,
        'niveau': admission.niveau.code,
        'vague_id': admission.vague_id,
        'categorie_id': admission.categorie_id,
        'grade_id': admission.grade_id,
        'voie_acces_id': admission.voie_acces_id,
        'decision': admission.decision,
        'decision_libelle': admission.get_decision_display(),
        'date_decision': admission.date_decision,
        'reference_decision': admission.reference_decision,
        'date_limite_inscription': admission.date_limite_inscription,
        'est_expiree': admission.est_expiree,
        'permet_inscription': admission.permet_inscription,
        'observations': admission.observations,
        'decide_par': admission.decide_par.username if admission.decide_par else None,
    }
    inscription = _inscription_active(admission)
    data.update({
        'inscrit': inscription is not None,
        'matricule': inscription.etudiant.matricule if inscription else None,
        'etudiant_id': inscription.etudiant_id if inscription else None,
        'inscription_statut': inscription.get_statut_display() if inscription else None,
    })
    return data


def _inscription_active(admission):
    """Inscription vivante issue de l'admission (hors annulées/rejetées)."""
    for inscription in admission.inscriptions.all():
        if inscription.statut not in ('ANNULEE', 'REJETEE'):
            return inscription
    return None


def _admission_queryset():
    return Admission.objects.select_related(
        'candidature', 'candidat', 'annee_academique', 'ref_formation', 'niveau', 'decide_par',
    ).prefetch_related('inscriptions__etudiant')


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: AdmissionReponseSerializer(many=True), 201: AdmissionReponseSerializer, 400: OpenApiTypes.OBJECT, 409: AdmissionErreurSerializer})
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def admission_list(request):
    if request.method == 'GET':
        queryset = _admission_queryset()
        for champ in ('decision', 'annee_academique_id', 'ref_formation_id', 'niveau_id', 'candidat_id'):
            if champ in request.query_params:
                queryset = queryset.filter(**{champ: request.query_params[champ]})
        recherche = (request.query_params.get('q') or '').strip()
        if recherche:
            queryset = queryset.filter(
                Q(candidat__nom__icontains=recherche)
                | Q(candidat__prenom__icontains=recherche)
                | Q(candidature__numero__icontains=recherche)
                | Q(reference_decision__icontains=recherche)
            )
        return Response([_serialize_admission(a) for a in queryset[:500]])

    candidature = Candidature.objects.select_related(
        'candidat', 'annee_academique', 'ref_formation', 'niveau',
    ).filter(pk=request.data.get('candidature_id')).first()
    if candidature is None:
        return Response({'candidature_id': ['Candidature introuvable.']}, status=400)
    champs = {
        champ: request.data[champ]
        for champ in ADMISSION_CHAMPS_CREATION
        if request.data.get(champ) not in (None, '')
    }
    try:
        admission = admission_services.creer_admission(candidature, acteur=request.user, **champs)
    except admission_services.AdmissionImpossible as erreur:
        return Response({'error': erreur.messages[0]}, status=409)
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
    return Response(_serialize_admission(admission), status=201)


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: AdmissionReponseSerializer, 400: OpenApiTypes.OBJECT, 404: AdmissionErreurSerializer})
@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def admission_detail(request, pk):
    admission = _admission_queryset().filter(pk=pk).first()
    if admission is None:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PATCH':
        # La décision ne se modifie que par l'endpoint dédié.
        for champ in ADMISSION_CHAMPS_CREATION:
            if champ in request.data:
                setattr(admission, champ, request.data[champ] or None)
        try:
            admission.full_clean()
        except ValidationError as erreur:
            return Response(erreur.message_dict, status=400)
        admission.save()
    return Response(_serialize_admission(admission))


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: AdmissionReponseSerializer, 400: OpenApiTypes.OBJECT, 404: AdmissionErreurSerializer, 409: AdmissionErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def admission_decision(request, pk):
    """Prononce la décision d'admission et aligne le statut de la candidature."""
    admission = _admission_queryset().filter(pk=pk).first()
    if admission is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        admission_services.prononcer_decision(
            admission,
            request.data.get('decision'),
            acteur=request.user,
            reference=request.data.get('reference_decision', ''),
            date_limite=request.data.get('date_limite_inscription'),
            observations=request.data.get('observations', ''),
            forcer_dossier=bool(request.data.get('forcer_dossier')),
        )
    except (admission_services.AdmissionImpossible, workflow.TransitionInterdite) as erreur:
        return Response({'error': erreur.messages[0]}, status=409)
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
    return Response(_serialize_admission(admission))


@extend_schema(request=None, responses={200: AdmissionReponseSerializer, 404: AdmissionErreurSerializer, 409: AdmissionErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def admission_annuler(request, pk):
    admission = _admission_queryset().filter(pk=pk).first()
    if admission is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        admission_services.annuler_admission(
            admission, acteur=request.user, motif=request.data.get('motif', ''),
        )
    except (admission_services.AdmissionImpossible, workflow.TransitionInterdite) as erreur:
        return Response({'error': erreur.messages[0]}, status=409)
    return Response(_serialize_admission(admission))


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def admission_stats(request):
    """Répartition des admissions par décision + chaîne d'inscription."""
    queryset = Admission.objects.all()
    if 'annee_academique_id' in request.query_params:
        queryset = queryset.filter(annee_academique_id=request.query_params['annee_academique_id'])
    repartition = {
        ligne['decision']: ligne['total']
        for ligne in queryset.values('decision').annotate(total=Count('id'))
    }
    # « À inscrire » = permis d'inscription sans inscription vivante ;
    # « inscrits » = admissions déjà converties en dossiers étudiants.
    inscrits = 0
    a_inscrire = 0
    for admission in queryset.prefetch_related('inscriptions'):
        if _inscription_active(admission) is not None:
            inscrits += 1
        elif admission.permet_inscription:
            a_inscrire += 1
    return Response({
        'total': sum(repartition.values()),
        'par_decision': repartition,
        'a_inscrire': a_inscrire,
        'inscrits': inscrits,
    })


@extend_schema(responses={(200, 'application/octet-stream'): OpenApiTypes.BINARY, 404: AdmissionErreurSerializer})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def piece_telecharger(request, piece_id):
    """Téléchargement contrôlé d'une pièce. Les fichiers ne sont jamais servis en direct."""
    piece = PieceCandidature.objects.select_related('candidature').filter(pk=piece_id).first()
    if piece is None or not piece.fichier:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        fichier = piece.fichier.open('rb')
    except FileNotFoundError as erreur:
        raise Http404('Fichier absent du stockage.') from erreur
    return FileResponse(fichier, as_attachment=True, filename=piece.fichier.name.rsplit('/', 1)[-1])
