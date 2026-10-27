import logging

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .role_groups import get_creatable_roles, ROLE_LABELS, get_user_role, get_user_roles, users_with_role, user_in_roles

logger = logging.getLogger(__name__)

User = get_user_model()


def _requester_creatable_roles(requester):
    allowed = set()
    for role in get_user_roles(requester):
        allowed.update(get_creatable_roles(role))
    return allowed


class UserSelfProfileSerializer(serializers.ModelSerializer):
    """Champs modifiables par l'utilisateur sur son propre profil (sans rôle / secrétariat / statut)."""

    matricule = serializers.CharField(
        max_length=50,
        required=False,
        allow_null=True,
        allow_blank=True,
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'telephone', 'organisation', 'grade', 'matricule']

    def validate_matricule(self, value):
        if value in (None, ''):
            return None
        value = value.strip()
        qs = User.objects.filter(matricule__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Ce numéro de matricule est déjà utilisé.')
        return value


class UserSerializer(serializers.ModelSerializer):
    secretariat_nom = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'matricule',
            'role', 'roles', 'grade', 'telephone', 'organisation', 'is_active',
            'must_change_password',
            'secretariat', 'secretariat_nom',
        ]
        read_only_fields = ['id', 'secretariat_nom', 'must_change_password', 'role', 'roles']

    def get_role(self, obj):
        return get_user_role(obj) or obj.role

    def get_roles(self, obj):
        roles = sorted(get_user_roles(obj))
        if roles:
            return roles
        return [obj.role] if obj.role else []

    def get_secretariat_nom(self, obj):
        if obj.secretariat:
            return obj.secretariat.nom
        return None


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'matricule',
            'password', 'role', 'grade', 'telephone', 'organisation', 'secretariat',
        ]

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            msg = f"L'identifiant « {value} » est déjà utilisé."
            logger.warning('user_create_username_conflict username=%s', value)
            raise serializers.ValidationError(msg)
        return value

    def validate_matricule(self, value):
        if value in (None, ''):
            return None
        if User.objects.filter(matricule__iexact=value).exists():
            msg = f"Le numéro de matricule « {value} » est déjà utilisé."
            logger.warning('user_create_matricule_conflict matricule=%s', value)
            raise serializers.ValidationError(msg)
        return value

    def validate_role(self, value):
        request = self.context.get('request')
        requester = getattr(request, 'user', None)
        requester_role = get_user_role(requester)
        allowed = _requester_creatable_roles(requester)
        if value not in allowed:
            role_label = ROLE_LABELS.get(value, value)
            requester_label = ROLE_LABELS.get(requester_role, requester_role)
            allowed_labels = ', '.join(ROLE_LABELS.get(r, r) for r in allowed) or 'aucun'
            if value == User.Role.ADMIN:
                msg = (
                    "Le rôle Administrateur système est unique et ne peut pas être "
                    "créé depuis la plateforme."
                )
            else:
                msg = (
                    f"Vous ne pouvez pas attribuer le rôle « {role_label} » avec votre "
                    f"compte ({requester_label}). Rôles autorisés : {allowed_labels}."
                )
            logger.warning(
                'user_role_denied requester=%s requester_role=%s attempted_role=%s',
                getattr(requester, 'username', None),
                requester_role,
                value,
            )
            raise serializers.ValidationError(msg)
        return value

    def validate_secretariat(self, value):
        request = self.context.get('request')
        requester = getattr(request, 'user', None)
        if user_in_roles(requester, ('SECRETARIAT', 'CHEF_SECRETARIAT')):
            if value is not None and value != requester.secretariat:
                logger.warning(
                    'user_create_secretariat_denied requester=%s requester_secretariat=%s attempted_secretariat=%s',
                    getattr(requester, 'username', None),
                    getattr(requester.secretariat, 'pk', None),
                    getattr(value, 'pk', value),
                )
                raise serializers.ValidationError(
                    "Vous ne pouvez créer des utilisateurs que pour votre propre secrétariat."
                )
        return value

    def validate(self, attrs):
        role = attrs.get('role')
        secretariat = attrs.get('secretariat')
        if role in ('CHEF_INJS_ADMIN', 'INJS_ADMIN', 'FINANCE', 'ENCADRANT'):
            attrs['secretariat'] = None
        if role == 'CHEF_INJS_ADMIN':
            if users_with_role('CHEF_INJS_ADMIN').exists():
                logger.warning('user_create_chef_cpfae_admin_already_exists')
                raise serializers.ValidationError(
                    {'role': "Un Chef CPFAE Admin existe déjà. Ce rôle est unique sur toute la plateforme."}
                )
        if role == 'CHEF_SECRETARIAT' and secretariat:
            already_exists = users_with_role('CHEF_SECRETARIAT').filter(
                secretariat=secretariat
            ).exists()
            if already_exists:
                logger.warning(
                    'user_create_chef_secretariat_already_exists secretariat_id=%s',
                    getattr(secretariat, 'pk', secretariat),
                )
                raise serializers.ValidationError(
                    {'role': "Ce secrétariat a déjà un Chef Secrétariat. Un seul Chef Secrétariat est autorisé par secrétariat."}
                )
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, required=False)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'matricule',
            'password', 'role', 'grade', 'telephone', 'organisation', 'is_active',
            'secretariat',
        ]
        read_only_fields = ['id']

    def validate_role(self, value):
        request = self.context.get('request')
        requester = getattr(request, 'user', None)
        requester_role = get_user_role(requester)
        allowed = _requester_creatable_roles(requester)
        if value not in allowed:
            role_label = ROLE_LABELS.get(value, value)
            requester_label = ROLE_LABELS.get(requester_role, requester_role)
            allowed_labels = ', '.join(ROLE_LABELS.get(r, r) for r in allowed) or 'aucun'
            if value == User.Role.ADMIN:
                msg = (
                    "Le rôle Administrateur système est unique et ne peut pas être "
                    "créé depuis la plateforme."
                )
            else:
                msg = (
                    f"Vous ne pouvez pas attribuer le rôle « {role_label} » avec votre "
                    f"compte ({requester_label}). Rôles autorisés : {allowed_labels}."
                )
            logger.warning(
                'user_role_denied requester=%s requester_role=%s attempted_role=%s',
                getattr(requester, 'username', None),
                requester_role,
                value,
            )
            raise serializers.ValidationError(msg)
        return value

    def validate_secretariat(self, value):
        request = self.context.get('request')
        requester = getattr(request, 'user', None)
        if user_in_roles(requester, ('SECRETARIAT', 'CHEF_SECRETARIAT')):
            if value is not None and value != requester.secretariat:
                logger.warning(
                    'user_update_secretariat_denied requester=%s requester_secretariat=%s attempted_secretariat=%s',
                    getattr(requester, 'username', None),
                    getattr(requester.secretariat, 'pk', None),
                    getattr(value, 'pk', value),
                )
                raise serializers.ValidationError(
                    "Vous ne pouvez modifier que les utilisateurs de votre propre secrétariat."
                )
        return value

    def validate(self, attrs):
        role = attrs.get('role', get_user_role(self.instance) if self.instance else None)
        secretariat = attrs.get('secretariat', self.instance.secretariat if self.instance else None)
        if role in ('CHEF_INJS_ADMIN', 'INJS_ADMIN', 'FINANCE', 'ENCADRANT'):
            attrs['secretariat'] = None
        if role == 'CHEF_INJS_ADMIN':
            already_exists = users_with_role('CHEF_INJS_ADMIN').exclude(
                pk=self.instance.pk if self.instance else None
            ).exists()
            if already_exists:
                logger.warning('user_update_chef_cpfae_admin_already_exists')
                raise serializers.ValidationError(
                    {'role': "Un Chef CPFAE Admin existe déjà. Ce rôle est unique sur toute la plateforme."}
                )
        if role == 'CHEF_SECRETARIAT' and secretariat:
            already_exists = users_with_role('CHEF_SECRETARIAT').filter(
                secretariat=secretariat
            ).exclude(pk=self.instance.pk if self.instance else None).exists()
            if already_exists:
                logger.warning(
                    'user_update_chef_secretariat_already_exists secretariat_id=%s',
                    getattr(secretariat, 'pk', secretariat),
                )
                raise serializers.ValidationError(
                    {'role': "Ce secrétariat a déjà un Chef Secrétariat. Un seul Chef Secrétariat est autorisé par secrétariat."}
                )
        return attrs

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate_new_password(self, value):
        old = self.initial_data.get('old_password', '')
        if value == old:
            raise serializers.ValidationError("Le nouveau mot de passe doit être différent de l'ancien.")
        return value
