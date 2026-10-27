import logging
import os

from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError
from django.db.models import Q

from django.conf import settings as django_settings
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTTokenRefreshView

from .serializers import (
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    UserSelfProfileSerializer,
    LoginSerializer,
    ChangePasswordSerializer,
)
from .permissions import IsDFRC, IsSecretariatOrDFRC, IsUserMutationAllowed, get_creatable_roles
from .role_groups import (
    ALLOWED_WEB_ROLES,
    MOBILE_ONLY_ROLES,
    ROLE_GROUP_NAMES,
    user_role_context,
    get_user_role,
    get_user_roles,
    user_has_perm,
    user_in_roles,
    user_is_mobile_encadrant,
    users_with_roles,
)
from .throttles import LoginRateThrottle
from . import connexion_sure
from .emails import send_welcome_email
from .capabilities import CapabilitiesResponseSerializer, compute_capabilities
from drf_spectacular.utils import extend_schema
from presences.models import DeviceBinding, AuditLog, _log_audit
from config.client_ip import get_client_ip

User = get_user_model()


def _user_payload(user):
    """Profil utilisateur pour le client avec les rôles effectifs (groupes Django)."""
    data = UserSerializer(user).data
    effective = get_user_role(user)
    roles = sorted(get_user_roles(user))
    if effective:
        data['role'] = effective
    data['roles'] = roles or data.get('roles', [])
    return data


# Rôles sans rattachement secrétariat sur le compte User (aligné serializers UserCreate/Update).
USER_ROLES_WITHOUT_SECRETARIAT = frozenset({
    User.Role.CHEF_INJS_ADMIN,
    User.Role.INJS_ADMIN,
    User.Role.FINANCE,
    User.Role.ARCHIVE,
    User.Role.ENCADRANT,
})

logger = logging.getLogger(__name__)

# ── Cookie HttpOnly du refresh token (risque R6 — socle L0/L7) ───────────────
# Le web React n'utilise plus le refresh stocké en localStorage : il est posé
# en cookie HttpOnly (illisible en JavaScript, jamais exposé à un XSS) et
# renvoyé automatiquement sur /api/auth/token/refresh/.
# L'app mobile Flutter conserve le refresh dans le body des réponses (stockage
# sécurisé applicatif) — rétrocompatibilité totale des endpoints /login,
# /token/refresh et /me est assurée.
REFRESH_COOKIE_NAME = 'refresh_token'
REFRESH_COOKIE_PATH = '/api/auth/'


def _cookie_samesite():
    return os.environ.get('JWT_COOKIE_SAMESITE', 'Lax')


def _cookie_secure(samesite):
    # SameSite=None IMPOSE Secure. En aperçu derrière passerelle HTTPS, la
    # variable d'env force Secure même si DEBUG=True (SECURE_PROXY_SSL_HEADER
    # est alors activé et la requête est bien vue comme https).
    forced = os.environ.get('JWT_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes')
    if forced:
        return True
    if samesite == 'None':
        return True
    return not django_settings.DEBUG


def _set_refresh_cookie(response, token):
    """Pose le cookie HttpOnly du refresh token (scope limité à /api/auth/)."""
    samesite = _cookie_samesite()
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token,
        max_age=int(django_settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
        httponly=True,
        secure=_cookie_secure(samesite),
        samesite=samesite,
        path=REFRESH_COOKIE_PATH,
    )


def _delete_refresh_cookie(response):
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


@api_view(['POST'])
@permission_classes([AllowAny])
def logout_view(request):
    """Déconnexion web : invalide le cookie du refresh token côté navigateur.

    Sans effet de bord serveur (JWT stateless, pas de blacklist activée) ;
    le mobile continue de gérer la déconnexion localement.
    """
    response = Response({'detail': 'Déconnexion effectuée.'})
    _delete_refresh_cookie(response)
    return response


