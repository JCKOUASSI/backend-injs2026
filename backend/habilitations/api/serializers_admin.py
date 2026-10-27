"""Sérialiseurs et mise en forme des données de la console CURP (U4).

Les sérialiseurs DRF ici servent à *valider les entrées* ; les sorties sont
des dictionnaires explicites (les vues restent fines). Les formats des
attributions/dérogations/délégations réutilisent les helpers de
``serializers.py`` posés en U2.
"""
from rest_framework import serializers

from habilitations.models import (
    DelegationHabilitation,
    PermissionAttribuee,
)
from habilitations.models.enums import CanalAcces, NiveauAcces

from .serializers import (
    serialiser_attribution,
    serialiser_delegation,
    serialiser_derogation,
)

ROLES_LEGACY_CHOICES = None  # renseigné à la volée depuis le modèle User


def _role_legacy_choices():
    from django.contrib.auth import get_user_model
    return list(get_user_model().Role.choices)


# ---------------------------------------------------------------------------
# Validation des entrées
# ---------------------------------------------------------------------------
class PersonneInputSerializer(serializers.Serializer):
    matricule = serializers.CharField(required=False, allow_blank=True)
    nom = serializers.CharField(required=False, allow_blank=True)
    prenoms = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    telephone = serializers.CharField(required=False, allow_blank=True)
    service = serializers.CharField(required=False, allow_blank=True)


class AttributionInputSerializer(serializers.Serializer):
    role = serializers.CharField()
    niveau = serializers.ChoiceField(choices=NiveauAcces.choices, required=False)
    date_fin = serializers.DateField(required=False, allow_null=True)
    motif = serializers.CharField(required=False, allow_blank=True)
    perimetres_secretariats = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list,
    )
    # LOT 5 (L4-02) : périmètres bornés de tout type, en plus de l'alliage
    # historique secrétariat. Ex. [{"type": "DIRECTION", "object_id": 3}].
    perimetres = serializers.ListField(
        child=serializers.DictField(), required=False, default=list,
    )
    sensible_valide = serializers.BooleanField(required=False, default=False)

    def validate_perimetres(self, valeur):
        from habilitations.services.resolveurs import TYPES_OBJETS
        for spec in valeur:
            if not isinstance(spec, dict) or 'type' not in spec \
                    or 'object_id' not in spec:
                raise serializers.ValidationError(
                    'Chaque périmètre doit porter « type » et « object_id ».')
            if spec['type'] not in TYPES_OBJETS:
                raise serializers.ValidationError(
                    f'Type de périmètre « {spec["type"]} » non posable par la '
                    'console.')
        return valeur


class IdentifiantsInputSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True)
    mot_de_passe = serializers.CharField(min_length=6)
    role_legacy = serializers.CharField()


class CreationCompteSerializer(serializers.Serializer):
    identifiants = IdentifiantsInputSerializer()
    personne = PersonneInputSerializer(required=False)
    canal = serializers.ChoiceField(
        choices=CanalAcces.choices, required=False, default=CanalAcces.WEB,
    )
    roles = AttributionInputSerializer(many=True, required=False, default=list)
    motif = serializers.CharField()
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_identifiants(self, valeur):
        choix = {code for code, _ in _role_legacy_choices()}
        if valeur['role_legacy'] not in choix:
            raise serializers.ValidationError(
                "Rôle d'accès de transition inconnu."
            )
        return valeur


