"""Lot L5 — API des équivalences et dispenses.

Conventions du projet : vues fonctions ``@api_view``, routes ``path()``
explicites, permissions IsSecretariatOrDFRC (traitement staff). Aucune
suppression : une décision n'est jamais détruite.
"""
from django.core.exceptions import ValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsSecretariatOrDFRC
from scolarite.models import JournalScolarite

from . import services, workflow
from .models import (
    DemandeEquivalenceDispense,
    HistoriqueEquivalence,
    PieceEquivalence,
)


def _serializer_piece(piece):
    return {
        'id': piece.id,
        'type_piece_id': piece.type_piece_id,
        'libelle': piece.libelle,
        'obligatoire': piece.obligatoire,
        'statut': piece.statut,
        'commentaire': piece.commentaire,
    }


def _serializer_demande(demande, detail=False):
    pieces = list(demande.pieces.all())
    obligatoires = [p for p in pieces if p.obligatoire]
    data = {
        'id': demande.id,
        'type_demande': demande.type_demande,
        'etudiant_id': demande.etudiant_id,
        'matricule': demande.etudiant.matricule,
        'etudiant_nom': demande.etudiant.nom_complet,
        'annee_academique_id': demande.annee_academique_id,
        'annee_academique': demande.annee_academique.libelle,
        'ref_formation_id': demande.ref_formation_id,
        'ref_formation': demande.ref_formation.intitule,
        'parcours_id': demande.parcours_id,
        'niveau_id': demande.niveau_id,
        'niveau': demande.niveau.code,
        'semestre_id': demande.semestre_id,
        'ue_id': demande.ue_id,
        'ue_code': demande.ue.code if demande.ue_id else None,
        'ue_intitule': demande.ue.intitule if demande.ue_id else None,
        'ecue_id': demande.ecue_id,
        'ecue_code': demande.ecue.code if demande.ecue_id else None,
        'ecue_intitule': demande.ecue.intitule if demande.ecue_id else None,
        'etablissement_origine': demande.etablissement_origine,
        'diplome_origine': demande.diplome_origine,
        'motif': demande.motif,
        'decision': demande.decision,
        'statut': demande.statut,
        'credits_reconnus': demande.credits_reconnus,
        'date_effet': demande.date_effet,
        'fin_validite': demande.fin_validite,
        'est_verrouillee': demande.est_verrouillee,
        'nb_pieces': len(pieces),
        'pieces_validees': sum(1 for p in pieces if p.est_validee),
        'dossier_complet': all(p.est_validee for p in obligatoires),
    }
    if detail:
        data.update({
            'annee_obtention': demande.annee_obtention,
            'analyse_pedagogique': demande.analyse_pedagogique,
            'commission': demande.commission,
            'date_commission': demande.date_commission,
            'note_transferee': demande.note_transferee,
            'autorite_validation': demande.autorite_validation,
            'appliquee_le': demande.appliquee_le,
            'rectifiee_le': demande.rectifiee_le,
            'motif_rectification': demande.motif_rectification,
            'pieces': [_serializer_piece(p) for p in demande.pieces.all()],
            'transitions_possibles': workflow.transitions_possibles(demande),
        })
    return data


def _get_demande(pk):
    return DemandeEquivalenceDispense.objects.select_related(
        'etudiant__participant', 'annee_academique', 'ref_formation',
    ).filter(pk=pk).first()


def _dossier_complet_pieces(demande):
    obligatoires = list(demande.pieces.filter(obligatoire=True))
    if not obligatoires:
        return True
    return all(p.est_validee for p in obligatoires)




# ── Contrats OpenAPI (équivalences et dispenses) ─────────────────────


class EquivalenceErreurSerializer(serializers.Serializer):
    error = serializers.JSONField()


class PieceEquivalenceReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type_piece_id = serializers.IntegerField()
    libelle = serializers.CharField()
    obligatoire = serializers.BooleanField()
    statut = serializers.CharField()
    commentaire = serializers.CharField()


class DemandeEquivalenceReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type_demande = serializers.CharField()
    etudiant_id = serializers.IntegerField()
    matricule = serializers.CharField()
    etudiant_nom = serializers.CharField()
    annee_academique_id = serializers.IntegerField()
    annee_academique = serializers.CharField()
    ref_formation_id = serializers.IntegerField()
    ref_formation = serializers.CharField()
    parcours_id = serializers.IntegerField(allow_null=True)
    niveau_id = serializers.IntegerField()
    niveau = serializers.CharField()
    semestre_id = serializers.IntegerField(allow_null=True)
    ue_id = serializers.IntegerField(allow_null=True)
    ue_code = serializers.CharField(allow_null=True)
    ue_intitule = serializers.CharField(allow_null=True)
    ecue_id = serializers.IntegerField(allow_null=True)
    ecue_code = serializers.CharField(allow_null=True)
    ecue_intitule = serializers.CharField(allow_null=True)
    etablissement_origine = serializers.CharField()
    diplome_origine = serializers.CharField()
    motif = serializers.CharField()
    decision = serializers.CharField()
    statut = serializers.CharField()
    credits_reconnus = serializers.IntegerField()
    date_effet = serializers.DateField(allow_null=True)
    fin_validite = serializers.DateField(allow_null=True)
    est_verrouillee = serializers.BooleanField()
    nb_pieces = serializers.IntegerField()
    pieces_validees = serializers.IntegerField()
    dossier_complet = serializers.BooleanField()


