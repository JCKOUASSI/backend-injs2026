"""API des affectations de groupe, réinscriptions et événements de scolarité."""

from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsSecretariatOrDFRC

from . import groupes_services
from .models import (
    AffectationGroupe,
    AnneeAcademique,
    DossierEtudiant,
    EvenementScolarite,
    Groupe,
    InscriptionAdministrative,
    Niveau,
)


def _serialize_affectation(affectation):
    return {
        'id': affectation.id,
        'inscription_id': affectation.inscription_id,
        'groupe_id': affectation.groupe_id,
        'groupe': affectation.groupe.nom,
        'date_debut': affectation.date_debut,
        'date_fin': affectation.date_fin,
        'active': affectation.active,
        'motif': affectation.motif,
        'affecte_par': affectation.affecte_par.username if affectation.affecte_par else None,
    }


def _serialize_evenement(evenement):
    return {
        'id': evenement.id,
        'etudiant_id': evenement.etudiant_id,
        'inscription_id': evenement.inscription_id,
        'type_evenement': evenement.type_evenement,
        'type_libelle': evenement.get_type_evenement_display(),
        'date_evenement': evenement.date_evenement,
        'ancienne_valeur': evenement.ancienne_valeur,
        'nouvelle_valeur': evenement.nouvelle_valeur,
        'commentaire': evenement.commentaire,
        'enregistre_par': evenement.enregistre_par.username if evenement.enregistre_par else None,
    }




# ── Contrats OpenAPI (groupes, affectations, réinscriptions) ─────────


class ErreurGroupesSerializer(serializers.Serializer):
    error = serializers.JSONField()


class AffectationGroupeReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    inscription_id = serializers.IntegerField()
    groupe_id = serializers.IntegerField()
    groupe = serializers.CharField()
    date_debut = serializers.DateField()
    date_fin = serializers.DateField(allow_null=True)
    active = serializers.BooleanField()
    motif = serializers.CharField()
    affecte_par = serializers.CharField(allow_null=True)


class EvenementEtudiantReponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    etudiant_id = serializers.IntegerField()
    inscription_id = serializers.IntegerField(allow_null=True)
    type_evenement = serializers.CharField()
    type_libelle = serializers.CharField()
    date_evenement = serializers.DateField()
    ancienne_valeur = serializers.CharField()
    nouvelle_valeur = serializers.CharField()
    commentaire = serializers.CharField()
    enregistre_par = serializers.CharField(allow_null=True)


class RepartitionAutomatiqueSerializer(serializers.Serializer):
    affectations = serializers.IntegerField()
    echecs = serializers.JSONField()


class NonAffectesSerializer(serializers.Serializer):
    non_affectes = serializers.IntegerField()


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def groupe_effectifs(request):
    """Effectifs et places restantes par groupe."""
    queryset = (
        Groupe.objects
        .select_related('annee_academique', 'ref_formation', 'niveau')
        # Effectif annoté en une seule requête (le registre compte plus
        # d'une centaine de groupes : éviter deux requêtes par groupe).
        .annotate(effectif=Count(
            'affectations', filter=Q(affectations__active=True)))
    )
    for champ in ('annee_academique_id', 'ref_formation_id', 'niveau_id', 'parcours_id', 'actif'):
        if champ in request.query_params:
            valeur = request.query_params[champ]
            if champ == 'actif':
                valeur = valeur not in ('0', 'false', 'False')
            queryset = queryset.filter(**{champ: valeur})

    def _ligne(groupe):
        return {
            'id': groupe.id,
            'nom': groupe.nom,
            'annee_academique': groupe.annee_academique.libelle,
            'ref_formation': groupe.ref_formation.intitule,
            'niveau': groupe.niveau.code,
            'capacite_max': groupe.capacite_max,
            'effectif': groupe.effectif,
            'places_restantes': (
                None if groupe.capacite_max is None
                else max(groupe.capacite_max - groupe.effectif, 0)
            ),
            'actif': groupe.actif,
        }

    # Chargement explicite (extension de la série, 05/11/2026) : si
    # `page_size` est fourni, réponse paginée bornée à 200 lignes — même
    # convention que les écrans Campagnes / Équivalences. Sans `page_size`,
    # tableau complet historique inchangé.
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
            'results': [_ligne(g) for g in lignes],
        })
    return Response([_ligne(groupe) for groupe in queryset])


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: AffectationGroupeReponseSerializer(many=True), 400: OpenApiTypes.OBJECT, 404: ErreurGroupesSerializer, 409: ErreurGroupesSerializer})
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def inscription_affectations(request, pk):
    """Historique des affectations d'une inscription, et création d'une nouvelle."""
    inscription = InscriptionAdministrative.objects.select_related(
        'etudiant__participant', 'annee_academique', 'ref_formation', 'niveau',
    ).filter(pk=pk).first()
    if inscription is None:
        return Response({'error': 'Introuvable'}, status=404)

    if request.method == 'POST':
        groupe = Groupe.objects.filter(pk=request.data.get('groupe_id')).first()
        if groupe is None:
            return Response({'groupe_id': ['Groupe introuvable.']}, status=400)
        try:
            groupes_services.affecter_groupe(
                inscription, groupe, acteur=request.user,
                motif=request.data.get('motif', ''),
                ignorer_capacite=bool(request.data.get('ignorer_capacite')),
            )
        except groupes_services.AffectationImpossible as erreur:
            return Response({'error': erreur.messages[0]}, status=409)

    affectations = inscription.affectations.select_related('groupe', 'affecte_par')
    return Response([_serialize_affectation(a) for a in affectations])


