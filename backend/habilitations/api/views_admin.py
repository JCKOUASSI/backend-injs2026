"""Vues de la console web d'administration CURP (unité U4, prompt C2).

Toutes les routes sont gardées par :class:`ExigeDrapeauAdmin` (drapeau
``flag.curp_ui_admin`` OUVERT et trio d'administration) : drapeau fermé,
elles renvoient 403 et l'interface ne les référence pas. Les gestes sont
journalisés ; le moteur d'autorisation reste en mode observation.
"""
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    JournalHabilitation,
    Personne,
    RoleMetier,
)
from habilitations.permissions import ExigeDrapeauAdmin
from habilitations.referentiel.catalogue_modules import MODULES
from habilitations.referentiel.chargement import niveaux_du_role
from habilitations.services import comptes_admin as service
from habilitations.services import impact as service_impact
from habilitations.services.journalisation import verifier_chaine

from .serializers_admin import (
    CreationCompteSerializer,
    ModificationCompteSerializer,
    StatutCompteSerializer,
    serialiser_compte,
    serialiser_journal,
    serializer_role_detail,
    serialiser_personne,
)

GARDE = [ExigeDrapeauAdmin]


def _meta(request):
    return {
        'ip': request.META.get('REMOTE_ADDR', ''),
        'ua': request.META.get('HTTP_USER_AGENT', '')[:250],
    }


def _queryset_comptes():
    return (
        CompteUtilisateur.objects
        .select_related('user', 'personne')
        .prefetch_related('attributions__role')
    )


# ---------------------------------------------------------------------------
# Comptes : liste, création, fiche, différentiel, modification, statut
# ---------------------------------------------------------------------------
class CompteListCreateView(APIView):
    permission_classes = GARDE

    def get(self, request):
        qs = _queryset_comptes()
        recherche = request.query_params.get('search', '').strip()
        if recherche:
            qs = qs.filter(
                Q(user__username__icontains=recherche)
                | Q(user__email__icontains=recherche)
                | Q(personne__nom__icontains=recherche)
                | Q(personne__prenoms__icontains=recherche)
                | Q(personne__matricule__icontains=recherche)
            )
        if request.query_params.get('statut'):
            qs = qs.filter(statut=request.query_params['statut'])
        if request.query_params.get('canal'):
            qs = qs.filter(canal=request.query_params['canal'])
        role = request.query_params.get('role')
        if role:
            qs = qs.filter(
                attributions__statut=AttributionRole.Statut.ACTIVE,
                attributions__role__code=role,
            ).distinct()
        domaine = request.query_params.get('domaine')
        if domaine:
            qs = qs.filter(
                attributions__statut=AttributionRole.Statut.ACTIVE,
                attributions__role__domaine=domaine,
            ).distinct()
        qs = qs.order_by('-date_creation')
        page = self._paginer(request, qs)
        return page

    def _paginer(self, request, qs):
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        paginator.page_size = int(request.query_params.get('page_size', 50))
        page_obj = paginator.paginate_queryset(qs, request, view=self)
        data = [serialiser_compte(c) for c in page_obj]
        return paginator.get_paginated_response(data)

    def post(self, request):
        serializer = CreationCompteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            compte = service.creer_compte(request.user, serializer.validated_data, _meta(request))
        except service.ErreurConsole as erreur:
            return Response({'detail': str(erreur), 'code': erreur.code},
                            status=erreur.statut)
        return Response(serialiser_compte(compte, detail=True),
                        status=status.HTTP_201_CREATED)


class CompteDetailView(APIView):
    permission_classes = GARDE

    def _objet(self, pk):
        return _queryset_comptes().filter(pk=pk).first()

    def get(self, request, pk):
        compte = self._objet(pk)
        if compte is None:
            return Response({'detail': 'Compte introuvable.', 'code': 'COMPTE_INCONNU'},
                            status=404)
        data = serialiser_compte(compte, detail=True)
        data['journal'] = [
            serialiser_journal(e)
            for e in JournalHabilitation.objects.filter(compte_concerne=compte)
            .order_by('-numero')[:100]
        ]
        # Couche IMPACT (additive) : vue des accès effectifs de ce compte,
        # dérivée du service CURP — aucun champ existant modifié.
        data['impact'] = service_impact.impact_utilisateur(compte.user_id)
        return Response(data)


class CompteDifferentialView(APIView):
    permission_classes = GARDE

    def post(self, request, pk):
        compte = CompteUtilisateur.objects.filter(pk=pk).first()
        if compte is None:
            return Response({'detail': 'Compte introuvable.'}, status=404)
        codes = [ligne['role'] for ligne in request.data.get('roles', [])]
        roles = list(RoleMetier.objects.filter(code__in=codes))
        derogations = {
            ligne.get('permission'): ligne.get('sens')
            for ligne in request.data.get('derogations', [])
        }
        return Response(service.calculer_differential(compte, roles, derogations))


class CompteModifierView(APIView):
    permission_classes = GARDE

    def patch(self, request, pk):
        compte = _queryset_comptes().filter(pk=pk).first()
        if compte is None:
            return Response({'detail': 'Compte introuvable.'}, status=404)
        serializer = ModificationCompteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data
        if 'roles' in donnees:
            donnees['roles'] = [dict(ligne) for ligne in donnees['roles']]
        try:
            compte = service.modifier_compte(compte, request.user, donnees, _meta(request))
        except service.ErreurConsole as erreur:
            return Response({'detail': str(erreur), 'code': erreur.code},
                            status=erreur.statut)
        return Response(serialiser_compte(compte, detail=True))


