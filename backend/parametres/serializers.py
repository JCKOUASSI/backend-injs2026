"""
Serializers DRF pour le module Paramètres.

Sérialisation/désérialisation des modèles Parametre et ParametreHistorique.
"""

from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from config.client_ip import get_client_ip
from .models import Parametre, ParametreHistorique, CLES_CRITIQUES


class ParametreHistoriqueSerializer(serializers.ModelSerializer):
    """
    Sérialise l'historique d'un paramètre.
    """
    modifie_par_username = serializers.CharField(
        source='modifie_par.username',
        read_only=True,
        allow_null=True,
    )
    modifie_par_nom = serializers.CharField(
        source='modifie_par.get_full_name',
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = ParametreHistorique
        fields = [
            'id',
            'ancienne_valeur',
            'nouvelle_valeur',
            'modifie_par',
            'modifie_par_username',
            'modifie_par_nom',
            'modifie_le',
            'motif_modification',
        ]
        read_only_fields = [
            'id',
            'ancienne_valeur',
            'nouvelle_valeur',
            'modifie_par',
            'modifie_par_username',
            'modifie_par_nom',
            'modifie_le',
        ]


class ParametreSerializer(serializers.ModelSerializer):
    """
    Sérialise un paramètre avec ses métadonnées.
    """
    can_edit = serializers.SerializerMethodField()
    can_view = serializers.SerializerMethodField()
    est_critique = serializers.SerializerMethodField()
    cree_par_username = serializers.CharField(
        source='cree_par.username',
        read_only=True,
        allow_null=True,
    )
    modifie_par_username = serializers.CharField(
        source='modifie_par.username',
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Parametre
        fields = [
            'id',
            'cle',
            'libelle',
            'description',
            'categorie',
            'type',
            'ordre',
            'valeur',
            'valeur_defaut',
            'choices_json',
            'modifiable',
            'actif',
            'est_critique',
            'can_edit',
            'can_view',
            'cree_par_username',
            'cree_le',
            'modifie_par_username',
            'modifie_le',
        ]
        read_only_fields = [
            'id',
            'cle',
            'cree_le',
            'cree_par_username',
            'modifie_le',
            'modifie_par_username',
        ]

    def get_can_edit(self, obj):
        """Vérifie si l'utilisateur peut éditer ce paramètre."""
        request = self.context.get('request')
        if not request or not request.user:
            return False
        return obj.can_be_modified_by(request.user)

    def get_can_view(self, obj):
        """Vérifie si l'utilisateur peut consulter ce paramètre."""
        request = self.context.get('request')
        if not request or not request.user:
            return False
        return obj.can_be_read_by(request.user)

    def get_est_critique(self, obj):
        return obj.cle in CLES_CRITIQUES


class ParametreUpdateSerializer(serializers.ModelSerializer):
    """Accepte uniquement valeur, motif et confirmation (paramètres critiques)."""
    motif_modification = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        max_length=500,
    )
    confirmation = serializers.BooleanField(required=False, write_only=True)

    class Meta:
        model = Parametre
        fields = ['valeur', 'motif_modification', 'confirmation']

    def validate(self, attrs):
        allowed = {'valeur', 'motif_modification', 'confirmation'}
        extra = set(getattr(self, 'initial_data', {}).keys()) - allowed
        if extra:
            raise serializers.ValidationError(
                {field: 'Champ non autorisé.' for field in extra}
            )
        instance = self.instance
        if instance and not instance.modifiable:
            raise serializers.ValidationError(
                {'valeur': 'Ce paramètre n’est pas modifiable.'}
            )
        if 'valeur' not in attrs:
            raise serializers.ValidationError({'valeur': 'Valeur obligatoire.'})
        try:
            attrs['valeur'] = instance.normalize_valeur(attrs['valeur'])
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict or exc.messages)
        if instance.cle in CLES_CRITIQUES:
            if not attrs.get('confirmation'):
                raise serializers.ValidationError({
                    'confirmation': 'Confirmation obligatoire pour ce paramètre critique.',
                })
            if not (attrs.get('motif_modification') or '').strip():
                raise serializers.ValidationError({
                    'motif_modification': 'Un motif est obligatoire pour ce paramètre critique.',
                })
        return attrs

    def update(self, instance, validated_data):
        motif = validated_data.pop('motif_modification', '')
        validated_data.pop('confirmation', None)
        request = self.context.get('request')

        ancienne_valeur = instance.valeur
        nouvelle_valeur = validated_data.get('valeur', instance.valeur)

        if request and request.user:
            instance.modifie_par = request.user

        instance.valeur = nouvelle_valeur
        instance.save(update_fields=['valeur', 'modifie_par', 'modifie_le'])

        if ancienne_valeur != nouvelle_valeur:
            ParametreHistorique.objects.create(
                parametre=instance,
                ancienne_valeur=ancienne_valeur,
                nouvelle_valeur=nouvelle_valeur,
                modifie_par=instance.modifie_par,
                motif_modification=motif,
                adresse_ip=get_client_ip(request) if request else '',
            )

        return instance
