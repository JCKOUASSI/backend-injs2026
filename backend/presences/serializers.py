from rest_framework import serializers
from .models import Pointage
from formations.serializers import ParticipantSerializer, FormateurSerializer


class PointageSerializer(serializers.ModelSerializer):
    participant_detail = ParticipantSerializer(source='participant', read_only=True)
    formateur_detail = FormateurSerializer(source='formateur', read_only=True)
    encadrant_detail = serializers.SerializerMethodField()
    formation_id = serializers.IntegerField(source='session.module.formation_id', read_only=True)
    formation_titre = serializers.CharField(source='session.module.formation.formation', read_only=True)
    type_personne = serializers.CharField(read_only=True)

    def get_encadrant_detail(self, obj):
        if not obj.encadrant:
            return None
        return {
            'id': obj.encadrant.id,
            'username': obj.encadrant.username,
            'nom_complet': obj.encadrant.get_full_name() or obj.encadrant.username,
            'matricule': obj.encadrant.matricule,
        }

    class Meta:
        model = Pointage
        fields = [
            'id', 'participant', 'participant_detail',
            'formateur', 'formateur_detail',
            'encadrant', 'encadrant_detail',
            'type_personne',
            'session', 'formation_id', 'formation_titre',
            'date_journee', 'device_id', 'timestamp_entree', 'timestamp_sortie',
            'last_heartbeat_at', 'last_latitude', 'last_longitude', 'last_accuracy_m',
            'last_battery_level', 'last_is_charging', 'outside_geofence_count',
            'duree_presence_minutes', 'statut',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'duree_presence_minutes', 'created_at', 'updated_at',
        ]


class ScanSerializer(serializers.Serializer):
    token_qr = serializers.UUIDField()
    numero_participant = serializers.CharField(max_length=50)
    device_id = serializers.CharField(max_length=255, required=False, default='')


class ScanResponseSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['ENTREE', 'SORTIE'])
    # Endpoint public: ne renvoie que des champs minimaux (numero/nom/prenom)
    participant = serializers.DictField(required=False, allow_null=True)
    formateur = serializers.DictField(required=False, allow_null=True)
    encadrant = serializers.DictField(required=False, allow_null=True)
    timestamp = serializers.DateTimeField()
    duree_presence_minutes = serializers.DecimalField(
        max_digits=8, decimal_places=2, allow_null=True,
    )
    message = serializers.CharField()


class SecureScanSerializer(serializers.Serializer):
    """Scan sécurisé — seul le token QR est requis, le numéro est déduit du user connecté."""
    token_qr = serializers.UUIDField()
    device_id = serializers.CharField(max_length=255, required=False, default='')
    latitude = serializers.FloatField(required=False)
    longitude = serializers.FloatField(required=False)
    accuracy_m = serializers.FloatField(required=False)
    battery_level = serializers.IntegerField(required=False, min_value=0, max_value=100)
    is_charging = serializers.BooleanField(required=False)


class SecureHeartbeatSerializer(serializers.Serializer):
    """Ping de présence mobile géolocalisé pour une session en cours."""
    token_qr = serializers.UUIDField()
    device_id = serializers.CharField(max_length=255, required=False, default='')
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    accuracy_m = serializers.FloatField(required=False, default=9999)
    battery_level = serializers.IntegerField(required=False, min_value=0, max_value=100)
    is_charging = serializers.BooleanField(required=False)


class ForcePointageSerializer(serializers.Serializer):
    personne_id = serializers.IntegerField()
    type_personne = serializers.ChoiceField(
        choices=['participant', 'formateur', 'encadrant'], default='participant'
    )
    action = serializers.ChoiceField(choices=['ENTREE', 'SORTIE'])
    motif = serializers.CharField(
        max_length=500,
        required=True,
        allow_blank=False,
        error_messages={
            'blank': 'Le motif est obligatoire pour forcer un badgeage.',
            'required': 'Le motif est obligatoire pour forcer un badgeage.',
        },
    )
    date_journee = serializers.DateField(required=False, allow_null=True, default=None)
    timestamp_entree = serializers.DateTimeField(required=False, allow_null=True, default=None)
    timestamp_sortie = serializers.DateTimeField(required=False, allow_null=True, default=None)
    module_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class ForceBadgeageBulkAuditeursSerializer(serializers.Serializer):
    """Forçage en masse des entrées auditeurs (80–95 % aléatoire par séance)."""
    module_id = serializers.IntegerField()
    session_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    date_journee = serializers.DateField(required=False, allow_null=True, default=None)
    motif = serializers.CharField(
        max_length=500,
        required=True,
        allow_blank=False,
        error_messages={
            'blank': 'Le motif est obligatoire pour forcer un badgeage.',
            'required': 'Le motif est obligatoire pour forcer un badgeage.',
        },
    )
    ignore_constraints = serializers.BooleanField(required=False, default=False)
    all_sessions = serializers.BooleanField(required=False, default=False)


class DashboardSerializer(serializers.Serializer):
    formation = serializers.DictField()
    presents = serializers.ListField()
    absents = serializers.ListField()
    en_salle = serializers.ListField()
    taux_presence = serializers.FloatField()
    total_attendus = serializers.IntegerField()
    total_pointes = serializers.IntegerField()