@extend_schema(request=None, responses={200: AffectationGroupeReponseSerializer, 400: OpenApiTypes.OBJECT, 404: ErreurGroupesSerializer})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def inscription_retirer_groupe(request, pk):
    inscription = InscriptionAdministrative.objects.filter(pk=pk).first()
    if inscription is None:
        return Response({'error': 'Introuvable'}, status=404)
    try:
        affectation = groupes_services.retirer_du_groupe(
            inscription, acteur=request.user, motif=request.data.get('motif', ''),
        )
    except groupes_services.AffectationImpossible as erreur:
        return Response({'error': erreur.messages[0]}, status=409)
    return Response(_serialize_affectation(affectation))


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: RepartitionAutomatiqueSerializer, 400: OpenApiTypes.OBJECT})
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def repartition_automatique(request):
    """Répartit les inscriptions validées d'un périmètre sur les groupes disponibles."""
    inscriptions = InscriptionAdministrative.objects.filter(
        statut=InscriptionAdministrative.Statut.VALIDEE,
    ).select_related('etudiant__participant')
    for champ in ('annee_academique_id', 'ref_formation_id', 'niveau_id', 'parcours_id'):
        if request.data.get(champ):
            inscriptions = inscriptions.filter(**{champ: request.data[champ]})
    inscriptions = inscriptions.exclude(affectations__active=True)

    groupes = list(Groupe.objects.filter(actif=True))
    for champ in ('annee_academique_id', 'ref_formation_id', 'niveau_id'):
        if request.data.get(champ):
            groupes = [g for g in groupes if getattr(g, champ) == int(request.data[champ])]

    realisees, echecs = groupes_services.repartir_automatiquement(
        list(inscriptions), groupes, acteur=request.user,
    )
    return Response({
        'affectations': len(realisees),
        'echecs': echecs,
    })


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT})
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def reinscrire(request):
    """Réinscrit un étudiant existant pour une nouvelle année académique (POST),

    ou liste les réinscriptions, transferts et réorientations enregistrés (GET).
    """
    if request.method == 'GET':
        from .inscription_api import _inscription_queryset, _serialize_inscription

        queryset = _inscription_queryset()
        type_param = request.query_params.get('type_inscription')
        if type_param:
            queryset = queryset.filter(type_inscription=type_param)
        else:
            # Exclut les premières inscriptions simples par défaut
            queryset = queryset.exclude(type_inscription=InscriptionAdministrative.Type.PREMIERE)

        for champ in ('statut', 'annee_academique_id', 'ref_formation_id', 'niveau_id', 'etudiant_id'):
            if champ in request.query_params:
                queryset = queryset.filter(**{champ: request.query_params[champ]})

        recherche = request.query_params.get('search') or request.query_params.get('q')
        if recherche:
            queryset = queryset.filter(
                Q(etudiant__participant__matricule__icontains=recherche)
                | Q(etudiant__participant__nom__icontains=recherche)
                | Q(etudiant__participant__prenom__icontains=recherche)
            )
        # Tri déterministe : sans lui, des pages successives peuvent se
        # chevaucher (même convention que la liste des dossiers étudiants).
        queryset = queryset.order_by(
            'etudiant__participant__nom', 'etudiant__participant__prenom',
            'etudiant__participant__matricule', 'pk',
        )
        # Compatibilité : sans paramètres de pagination, la liste historique
        # (plafond 500) est conservée. L'écran dédié demande des pages et
        # obtient le total réel des flux (1 867 en 2026-2027, pas 500).
        if 'page' not in request.query_params and 'page_size' not in request.query_params:
            return Response([_serialize_inscription(i) for i in queryset[:500]])
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 50))
        except (TypeError, ValueError):
            return Response(
                {'error': 'Les paramètres page et page_size doivent être numériques.'},
                status=400,
            )
        if page < 1 or page_size < 1 or page_size > 100:
            return Response(
                {'error': 'page doit être >= 1 et page_size compris entre 1 et 100.'},
                status=400,
            )
        total = queryset.count()
        start = (page - 1) * page_size
        return Response({
            'results': [_serialize_inscription(i) for i in queryset[start:start + page_size]],
            'count': total,
            'total_pages': (total + page_size - 1) // page_size,
            'page': page,
            'page_size': page_size,
        })

    etudiant = DossierEtudiant.objects.select_related('statut', 'participant').filter(
        pk=request.data.get('etudiant_id'),
    ).first()
    if etudiant is None:
        return Response({'etudiant_id': ['Dossier étudiant introuvable.']}, status=400)
    annee = AnneeAcademique.objects.filter(pk=request.data.get('annee_academique_id')).first()
    if annee is None:
        return Response({'annee_academique_id': ['Année académique introuvable.']}, status=400)
    niveau = Niveau.objects.filter(pk=request.data.get('niveau_id')).first()
    if niveau is None:
        return Response({'niveau_id': ['Niveau introuvable.']}, status=400)

    type_inscription = request.data.get(
        'type_inscription', InscriptionAdministrative.Type.REINSCRIPTION,
    )
    if type_inscription not in InscriptionAdministrative.Type.values:
        return Response({'type_inscription': ['Type inconnu.']}, status=400)

    try:
        inscription = groupes_services.reinscrire(
            etudiant, annee, niveau, acteur=request.user,
            type_inscription=type_inscription,
            valider=bool(request.data.get('valider')),
        )
    except groupes_services.ReinscriptionImpossible as erreur:
        return Response({'error': erreur.messages[0]}, status=409)
    except ValidationError as erreur:
        return Response(getattr(erreur, 'message_dict', {'error': str(erreur)}), status=400)

    from .inscription_api import _serialize_inscription

    return Response(_serialize_inscription(inscription, detail=True), status=201)


