"""Vues de l'API d'habilitation (unité U2).

Routes livrées (toutes nouvelles, toutes sous /api/habilitations/) :

* ``GET mes-acces/``      — ce que le moteur sait du compte connecté ;
* ``POST evaluer/``        — évaluation à la demande d'une permission ;
* ``GET observations/synthese/`` et ``POST observations/remettre-a-zero/``
                            — pilotage du mode observation (administrateurs) ;
* ``GET roles/``, ``GET permissions/`` — référentiels en lecture (vidés en U2,
                            peuplés en U3).

Aucune de ces vues ne modifie une décision d'accès legacy : l'écriture des
attributions relève de l'admin Django et, plus tard, des écrans U4.
"""
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from habilitations.models import (
    CompteUtilisateur,
    DelegationHabilitation,
    JournalHabilitation,
    PermissionAttribuee,
    PermissionMetier,
    RoleMetier,
)
from habilitations.permissions import EstAdministrateurHabilitations
from habilitations.services import observation as observation_service
from habilitations.services.journalisation import journaliser
from habilitations.services.moteur import est_autorise
from habilitations.services.projection import projection_capacites

from .serializers import (
    DemandeEvaluationSerializer,
    PermissionMetierSerializer,
    RoleMetierSerializer,
    serialiser_attribution,
    serialiser_delegation,
    serialiser_derogation,
)

User = get_user_model()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mes_acces_view(request):
    """`GET /api/habilitations/mes-acces/` : état gouverné du compte connecté."""
    compte = CompteUtilisateur.objects.filter(user=request.user).first()
    reponse = projection_capacites(request.user)
    if compte is None:
        return Response(reponse)
    date = timezone.localdate()
    attributions = (
        compte.attributions.select_related('role')
        .prefetch_related('perimetres')
    )
    derogations = (
        compte.derogations.filter(statut=PermissionAttribuee.Statut.ACTIVE)
        .select_related('permission', 'perimetre')
    )
    delegations_recues = (
        compte.delegations_recues.filter(
            statut=DelegationHabilitation.Statut.ACTIVE
        )
        .select_related('delegant__user', 'delegataire__user')
        .prefetch_related('roles', 'permissions', 'perimetres')
    )
    delegations_donnees = (
        compte.delegations_donnees.filter(
            statut=DelegationHabilitation.Statut.ACTIVE
        )
        .select_related('delegant__user', 'delegataire__user')
        .prefetch_related('roles', 'permissions', 'perimetres')
    )
    # Clé additive (réorganisation de la navigation RBAC) : codes de permissions
    # effectivement détenus par le compte connecté (rôles actifs + dérogations
    # OCTROI − RETRAIT). Lecture seule, auto-portée (aucun droit tiers), et
    # strictement descriptive : l'API reste la seule autorité, cette liste ne
    # sert qu'à masquer/afficher des entrées de menu. Même calcul que
    # ``GET comptes/<pk>/effective-permissions/`` (réservé aux administrateurs).
    from habilitations.services.comptes_admin import permissions_effectives

    reponse.update({
        'compte': {
            'statut': compte.statut,
            'canal': compte.canal,
            'mfa_actif': compte.mfa_actif,
            'date_expiration': (
                compte.date_expiration.isoformat()
                if compte.date_expiration else None
            ),
        },
        'permissions_effectives': sorted(permissions_effectives(compte)),
        'attributions': [
            serialiser_attribution(a) for a in attributions
            if a.est_active(date)
        ],
        'attributions_inactives': [
            serialiser_attribution(a) for a in attributions
            if not a.est_active(date)
        ],
        'derogations_actives': [
            serialiser_derogation(d) for d in derogations
            if d.est_active(date)
        ],
        'delegations_recues': [
            serialiser_delegation(d) for d in delegations_recues
            if d.est_active(date)
        ],
        'delegations_donnees': [
            serialiser_delegation(d) for d in delegations_donnees
            if d.est_active(date)
        ],
    })
    return Response(reponse)