class CompteStatutView(APIView):
    permission_classes = GARDE

    def post(self, request, pk):
        compte = _queryset_comptes().filter(pk=pk).first()
        if compte is None:
            return Response({'detail': 'Compte introuvable.'}, status=404)
        serializer = StatutCompteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            compte = service.changer_statut(
                compte, request.user,
                serializer.validated_data['transition'],
                serializer.validated_data['motif'], _meta(request),
            )
        except service.ErreurConsole as erreur:
            return Response({'detail': str(erreur), 'code': erreur.code},
                            status=erreur.statut)
        return Response(serialiser_compte(compte, detail=True))


# ---------------------------------------------------------------------------
# Personnes (recherche préalable de l'assistant)
# ---------------------------------------------------------------------------
class PersonneRechercheView(APIView):
    permission_classes = GARDE

    def get(self, request):
        terme = request.query_params.get('q', '').strip()
        if len(terme) < 2:
            return Response({'resultats': []})
        qs = Personne.objects.filter(
            Q(nom__icontains=terme) | Q(prenoms__icontains=terme)
            | Q(matricule__icontains=terme)
            | Q(email_institutionnel__icontains=terme)
        )[:10]
        return Response({'resultats': [serialiser_personne(p) for p in qs]})


# ---------------------------------------------------------------------------
# Référentiel : rôle détaillé, titulaires, matrice compacte
# ---------------------------------------------------------------------------
class RoleDetailView(APIView):
    permission_classes = GARDE

    def get(self, request, code):
        role = RoleMetier.objects.filter(code=code).prefetch_related('permissions').first()
        if role is None:
            return Response({'detail': 'Rôle introuvable.'}, status=404)
        titulaires = [
            {
                'compte': c.pk,
                'username': c.user.get_username(),
                'nom': c.personne.nom if c.personne_id else '',
                'prenoms': c.personne.prenoms if c.personne_id else '',
                'statut': c.statut,
            }
            for c in (
                CompteUtilisateur.objects
                .filter(attributions__statut=AttributionRole.Statut.ACTIVE,
                        attributions__role=role)
                .select_related('user', 'personne').distinct()
            )
        ]
        return Response(serializer_role_detail(role, titulaires))


class MatriceView(APIView):
    permission_classes = GARDE

    def get(self, request):
        """Vue compacte rôle × module (niveaux), pour l'écran matrice."""
        titulaires = dict(
            AttributionRole.objects
            .filter(statut=AttributionRole.Statut.ACTIVE)
            .values_list('role_id')
            .annotate(total=Count('id'))
            .values_list('role_id', 'total')
        )
        lignes = []
        for role in RoleMetier.objects.prefetch_related('permissions').order_by('ordre'):
            niveaux, origine = niveaux_du_role(role.code, role.domaine)
            permissions_par_module = {}
            for permission in role.permissions.all():
                permissions_par_module.setdefault(permission.module, []).append(
                    permission.action,
                )
            actions_par_module = {
                module: sorted(set(actions))
                for module, actions in permissions_par_module.items()
            }
            lignes.append({
                'code': role.code,
                'libelle': role.libelle,
                'domaine': role.domaine,
                'sensible': role.sensible,
                'niveaux': {m: {'niveau': n, 'origine': origine.get(m, 'A2')}
                            for m, n in niveaux.items()},
                'permissions_count': role.permissions.count(),
                'actions_par_module': actions_par_module,
                'comptes_titulaires': titulaires.get(role.pk, 0),
            })
        return Response({
            'modules': [
                {'code': code, 'libelle': libelle, 'application': app}
                for code, (libelle, app, _conditionnel) in MODULES.items()
            ],
            'lignes': lignes,
        })


# ---------------------------------------------------------------------------
# Journal : consultation filtrable et intégrité du chaînage
# ---------------------------------------------------------------------------
class JournalView(APIView):
    permission_classes = GARDE

    def get(self, request):
        qs = JournalHabilitation.objects.select_related('acteur')
        if request.query_params.get('type'):
            qs = qs.filter(type_evenement=request.query_params['type'])
        if request.query_params.get('compte'):
            qs = qs.filter(compte_concerne_id=request.query_params['compte'])
        if request.query_params.get('date_min'):
            qs = qs.filter(horodatage__date__gte=request.query_params['date_min'])
        if request.query_params.get('date_max'):
            qs = qs.filter(horodatage__date__lte=request.query_params['date_max'])
        q = request.query_params.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(objet_libelle__icontains=q) | Q(acteur_label__icontains=q)
                | Q(motif__icontains=q)
            )
        qs = qs.order_by('-numero')
        from rest_framework.pagination import PageNumberPagination
        paginator = PageNumberPagination()
        paginator.page_size = int(request.query_params.get('page_size', 50))
        page_obj = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            [serialiser_journal(e) for e in page_obj]
        )


class JournalIntegriteView(APIView):
    permission_classes = GARDE

    def get(self, request):
        anomalies = verifier_chaine()
        return Response({
            'integre': not anomalies,
            'anomalies': anomalies,
            'total': JournalHabilitation.objects.count(),
            'verifie_le': timezone.now().isoformat(),
        })
