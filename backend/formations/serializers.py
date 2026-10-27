from django.utils import timezone
from rest_framework import serializers
from .models import Formation, RefFormation, Participant, Secretariat, ModuleParticipant, ModuleFormateur, Formateur, QRToken, SessionModule, Module
from .formateur_privacy import can_view_formateur_sensitive_data, can_edit_formateur_sensitive_data
FormationParticipant = ModuleParticipant
FormationFormateur = ModuleFormateur
from authentication.serializers import UserSerializer


class ModuleSerializer(serializers.ModelSerializer):
    """Serializer for Module."""
    sessions = serializers.SerializerMethodField()
    formation_intitule = serializers.CharField(source='formation.formation', read_only=True)
    formateur_nom = serializers.SerializerMethodField()
    statut_label = serializers.CharField(source='get_statut_display', read_only=True)
    secretariat_nom = serializers.CharField(source='secretariat.nom', read_only=True, allow_null=True)
    secretariat_type = serializers.CharField(source='secretariat.type.libelle', read_only=True, allow_null=True)
    nb_participants = serializers.SerializerMethodField()
    site = serializers.SerializerMethodField()
    site_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = Module
        fields = [
            'id', 'formation', 'formation_intitule', 'intitule',
            'grade', 'groupe', 'vague',
            'secretariat', 'secretariat_nom', 'secretariat_type',
            'duree_prevue_heures', 'ordre', 'statut', 'statut_label',
            'site', 'site_id', 'batiment', 'salle',
            'date_debut', 'date_fin',
            'formateur', 'formateur_nom',
            'nb_participants',
            'sessions', 'created_at',
            'archived', 'archived_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_nb_participants(self, obj):
        if hasattr(obj, '_nb_participants'):
            return obj._nb_participants
        return ModuleParticipant.objects.filter(module=obj).count()

    def get_sessions(self, obj):
        return SessionSerializer(obj.sessions.all(), many=True).data

    def get_formateur_nom(self, obj):
        if obj.formateur:
            return f"{obj.formateur.prenom} {obj.formateur.nom}".strip()
        return None

    def get_site(self, obj):
        # Compat API: renvoyer un libellé (string) comme avant.
        if getattr(obj, 'site', None) is not None and getattr(obj.site, 'nom', None):
            return obj.site.nom
        return (getattr(obj, 'site_legacy', '') or '').strip()


class SecretariatSerializer(serializers.ModelSerializer):
    nb_participants = serializers.SerializerMethodField()
    nb_formations = serializers.SerializerMethodField()
    nb_modules = serializers.SerializerMethodField()
    membres = serializers.SerializerMethodField()

    class Meta:
        model = Secretariat
        fields = ['id', 'numero', 'nom', 'type', 'description', 'responsable', 'nb_participants', 'nb_formations', 'nb_modules', 'membres', 'created_at']
        read_only_fields = ['id', 'numero', 'created_at']

    def validate_responsable(self, value):
        if value is not None and value.role != 'CHEF_SECRETARIAT':
            raise serializers.ValidationError(
                "Le responsable doit avoir le rôle Chef Secrétariat."
            )
        return value

    def get_nb_participants(self, obj):
        if hasattr(obj, '_nb_participants'):
            return obj._nb_participants
        return obj.nb_participants

    def get_nb_formations(self, obj):
        if hasattr(obj, '_nb_formations'):
            return obj._nb_formations
        return obj.nb_formations

    def get_nb_modules(self, obj):
        if hasattr(obj, '_nb_modules'):
            return obj._nb_modules
        return obj.nb_modules

    def get_membres(self, obj):
        return [
            {'id': u.id, 'nom': u.get_full_name() or u.username, 'role': u.role, 'is_active': u.is_active}
            for u in obj.membres.all()
        ]


class SessionSerializer(serializers.ModelSerializer):
    """Serializer for session data."""
    date = serializers.DateField(source='date_journee', read_only=True)
    heure_debut = serializers.TimeField(source='heure_debut_prevue', read_only=True)
    heure_fin = serializers.TimeField(source='heure_fin_prevue', read_only=True)
    formateur_nom = serializers.SerializerMethodField()
    en_cours = serializers.BooleanField(source='est_en_cours', read_only=True)
    terminee = serializers.BooleanField(source='est_terminee', read_only=True)
    nb_presences = serializers.SerializerMethodField()
    nb_attendus = serializers.SerializerMethodField()
    module_id = serializers.IntegerField(source='module.id', read_only=True, allow_null=True)
    module_intitule = serializers.CharField(source='module.intitule', read_only=True, allow_null=True)
    module_groupe = serializers.CharField(source='module.groupe', read_only=True, allow_null=True)

    class Meta:
        model = SessionModule
        fields = [
            'id', 'numero', 'intitule', 'date', 'heure_debut', 'heure_fin',
            'en_cours', 'terminee', 'formateur_nom', 'nb_presences', 'nb_attendus',
            'module_id', 'module_intitule', 'module_groupe',
        ]

    def get_formateur_nom(self, obj):
        if obj.module and obj.module.formateur:
            f = obj.module.formateur
            return f"{f.prenom} {f.nom}".strip()
        mf = ModuleFormateur.objects.filter(module=obj.module).select_related('formateur').first() if obj.module else None
        return f"{mf.formateur.prenom} {mf.formateur.nom}".strip() if mf and mf.formateur else None

    def get_nb_presences(self, obj):
        if hasattr(obj, '_nb_presences_part'):
            return obj._nb_presences_part + getattr(obj, '_nb_presences_fmt', 0)
        from presences.models import Pointage
        qs = Pointage.objects.filter(session=obj)
        nb_participants = qs.filter(participant__isnull=False).values('participant').distinct().count()
        nb_formateurs = qs.filter(formateur__isnull=False).values('formateur').distinct().count()
        return nb_participants + nb_formateurs

    def get_nb_attendus(self, obj):
        if hasattr(obj, '_nb_attendus_part'):
            return obj._nb_attendus_part + getattr(obj, '_nb_attendus_fmt', 0)
        nb_p = ModuleParticipant.objects.filter(module=obj.module).values('participant').distinct().count()
        nb_f = ModuleFormateur.objects.filter(module=obj.module).values('formateur').distinct().count()
        return nb_p + nb_f


class ParticipantSerializer(serializers.ModelSerializer):
    secretariat_nom = serializers.CharField(source='secretariat.nom', read_only=True)

    class Meta:
        model = Participant
        fields = [
            'id', 'matricule', 'nom', 'prenom',
            'sexe', 'date_naissance', 'lieu_naissance',
            'email', 'telephone', 'telephone2',
            'type_concours', 'libelle_concours',
            'categorie', 'grade', 'groupe', 'grade_groupe', 'vague',
            'site', 'salle', 'motif_notoire',
            'secretariat', 'secretariat_nom', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_matricule(self, value):
        from formations.participant_matricule import normalize_matricule, validate_participant_matricule

        matricule = normalize_matricule(value)
        linked_user_id = None
        if self.instance and self.instance.user_id:
            linked_user_id = self.instance.user_id
        try:
            return validate_participant_matricule(
                matricule,
                participant_id=getattr(self.instance, 'pk', None),
                linked_user_id=linked_user_id,
            )
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc


class FormateurSerializer(serializers.ModelSerializer):
    secretariats = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Secretariat.objects.all(),
        required=False,
    )
    secretariats_noms = serializers.SerializerMethodField()
    nb_formations = serializers.SerializerMethodField()

    class Meta:
        model = Formateur
        fields = [
            'id', 'numerobadge', 'nom', 'prenom', 'email',
            'telephone', 'specialite', 'organisation',
            'numero_piece_identite', 'numero_compte_bancaire',
            'observations',
            'secretariats', 'secretariats_noms', 'nb_formations', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        user = request.user if request else None
        if not can_view_formateur_sensitive_data(user, instance):
            data.pop('numero_piece_identite', None)
            data.pop('numero_compte_bancaire', None)
        return data

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None
        instance = self.instance
        if not can_edit_formateur_sensitive_data(user, instance):
            attrs.pop('numero_piece_identite', None)
            attrs.pop('numero_compte_bancaire', None)
        return super().validate(attrs)

    def get_secretariats_noms(self, obj):
        return [f"{s.nom} ({s.numero})" for s in obj.secretariats.all()]

    def get_nb_formations(self, obj):
        return obj.modules_assignes.count()

    def create(self, validated_data):
        secretariats = validated_data.pop('secretariats', [])
        formateur = super().create(validated_data)
        formateur.secretariats.set(secretariats)
        return formateur

    def update(self, instance, validated_data):
        secretariats = validated_data.pop('secretariats', None)
        instance = super().update(instance, validated_data)
        if secretariats is not None:
            instance.secretariats.set(secretariats)
        return instance


class ModuleParticipantSerializer(serializers.ModelSerializer):
    participant = ParticipantSerializer(read_only=True)
    participant_id = serializers.PrimaryKeyRelatedField(
        queryset=Participant.objects.all(),
        source='participant',
        write_only=True,
    )
    module_intitule = serializers.CharField(source='module.intitule', read_only=True)
    formation_id = serializers.IntegerField(source='module.formation_id', read_only=True)

    class Meta:
        model = ModuleParticipant
        fields = ['id', 'module', 'module_intitule', 'formation_id', 'participant', 'participant_id', 'inscrit_le']
        read_only_fields = ['id', 'inscrit_le']

    def validate(self, attrs):
        """
        Empêche un participant d'être inscrit à plusieurs modules qui se chevauchent en date.
        """
        participant = attrs.get('participant')
        module = attrs.get('module')

        if not participant or not module:
            return attrs

        inscriptions_existantes = ModuleParticipant.objects.filter(
            participant=participant
        ).exclude(
            module=module
        ).select_related('module')

        for inscription in inscriptions_existantes:
            m_exist = inscription.module
            if not m_exist.date_debut or not m_exist.date_fin or not module.date_debut or not module.date_fin:
                continue
            if (module.date_debut < m_exist.date_fin and module.date_fin > m_exist.date_debut):
                raise serializers.ValidationError({
                    'participant_id': (
                        f"Ce participant est déjà inscrit au module "
                        f"« {m_exist.intitule} » durant cette période "
                        f"(du {m_exist.date_debut.strftime('%d/%m/%Y')} "
                        f"au {m_exist.date_fin.strftime('%d/%m/%Y')})"
                    )
                })

        return attrs


FormationParticipantSerializer = ModuleParticipantSerializer


class FormationListSerializer(serializers.ModelSerializer):
    intitule = serializers.CharField(source='formation', read_only=True)
    module = serializers.SerializerMethodField()
    modules_list = serializers.SerializerMethodField()
    module_input = serializers.CharField(write_only=True, required=False, allow_blank=True)
    nb_participants = serializers.SerializerMethodField()
    nb_presents = serializers.SerializerMethodField()
    ref_formation = serializers.PrimaryKeyRelatedField(
        queryset=RefFormation.objects.filter(actif=True), required=False, allow_null=True)
    ref_formation_intitule = serializers.SerializerMethodField()

    class Meta:
        model = Formation
        fields = [
            'id', 'numero_formation', 'intitule', 'formation',
            'module', 'modules_list', 'module_input',
            'nb_participants', 'nb_presents',
            'ref_formation', 'ref_formation_intitule',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_ref_formation_intitule(self, obj):
        return obj.ref_formation.intitule if obj.ref_formation_id else ''

    def get_module(self, obj):
        """Retourne l'intitulé du premier module lié (compatibilité)."""
        first = obj.modules.order_by('ordre', 'intitule').first()
        if first:
            return first.intitule
        return ''

    def get_modules_list(self, obj):
        """Retourne la liste de tous les modules avec leurs infos propres (grade, groupe, secrétariat…)."""
        from presences.models import Pointage
        today = timezone.localdate()
        rows = []
        for m in obj.modules.select_related('secretariat__type').order_by('ordre', 'intitule'):
            nb_p = ModuleParticipant.objects.filter(module=m).count()
            nb_presents = (
                Pointage.objects
                .filter(session__module=m, date_journee=today, participant__isnull=False)
                .values('participant').distinct().count()
            )
            rows.append({
                'id': m.id,
                'intitule': m.intitule,
                'ordre': m.ordre,
                'grade': m.grade,
                'groupe': m.groupe,
                'vague': m.vague,
                'secretariat_nom': (m.secretariat.nom if m.secretariat else None),
                'secretariat_type': (m.secretariat.type.libelle if m.secretariat and m.secretariat.type else None),
                'date_debut': m.date_debut,
                'date_fin': m.date_fin,
                'statut': m.statut,
                'nb_participants': nb_p,
                'nb_presents': nb_presents,
            })
        return rows

    def _sync_module(self, instance, validated_data):
        module_intitule = validated_data.pop('module_input', None)
        if module_intitule is not None:
            first = instance.modules.order_by('ordre').first()
            if first:
                if first.intitule != module_intitule:
                    first.intitule = module_intitule
                    first.save(update_fields=['intitule'])
            else:
                Module.objects.create(formation=instance, intitule=module_intitule, ordre=1)

    def create(self, validated_data):
        module_intitule = validated_data.pop('module_input', None)
        instance = super().create(validated_data)
        if module_intitule:
            Module.objects.create(formation=instance, intitule=module_intitule, ordre=1)
        return instance

    def update(self, instance, validated_data):
        self._sync_module(instance, validated_data)
        return super().update(instance, validated_data)

    def get_nb_participants(self, obj):
        return ModuleParticipant.objects.filter(module__formation=obj).count()

    def get_nb_presents(self, obj):
        from presences.models import Pointage
        today = timezone.localdate()
        return (
            Pointage.objects
            .filter(session__module__formation=obj, date_journee=today, participant__isnull=False)
            .values('participant')
            .distinct()
            .count()
        )



class FormationDetailSerializer(FormationListSerializer):
    participants_attendus = serializers.SerializerMethodField()
    sessions = serializers.SerializerMethodField()
    modules = serializers.SerializerMethodField()
    participants = serializers.SerializerMethodField()
    formateurs = serializers.SerializerMethodField()

    class Meta(FormationListSerializer.Meta):
        fields = FormationListSerializer.Meta.fields + [
            'participants_attendus', 'sessions', 'modules', 'participants', 'formateurs',
        ]

    def get_participants_attendus(self, obj):
        inscriptions = ModuleParticipant.objects.filter(
            module__formation=obj
        ).select_related('participant').distinct()
        seen = set()
        participants = []
        for mp in inscriptions:
            if mp.participant_id not in seen:
                seen.add(mp.participant_id)
                participants.append(mp.participant)
        return ParticipantSerializer(participants, many=True).data

    def get_participants(self, obj):
        """Alias for frontend compatibility."""
        return self.get_participants_attendus(obj)

    def get_modules(self, obj):
        from .serializer_querysets import annotate_modules_for_serializer
        cached = getattr(obj, '_prefetched_objects_cache', {})
        if 'modules' in cached:
            modules = obj.modules.all()
        else:
            modules = annotate_modules_for_serializer(
                Module.objects.filter(formation=obj).order_by('ordre', 'intitule')
            )
        return ModuleSerializer(modules, many=True).data

    def get_sessions(self, obj):
        from .serializer_querysets import annotate_sessions_for_serializer
        sessions = annotate_sessions_for_serializer(
            SessionModule.objects.filter(module__formation=obj)
        ).order_by('date_journee', 'numero')
        return SessionSerializer(sessions, many=True).data

    def get_formateurs(self, obj):
        return [
            {'id': mf.formateur.id, 'nom': mf.formateur.nom, 'prenom': mf.formateur.prenom, 'numero': mf.formateur.numerobadge}
            for mf in ModuleFormateur.objects.filter(module__formation=obj).select_related('formateur').distinct()
        ]


class QRTokenSerializer(serializers.ModelSerializer):
    formation_id = serializers.IntegerField(source='session.module.formation_id', read_only=True)
    formation_titre = serializers.CharField(source='session.module.formation.formation', read_only=True)
    module_id = serializers.IntegerField(source='session.module_id', read_only=True)
    module_intitule = serializers.CharField(source='session.module.intitule', read_only=True)
    module_groupe = serializers.CharField(source='session.module.groupe', read_only=True)
    session_intitule = serializers.SerializerMethodField()
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = QRToken
        fields = [
            'id', 'formation_id', 'formation_titre',
            'module_id', 'module_intitule', 'module_groupe',
            'session', 'session_intitule',
            'token', 'genere_par', 'actif', 'expire_at', 'is_valid', 'created_at',
        ]
        read_only_fields = ['id', 'token', 'genere_par', 'created_at']

    def get_session_intitule(self, obj):
        return obj.session.intitule or f"Session {obj.session.numero}"


class AssignSuperviseurSerializer(serializers.Serializer):
    superviseur_id = serializers.IntegerField()
