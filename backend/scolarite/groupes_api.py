"""API des affectations de groupe, réinscriptions et événements de scolarité."""

from django.core.exceptions import ValidationError
from django.db.models import Q
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


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def groupe_effectifs(request):
    """Effectifs et places restantes par groupe."""
    queryset = Groupe.objects.select_related('annee_academique', 'ref_formation', 'niveau')
    for champ in ('annee_academique_id', 'ref_formation_id', 'niveau_id', 'parcours_id', 'actif'):
        if champ in request.query_params:
            valeur = request.query_params[champ]
            if champ == 'actif':
                valeur = valeur not in ('0', 'false', 'False')
            queryset = queryset.filter(**{champ: valeur})
    return Response([
        {
            'id': groupe.id,
            'nom': groupe.nom,
            'annee_academique': groupe.annee_academique.libelle,
            'ref_formation': groupe.ref_formation.intitule,
            'niveau': groupe.niveau.code,
            'capacite_max': groupe.capacite_max,
            'effectif': groupes_services.effectif_groupe(groupe),
            'places_restantes': groupes_services.places_restantes(groupe),
            'actif': groupe.actif,
        }
        for groupe in queryset
    ])


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
        return Response([_serialize_inscription(i) for i in queryset[:500]])

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
