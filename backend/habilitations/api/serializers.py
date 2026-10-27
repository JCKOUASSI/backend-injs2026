"""Sérialiseurs de l'API REST d'habilitation (unité U2).

L'API d'U2 est **en lecture et évaluation** : aucune écriture de rôle,
d'attribution ou de dérogation n'expose de création/mutation (ce sera U4,
avec la double commande et le motif, règle S4).
"""
from rest_framework import serializers

from habilitations.models import PermissionMetier, RoleMetier


class RoleMetierSerializer(serializers.ModelSerializer):
    # U3 : codes des rôles incompatibles (séparation des tâches) et volume de
    # permissions ; la liste complète des codes atomiques reste accessible via
    # le catalogue ``/permissions/`` pour ne pas alourdir la liste des rôles.
    incompatible_avec = serializers.SlugRelatedField(
        slug_field='code', many=True, read_only=True,
    )
    permissions_count = serializers.SerializerMethodField()

    class Meta:
        model = RoleMetier
        fields = (
            'code', 'libelle', 'libelle_court', 'domaine', 'niveau_defaut',
            'perimetre_defaut', 'module_requis', 'disponible', 'sensible',
            'cumulable', 'canal_impose', 'actif', 'incompatible_avec',
            'permissions_count',
        )
        read_only_fields = fields

    def get_permissions_count(self, obj):
        compteur = getattr(obj, '_permissions_count', None)
        return compteur if compteur is not None else obj.permissions.count()


class PermissionMetierSerializer(serializers.ModelSerializer):
    #: Nombre réel de rôles qui octroient cette permission (annotation du
    #: queryset ; source de vérité : M2M ``RoleMetier.permissions``).
    total_roles = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = PermissionMetier
        fields = (
            'code', 'module', 'ressource', 'action', 'portee_maximale',
            'libelle', 'criticite', 'necessite_motif',
            'necessite_double_validation', 'journalisee', 'actif',
            'total_roles',
        )
        read_only_fields = fields


class DemandeEvaluationSerializer(serializers.Serializer):
    """Corps de ``POST /api/habilitations/evaluer/``."""

    permission = serializers.CharField(
        help_text="Code canonique module.ressource.action.",
    )
    canal = serializers.ChoiceField(
        choices=[('WEB', 'Web'), ('MOBILE', 'Mobile')],
        default='WEB',
    )
    niveau_minimum = serializers.CharField(required=False, allow_blank=True)
    # Cible nommée : {'type': 'SECRETARIAT', 'object_id': 12} ; résolution
    # complète des objets métier (et des secrétariats induits) branchée en U4.
    cible = serializers.DictField(required=False, allow_null=True)
    # L'évaluation d'un AUTRE compte est réservée aux administrateurs.
    username = serializers.CharField(required=False, allow_blank=True)


def _perimetre_resume(perimetre):
    return {
        'type': perimetre.type,
        'reference': perimetre.reference_lisible,
        'libelle': str(perimetre),
    }


def serialiser_attribution(attribution):
    return {
        'id': attribution.pk,
        'role': attribution.role.code,
        'role_libelle': attribution.role.libelle,
        'niveau': attribution.niveau_effectif,
        'statut': attribution.statut,
        'active': attribution.est_active(),
        'sensible': attribution.role.sensible,
        'validee': attribution.valide_par_id is not None,
        'date_debut': attribution.date_debut.isoformat(),
        'date_fin': attribution.date_fin.isoformat() if attribution.date_fin else None,
        'perimetres': [
            _perimetre_resume(p) for p in attribution.perimetres.all()
        ],
    }


def serialiser_derogation(derogation):
    return {
        'id': derogation.pk,
        'sens': derogation.sens,
        'permission': derogation.permission.code,
        'statut': derogation.statut,
        'active': derogation.est_active(),
        'date_debut': derogation.date_debut.isoformat(),
        'date_fin': derogation.date_fin.isoformat() if derogation.date_fin else None,
        'perimetre': _perimetre_resume(derogation.perimetre)
        if derogation.perimetre_id else None,
    }


def serialiser_delegation(delegation):
    return {
        'id': delegation.pk,
        'delegant': delegation.delegant.user.get_username(),
        'delegataire': delegation.delegataire.user.get_username(),
        'statut': delegation.statut,
        'active': delegation.est_active(),
        'date_debut': delegation.date_debut.isoformat(),
        'date_fin': delegation.date_fin.isoformat(),
        'roles': [r.code for r in delegation.roles.all()],
        'permissions': [p.code for p in delegation.permissions.all()],
        'perimetres': [
            _perimetre_resume(p) for p in delegation.perimetres.all()
        ],
    }