class ModificationCompteSerializer(serializers.Serializer):
    roles = AttributionInputSerializer(many=True, required=False)
    canal = serializers.ChoiceField(choices=CanalAcces.choices, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    motif = serializers.CharField(required=False, allow_blank=True)
    differential_accepte = serializers.BooleanField(required=False, default=False)


class StatutCompteSerializer(serializers.Serializer):
    transition = serializers.ChoiceField(
        choices=['activer', 'suspendre', 'desactiver', 'verrouiller', 'deverrouiller'],
    )
    motif = serializers.CharField()


class SimulationImportSerializer(serializers.Serializer):
    lignes = serializers.ListField(
        child=serializers.DictField(), min_length=1, max_length=2000,
    )


# ─────────────────────────────────────────────────────────────────────
# U5 — cycle de vie, file de provisionnement, imports écrits, délégation
# ─────────────────────────────────────────────────────────────────────
class ImportExecuterSerializer(serializers.Serializer):
    lignes = serializers.ListField(
        child=serializers.DictField(), min_length=1, max_length=2000,
    )
    nom_fichier = serializers.CharField(required=False, allow_blank=True, default='')


class AnnulationImportSerializer(serializers.Serializer):
    motif = serializers.CharField(min_length=8)


class PropositionDecisionSerializer(serializers.Serializer):
    motif = serializers.CharField(min_length=8)
    # Corrections autorisées à la validation (rôle d'accès notamment pour
    # les agents recrutés dont le rôle n'est pas déductible).
    ajustements = serializers.DictField(required=False)


class DelegationActiverSerializer(serializers.Serializer):
    motif = serializers.CharField(required=False, allow_blank=True, default='')


class ActionDelegueeSerializer(serializers.Serializer):
    action = serializers.CharField(min_length=3, max_length=200)
    detail = serializers.DictField(required=False)
    motif = serializers.CharField(required=False, allow_blank=True, default='')


class DerogationInputSerializer(serializers.Serializer):
    compte = serializers.IntegerField()
    permission = serializers.CharField()
    sens = serializers.ChoiceField(
        choices=[PermissionAttribuee.Sens.OCTROI, PermissionAttribuee.Sens.RETRAIT],
    )
    motif = serializers.CharField()
    date_debut = serializers.DateField(required=False)
    date_fin = serializers.DateField(required=False, allow_null=True)

    def validate(self, donnees):
        if (
            donnees['sens'] == PermissionAttribuee.Sens.OCTROI
            and not donnees.get('date_fin')
        ):
            raise serializers.ValidationError(
                {'date_fin': 'Une dérogation d’octroi doit être bornée dans le temps.'}
            )
        return donnees


class DelegationInputSerializer(serializers.Serializer):
    delegant = serializers.IntegerField()
    delegataire = serializers.IntegerField()
    roles = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    permissions = serializers.ListField(
        child=serializers.CharField(), required=False, default=list,
    )
    date_debut = serializers.DateField(required=False)
    date_fin = serializers.DateField()
    motif = serializers.CharField()

    def validate(self, donnees):
        if donnees['delegant'] == donnees['delegataire']:
            raise serializers.ValidationError(
                'Le délégant et le délégataire doivent être deux comptes distincts.'
            )
        if donnees.get('date_debut') and donnees['date_fin'] < donnees['date_debut']:
            raise serializers.ValidationError(
                {'date_fin': 'La date de fin doit être postérieure au début.'}
            )
        return donnees


# ---------------------------------------------------------------------------
# Mise en forme des sorties
# ---------------------------------------------------------------------------
def serialiser_personne(personne):
    if personne is None:
        return None
    return {
        'id': personne.pk,
        'matricule': personne.matricule,
        'nom': personne.nom,
        'prenoms': personne.prenoms,
        'email': personne.email_institutionnel or personne.email_personnel,
        'telephone': personne.telephone,
        'service': personne.service,
        'statut': personne.statut,
    }


def serialiser_compte(compte, detail=False):
    aujourdhui = __import__('django.utils.timezone', fromlist=['localdate']).localdate()
    attributions = list(compte.attributions.select_related('role').prefetch_related('perimetres'))
    roles_actifs = [
        serialiser_attribution(a)
        for a in attributions if a.est_active(aujourdhui)
    ]
    roles_inactifs = [
        serialiser_attribution(a)
        for a in attributions if not a.est_active(aujourdhui)
    ]
    data = {
        'id': compte.pk,
        # PK de l'utilisateur Django (cible des endpoints /auth/mfa/*).
        'user_id': compte.user_id,
        'username': compte.user.get_username(),
        'email': compte.user.email,
        'is_active': compte.user.is_active,
        'role_legacy': compte.user.role,
        'personne': serialiser_personne(compte.personne),
        'statut': compte.statut,
        'canal': compte.canal,
        'mfa_actif': compte.mfa_actif,
        'notes': compte.notes,
        'date_creation': compte.date_creation.isoformat(),
        'derniere_connexion': (
            compte.derniere_connexion.isoformat()
            if compte.derniere_connexion else
            (compte.user.last_login.isoformat() if compte.user.last_login else None)
        ),
        'roles_actifs': roles_actifs,
        'nb_roles': len(roles_actifs),
        'nb_roles_sensibles': sum(1 for r in roles_actifs if r['sensible']),
        'domaines': sorted({r['role'].split('_')[0] for r in roles_actifs}),
    }
    if detail:
        data.update({
            'roles_inactifs': roles_inactifs,
            'derogations': [
                serialiser_derogation(d)
                for d in compte.derogations.select_related('permission', 'perimetre')
            ],
            'delegations_recues': [
                serialiser_delegation(d)
                for d in compte.delegations_recues.select_related(
                    'delegant__user', 'delegataire__user'
                ).prefetch_related('roles', 'permissions')
            ],
            'delegations_donnees': [
                serialiser_delegation(d)
                for d in compte.delegations_donnees.select_related(
                    'delegant__user', 'delegataire__user'
                ).prefetch_related('roles', 'permissions')
            ],
        })
    return data


def serialiser_journal(entree):
    return {
        'numero': entree.numero,
        'horodatage': entree.horodatage.isoformat(),
        'type': entree.type_evenement,
        'type_libelle': entree.get_type_evenement_display(),
        'acteur': entree.acteur_label or (
            entree.acteur.get_username() if entree.acteur_id else ''
        ),
        'objet_libelle': entree.objet_libelle,
        'motif': entree.motif,
        'ancienne_valeur': entree.ancienne_valeur,
        'nouvelle_valeur': entree.nouvelle_valeur,
        'compte': entree.compte_concerne_id,
    }


def serializer_role_detail(role, comptes=None):
    return {
        'code': role.code,
        'libelle': role.libelle,
        'description': role.description,
        'domaine': role.domaine,
        'niveau_defaut': role.niveau_defaut,
        'perimetre_defaut': role.perimetre_defaut,
        'canal_impose': role.canal_impose,
        'sensible': role.sensible,
        'disponible': role.disponible,
        'module_requis': role.module_requis,
        'incompatible_avec': list(
            role.incompatible_avec.values_list('code', flat=True)
        ),
        'permissions': sorted(
            role.permissions.values_list('code', flat=True)
        ),
        'permissions_count': role.permissions.count(),
        'comptes_titulaires': comptes if comptes is not None else [],
    }