class DemandeEquivalenceDetailSerializer(DemandeEquivalenceReponseSerializer):
    annee_obtention = serializers.IntegerField(allow_null=True)
    analyse_pedagogique = serializers.CharField()
    commission = serializers.CharField()
    date_commission = serializers.DateField(allow_null=True)
    note_transferee = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    autorite_validation = serializers.CharField()
    appliquee_le = serializers.DateTimeField(allow_null=True)
    rectifiee_le = serializers.DateTimeField(allow_null=True)
    motif_rectification = serializers.CharField()
    pieces = PieceEquivalenceReponseSerializer(many=True)
    transitions_possibles = serializers.JSONField()


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: DemandeEquivalenceReponseSerializer(many=True), 201: DemandeEquivalenceDetailSerializer, 400: OpenApiTypes.OBJECT, 409: EquivalenceErreurSerializer})
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def demande_list(request):
    if request.method == 'GET':
        queryset = DemandeEquivalenceDispense.objects.select_related(
            'etudiant__participant', 'annee_academique', 'ref_formation', 'niveau',
            'ue', 'ecue',
        ).prefetch_related('pieces')
        for champ in ('statut', 'type_demande', 'etudiant_id', 'annee_academique_id'):
            if champ in request.query_params:
                queryset = queryset.filter(**{champ: request.query_params[champ]})
        # Chargement explicite (demande du 05/11/2026, écran Équivalences
        # et dispenses) : si `page_size` est fourni, réponse paginée bornée
        # à 200 lignes — même convention que le « chargement explicite :
        # 200 événements » du hub Présences et des écrans Campagnes. Sans
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
                'results': [_serializer_demande(d) for d in lignes],
            })
        return Response([_serializer_demande(d) for d in queryset[:500]])

    try:
        demande = DemandeEquivalenceDispense(
            type_demande=request.data.get('type_demande'),
            etudiant_id=request.data.get('etudiant_id'),
            annee_academique_id=request.data.get('annee_academique_id'),
            ref_formation_id=request.data.get('ref_formation_id'),
            parcours_id=request.data.get('parcours_id') or None,
            niveau_id=request.data.get('niveau_id'),
            semestre_id=request.data.get('semestre_id') or None,
            ue_id=request.data.get('ue_id') or None,
            ecue_id=request.data.get('ecue_id') or None,
            etablissement_origine=request.data.get('etablissement_origine', ''),
            diplome_origine=request.data.get('diplome_origine', ''),
            motif=request.data.get('motif', ''),
        )
        demande.full_clean(exclude=['credits_reconnus'])
        demande.save()
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
    demande.journaliser(
        JournalScolarite.Action.EVENEMENT_SCOLARITE, request.user,
        nouvelle_valeur='BROUILLON', commentaire='Création de la demande',
    )
    return Response(_serializer_demande(demande, detail=True), status=201)


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: DemandeEquivalenceDetailSerializer, 400: OpenApiTypes.OBJECT, 404: EquivalenceErreurSerializer})
@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def demande_detail(request, pk):
    demande = _get_demande(pk)
    if demande is None:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PATCH':
        if demande.est_verrouillee:
            return Response(
                {'error': 'Demande verrouillée : passez par la procédure de rectification.'},
                status=400,
            )
        if demande.statut not in (
            DemandeEquivalenceDispense.Statut.BROUILLON,
            DemandeEquivalenceDispense.Statut.A_COMPLETER,
        ):
            return Response({'error': f'Statut {demande.statut} : édition non autorisée.'}, status=400)
        for champ in ('etablissement_origine', 'diplome_origine', 'analyse_pedagogique', 'motif'):
            if champ in request.data:
                setattr(demande, champ, request.data[champ])
        try:
            demande.full_clean(exclude=['credits_reconnus'])
        except ValidationError as erreur:
            return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
        demande.save()
    return Response(_serializer_demande(demande, detail=True))


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: DemandeEquivalenceDetailSerializer, 400: OpenApiTypes.OBJECT, 404: EquivalenceErreurSerializer, 409: EquivalenceErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def demande_transition(request, pk):
    """Transition de workflow. Complétude bloquante vers AVIS_PEDAGOGIQUE."""
    demande = _get_demande(pk)
    if demande is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        if request.data.get('statut') == DemandeEquivalenceDispense.Statut.AVIS_PEDAGOGIQUE:
            if not _dossier_complet_pieces(demande):
                raise ValidationError(
                    'Dossier incomplet : toutes les pièces obligatoires doivent '
                    'être validées avant l’avis pédagogique.'
                )
        workflow.appliquer_transition(
            demande, request.data.get('statut'), utilisateur=request.user,
            commentaire=request.data.get('commentaire', ''),
        )
    except ValidationError as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response(_serializer_demande(demande, detail=True))


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: DemandeEquivalenceDetailSerializer, 400: OpenApiTypes.OBJECT, 404: EquivalenceErreurSerializer, 409: EquivalenceErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def demande_decision(request, pk):
    """Avis pédagogique puis décision officielle (VALIDEE/REJETEE)."""
    demande = _get_demande(pk)
    if demande is None:
        return Response({'error': 'Introuvable'}, status=404)
    S = DemandeEquivalenceDispense.Statut
    decision = request.data.get('decision')
    try:
        if demande.statut == S.AVIS_PEDAGOGIQUE:
            if 'analyse_pedagogique' in request.data:
                demande.analyse_pedagogique = request.data['analyse_pedagogique']
                demande.save(update_fields=['analyse_pedagogique', 'updated_at'])
            workflow.appliquer_transition(demande, S.DECISION, utilisateur=request.user)
        elif demande.statut != S.DECISION:
            return Response({'error': f'Statut {demande.statut} : décision indisponible.'}, status=400)
        if decision not in (DemandeEquivalenceDispense.Decision.FAVORABLE,
                            DemandeEquivalenceDispense.Decision.DEFAVORABLE):
            return Response({'error': 'decision doit être FAVORABLE ou DEFAVORABLE.'}, status=400)
        demande.decision = decision
        demande.credits_reconnus = request.data.get('credits_reconnus') or None
        demande.note_transferee = request.data.get('note_transferee') or None
        demande.autorite_validation = request.data.get('autorite_validation', demande.autorite_validation)
        demande.commission = request.data.get('commission', demande.commission)
        if request.data.get('date_commission'):
            demande.date_commission = request.data['date_commission']
        cible = (S.VALIDEE if decision == DemandeEquivalenceDispense.Decision.FAVORABLE
                 else S.REJETEE)
        workflow.appliquer_transition(demande, cible, utilisateur=request.user,
                                      commentaire=request.data.get('commentaire', ''))
    except ValidationError as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response(_serializer_demande(demande, detail=True))


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: DemandeEquivalenceDetailSerializer, 400: OpenApiTypes.OBJECT, 404: EquivalenceErreurSerializer, 409: EquivalenceErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def demande_appliquer(request, pk):
    """Application de la dispense/équivalence — réservée aux demandes VALIDEE."""
    demande = _get_demande(pk)
    if demande is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        services.appliquer(demande, utilisateur=request.user,
                           commentaire=request.data.get('commentaire', ''))
    except services.ApplicationImpossible as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response(_serializer_demande(demande, detail=True))


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: DemandeEquivalenceDetailSerializer, 400: OpenApiTypes.OBJECT, 404: EquivalenceErreurSerializer, 409: EquivalenceErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def demande_rectifier(request, pk):
    """Procédure de rectification après validation (aucune suppression)."""
    demande = _get_demande(pk)
    if demande is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        services.rectifier(
            demande, utilisateur=request.user,
            motif=request.data.get('motif', ''),
            credits_reconnus=request.data.get('credits_reconnus') or None,
            note_transferee=request.data.get('note_transferee') or None,
            autorite_validation=request.data.get('autorite_validation', ''),
        )
    except services.ApplicationImpossible as erreur:
        return Response({'error': erreur.messages}, status=400)
    return Response(_serializer_demande(demande, detail=True))