class EvaluerView(APIView):
    """``POST /api/habilitations/evaluer/`` : décision motivée du moteur.

    Diagnostic en lecture : la réponse vaut toujours 200 (la décision est dans
    le corps). Évaluer un autre compte est réservé aux administrateurs et est
    tracé au journal. L'évaluation ne nourrit pas les compteurs d'observation
    (ce ne sont pas des tentatives d'accès réelles).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DemandeEvaluationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data

        username_cible = donnees.get('username') or ''
        user_cible = request.user
        compte_cible = CompteUtilisateur.objects.filter(
            user=request.user
        ).first()
        if username_cible and username_cible != request.user.get_username():
            if not EstAdministrateurHabilitations().has_permission(request, self):
                return Response(
                    {'detail': EstAdministrateurHabilitations.message},
                    status=status.HTTP_403_FORBIDDEN,
                )
            user_cible = User.objects.filter(username=username_cible).first()
            if user_cible is None:
                return Response(
                    {'detail': "Compte cible introuvable."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            compte_cible = CompteUtilisateur.objects.filter(
                user=user_cible
            ).first()

        contexte = {}
        if donnees.get('niveau_minimum'):
            contexte['niveau_minimum'] = donnees['niveau_minimum']
        decision = est_autorise(
            user_cible,
            donnees['permission'],
            canal=donnees.get('canal', 'WEB'),
            cible=donnees.get('cible'),
            contexte=contexte,
        )
        if username_cible and username_cible != request.user.get_username():
            journaliser(
                JournalHabilitation.TypeEvenement.AUTRE,
                acteur=request.user,
                compte=compte_cible,
                nouvelle_valeur={'evaluation': decision.pour_api()},
                motif=f"Évaluation d'habilitation par {request.user.get_username()}",
                adresse_ip=request.META.get('REMOTE_ADDR', ''),
                agent_utilisateur=request.META.get('HTTP_USER_AGENT', '')[:200],
            )
        return Response(decision.pour_api())


class RoleListView(generics.ListAPIView):
    """``GET /api/habilitations/roles/`` : référentiel des rôles (U3 pour les données)."""

    serializer_class = RoleMetierSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            RoleMetier.objects.all()
            .prefetch_related('incompatible_avec')
            .annotate(_permissions_count=Count('permissions', distinct=True))
            .order_by('domaine', 'ordre', 'libelle')
        )


class PermissionListView(generics.ListAPIView):
    """``GET /api/habilitations/permissions/`` : référentiel des permissions.

    Filtres serveur (additifs) : ``module``, ``ressource``, ``action``,
    ``criticite`` et recherche ``q`` (code/libellé). Chaque ligne porte
    ``total_roles`` — nombre réel de rôles qui l'octroient (source de
    vérité : M2M ``RoleMetier.permissions``).
    """

    serializer_class = PermissionMetierSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = (
            PermissionMetier.objects.all()
            .annotate(total_roles=Count('roles_octroyants', distinct=True))
            .order_by('module', 'ressource')
        )
        params = self.request.query_params
        if params.get('module'):
            qs = qs.filter(module=params['module'])
        if params.get('ressource'):
            qs = qs.filter(ressource=params['ressource'])
        if params.get('action'):
            qs = qs.filter(action=params['action'])
        if params.get('criticite'):
            qs = qs.filter(criticite=params['criticite'])
        q = params.get('q', '').strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(libelle__icontains=q))
        return qs


class ObservationsSyntheseView(APIView):
    permission_classes = [IsAuthenticated, EstAdministrateurHabilitations]

    def get(self, request):
        return Response(observation_service.synthese_pour_api())


class ObservationsResetView(APIView):
    permission_classes = [IsAuthenticated, EstAdministrateurHabilitations]

    def post(self, request):
        etat = observation_service.remettre_a_zero()
        journaliser(
            JournalHabilitation.TypeEvenement.AUTRE,
            acteur=request.user,
            nouvelle_valeur={'remise_a_zero_observations': True},
            motif='Remise à zéro des compteurs d’observation d’habilitation',
            adresse_ip=request.META.get('REMOTE_ADDR', ''),
            agent_utilisateur=request.META.get('HTTP_USER_AGENT', '')[:200],
        )
        return Response({'mode': observation_service.mode_moteur(),
                         'observations': etat})
