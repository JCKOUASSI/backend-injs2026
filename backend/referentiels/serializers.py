"""Serializers des référentiels (lot L0/L7).

Contrat : le `code` est fourni à la création puis immuable ; l'archivage
ne passe pas par le serializer (action dédiée) — règle 2.
"""
import re

from rest_framework import serializers

from .models import (
    ReferentielJournal,
    RefModuleOfficiel,
    RefVolumeHoraireFormation,
    RefGradeEnseignant,
    RefModePaiement,
    RefTypeDecision,
    RefTypeDocument,
    RefTypeEspaceSportif,
    RefTypeEvaluation,
    RefTypeFrais,
    RefTypeNotification,
)

CODE_RE = re.compile(r'^[A-Z0-9_]{2,50}$')


class RefSocleSerializer(serializers.ModelSerializer):
    """Serializer partagé par tous les référentiels du socle."""

    class Meta:
        # `source_document` et `fiabilite` font partie du contrat : sans eux,
        # l'écran affichait une colonne « Fiabilité » toujours vide et les deux
        # champs de traçabilité saisis dans le formulaire étaient silencieusement
        # ignorés par l'API (les 8 routes historiques du routeur).
        fields = [
            'id', 'code', 'libelle', 'description',
            'actif', 'date_activation', 'date_desactivation',
            'archive', 'annee_academique',
            'source_document', 'fiabilite',
            'cree_le', 'modifie_le',
        ]
        read_only_fields = ['archive', 'date_activation', 'date_desactivation']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Le code métier est fourni à la création puis immuable.
        if self.instance is not None:
            self.fields['code'].read_only = True

    def validate_code(self, value):
        value = value.strip().upper()
        if not CODE_RE.match(value):
            raise serializers.ValidationError(
                "Code invalide : 2 à 50 caractères parmi A-Z, 0-9 et _."
            )
        return value

    def validate_libelle(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Le libellé est obligatoire.')
        return value


# Un serializer par modèle (mécanique commune, meta differente)
class RefTypeEvaluationSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefTypeEvaluation


class RefTypeDocumentSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefTypeDocument


class RefGradeEnseignantSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefGradeEnseignant


class RefTypeFraisSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefTypeFrais


class RefModePaiementSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefModePaiement


class RefTypeDecisionSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefTypeDecision


class RefTypeNotificationSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefTypeNotification


class RefTypeEspaceSportifSerializer(RefSocleSerializer):
    class Meta(RefSocleSerializer.Meta):
        model = RefTypeEspaceSportif


class ReferentielJournalSerializer(serializers.ModelSerializer):
    """Lecture seule — journal des modifications (règle 6)."""

    class Meta:
        model = ReferentielJournal
        fields = ['id', 'action', 'object_id', 'horodatage', 'detail', 'utilisateur']
        read_only_fields = fields


# ═══════════════════════════════════════════════════════════════════════════
# Refonte « Référentiels » — sérialiseurs générés depuis le registre.
#
# Un seul sérialiseur paramétré sert tous les référentiels déclarés au
# registre : champs du socle + champs métier propres au référentiel + libellés
# des clés étrangères (pour que le front n'ait jamais à recoder une liste).
# ═══════════════════════════════════════════════════════════════════════════
from .registre import REGISTRE, modele_de  # noqa: E402  (après le socle)

CHAMPS_SOCLE = [
    'id', 'code', 'libelle', 'description',
    'actif', 'date_activation', 'date_desactivation',
    'archive', 'annee_academique',
    'source_document', 'fiabilite',
    'cree_le', 'modifie_le',
]

_CACHE_SERIALISEURS = {}


def serializer_pour_ref(slug):
    """Construit (et mémorise) le sérialiseur d'une entrée du registre."""
    if slug in _CACHE_SERIALISEURS:
        return _CACHE_SERIALISEURS[slug]
    entree = REGISTRE[slug]
    modele = modele_de(entree)

    champs = list(CHAMPS_SOCLE) + list(entree['champs'])
    for fk in entree['selecteurs']:
        champs.extend([fk, f'{fk}_libelle'])

    attributs = {}
    for fk in entree['selecteurs']:
        attributs[f'{fk}_libelle'] = serializers.CharField(
            source=f'{fk}.libelle', read_only=True, default=None,
        )
    attributs['Meta'] = type('Meta', (), {
        'model': modele,
        'fields': champs,
        'read_only_fields': ['archive', 'date_activation', 'date_desactivation'],
    })
    serie = type(
        f'{modele.__name__}Serializer',
        (RefSocleSerializer,),
        attributs,
    )
    _CACHE_SERIALISEURS[slug] = serie
    return serie


class RefModuleOfficielSerializer(serializers.ModelSerializer):
    """Modules officiels des maquettes (lecture seule : issus de l'import)."""

    formation_intitule = serializers.CharField(source='formation.intitule', read_only=True)

    class Meta:
        model = RefModuleOfficiel
        fields = [
            'id', 'formation', 'formation_intitule', 'filiere_code',
            'semestre', 'libelle', 'ordre', 'etat_ventilation',
            'source_document', 'fiabilite',
        ]


class RefVolumeHoraireFormationSerializer(serializers.ModelSerializer):
    """Volumes horaires de modélisation (lecture seule)."""

    formation_intitule = serializers.CharField(source='formation.intitule', read_only=True)

    class Meta:
        model = RefVolumeHoraireFormation
        fields = [
            'id', 'formation', 'formation_intitule', 'intitule_module',
            'heures_cm', 'heures_td', 'heures_tp', 'heures_stage', 'heures_total',
            'source_document', 'fiabilite',
        ]