@extend_schema(responses={200: OpenApiTypes.OBJECT, 404: EquivalenceErreurSerializer})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def demande_historique(request, pk):
    """Historique immuable des changements de statut et décisions."""
    demande = _get_demande(pk)
    if demande is None:
        return Response({'error': 'Introuvable'}, status=404)
    return Response([
        {
            'statut': h.statut, 'decision': h.decision,
            'utilisateur': h.utilisateur.username if h.utilisateur else None,
            'commentaire': h.commentaire, 'horodatage': h.horodatage,
        }
        for h in demande.historique.select_related('utilisateur')
    ])


@extend_schema(request=OpenApiTypes.OBJECT, responses={201: PieceEquivalenceReponseSerializer, 400: OpenApiTypes.OBJECT, 404: EquivalenceErreurSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def demande_piece_add(request, pk):
    """Ajout d'une pièce justificative à la demande."""
    demande = _get_demande(pk)
    if demande is None:
        return Response({'error': 'Introuvable'}, status=404)
    piece = PieceEquivalence(
        demande=demande,
        type_piece_id=request.data.get('type_piece_id') or None,
        libelle=request.data.get('libelle', ''),
        obligatoire=bool(request.data.get('obligatoire', True)),
        statut=request.data.get('statut', PieceEquivalence.Statut.MANQUANTE),
    )
    try:
        piece.full_clean()
        piece.save()
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
    return Response(_serializer_piece(piece), status=201)


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: PieceEquivalenceReponseSerializer, 400: OpenApiTypes.OBJECT, 404: EquivalenceErreurSerializer})
@api_view(['PATCH'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def demande_piece_verifier(request, piece_id):
    """Vérification d'une pièce (VALIDEE/REFUSEE + commentaire)."""
    piece = PieceEquivalence.objects.select_related('demande').filter(pk=piece_id).first()
    if piece is None:
        return Response({'error': 'Introuvable'}, status=404)
    piece.statut = request.data.get('statut', piece.statut)
    piece.commentaire = request.data.get('commentaire', piece.commentaire)
    piece.verifie_par = request.user
    try:
        piece.full_clean()
        piece.save()
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)
