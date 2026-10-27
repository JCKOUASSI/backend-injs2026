from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsDFRC, IsDFRCOrEncadrant, IsSecretariat, IsSecretariatOrDFRC, IsEncadrant, IsSecretariatOrEncadrant, IsSecretariatOrEncadrantOrDFRC, CanManageParticipant, CanManageModuleParticipant
from presences.models import AuditLog, _log_audit
from presences.offline_cache import invalidate_offline_data_cache
from .models import Formation, Participant, Secretariat, ModuleParticipant, ModuleFormateur, Formateur, QRToken, SessionModule, Module
FormationParticipant = ModuleParticipant
FormationFormateur = ModuleFormateur
from .access import formation_accessible, participants_queryset_for_user, formateurs_queryset_for_user
from .api_access import IsOperationalWebStaff
from .formateur_assignment import check_formateur_groupe_jour_conflict
from .qr_helpers import get_session_for_qr
from .serializer_querysets import secretariat_queryset_for_serializer
from .serializers import (
    FormationListSerializer,
    FormationDetailSerializer,
    ParticipantSerializer,
    SecretariatSerializer,
    FormateurSerializer,
    FormationParticipantSerializer,
    QRTokenSerializer,
    AssignSuperviseurSerializer,
)

User = get_user_model()


# ──────────────────────────────────────────────
# Helper — grades autorisés par type de secrétariat
# ──────────────────────────────────────────────

def _participants_grade_filter(secretariat):
    """Retourne un Q-filtre sur le grade selon le type du secrétariat.
    Type A → grade commençant par 'A' (A1, A2, A3…)
    Type B → grade commençant par 'B', Type C → 'C'
    Pas de type → aucun filtre.
    """
    from django.db.models import Q
    if secretariat and secretariat.type:
        return Q(grade__istartswith=secretariat.type) | Q(grade='')
    return Q()


def _secretariat_scope(user):
    """Retourne le secrétariat de l'utilisateur si rôle SECRETARIAT ou CHEF_SECRETARIAT."""
    if user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
        return user.secretariat
    return None


def _formations_queryset_for_user(user):
    """Formations visibles selon le périmètre opérationnel de l'utilisateur."""
    if user.role == 'ENCADRANT':
        return Formation.objects.filter(modules__superviseur=user).distinct().order_by('id')
    sec = _secretariat_scope(user)
    if sec is not None:
        if not sec:
            return Formation.objects.none()
        return Formation.objects.filter(modules__secretariat=sec).distinct().order_by('id')
    return Formation.objects.all().order_by('id')


def _secretariat_hint_from_matricule(matricule):
    """Retourne le code secrétariat prioritaire selon le matricule."""
    m = (matricule or '').strip().upper()
    if m.startswith('FNCE'):
        return 'FAB'
    if m.startswith('FNCP'):
        return 'FAC'
    return ''


def _resolve_secretariat_from_matricule(matricule):
    """Résout le secrétariat prioritaire depuis le matricule si applicable."""
    hint = _secretariat_hint_from_matricule(matricule)
    if not hint:
        return None
    return (
        Secretariat.objects.filter(nom__iexact=hint).first()
        or Secretariat.objects.filter(type__libelle__iexact=hint).first()
        or Secretariat.objects.filter(nom__istartswith=f'{hint} ').first()
    )


# ──────────────────────────────────────────────
# SECRETARIAT — Formations CRUD
# ──────────────────────────────────────────────

class FormationListCreateView(generics.ListCreateAPIView):
    """DFRC/Secrétariat/Encadrant : lister et créer des formations."""
    serializer_class = FormationListSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsSecretariatOrDFRC()]
        return [IsSecretariatOrEncadrantOrDFRC()]

    def get_queryset(self):
        return _formations_queryset_for_user(self.request.user)

    def perform_create(self, serializer):
        instance = serializer.save()
        _log_audit(
            action=AuditLog.Action.FORMATION_CREATE,
            request=self.request,
            formation=instance,
            cible_nom=instance.formation,
        )


class FormationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """DFRC/Secrétariat/Encadrant : détail / modifier / supprimer une formation."""
    serializer_class = FormationDetailSerializer

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH', 'DELETE'):
            return [IsSecretariatOrDFRC()]
        return [IsSecretariatOrEncadrantOrDFRC()]

    def get_queryset(self):
        return _formations_queryset_for_user(self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        _log_audit(
            action=AuditLog.Action.FORMATION_UPDATE,
            request=self.request,
            formation=instance,
            cible_nom=instance.formation,
        )

    def perform_destroy(self, instance):
        titre = instance.formation
        _log_audit(
            action=AuditLog.Action.FORMATION_DELETE,
            request=self.request,
            formation=instance,
            cible_nom=titre,
        )
        instance.delete()


# ──────────────────────────────────────────────
# DFRC — Assigner superviseur
# ──────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsSecretariatOrDFRC])
def assign_superviseur(request, pk):
    """DFRC : assigner un superviseur à une formation."""
    try:
        formation = Formation.objects.get(pk=pk)
    except Formation.DoesNotExist:
        return Response(
            {'detail': 'Formation introuvable.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = AssignSuperviseurSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    from authentication.role_groups import user_is_mobile_encadrant

    try:
        superviseur = User.objects.get(pk=serializer.validated_data['superviseur_id'])
    except User.DoesNotExist:
        return Response(
            {'detail': 'Encadrant introuvable ou rôle incorrect.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not user_is_mobile_encadrant(superviseur):
        return Response(
            {'detail': 'Encadrant introuvable ou rôle incorrect.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    formation.modules.update(superviseur=superviseur)

    _log_audit(
        action=AuditLog.Action.FORMATION_ASSIGN_SUPERVISEUR,
        request=request,
        formation=formation,
        extra={'superviseur_id': superviseur.id, 'superviseur_nom': superviseur.get_full_name()},
    )

    return Response({
        'detail': f'Superviseur {superviseur.get_full_name()} assigné à {formation.formation}.',
        'formation': FormationDetailSerializer(formation).data,
    })


# ──────────────────────────────────────────────
# SECRETARIAT — Participants CRUD
# ──────────────────────────────────────────────

class ParticipantListCreateView(generics.ListCreateAPIView):
    """Secrétariat/INJS_ADMIN : lister et créer des participants. Encadrant : lecture seule."""
    serializer_class = ParticipantSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            # Vérifie la permission Django formations.add_participant — respecte le ROLE_POLICY.
            return [CanManageParticipant()]
        if self.request.user.is_authenticated and self.request.user.role == 'ENCADRANT':
            return [IsEncadrant()]
        return [IsDFRC()]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'ENCADRANT':
            return participants_queryset_for_user(user)
        sec = _secretariat_scope(user)
        if sec is not None:
            if not sec:
                return Participant.objects.none()
            grade_q = _participants_grade_filter(sec)
            return Participant.objects.filter(secretariat=sec).filter(grade_q)
        return Participant.objects.all()

    def perform_create(self, serializer):
        user = self.request.user
        secretariat = user.secretariat if user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT') else None
        if secretariat is None:
            matricule = serializer.validated_data.get('matricule')
            secretariat = _resolve_secretariat_from_matricule(matricule)
        instance = serializer.save(secretariat=secretariat)
        _log_audit(
            action=AuditLog.Action.PARTICIPANT_CREATE,
            request=self.request,
            cible_type='participant',
            cible_numero=instance.matricule,
            cible_nom=f'{instance.nom} {instance.prenom}',
        )

    def perform_destroy(self, instance):
        _log_audit(
            action=AuditLog.Action.PARTICIPANT_DELETE,
            request=self.request,
            cible_type='participant',
            cible_numero=instance.matricule,
            cible_nom=f'{instance.nom} {instance.prenom}',
        )
        instance.delete()


class ParticipantDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Secrétariat/INJS_ADMIN : détail / modifier / supprimer un participant. Encadrant : lecture seule."""
    serializer_class = ParticipantSerializer

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH', 'DELETE'):
            # Vérifie la permission Django formations.change_participant / delete_participant.
            return [CanManageParticipant()]
        if self.request.user.is_authenticated and self.request.user.role == 'ENCADRANT':
            return [IsEncadrant()]
        return [IsDFRC()]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'ENCADRANT':
            return participants_queryset_for_user(user)
        sec = _secretariat_scope(user)
        if sec is not None:
            if not sec:
                return Participant.objects.none()
            grade_q = _participants_grade_filter(sec)
            return Participant.objects.filter(secretariat=sec).filter(grade_q)
        return Participant.objects.all()

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except IntegrityError as exc:
            raise ValidationError({
                'matricule': ['Ce matricule est déjà utilisé.'],
            }) from exc

    def perform_update(self, serializer):
        user = self.request.user
        instance = serializer.instance
        matricule_changed = (
            'matricule' in serializer.validated_data
            and serializer.validated_data['matricule'] != instance.matricule
        )

        secretariat = None
        if user.role not in ('SECRETARIAT', 'CHEF_SECRETARIAT') and matricule_changed:
            from formations.participant_matricule import secretariat_from_matricule_for_actor

            secretariat = secretariat_from_matricule_for_actor(
                serializer.validated_data['matricule'],
                user,
            )

        with transaction.atomic():
            if secretariat is not None:
                instance = serializer.save(secretariat=secretariat)
            else:
                instance = serializer.save()

            if matricule_changed and instance.user_id:
                from formations.participant_matricule import sync_participant_user_after_matricule_change

                sync_participant_user_after_matricule_change(instance)

        _log_audit(
            action=AuditLog.Action.PARTICIPANT_UPDATE,
            request=self.request,
            cible_type='participant',
            cible_numero=instance.matricule,
            cible_nom=f'{instance.nom} {instance.prenom}',
        )

    def perform_destroy(self, instance):
        _log_audit(
            action=AuditLog.Action.PARTICIPANT_DELETE,
            request=self.request,
            cible_type='participant',
            cible_numero=instance.matricule,
            cible_nom=f'{instance.nom} {instance.prenom}',
        )
        instance.delete()


# ──────────────────────────────────────────────
# DFRC — Inscrire participants à une formation
# ──────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([CanManageModuleParticipant])
def add_participant_to_formation(request, pk):
    """Inscrire un participant à une formation — respecte les permissions du groupe (add_moduleparticipant)."""
    try:
        formation = Formation.objects.get(pk=pk)
    except Formation.DoesNotExist:
        return Response(
            {'detail': 'Formation introuvable.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    participant_id = request.data.get('participant_id')
    if not participant_id:
        return Response(
            {'detail': 'participant_id requis.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        participant = Participant.objects.get(pk=participant_id)
    except Participant.DoesNotExist:
        return Response(
            {'detail': 'Auditeur introuvable.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.user.role == 'SECRETARIAT' and participant.secretariat != request.user.secretariat:
        return Response(
            {'detail': 'Vous ne pouvez inscrire que les auditeurs de votre secrétariat.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    module_pk = request.data.get('module_id')
    if not module_pk:
        return Response(
            {'detail': 'Le champ module_id est obligatoire.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        from .models import Module
        module = Module.objects.get(pk=module_pk, formation=formation)
    except Module.DoesNotExist:
        return Response({'detail': 'Module introuvable.'}, status=status.HTTP_404_NOT_FOUND)

    # Vérification de compatibilité grade/catégorie
    # Pour A : comparaison stricte du grade (A3≠A4). Pour B/C/D : comparaison par catégorie.
    def _get_compat_key(g):
        if not g:
            return ''
        g = g.strip().upper()
        if g.startswith('A'):
            return g  # A3, A4, A5... strict
        return g[0] if g else ''  # B, C, D... par catégorie
    p_compat = _get_compat_key(participant.grade)
    mod_compat = _get_compat_key(module.grade)
    if p_compat and mod_compat and p_compat != mod_compat:
        return Response(
            {'detail': f'Grade incompatible : le participant est {participant.grade}, '
                      f'mais ce module est pour {module.grade}.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    fp, created = ModuleParticipant.objects.get_or_create(
        module=module,
        participant=participant,
    )
    if not created:
        return Response(
            {'detail': 'Auditeur déjà inscrit à ce module.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    _log_audit(
        action=AuditLog.Action.PARTICIPANT_ADD_FORMATION,
        request=request,
        cible_type='participant',
        cible_numero=participant.matricule,
        cible_nom=f'{participant.nom} {participant.prenom}',
        formation=formation,
    )

    return Response({
        'detail': f'Auditeur {participant} inscrit au module « {module.intitule} ».',
        'inscription': FormationParticipantSerializer(fp).data,
    }, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsSecretariatOrDFRC])
def remove_participant_from_formation(request, pk, participant_id):
    """DFRC/Secrétariat : retirer un participant d'une formation."""
    try:
        fp = ModuleParticipant.objects.filter(
            module__formation_id=pk,
            participant_id=participant_id,
        ).first()
        if not fp:
            raise ModuleParticipant.DoesNotExist
    except ModuleParticipant.DoesNotExist:
        return Response(
            {'detail': 'Inscription introuvable.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    participant = fp.participant
    formation = fp.formation
    fp.delete()
    _log_audit(
        action=AuditLog.Action.PARTICIPANT_REMOVE_FORMATION,
        request=request,
        cible_type='participant',
        cible_numero=participant.matricule,
        cible_nom=f'{participant.nom} {participant.prenom}',
        formation=formation,
    )
    return Response({'detail': 'Auditeur retiré de la formation.'})


# ──────────────────────────────────────────────
# DFRC/SECRETARIAT — Assigner formateurs à une formation
# ──────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsSecretariatOrDFRC])
def add_formateur_to_formation(request, pk):
    """DFRC/Secrétariat : assigner un formateur à une formation."""
    try:
        formation = Formation.objects.get(pk=pk)
    except Formation.DoesNotExist:
        return Response({'detail': 'Formation introuvable.'}, status=status.HTTP_404_NOT_FOUND)

    formateur_id = request.data.get('formateur_id')
    if not formateur_id:
        return Response({'detail': 'formateur_id requis.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        formateur = Formateur.objects.get(pk=formateur_id)
    except Formateur.DoesNotExist:
        return Response({'detail': 'Formateur introuvable.'}, status=status.HTTP_404_NOT_FOUND)

    module_pk = request.data.get('module_id')
    if not module_pk:
        return Response({'detail': 'Le champ module_id est obligatoire.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        module = Module.objects.get(pk=module_pk, formation=formation)
    except Module.DoesNotExist:
        return Response({'detail': 'Module introuvable.'}, status=status.HTTP_404_NOT_FOUND)

    if ModuleFormateur.objects.filter(module=module, formateur=formateur).exists():
        return Response({'detail': 'Formateur déjà assigné à ce module.'}, status=status.HTTP_400_BAD_REQUEST)

    conflict = check_formateur_groupe_jour_conflict(formateur, module)
    if conflict:
        return Response({'detail': conflict}, status=status.HTTP_400_BAD_REQUEST)

    ModuleFormateur.objects.create(module=module, formateur=formateur)

    _log_audit(
        action=AuditLog.Action.FORMATEUR_ADD_FORMATION,
        request=request,
        cible_type='formateur',
        cible_numero=formateur.numerobadge,
        cible_nom=f'{formateur.nom} {formateur.prenom}',
        formation=formation,
    )

    return Response({
        'detail': f'{formateur} assigné à {formation.formation}.',
        'formateur': FormateurSerializer(formateur).data,
    }, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsSecretariatOrDFRC])
def remove_formateur_from_formation(request, pk, formateur_id):
    """DFRC/Secrétariat : retirer un formateur d'une formation."""
    ff = ModuleFormateur.objects.filter(module__formation_id=pk, formateur_id=formateur_id).first()
    if not ff:
        return Response({'detail': 'Assignation introuvable.'}, status=status.HTTP_404_NOT_FOUND)

    formateur = ff.formateur
    formation = ff.formation
    ff.delete()
    _log_audit(
        action=AuditLog.Action.FORMATEUR_REMOVE_FORMATION,
        request=request,
        cible_type='formateur',
        cible_numero=formateur.numerobadge,
        cible_nom=f'{formateur.nom} {formateur.prenom}',
        formation=formation,
    )
    return Response({'detail': 'Formateur retiré de la formation.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_formateurs_of_formation(request, pk):
    """Lister les formateurs assignés à une formation."""
    formation = formation_accessible(request.user, pk)
    if not formation:
        return Response({'detail': 'Formation introuvable ou non autorisée.'}, status=status.HTTP_404_NOT_FOUND)

    formateurs = Formateur.objects.filter(modules_assignes__module__formation=formation).distinct()
    return Response(FormateurSerializer(formateurs, many=True).data)


# ──────────────────────────────────────────────
# SUPERVISEUR — Mes formations
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsDFRCOrEncadrant])
def superviseur_formations(request):
    """Superviseur : lister mes formations assignées."""
    formations = Formation.objects.filter(
        modules__superviseur=request.user
    ).distinct()
    serializer = FormationListSerializer(formations, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsDFRCOrEncadrant])
def superviseur_formation_detail(request, pk):
    """Superviseur : détail d'une formation assignée."""
    try:
        formation = Formation.objects.get(pk=pk, modules__superviseur=request.user)
    except Formation.DoesNotExist:
        return Response(
            {'detail': 'Formation introuvable ou non assignée.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(FormationDetailSerializer(formation).data)


# ──────────────────────────────────────────────
# SUPERVISEUR — Générer QR code (R1)
# ──────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsDFRCOrEncadrant])
def generate_qr(request, pk):
    """Superviseur : générer un QR code pour sa formation (R1)."""
    formation = formation_accessible(request.user, pk)
    if not formation:
        return Response(
            {'detail': 'Formation introuvable ou vous n\'êtes pas le superviseur assigné.'},
            status=status.HTTP_403_FORBIDDEN,
        )

    session_id = request.data.get('session_id')
    module_id = request.data.get('module_id')
    session, err = get_session_for_qr(
        formation=formation,
        session_id=session_id,
        module_id=module_id,
    )
    if err:
        return err
    if session.est_terminee:
        return Response(
            {'detail': 'Impossible de générer un QR pour une séance terminée.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Désactiver les anciens QR tokens (formation + séance cible si fournie)
    # et invalider leur cache offline-data pour éviter de servir des données
    # obsolètes après régénération.
    qr_filter = QRToken.objects.filter(session__module__formation=formation, actif=True)
    if session is not None:
        qr_filter = qr_filter.filter(session=session)
    old_tokens = list(qr_filter.values_list('token', flat=True))
    qr_filter.update(actif=False)
    for old_token in old_tokens:
        invalidate_offline_data_cache(old_token)

    # Durée d'expiration configurable
    expire_in = request.data.get('expire_in', None)
    expire_unit = request.data.get('expire_unit', 'heures')  # minutes | heures | jours

    if expire_in is not None:
        expire_in = int(expire_in)
        if expire_unit == 'minutes':
            delta = timedelta(minutes=expire_in)
        elif expire_unit == 'jours':
            delta = timedelta(days=expire_in)
        else:
            delta = timedelta(hours=expire_in)
    else:
        lifetime_hours = getattr(settings, 'QR_TOKEN_LIFETIME_HOURS', 24)
        delta = timedelta(hours=lifetime_hours)

    qr_token = QRToken.objects.create(
        session=session,
        genere_par=request.user,
        expire_at=timezone.now() + delta,
    )

    _log_audit(
        action=AuditLog.Action.FORMATION_QR_GENERATE,
        request=request,
        formation=formation,
        extra={
            'session_id': session.id,
            'session_numero': session.numero,
            'token': str(qr_token.token),
        },
    )

    return Response({
        'detail': 'QR code généré avec succès.',
        'qr_token': QRTokenSerializer(qr_token).data,
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsDFRCOrEncadrant])
def get_active_qr(request, pk):
    """Superviseur : récupérer le QR token actif de sa formation."""
    formation = formation_accessible(request.user, pk)
    if not formation:
        return Response(
            {'detail': 'Formation introuvable ou non assignée.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    session_id = request.query_params.get('session_id')
    module_id = request.query_params.get('module_id')
    session, err = get_session_for_qr(
        formation=formation,
        session_id=session_id,
        module_id=module_id,
    )
    if err:
        return err

    qr_token = (
        QRToken.objects.filter(session=session, actif=True)
        .select_related('session__module')
        .order_by('-created_at')
        .first()
    )

    if not qr_token or not qr_token.is_valid:
        return Response(
            {'detail': 'Aucun QR code actif pour cette séance.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(QRTokenSerializer(qr_token).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def qr_image(request, pk):
    """Génère l'image PNG du QR code actif d'une formation (A4 printable)."""
    import io
    import qrcode
    from django.http import HttpResponse

    formation = formation_accessible(request.user, pk)
    if not formation:
        return Response(
            {'detail': 'Formation introuvable.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Le QR est scopé à une séance/module. Si une séance (ou un module) est
    # fournie, on la résout explicitement pour éviter de servir le QR d'un
    # autre groupe. Sinon, on n'autorise l'image « formation » que s'il
    # existe une seule séance avec un QR actif (formation mono-groupe).
    session_id = request.query_params.get('session_id')
    module_id = request.query_params.get('module_id')

    if session_id or module_id:
        session, err = get_session_for_qr(
            formation=formation,
            session_id=session_id,
            module_id=module_id,
        )
        if err:
            return err
        qr_token = (
            QRToken.objects.filter(session=session, actif=True)
            .order_by('-created_at')
            .first()
        )
    else:
        active_tokens = QRToken.objects.filter(
            session__module__formation=formation, actif=True
        ).order_by('-created_at')
        distinct_sessions = {t.session_id for t in active_tokens}
        if len(distinct_sessions) > 1:
            return Response(
                {
                    'code': 'QR_AMBIGUOUS',
                    'detail': (
                        'Plusieurs groupes ont un QR actif. Précisez la séance '
                        '(session_id) ou utilisez l\'URL par séance '
                        '/formations/<pk>/sessions/<session_pk>/qr-image/.'
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )
        qr_token = active_tokens.first()

    if not qr_token or not qr_token.is_valid:
        return Response(
            {'detail': 'Aucun QR code actif pour cette formation.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Construire l'URL complète de la page de badgeage
    from django.conf import settings as django_settings
    base_url = getattr(django_settings, 'BADGE_BASE_URL', '')
    if not base_url:
        scheme = 'https' if request.is_secure() else 'http'
        base_url = f"{scheme}://{request.get_host()}"
    qr_data = f"{base_url}/dashboard/badge/?token={qr_token.token}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=20,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='image/png')
    response['Content-Disposition'] = f'inline; filename="qr_formation_{formation.id}.png"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def session_qr_image(request, pk, session_pk):
    """Génère l'image PNG du QR code actif d'une séance spécifique."""
    import io
    import qrcode
    from django.http import HttpResponse

    formation = formation_accessible(request.user, pk)
    if not formation:
        return Response(
            {'detail': 'Formation introuvable.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        session = SessionModule.objects.get(pk=session_pk, module__formation=formation)
    except SessionModule.DoesNotExist:
        return Response(
            {'detail': 'Séance introuvable.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    qr_token = QRToken.objects.filter(
        session=session, actif=True
    ).first()

    if not qr_token or not qr_token.is_valid:
        return Response(
            {'detail': 'Aucun QR code actif pour cette séance.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Construire l'URL complète de la page de badgeage
    from django.conf import settings as django_settings
    base_url = getattr(django_settings, 'BADGE_BASE_URL', '')
    if not base_url:
        scheme = 'https' if request.is_secure() else 'http'
        base_url = f"{scheme}://{request.get_host()}"
    qr_data = f"{base_url}/dashboard/badge/?token={qr_token.token}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=20,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    session_label = session.intitule or f"Session {session.numero}"
    response = HttpResponse(buffer, content_type='image/png')
    response['Content-Disposition'] = f'inline; filename="qr_{formation.id}_seance_{session.id}.png"'
    return response


# ──────────────────────────────────────────────
# SECRETARIAT — Formateurs CRUD
# ──────────────────────────────────────────────

class FormateurListCreateView(generics.ListCreateAPIView):
    """Secrétariat/INJS_ADMIN : lister et créer des formateurs. Encadrant : lecture seule."""
    serializer_class = FormateurSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsSecretariatOrDFRC()]
        if self.request.user.is_authenticated and self.request.user.role == 'ENCADRANT':
            return [IsEncadrant()]
        return [IsDFRC()]

    def get_queryset(self):
        return formateurs_queryset_for_user(self.request.user)

    def perform_create(self, serializer):
        instance = serializer.save()
        _log_audit(
            action=AuditLog.Action.FORMATEUR_CREATE,
            request=self.request,
            cible_type='formateur',
            cible_numero=instance.numerobadge,
            cible_nom=f'{instance.nom} {instance.prenom}',
        )


class FormateurDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Secrétariat/INJS_ADMIN : détail / modifier / supprimer un formateur. Encadrant : lecture seule."""
    serializer_class = FormateurSerializer

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH', 'DELETE'):
            return [IsSecretariatOrDFRC()]
        if self.request.user.is_authenticated and self.request.user.role == 'ENCADRANT':
            return [IsEncadrant()]
        return [IsDFRC()]

    def get_queryset(self):
        return formateurs_queryset_for_user(self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        _log_audit(
            action=AuditLog.Action.FORMATEUR_UPDATE,
            request=self.request,
            cible_type='formateur',
            cible_numero=instance.numerobadge,
            cible_nom=f'{instance.nom} {instance.prenom}',
        )

    def perform_destroy(self, instance):
        _log_audit(
            action=AuditLog.Action.FORMATEUR_DELETE,
            request=self.request,
            cible_type='formateur',
            cible_numero=instance.numerobadge,
            cible_nom=f'{instance.nom} {instance.prenom}',
        )
        instance.delete()


# ──────────────────────────────────────────────
# DFRC — Secretariats CRUD
# ──────────────────────────────────────────────

class SecretariatListCreateView(generics.ListCreateAPIView):
    """DFRC/Secrétariat : lister et créer des secrétariats."""
    serializer_class = SecretariatSerializer
    permission_classes = [IsSecretariatOrDFRC]

    def get_queryset(self):
        return secretariat_queryset_for_serializer()

    def perform_create(self, serializer):
        instance = serializer.save()
        _log_audit(
            action=AuditLog.Action.SECRETARIAT_CREATE,
            request=self.request,
            cible_type='secretariat',
            cible_numero=instance.numero or str(instance.pk),
            cible_nom=instance.nom,
        )


class SecretariatDetailView(generics.RetrieveUpdateDestroyAPIView):
    """DFRC/Secrétariat : détail / modifier / supprimer un secrétariat."""
    serializer_class = SecretariatSerializer
    permission_classes = [IsSecretariatOrDFRC]

    def get_queryset(self):
        return secretariat_queryset_for_serializer()

    def perform_update(self, serializer):
        instance = serializer.save()
        _log_audit(
            action=AuditLog.Action.SECRETARIAT_UPDATE,
            request=self.request,
            cible_type='secretariat',
            cible_numero=instance.numero or str(instance.pk),
            cible_nom=instance.nom,
        )

    def perform_destroy(self, instance):
        _log_audit(
            action=AuditLog.Action.SECRETARIAT_DELETE,
            request=self.request,
            cible_type='secretariat',
            cible_numero=instance.numero or str(instance.pk),
            cible_nom=instance.nom,
        )
        instance.delete()


# ──────────────────────────────────────────────
# DFRC/SECRETARIAT — Participants d'un secrétariat
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsDFRC])
def secretariat_participants(request, pk):
    """Lister les participants d'un secrétariat."""
    try:
        secretariat = Secretariat.objects.get(pk=pk)
    except Secretariat.DoesNotExist:
        return Response(
            {'detail': 'Secrétariat introuvable.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    # Secrétariat ne peut voir que ses propres participants
    user = request.user
    if user.role == 'SECRETARIAT':
        if not user.secretariat or user.secretariat_id != secretariat.pk:
            return Response(
                {'detail': 'Accès refusé.'},
                status=status.HTTP_403_FORBIDDEN,
            )
    participants = secretariat.participants.all()
    serializer = ParticipantSerializer(participants, many=True)
    return Response(serializer.data)
