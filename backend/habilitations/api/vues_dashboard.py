"""Dashboard des habilitations (couche IMPACT, strictement additive).

Vue d'ensemble dérivée UNIQUEMENT des données CURP réelles : aucun indicateur
inventé ; une statistique non calculable proprement n'est pas exposée.

Garde identique à la console U4 (:class:`ExigeDrapeauAdmin`) : le dashboard
révèle la cartographie des habilitations (comptes privilégiés, rôles
sensibles, dérogations) et reste réservé à l'administration.
"""
from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    DemandeAcces,
    DelegationHabilitation,
    JournalHabilitation,
    PermissionAttribuee,
    PermissionMetier,
    PropositionProvisionnement,
    RoleMetier,
)
from habilitations.models.politique import PolitiqueSecurite
from habilitations.permissions import ExigeDrapeauAdmin
from habilitations.services.impact import sensibilite_permission

from .serializers_admin import serialiser_journal

GARDE = [IsAuthenticated, ExigeDrapeauAdmin]

#: Fenêtre d'alerte des délégations arrivant à échéance (cohérent avec le
#: préavis J-7 déjà utilisé par les notifications d'échéance CURP).
PREAVIS_ECHEANCE_JOURS = 7

#: Fenêtre d'alerte des habilitations (attributions de rôles) arrivant
#: prochainement à expiration — Lot A (synthèse KPI).
PREAVIS_HABILITATION_JOURS = 30