@extend_schema(responses={200: OpenApiTypes.OBJECT, 400: ErreurGroupesSerializer})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def reinscriptions_stats(request):
    """Panorama des flux de continuité d'une année (hors premières inscriptions).

    Sert les indicateurs de l'écran « Réinscriptions & transferts » sans
    dépendre d'une liste plafonnée : répartition par type de flux
    (réinscription, redoublement, reprise, réorientation, transfert), par
    statut et par niveau, et part de continuité parmi les inscrits validés.
    """
    annee_id = request.query_params.get('annee_academique_id')
    if annee_id:
        annee = AnneeAcademique.objects.filter(pk=annee_id).first()
        if annee is None:
            return Response({'error': 'Année académique introuvable.'}, status=400)
    else:
        annee = (
            AnneeAcademique.objects.filter(courante=True).first()
            or AnneeAcademique.objects.order_by('-libelle').first()
        )
    base = (
        InscriptionAdministrative.objects.filter(annee_academique=annee)
        if annee is not None else InscriptionAdministrative.objects.none()
    )
    flux = base.exclude(type_inscription=InscriptionAdministrative.Type.PREMIERE)
    validees = base.filter(statut=InscriptionAdministrative.Statut.VALIDEE)
    flux_valides = flux.filter(statut=InscriptionAdministrative.Statut.VALIDEE)

    par_type = {choix: 0 for choix in InscriptionAdministrative.Type.values}
    for ligne in base.values('type_inscription').annotate(total=Count('id')):
        par_type[ligne['type_inscription']] = ligne['total']

    return Response({
        'annee_academique_id': annee.id if annee else None,
        'annee_academique': annee.libelle if annee else None,
        'total_inscriptions': base.count(),
        'total_flux': flux.count(),
        'taux_continuite': (
            round(100 * flux_valides.count() / validees.count(), 1)
            if validees.exists() else 0
        ),
        'par_type': par_type,
        'par_statut': {
            ligne['statut']: ligne['total']
            for ligne in flux.values('statut').annotate(total=Count('id'))
        },
        'par_niveau': {
            (ligne['niveau__code'] or 'Non renseigné'): ligne['total']
            for ligne in flux.values('niveau__code').annotate(total=Count('id'))
        },
    })


