"""Serializers des référentiels (lot L0/L7).

Contrat : le `code` est fourni à la création puis immuable ; l'archivage
ne passe pas par le serializer (action dédiée) — règle 2.
"""
import re

from rest_framework import serializers

from .models import (
    ReferentielJournal,
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
        fields = [
            'id', 'code', 'libelle', 'description',
            'actif', 'date_activation', 'date_desactivation',
            'archive', 'annee_academique',
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