class DashboardHabilitationsView(APIView):
    """GET /api/habilitations/dashboard/ — vue d'ensemble des habilitations."""

    permission_classes = GARDE

    def get(self, request):
        aujourdhui = timezone.localdate()
        echeance = aujourdhui + timedelta(days=PREAVIS_ECHEANCE_JOURS)

        # ── Comptes ────────────────────────────────────────────────────
        comptes_par_statut = dict(
            CompteUtilisateur.objects.values('statut')
            .annotate(total=Count('id')).values_list('statut', 'total')
        )
        total_comptes = sum(comptes_par_statut.values())

        # ── Rôles ──────────────────────────────────────────────────────
        roles = RoleMetier.objects.aggregate(
            total=Count('id'),
            actifs=Count('id', filter=Q(actif=True)),
            sensibles=Count('id', filter=Q(sensible=True)),
            disponibles=Count('id', filter=Q(disponible=True)),
        )

        # ── Permissions ────────────────────────────────────────────────
        permissions = PermissionMetier.objects.aggregate(
            total=Count('id'),
            actives=Count('id', filter=Q(actif=True)),
            sensibles=Count(
                'id', filter=~Q(criticite=PermissionMetier.Criticite.NORMALE)
            ),
            avec_motif=Count('id', filter=Q(necessite_motif=True)),
        )
        permissions_par_module = list(
            PermissionMetier.objects.values('module')
            .annotate(total=Count('id')).order_by('module')
            .values_list('module', 'total')
        )

        # ── Comptes à privilèges (au moins un rôle sensible ACTIF) ─────
        roles_sensibles = RoleMetier.objects.filter(sensible=True)
        comptes_privileges = (
            CompteUtilisateur.objects
            .filter(
                attributions__statut=AttributionRole.Statut.ACTIVE,
                attributions__role__in=roles_sensibles,
            )
            .distinct().count()
        )

        # ── Dérogations actives ────────────────────────────────────────
        derogations = PermissionAttribuee.objects.filter(
            statut=PermissionAttribuee.Statut.ACTIVE
        ).aggregate(
            octrois=Count(
                'id', filter=Q(sens=PermissionAttribuee.Sens.OCTROI)
            ),
            retraits=Count(
                'id', filter=Q(sens=PermissionAttribuee.Sens.RETRAIT)
            ),
        )

        # ── Délégations actives + échéances proches ────────────────────
        delegations = DelegationHabilitation.objects.filter(
            statut=DelegationHabilitation.Statut.ACTIVE
        )
        delegations_actives = delegations.count()
        delegations_expirantes = delegations.filter(
            date_fin__lte=echeance, date_fin__gte=aujourdhui
        ).count()

        # ── Provisionnement ────────────────────────────────────────────
        propositions_en_attente = PropositionProvisionnement.objects.filter(
            statut=PropositionProvisionnement.Statut.EN_ATTENTE
        ).count()

        # ── Demandes d'accès (Lot C/D) ──────────────────────────────────
        demandes_en_attente = DemandeAcces.objects.filter(
            statut__in=(
                DemandeAcces.Statut.SOUMISE,
                DemandeAcces.Statut.EN_REVUE,
            ),
        ).count()
        demandes_total = DemandeAcces.objects.count()

        # ── Habilitations (attributions de rôles) — Lot A ───────────────
        attributions_actives = AttributionRole.objects.filter(
            statut=AttributionRole.Statut.ACTIVE,
        )
        habilitations_actives = attributions_actives.count()
        echeance_habilitations = aujourdhui + timedelta(
            days=PREAVIS_HABILITATION_JOURS,
        )
        habilitations_expirantes = attributions_actives.filter(
            date_fin__isnull=False,
            date_fin__gte=aujourdhui,
            date_fin__lte=echeance_habilitations,
        ).count()
        # « Échue » = encore ACTIVE mais dont la date de fin est dépassée :
        # elle ne produit plus d'autorisation (moteur) et nécessite une revue.
        habilitations_echues = attributions_actives.filter(
            date_fin__isnull=False,
            date_fin__lt=aujourdhui,
        ).count()

        # ── Alertes et actions prioritaires — Lot A ─────────────────────
        politique = PolitiqueSecurite.objet()
        seuil_inactivite_jours = politique.inactivite_suspension_jours
        limite_inactivite = timezone.now() - timedelta(
            days=seuil_inactivite_jours,
        )
        comptes_inactifs = CompteUtilisateur.objects.filter(
            statut=CompteUtilisateur.Statut.ACTIF,
        ).filter(
            Q(derniere_activite__lt=limite_inactivite)
            | Q(derniere_activite__isnull=True, date_creation__lt=limite_inactivite),
        ).count()

        limite_modif_role = timezone.now() - timedelta(days=7)
        roles_sensibles_modifies = RoleMetier.objects.filter(
            sensible=True,
            date_modification__gte=limite_modif_role,
        ).order_by('-date_modification')
        roles_sensibles_modifies_codes = list(
            roles_sensibles_modifies.values_list('code', flat=True)[:5]
        )

        # Conflits de séparation des tâches : comptes portant simultanément
        # deux rôles ACTIFS déclarés incompatibles (2 requêtes + calcul local).
        paires_incompatibles = (
            RoleMetier.incompatible_avec.through.objects
            .values_list('from_rolemetier_id', 'to_rolemetier_id')
        )
        incompatibilites = defaultdict(set)
        for role_a, role_b in paires_incompatibles:
            incompatibilites[role_a].add(role_b)
            incompatibilites[role_b].add(role_a)
        roles_par_compte = defaultdict(set)
        for attribution in attributions_actives.values('compte_id', 'role_id'):
            roles_par_compte[attribution['compte_id']].add(
                attribution['role_id'],
            )
        comptes_en_conflit = []
        for compte_id, roles_ids in roles_par_compte.items():
            for role_id in roles_ids:
                if roles_ids & incompatibilites.get(role_id, set()):
                    comptes_en_conflit.append(compte_id)
                    break
        codes_roles_impliques = dict(
            RoleMetier.objects.filter(
                pk__in={r for ids in roles_par_compte.values() for r in ids},
            ).values_list('pk', 'code')
        )
        exemples_conflits = [
            {
                'compte': compte_id,
                'roles': sorted(
                    codes_roles_impliques.get(r, str(r))
                    for r in roles_par_compte[compte_id]
                ),
            }
            for compte_id in comptes_en_conflit[:5]
        ]

        # ── Dernières actions d'administration (journal CURP) ──────────
        dernieres_actions = [
            serialiser_journal(entree)
            for entree in JournalHabilitation.objects.order_by('-numero')[:10]
        ]

        return Response({
            'comptes': {
                'total': total_comptes,
                'par_statut': comptes_par_statut,
                'actifs': comptes_par_statut.get(
                    CompteUtilisateur.Statut.ACTIF, 0
                ),
                'non_actifs': total_comptes - comptes_par_statut.get(
                    CompteUtilisateur.Statut.ACTIF, 0
                ),
            },
            'roles': roles,
            'permissions': {
                **permissions,
                'par_module': [
                    {'module': module, 'total': total}
                    for module, total in permissions_par_module
                ],
            },
            'comptes_privileges': comptes_privileges,
            'habilitations': {
                'actives': habilitations_actives,
                'expirant_prochainement': habilitations_expirantes,
                'echues': habilitations_echues,
                'preavis_expiration_jours': PREAVIS_HABILITATION_JOURS,
            },
            'alertes': {
                'comptes_inactifs': {
                    'total': comptes_inactifs,
                    'seuil_jours': seuil_inactivite_jours,
                },
                'comptes_prileges': comptes_privileges,
                'roles_sensibles_recemment_modifies': {
                    'total': roles_sensibles_modifies.count(),
                    'codes': roles_sensibles_modifies_codes,
                },
                'conflits_separation_taches': {
                    'total': len(comptes_en_conflit),
                    'exemples': exemples_conflits,
                },
                'habilitations_echues': habilitations_echues,
                'habilitations_expirantes': habilitations_expirantes,
                'provisionnement_en_attente': propositions_en_attente,
                'demandes_acces_en_attente': demandes_en_attente,
            },
            'derogations': derogations,
            'delegations': {
                'actives': delegations_actives,
                'expirant_prochainement': delegations_expirantes,
            },
            'provisionnement': {
                'propositions_en_attente': propositions_en_attente,
            },
            'demandes_acces': {
                'en_attente': demandes_en_attente,
                'total': demandes_total,
            },
            'dernieres_actions': dernieres_actions,
            'date_reference': aujourdhui,
        })