class CookieTokenRefreshView(SimpleJWTTokenRefreshView):
    """Rafraîchit l'access token — /api/auth/token/refresh/ (contrat inchangé).

    - Web   : refresh lu depuis le cookie HttpOnly (body vide accepté).
    - Mobile: refresh lu depuis le body JSON (comportement historique).
    - Rotation (ROTATE_REFRESH_TOKENS=True) : le nouveau refresh est renvoyé
      dans le body (mobile) ET reposé en cookie HttpOnly (web).
    """

    def post(self, request, *args, **kwargs):
        data = request.data if isinstance(request.data, dict) else {}
        if not data.get('refresh'):
            cookie_refresh = request.COOKIES.get(REFRESH_COOKIE_NAME)
            if cookie_refresh:
                # DRF cache le payload parsé dans _full_data ; on l'injecte ici.
                request._full_data = {'refresh': cookie_refresh}
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200 and isinstance(response.data, dict):
            new_refresh = response.data.get('refresh')
            if new_refresh:
                response.data['refresh_in_cookie'] = True
                _set_refresh_cookie(response, new_refresh)
        return response


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
@throttle_classes([LoginRateThrottle])
def login_view(request):
    """Connexion — retourne access + refresh tokens.
    Si device_id est fourni (app mobile), vérifie le verrouillage appareil."""
    client_ip = get_client_ip(request)
    user_agent = (request.META.get('HTTP_USER_AGENT') or '')[:200]

    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        logger.warning(
            'login_payload_invalid ip=%s ua=%r errors=%s',
            client_ip,
            user_agent,
            serializer.errors,
        )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    username_try = serializer.validated_data['username']

    # ── Verrouillage de compte (CURP U6, drapeau curp_verrouillage_connexion) ──
    # Vérifié AVANT l'authentification : un compte verrouillé ne laisse pas
    # filtrer le bon mot de passe et son délai n'est pas contournable.
    secondes_restantes = connexion_sure.verifier_verrouillage(
        username=username_try)
    if secondes_restantes is not None:
        compte_verrouille = connexion_sure.compte_curp(username=username_try)
        if compte_verrouille is not None:
            connexion_sure.journaliser_refus_verrouille(
                compte_verrouille, secondes_restantes)
        logger.warning(
            'login_refuse_verrouille username=%r secondes=%s ip=%s',
            username_try, secondes_restantes, client_ip,
        )
        return Response(
            {
                'code': 'COMPTE_VERROUILLE',
                'detail': (
                    'Ce compte est verrouillé après plusieurs échecs '
                    'd’authentification. Réessayez dans quelques minutes '
                    'ou contactez un administrateur.'
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    user = authenticate(
        username=username_try,
        password=serializer.validated_data['password'],
    )
    if user is None:
        connexion_sure.enregistrer_echec(
            username_try, {'ip': client_ip, 'ua': user_agent},
        )
        logger.warning(
            'login_failed_bad_credentials username=%r ip=%s ua=%r',
            username_try,
            client_ip,
            user_agent,
        )
        return Response(
            {'detail': 'Identifiants invalides.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    device_id = request.data.get('device_id', '').strip()
    user_role = get_user_role(user)
    user_roles = get_user_roles(user)

    if not device_id and not user_has_perm(user, 'authentication.access_web') and not user_in_roles(user, ALLOWED_WEB_ROLES):
        if user_roles <= MOBILE_ONLY_ROLES and User.Role.AUDITEUR in user_roles:
            detail = 'Les comptes auditeur sont réservés à l\'application mobile.'
        elif user_roles <= MOBILE_ONLY_ROLES and User.Role.FORMATEUR in user_roles:
            detail = 'Les comptes formateur sont réservés à l\'application mobile.'
        elif user_role == User.Role.AUDITEUR:
            detail = 'Les comptes auditeur sont réservés à l\'application mobile.'
        elif user_role == User.Role.FORMATEUR:
            detail = 'Les comptes formateur sont réservés à l\'application mobile.'
        else:
            detail = 'Ce compte n\'a pas accès à la plateforme web.'
        logger.warning(
            'login_web_forbidden role=%s username=%r ip=%s',
            user_role,
            user.username,
            client_ip,
        )
        return Response({'detail': detail}, status=status.HTTP_403_FORBIDDEN)

    if user_in_roles(user, ('AUDITEUR', 'FORMATEUR')) or user_is_mobile_encadrant(user):
        from .profile_sync import sync_user_profile_links
        sync_user_profile_links(user)

    # ── Verrouillage appareil (auditeurs / formateurs uniquement) ──
    if device_id and user_in_roles(user, ('AUDITEUR', 'FORMATEUR')):
        existing = DeviceBinding.objects.filter(
            device_id=device_id, is_active=True
        ).select_related('user').first()

        if existing and existing.user_id != user.id:
            logger.warning(
                'login_device_locked device_id=%r attempted_user_id=%s bound_user_id=%s ip=%s',
                device_id,
                user.pk,
                existing.user_id,
                client_ip,
            )
            return Response({
                'code': 'DEVICE_LOCKED',
                'detail': (
                    f'Cet appareil est déjà lié au compte de '
                    f'{existing.user.get_full_name()}. '
                    f'Contactez votre encadrant pour le débloquer.'
                ),
            }, status=status.HTTP_403_FORBIDDEN)

        # Bind device to this user if not already bound
        if not existing:
            DeviceBinding.objects.update_or_create(
                device_id=device_id,
                defaults={
                    'user': user,
                    'device_info': request.data.get('device_info', ''),
                    'is_active': True,
                },
            )

    # ── Étape MFA (CURP U6, drapeau curp_mfa_active) ──
    etat = connexion_sure.etat_mfa(user)
    if etat == 'obligatoire':
        return Response(
            {
                'code': 'MFA_OBLIGATOIRE',
                'detail': (
                    'Ce compte porte un rôle sensible : l’authentification '
                    'multifactor (MFA) doit être activée par un '
                    'administrateur avant de pouvoir se connecter.'
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    if etat == 'etape':
        compte = connexion_sure.compte_curp(user)
        connexion_sure.journaliser_etape_mfa(compte)
        return Response(
            {
                'code': 'MFA_REQUIRED',
                'detail': (
                    'Vérification en deux étapes : saisissez le code à 6 '
                    'chiffres de votre application d’authentification.'
                ),
                'mfa_token': connexion_sure.jeton_etape_mfa(user),
                'mfa_duree': connexion_sure.DUREE_JETON_MFA,
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return connexion_sure.finaliser_connexion(user, request, device_id=device_id)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def me_view(request):
    """Profil de l'utilisateur connecté : lecture ou mise à jour partielle des données personnelles."""
    user = request.user
    if request.method == 'GET':
        data = _user_payload(user)
        data['role_context'] = user_role_context(user)
        return Response(data)
    serializer = UserSelfProfileSerializer(user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    _log_audit(
        action=AuditLog.Action.USER_UPDATE,
        request=request,
        cible_type='user',
        cible_numero=user.username,
        cible_nom=user.get_full_name() or user.username,
        extra={'self_profile': True, 'champs_modifies': list(request.data.keys())},
    )
    data = _user_payload(user)
    data['role_context'] = user_role_context(user)
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def roles_view(request):
    """Hiérarchie et périmètre de gestion des rôles pour l'utilisateur connecté."""
    return Response(user_role_context(request.user))


@extend_schema(
    tags=['Authentification'],
    summary="Capacités de l'utilisateur courant pour l'interface (P00-06)",
    responses=CapabilitiesResponseSerializer,
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def capabilities_view(request):
    """Droits d'affichage effectifs : {module: [actions]}, niveau, périmètres.

    Projection en lecture seule des permissions existantes ; l'API reste
    l'autorité (les vues conservent leurs permission_classes).
    """
    return Response(compute_capabilities(request.user))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    """Permet à l'utilisateur connecté de changer son propre mot de passe."""
    serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    was_forced_change = bool(getattr(request.user, 'must_change_password', False))
    request.user.set_password(serializer.validated_data['new_password'])
    if getattr(request.user, 'must_change_password', False):
        request.user.must_change_password = False
    request.user.save()
    _log_audit(
        action=AuditLog.Action.USER_PASSWORD_CHANGE,
        request=request,
        cible_type='user',
        cible_numero=request.user.username,
        cible_nom=request.user.get_full_name() or request.user.username,
        extra={'first_login_change': was_forced_change},
    )
    return Response({'detail': 'Mot de passe modifié avec succès.'})


def _staff_users_queryset(user):
    """Utilisateurs visibles/gérables par un compte personnel (hors auto-gestion)."""
    actor_role = get_user_role(user)
    subordinates = get_creatable_roles(actor_role)
    qs = users_with_roles(subordinates)
    if actor_role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
        # Encadrants : assignables sur tout secrétariat, donc listés globalement.
        qs = qs.filter(
            Q(groups__name=ROLE_GROUP_NAMES[User.Role.ENCADRANT])
            | Q(secretariat=user.secretariat)
        ).distinct()
    return qs


class UserListCreateView(generics.ListCreateAPIView):
    """DFRC/Secrétariat : lister et créer des utilisateurs."""
    permission_classes = [IsSecretariatOrDFRC]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsUserMutationAllowed()]
        return [IsSecretariatOrDFRC()]

    def create(self, request, *args, **kwargs):
        try:
            response = super().create(request, *args, **kwargs)
        except ValidationError as exc:
            logger.warning(
                'user_create_validation_failed actor=%s actor_role=%s detail=%s',
                request.user.username,
                request.user.role,
                exc.detail,
            )
            raise
        except IntegrityError as exc:
            logger.error(
                'user_create_integrity_failed actor=%s actor_role=%s payload=%s error=%s',
                request.user.username,
                request.user.role,
                request.data,
                exc,
            )
            raise ValidationError(
                {'non_field_errors': ["Impossible de créer l'utilisateur : une contrainte d'unicité est violée (identifiant ou matricule déjà utilisé)."]}
            ) from exc
        except Exception as exc:
            logger.exception(
                'user_create_failed actor=%s actor_role=%s payload=%s',
                request.user.username,
                request.user.role,
                request.data,
            )
            raise
        logger.info(
            'user_create_ok actor=%s actor_role=%s new_user_id=%s new_role=%s new_username=%s',
            request.user.username,
            request.user.role,
            response.data.get('id'),
            response.data.get('role'),
            response.data.get('username'),
        )
        return response

    def get_queryset(self):
        user = self.request.user
        qs = _staff_users_queryset(user).order_by('last_name', 'first_name')
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(username__icontains=search) |
                Q(matricule__icontains=search)
            )
        role = self.request.query_params.get('role')
        if role:
            group_name = ROLE_GROUP_NAMES.get(role)
            if group_name:
                qs = qs.filter(groups__name=group_name)
        exclude_role = self.request.query_params.get('exclude_role')
        if exclude_role:
            for role_code in exclude_role.split(','):
                role_code = role_code.strip()
                group_name = ROLE_GROUP_NAMES.get(role_code)
                if group_name:
                    qs = qs.exclude(groups__name=group_name)
        if get_user_role(user) == 'DIRECTION':
            for mobile_role in ('AUDITEUR', 'FORMATEUR'):
                group_name = ROLE_GROUP_NAMES.get(mobile_role)
                if group_name:
                    qs = qs.exclude(groups__name=group_name)
        return qs

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return UserCreateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        user = self.request.user
        plain_password = serializer.validated_data.get('password', '')
        role = serializer.validated_data.get('role')
        actor_role = get_user_role(user)
        if (
            actor_role in ('SECRETARIAT', 'CHEF_SECRETARIAT')
            and user.secretariat
            and role not in USER_ROLES_WITHOUT_SECRETARIAT
        ):
            new_user = serializer.save(secretariat=user.secretariat)
        else:
            new_user = serializer.save()
        try:
            send_welcome_email(new_user, plain_password)
        except Exception as exc:
            logger.error(
                'user_create_welcome_email_failed user_id=%s username=%s email=%s error=%s',
                new_user.pk,
                new_user.username,
                new_user.email,
                exc,
            )
        _log_audit(
            action=AuditLog.Action.USER_CREATE,
            request=self.request,
            cible_type='user',
            cible_numero=new_user.username,
            cible_nom=new_user.get_full_name() or new_user.username,
            extra={'role': get_user_role(new_user), 'secretariat': str(new_user.secretariat) if new_user.secretariat else None},
        )


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """DFRC/Secrétariat : détail / modifier / supprimer un utilisateur."""
    permission_classes = [IsSecretariatOrDFRC]

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH', 'DELETE'):
            return [IsUserMutationAllowed()]
        return [IsSecretariatOrDFRC()]

    def update(self, request, *args, **kwargs):
        try:
            response = super().update(request, *args, **kwargs)
        except ValidationError as exc:
            logger.warning(
                'user_update_validation_failed actor=%s target_id=%s detail=%s',
                request.user.username,
                kwargs.get('pk'),
                exc.detail,
            )
            raise
        except IntegrityError as exc:
            logger.error(
                'user_update_integrity_failed actor=%s target_id=%s payload=%s error=%s',
                request.user.username,
                kwargs.get('pk'),
                request.data,
                exc,
            )
            raise ValidationError(
                {'non_field_errors': ["Impossible de modifier l'utilisateur : une contrainte d'unicité est violée (identifiant ou matricule déjà utilisé)."]}
            ) from exc
        except Exception as exc:
            logger.exception(
                'user_update_failed actor=%s target_id=%s payload=%s',
                request.user.username,
                kwargs.get('pk'),
                request.data,
            )
            raise
        logger.info(
            'user_update_ok actor=%s target_id=%s role=%s username=%s',
            request.user.username,
            kwargs.get('pk'),
            response.data.get('role'),
            response.data.get('username'),
        )
        return response

    def destroy(self, request, *args, **kwargs):
        target_id = kwargs.get('pk')
        try:
            instance = self.get_object()
            username = instance.username
            role = instance.role
            response = super().destroy(request, *args, **kwargs)
        except Exception:
            logger.exception(
                'user_delete_failed actor=%s target_id=%s',
                request.user.username,
                target_id,
            )
            raise
        logger.info(
            'user_delete_ok actor=%s target_id=%s deleted_username=%s deleted_role=%s',
            request.user.username,
            target_id,
            username,
            role,
        )
        return response

    def get_queryset(self):
        user = self.request.user
        qs = _staff_users_queryset(user)
        if get_user_role(user) == 'DIRECTION':
            for mobile_role in ('AUDITEUR', 'FORMATEUR'):
                group_name = ROLE_GROUP_NAMES.get(mobile_role)
                if group_name:
                    qs = qs.exclude(groups__name=group_name)
        return qs

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return UserUpdateSerializer
        return UserSerializer

    def perform_update(self, serializer):
        instance = serializer.save()
        _log_audit(
            action=AuditLog.Action.USER_UPDATE,
            request=self.request,
            cible_type='user',
            cible_numero=instance.username,
            cible_nom=instance.get_full_name() or instance.username,
            extra={'role': get_user_role(instance), 'secretariat': str(instance.secretariat) if instance.secretariat else None},
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.pk == request.user.pk:
            return Response(
                {'detail': 'Impossible de supprimer votre propre compte.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _log_audit(
            action=AuditLog.Action.USER_DELETE,
            request=request,
            cible_type='user',
            cible_numero=instance.username,
            cible_nom=instance.get_full_name() or instance.username,
            extra={'role': get_user_role(instance), 'secretariat': str(instance.secretariat) if instance.secretariat else None},
        )
        return super().destroy(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# MFA TOTP (CURP U6, LOT 2) — montée / vérification / descente
# ---------------------------------------------------------------------------
def _compte_cible_mfa(request):
    """Compte cible : soi par défaut ; un tiers si le demandeur détient
    ``authentication.mutate_users``. Retourne ``(compte, erreur_response)``.
    """
    compte_id = request.data.get('compte_id')
    if compte_id in (None, ''):
        cible = request.user
    else:
        if not request.user.has_perm('authentication.mutate_users'):
            return None, Response(
                {'detail': 'Droits insuffisants pour gérer ce compte.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            cible = User.objects.get(pk=int(compte_id))
        except (ValueError, TypeError, User.DoesNotExist):
            return None, Response(
                {'detail': 'Compte introuvable.'},
                status=status.HTTP_404_NOT_FOUND,
            )
    from habilitations.models import CompteUtilisateur
    try:
        return cible.profil_habilitation, None
    except CompteUtilisateur.DoesNotExist:
        return None, Response(
            {'detail': 'Ce compte n’a pas de profil CURP (MFA indisponible).'},
            status=status.HTTP_404_NOT_FOUND,
        )


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def mfa_verify_view(request):
    """Complète la connexion après l'étape MFA (jeton court + code TOTP)."""
    from habilitations.services import totp

    username = connexion_sure.verifier_etape_mfa(
        (request.data.get('mfa_token') or '').strip())
    if username is None:
        return Response(
            {'code': 'MFA_JETON_INVALIDE',
             'detail': 'Jeton MFA invalide ou expiré : relancez la connexion.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user = User.objects.filter(username=username).first()
    if user is None or not user.is_active:
        return Response(
            {'code': 'MFA_JETON_INVALIDE',
             'detail': 'Jeton MFA invalide ou expiré : relancez la connexion.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    secondes = connexion_sure.verifier_verrouillage(user)
    if secondes is not None:
        compte_verrouille = connexion_sure.compte_curp(user)
        if compte_verrouille is not None:
            connexion_sure.journaliser_refus_verrouille(compte_verrouille, secondes)
        return Response(
            {'code': 'COMPTE_VERROUILLE',
             'detail': 'Ce compte est verrouillé : réessayez plus tard ou '
                       'contactez un administrateur.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    compte = connexion_sure.compte_curp(user)
    if compte is None or not (compte.mfa_actif and compte.mfa_secret):
        return Response(
            {'code': 'MFA_JETON_INVALIDE',
             'detail': 'Ce compte n’a pas de MFA actif : relancez la connexion.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not totp.verifier_code(compte.mfa_secret, request.data.get('code', '')):
        return Response(
            {'code': 'MFA_CODE_INVALIDE',
             'detail': 'Code MFA invalide : vérifiez votre application '
                       'd’authentification.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return connexion_sure.finaliser_connexion(
        user, request, device_id=(request.data.get('device_id') or '').strip())


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mfa_setup_view(request):
    """Arme un secret TOTP (soi, ou un tiers pour un détenteur de
    ``mutate_users``) — renvoie le secret et l'URI d'enrôlement."""
    compte, erreur = _compte_cible_mfa(request)
    if erreur is not None:
        return erreur
    secret, otpauth_url = connexion_sure.armer_mfa(compte)
    return Response({
        'secret': secret,
        'otpauth_url': otpauth_url,
        'detail': 'Secret armé : confirmez avec un code de votre application.',
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mfa_confirm_view(request):
    """Active le MFA après vérification d'un code valide sur le secret armé."""
    compte, erreur = _compte_cible_mfa(request)
    if erreur is not None:
        return erreur
    try:
        connexion_sure.confirmer_mfa(
            compte, str(request.data.get('code') or '').strip(), request.user)
    except connexion_sure.ErreurMfa as erreur_mfa:
        return Response(
            {'detail': erreur_mfa.message}, status=erreur_mfa.statut)
    return Response({'detail': 'MFA activé : la prochaine connexion exigera un code.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mfa_disable_view(request):
    """Désactive le MFA (code exigé pour soi ; un tiers par ``mutate_users``)."""
    compte, erreur = _compte_cible_mfa(request)
    if erreur is not None:
        return erreur
    try:
        connexion_sure.desactiver_mfa(
            compte, request.user,
            code=str(request.data.get('code') or '').strip())
    except connexion_sure.ErreurMfa as erreur_mfa:
        return Response(
            {'detail': erreur_mfa.message}, status=erreur_mfa.statut)
    return Response({'detail': 'MFA désactivé.'})