@extend_schema(request=OpenApiTypes.OBJECT, responses={200: EvenementEtudiantReponseSerializer(many=True), 400: OpenApiTypes.OBJECT, 404: ErreurGroupesSerializer})
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def etudiant_evenements(request, pk):
    """Chronologie du parcours d'un étudiant."""
    etudiant = DossierEtudiant.objects.filter(pk=pk).first()
    if etudiant is None:
        return Response({'error': 'Introuvable'}, status=404)

    if request.method == 'POST':
        type_evenement = request.data.get('type_evenement')
        if type_evenement not in EvenementScolarite.Type.values:
            return Response({'type_evenement': ['Type inconnu.']}, status=400)
        inscription = InscriptionAdministrative.objects.filter(
            pk=request.data.get('inscription_id'),
        ).first()
        groupes_services.enregistrer_evenement(
            etudiant, type_evenement, acteur=request.user, inscription=inscription,
            ancienne_valeur=request.data.get('ancienne_valeur', ''),
            nouvelle_valeur=request.data.get('nouvelle_valeur', ''),
            commentaire=request.data.get('commentaire', ''),
        )

    evenements = etudiant.evenements.select_related('enregistre_par')
    return Response([_serialize_evenement(e) for e in evenements])



@extend_schema(responses={200: NonAffectesSerializer})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def groupe_non_affectes(request):
    """Nombre d'inscriptions validées sans affectation de groupe active.

    Sert d'alerte sur l'écran Groupes pédagogiques : tant qu'il reste des
    étudiants non affectés sur le périmètre filtré, la répartition
    automatique a du travail.
    """
    inscriptions = (
        InscriptionAdministrative.objects
        .filter(statut=InscriptionAdministrative.Statut.VALIDEE)
        .exclude(affectations__active=True)
    )
    for champ in ('annee_academique_id', 'ref_formation_id', 'niveau_id'):
        if request.query_params.get(champ):
            inscriptions = inscriptions.filter(
                **{champ: request.query_params[champ]})
    return Response({'non_affectes': inscriptions.count()})


@extend_schema(responses={(200, 'application/pdf'): OpenApiTypes.BINARY, (200, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'): OpenApiTypes.BINARY, 400: ErreurGroupesSerializer, 404: ErreurGroupesSerializer, 503: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def groupe_liste_export(request, pk, fmt):
    """Liste nominative d'un groupe TD/TP (affectations actives), PDF ou Excel.

    Équivalent LMD de la « liste de classe » de la formation continue,
    qui repose sur le champ libre `Participant.groupe` et ignore donc
    les sections `scolarite.Groupe`.
    """
    from django.http import HttpResponse

    from . import groupes_export

    if fmt not in ('pdf', 'excel'):
        return Response({'error': 'Format inconnu (pdf ou excel).'}, status=400)
    groupe = (
        Groupe.objects
        .select_related('annee_academique', 'ref_formation', 'niveau')
        .filter(pk=pk)
        .first()
    )
    if groupe is None:
        return Response({'error': 'Groupe introuvable.'}, status=404)
    try:
        buffer = (
            groupes_export.export_groupe_pdf(groupe)
            if fmt == 'pdf'
            else groupes_export.export_groupe_excel(groupe)
        )
    except RuntimeError as exc:
        return Response({'detail': str(exc)}, status=503)
    type_contenu = (
        'application/pdf' if fmt == 'pdf'
        else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response = HttpResponse(buffer.getvalue(), content_type=type_contenu)
    nom_fichier = groupes_export.groupe_liste_filename(groupe, fmt)
    response['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
    return response
