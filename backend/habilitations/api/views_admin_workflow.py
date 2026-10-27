"""Vues de la console CURP U4 — gestes bornés sur dérogations et délégations,
simulation d'import (l'écriture est U5) et écran de revue en consultation
(la campagne signée relève de C5/U7).
"""
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    DelegationHabilitation,
    PermissionAttribuee,
    PermissionMetier,
    RoleMetier,
)
from habilitations.permissions import ExigeDrapeauAdmin
from habilitations.services import comptes_admin as service
from habilitations.services.journalisation import journaliser

from .serializers import (
    serialiser_delegation,
    serialiser_derogation,
)
from .serializers_admin import (
    DelegationInputSerializer,
    DerogationInputSerializer,
    SimulationImportSerializer,
)

GARDE = [ExigeDrapeauAdmin]


def _meta(request):
    return {
        'adresse_ip': request.META.get('REMOTE_ADDR', ''),
        'agent_utilisateur': request.META.get('HTTP_USER_AGENT', '')[:250],
    }


# ---------------------------------------------------------------------------
# Dérogations (geste borné : proposition et révocation ; instruction U5)
# ---------------------------------------------------------------------------
class DerogationListCreateView(APIView):
    permission_classes = GARDE

    def get(self, request):
        qs = (
            PermissionAttribuee.objects
            .select_related('compte__user', 'permission')
            .order_by('-date_creation')
        )
        if request.query_params.get('statut'):
            qs = qs.filter(statut=request.query_params['statut'])
        paginator = PageNumberPagination()
        paginator.page_size = int(request.query_params.get('page_size', 50))
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([
            {
                **serialiser_derogation(d),
                'id': d.pk,
                'compte': d.compte_id,
                'username': d.compte.user.get_username(),
                'motif': d.motif,
                'sensible': d.permission.criticite == 'CRITIQUE',
            }
            for d in page
        ])

    def post(self, request):
        serializer = DerogationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data
        compte = CompteUtilisateur.objects.filter(pk=donnees['compte']).first()
        if compte is None:
            return Response({'detail': 'Compte introuvable.'}, status=404)
        permission = PermissionMetier.objects.filter(code=donnees['permission']).first()
        if permission is None:
            return Response({'detail': 'Permission inconnue.'}, status=404)
        derogation = PermissionAttribuee.objects.create(
            compte=compte, permission=permission, sens=donnees['sens'],
            motif=donnees['motif'],
            date_debut=donnees.get('date_debut') or timezone.localdate(),
            date_fin=donnees.get('date_fin'),
            attribue_par=request.user,
            statut=PermissionAttribuee.Statut.PROPOSEE,
        )
        journaliser(
            'PERMISSION_OCTROYEE' if derogation.sens == PermissionAttribuee.Sens.OCTROI
            else 'PERMISSION_RETIREE',
            acteur=request.user, compte=compte, cible=derogation,
            nouvelle_valeur={'permission': permission.code, 'sens': derogation.sens},
            motif=donnees['motif'], **_meta(request),
        )
        return Response(serialiser_derogation(derogation),
                        status=status.HTTP_201_CREATED)


class DerogationRevokeView(APIView):
    permission_classes = GARDE

    def post(self, request, pk):
        derogation = PermissionAttribuee.objects.filter(pk=pk).first()
        if derogation is None:
            return Response({'detail': 'Dérogation introuvable.'}, status=404)
        motif = (request.data.get('motif') or '').strip()
        if not motif:
            return Response({'detail': 'Un motif est obligatoire.', 'code': 'MOTIF_REQUIS'},
                            status=400)
        derogation.statut = PermissionAttribuee.Statut.REVOQUEE
        derogation.save(update_fields=['statut'])
        journaliser(
            'PERMISSION_RETIREE', acteur=request.user, compte=derogation.compte,
            cible=derogation, ancienne_valeur={'statut': 'ACTIVE'},
            motif=motif, **_meta(request),
        )
        return Response(serialiser_derogation(derogation))


# ---------------------------------------------------------------------------
# Délégations (geste borné : création bornée, fin anticipée ; re-délégation U5)
# ---------------------------------------------------------------------------
class DelegationListCreateView(APIView):
    permission_classes = GARDE

    def get(self, request):
        qs = (
            DelegationHabilitation.objects
            .select_related('delegant__user', 'delegataire__user')
            .prefetch_related('roles', 'permissions')
            .order_by('-date_creation')
        )
        if request.query_params.get('statut'):
            qs = qs.filter(statut=request.query_params['statut'])
        paginator = PageNumberPagination()
        paginator.page_size = int(request.query_params.get('page_size', 50))
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([
            {
                **serialiser_delegation(d),
                'id': d.pk,
                'motif': d.motif,
            }
            for d in page
        ])

    @transaction.atomic
    def post(self, request):
        serializer = DelegationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data
        delegant = CompteUtilisateur.objects.filter(pk=donnees['delegant']).first()
        delegataire = CompteUtilisateur.objects.filter(pk=donnees['delegataire']).first()
        if delegant is None or delegataire is None:
            return Response({'detail': 'Compte délégant ou délégataire introuvable.'},
                            status=404)
        # U5 — contrôles de cohérence : droits réellement détenus en direct,
        # pas de re-délégation, terme borné, périmètres couverts. La
        # délégation reste PROPOSÉE tant qu'un administrateur ne l'active pas.
        try:
            from ..services.delegations_u5 import controler_delegation
            controler_delegation(
                delegant, delegataire,
                donnees.get('roles') or [], donnees.get('permissions') or [],
                donnees['date_fin'],
                perimetres_ids=None,
                date_debut=donnees.get('date_debut') or timezone.localdate(),
            )
        except service.ErreurConsole as erreur:
            return Response({'detail': str(erreur), 'code': erreur.code},
                            status=getattr(erreur, 'statut', 400))
        delegation = DelegationHabilitation.objects.create(
            delegant=delegant, delegataire=delegataire,
            date_debut=donnees.get('date_debut') or timezone.localdate(),
            date_fin=donnees['date_fin'], motif=donnees['motif'],
            statut=DelegationHabilitation.Statut.PROPOSEE,
        )
        roles = RoleMetier.objects.filter(code__in=donnees['roles'])
        permissions = PermissionMetier.objects.filter(code__in=donnees['permissions'])
        delegation.roles.set(roles)
        delegation.permissions.set(permissions)
        journaliser(
            'DELEGATION_CREE', acteur=request.user, compte=delegataire,
            cible=delegation,
            nouvelle_valeur={
                'delegant': delegant.user.get_username(),
                'roles': list(roles.values_list('code', flat=True)),
            },
            motif=donnees['motif'], **_meta(request),
        )
        return Response(serialiser_delegation(delegation),
                        status=status.HTTP_201_CREATED)


class DelegationTerminateView(APIView):
    permission_classes = GARDE

    def post(self, request, pk):
        delegation = DelegationHabilitation.objects.filter(pk=pk).first()
        if delegation is None:
            return Response({'detail': 'Délégation introuvable.'}, status=404)
        motif = (request.data.get('motif') or '').strip()
        if not motif:
            return Response({'detail': 'Un motif est obligatoire.', 'code': 'MOTIF_REQUIS'},
                            status=400)
        delegation.statut = DelegationHabilitation.Statut.TERMINEE
        delegation.raison_arret = motif
        delegation.save(update_fields=['statut', 'raison_arret', 'date_modification'])
        journaliser(
            'DELEGATION_REVOQUEE', acteur=request.user,
            compte=delegation.delegataire, cible=delegation,
            motif=motif, **_meta(request),
        )
        return Response(serialiser_delegation(delegation))


# ---------------------------------------------------------------------------
# Opérations en masse : APERÇU SEUL (l'écriture en transaction est U5)
# ---------------------------------------------------------------------------
class ImportApercuView(APIView):
    permission_classes = GARDE

    def post(self, request):
        serializer = SimulationImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rapport = service.simuler_import(serializer.validated_data['lignes'])
        # Aucune écriture : la transaction et la réversibilité sont U5.
        rapport['ecriture'] = False
        rapport['message'] = (
            'Aperçu uniquement : la création en une transaction et la '
            'réversibilité de l’import sont livrées à l’unité U5.'
        )
        return Response(rapport)


# ---------------------------------------------------------------------------
# Revue des habilitations — consultation (campagne signée C5/U7)
# ---------------------------------------------------------------------------
class RevueConsultationView(APIView):
    permission_classes = GARDE

    def get(self, request):
        comptes = (
            CompteUtilisateur.objects
            .select_related('user', 'personne')
            .prefetch_related('attributions__role')
        )
        groupes = {}
        aujourdhui = timezone.localdate()
        for compte in comptes:
            actives = [
                a for a in compte.attributions.all()
                if a.statut == AttributionRole.Statut.ACTIVE and a.est_active(aujourdhui)
            ]
            responsable = 'Sans rôle'
            if any(a.role.domaine == 'ADMINISTRATION' for a in actives):
                responsable = 'Administration centrale'
            elif actives:
                responsable = actives[0].role.domaine.title()
            groupes.setdefault(responsable, []).append({
                'compte': compte.pk,
                'username': compte.user.get_username(),
                'nom': compte.personne.nom if compte.personne_id else '',
                'prenoms': compte.personne.prenoms if compte.personne_id else '',
                'statut': compte.statut,
                'roles': [a.role.code for a in actives],
                'sensible': any(a.role.sensible for a in actives),
            })
        return Response({
            'consultation_seule': True,
            'message': (
                'Campagne de revue signée, confirmations et révocations : '
                'unité C5/U7. Cet écran présente la répartition actuelle.'
            ),
            'groupes': groupes,
        })
