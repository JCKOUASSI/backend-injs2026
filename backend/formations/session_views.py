"""
Session management views for the React frontend.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsDFRC, IsDFRCOrEncadrant, IsSecretariatOrEncadrantOrDFRC, IsSecretariatOrDFRC
from presences.models import AuditLog, _log_audit, log_audit_system
from presences.offline_cache import invalidate_offline_data_cache
from .models import Formation, Module, SessionModule, QRToken
from .serializers import SessionSerializer, ModuleSerializer
from .session_edt_balance import SessionEdtBalanceError, apply_session_edit_with_edt_balance


REACTIVATION_GRACE_HOURS = 4
AUTO_CLOSE_DELAY_MINUTES = 30
TZ_LOCALE = ZoneInfo('Africa/Abidjan')


def _session_audit_extra(session):
    return {
        'session_id': session.id,
        'session_numero': session.numero,
        'session_intitule': session.intitule or f'Séance {session.numero}',
        'date_journee': str(session.date_journee),
        'module_id': session.module_id,
        'module_intitule': session.module.intitule,
    }


def _invalidate_session_qr_cache(session):
    """Invalide le cache offline-data des QR tokens actifs d'une séance."""
    for token in QRToken.objects.filter(session=session, actif=True).values_list('token', flat=True):
        invalidate_offline_data_cache(token)


def close_open_sessions_for_module(module=None, *, module_id=None, exclude_pks=None, when=None):
    """Ferme (``terminee_le``) les séances ouvertes d'UN module.

    Ne touche qu'au module ciblé : les autres modules/groupes de la formation
    ne sont pas affectés, ce qui évite d'invalider leurs QR codes lorsqu'on
    démarre/réactive une séance.

    Args:
        module: instance ``Module`` (ou passer ``module_id``).
        module_id: identifiant du module (alternative à ``module``).
        exclude_pks: séances à ne pas fermer (itérable de pk).
        when: horodatage de clôture (par défaut ``timezone.now()``).

    Returns:
        Nombre de séances fermées.
    """
    when = when or timezone.now()
    qs = SessionModule.objects.filter(
        demarree_le__isnull=False,
        terminee_le__isnull=True,
    )
    qs = qs.filter(module=module) if module is not None else qs.filter(module_id=module_id)
    if exclude_pks:
        qs = qs.exclude(pk__in=list(exclude_pks))
    return qs.update(terminee_le=when)


def _session_duplicate_detail(session, *, conflict=None):
    """Message lisible pour une collision (module, date_journee, numero)."""
    date_label = session.date_journee.strftime('%d/%m/%Y') if session.date_journee else '—'
    base = (
        f'Une séance n°{session.numero} existe déjà pour ce module le {date_label}.'
    )
    if conflict:
        label = (conflict.intitule or f'Séance {conflict.numero}').strip()
        return f'{base} Conflit avec « {label} » — choisissez une autre date.'
    return base


def _session_save_error_detail(exc, session=None):
    if isinstance(exc, IntegrityError):
        return _session_duplicate_detail(session) if session else (
            'Une séance avec le même module, date et numéro existe déjà.'
        )
    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, 'message_dict') and exc.message_dict.get('__all__'):
            msg = exc.message_dict['__all__'][0]
        elif hasattr(exc, 'messages') and exc.messages:
            msg = exc.messages[0]
        else:
            msg = str(exc)
        if session and ('existe déjà' in msg.lower() or 'already exists' in msg.lower()):
            return _session_duplicate_detail(session)
        return msg
    return str(exc)


def reactiver_session_et_qr(session, *, close_other_open_sessions=False):
    """
    Réouvre une séance terminée, prolonge la fin prévue pour éviter une
    re-clôture immédiate par _auto_manage_sessions / auto_close_sessions,
    et réactive le QR associé.

    Ne ferme pas les autres séances ouvertes (autres groupes / modules).
    La coexistence de plusieurs séances ouvertes est gérée au badgeage
    (une entrée à la fois par module et par jour). Pour forcer la fermeture
    des autres séances du même module, passer ``close_other_open_sessions=True``
    (utilisé par « Démarrer une séance » depuis l'interface, pas par Réactiver).
    """
    now = timezone.now()
    local_now = timezone.localtime(now)
    today = local_now.date()

    if close_other_open_sessions:
        close_open_sessions_for_module(
            session.module, exclude_pks=[session.pk], when=now,
        )

    # Invalider le cache offline-data avant de réactiver : la date de
    # séance ou les participants/formateurs peuvent avoir changé.
    _invalidate_session_qr_cache(session)

    update_fields = ['terminee_le']
    session.terminee_le = None

    if session.date_journee < today:
        session.date_journee = today
        update_fields.append('date_journee')

    fin_est_future = (
        session.heure_fin_prevue is not None
        and session.date_journee == today
        and session.heure_fin_prevue > local_now.time()
    )
    if not fin_est_future:
        grace_end = local_now + timedelta(hours=REACTIVATION_GRACE_HOURS)
        # Si la grâce dépasse minuit, garder 23:59 le jour courant pour que
        # heure_fin_prevue reste > l'heure locale (évite re-clôture immédiate).
        if grace_end.date() > local_now.date():
            new_fin = time(23, 59)
        else:
            new_fin = grace_end.time().replace(second=0, microsecond=0)
            if new_fin <= local_now.time():
                new_fin = time(23, 59)
        session.heure_fin_prevue = new_fin
        update_fields.append('heure_fin_prevue')

    session.save(update_fields=update_fields)

    module = session.module
    if module.statut in ('TERMINEE', 'SUSPENDUE', 'PLANIFIEE'):
        module.statut = 'EN_COURS'
        module.save(update_fields=['statut'])

    qr = QRToken.objects.filter(session=session).order_by('-created_at').first()
    if qr:
        qr_updates = []
        if not qr.actif:
            qr.actif = True
            qr_updates.append('actif')
        if qr.is_expired:
            qr.expire_at = now + timedelta(hours=24)
            qr_updates.append('expire_at')
        if qr_updates:
            qr.save(update_fields=qr_updates)


def reactiver_sessions_en_lot(sessions):
    """
    Réactive plusieurs séances sans que chaque itération ne referme les
    précédentes. Ferme uniquement les séances ouvertes qui ne font pas
    partie du lot, par module.
    """
    from collections import defaultdict

    now = timezone.now()
    par_module = defaultdict(list)
    for session in sessions:
        par_module[session.module_id].append(session)

    for module_id, module_sessions in par_module.items():
        pks = [s.pk for s in module_sessions]
        close_open_sessions_for_module(module_id=module_id, exclude_pks=pks, when=now)
        for session in module_sessions:
            reactiver_session_et_qr(session, close_other_open_sessions=False)


def _has_unfinished_previous_session(session):
    """
    Retourne True si une séance précédente (même module, même date) n'est pas terminée.
    La précédence est définie par le numéro de séance.
    """
    return SessionModule.objects.filter(
        module=session.module,
        date_journee=session.date_journee,
        numero__lt=session.numero,
        terminee_le__isnull=True,
    ).exists()


def _session_debut_prevu_local(session):
    return datetime.combine(
        session.date_journee, session.heure_debut_prevue, tzinfo=TZ_LOCALE,
    )


def _session_fin_prevue_local(session):
    return datetime.combine(
        session.date_journee, session.heure_fin_prevue, tzinfo=TZ_LOCALE,
    )


def _should_auto_start_session(session, local_now):
    """
    Démarrage auto si l'heure de début prévue est atteinte et que
    l'encadrant n'a pas encore démarré la séance (``demarree_le`` encore vide).
    """
    if session.demarree_le is not None or session.terminee_le is not None:
        return False
    if not session.auto_demarrage or session.heure_debut_prevue is None:
        return False
    if session.date_journee != local_now.date():
        return False
    if local_now < _session_debut_prevu_local(session):
        return False
    return not _has_unfinished_previous_session(session)


def _should_auto_close_session(session, local_now, *, delai_minutes=AUTO_CLOSE_DELAY_MINUTES):
    """
    Fermeture auto uniquement si l'heure de fin prévue est dépassée et que
    l'encadrant n'a pas encore fermé la séance (``terminee_le`` encore vide).
    Dans ce cas, on attend ``delai_minutes`` avant de clôturer automatiquement.
    """
    if (
        session.demarree_le is None
        or session.terminee_le is not None
        or session.heure_fin_prevue is None
    ):
        return False
    fin_prevue_local = _session_fin_prevue_local(session)
    if local_now < fin_prevue_local:
        return False
    return local_now >= fin_prevue_local + timedelta(minutes=delai_minutes)


def _auto_manage_sessions(formation):
    """
    Auto-start sessions when heure_debut_prevue is reached and the encadrant
    has not started them yet. Auto-close sessions when heure_fin_prevue is
    passed, the encadrant has not closed them yet, and AUTO_CLOSE_DELAY_MINUTES
    has elapsed.

    À appeler uniquement via la tâche planifiée ``manage.py auto_sessions``
    (cron / service compose), jamais depuis un endpoint GET de lecture.
    """
    now = timezone.now()
    local_now = timezone.localtime(now)

    sessions = SessionModule.objects.filter(module__formation=formation).select_related('module__formation')

    modules_updated = set()

    for session in sessions:
        module = session.module
        formation_obj = module.formation
        # Auto-start si l'heure de début est passée et l'encadrant n'a pas démarré.
        # ``demarree_le`` est posé à l'heure prévue (et non ``now``).
        if _should_auto_start_session(session, local_now):
            session.demarree_le = _session_debut_prevu_local(session)
            session.save(update_fields=['demarree_le'])
            if module.statut == 'PLANIFIEE':
                module.statut = 'EN_COURS'
                module.save(update_fields=['statut'])
                modules_updated.add(module.pk)
            log_audit_system(
                AuditLog.Action.SEANCE_START,
                formation=formation_obj,
                extra={**_session_audit_extra(session), 'auto': True},
            )

        # Auto-close si l'heure de fin est passée, l'encadrant n'a pas fermé,
        # et le délai de grâce est écoulé. ``terminee_le`` reste borné à la fin
        # prévue pour ne pas gonfler la durée effective (volume horaire).
        if _should_auto_close_session(session, local_now):
            session.terminee_le = _session_fin_prevue_local(session)
            session.save(update_fields=['terminee_le'])
            _invalidate_session_qr_cache(session)
            QRToken.objects.filter(session=session, actif=True).update(actif=False)
            log_audit_system(
                AuditLog.Action.SEANCE_STOP,
                formation=formation_obj,
                extra={**_session_audit_extra(session), 'auto': True},
            )

    # If all sessions of a module are terminated → mark module TERMINEE
    for module in formation.modules.all():
        if (
            module.statut != 'TERMINEE'
            and module.sessions.exists()
            and not module.sessions.filter(terminee_le__isnull=True).exists()
        ):
            module.statut = 'TERMINEE'
            module.save(update_fields=['statut'])


@api_view(['POST'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def session_start(request, formation_pk, session_pk):
    """Start a session."""
    try:
        formation = Formation.objects.get(pk=formation_pk)
        session = SessionModule.objects.get(pk=session_pk, module__formation=formation)
    except (Formation.DoesNotExist, SessionModule.DoesNotExist):
        return Response({'detail': 'Formation ou séance introuvable.'}, status=404)
    
    # Check permission
    user = request.user
    module = session.module
    if user.role == 'ENCADRANT' and module.superviseur is not None and module.superviseur != user:
        return Response({'detail': 'Non autorisé.'}, status=403)
    
    if session.demarree_le and session.terminee_le is None:
        return Response({'detail': 'Cette séance est déjà démarrée.'}, status=400)

    if session.terminee_le is not None:
        # Réouverture : ne pas fermer les séances des autres modules/groupes.
        reactiver_session_et_qr(session, close_other_open_sessions=False)
        session.refresh_from_db()
        _log_audit(
            action=AuditLog.Action.SEANCE_START,
            request=request,
            formation=formation,
            extra={**_session_audit_extra(session), 'reactivation': True},
        )
        return Response({
            'detail': 'Séance réactivée.',
            'session': SessionSerializer(session).data,
        })

    if _has_unfinished_previous_session(session):
        return Response(
            {'detail': 'Impossible de démarrer cette séance tant que la précédente du même jour n’est pas terminée.'},
            status=400,
        )
    
    session.demarree_le = timezone.now()
    session.demarree_par = user
    session.save()
    
    # Update module status if needed
    if module.statut == 'PLANIFIEE':
        module.statut = 'EN_COURS'
        module.save(update_fields=['statut'])

    _log_audit(
        action=AuditLog.Action.SEANCE_START,
        request=request,
        formation=formation,
        extra=_session_audit_extra(session),
    )
    
    return Response({
        'detail': 'Séance démarrée.',
        'session': SessionSerializer(session).data,
    })


@api_view(['POST'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def session_stop(request, formation_pk, session_pk):
    """Stop (terminate) a session."""
    try:
        formation = Formation.objects.get(pk=formation_pk)
        session = SessionModule.objects.get(pk=session_pk, module__formation=formation)
    except (Formation.DoesNotExist, SessionModule.DoesNotExist):
        return Response({'detail': 'Formation ou séance introuvable.'}, status=404)
    
    if not session.demarree_le:
        return Response({'detail': 'Cette séance n\'a pas été démarrée.'}, status=400)
    
    if session.terminee_le:
        return Response({'detail': 'Cette séance est déjà terminée.'}, status=400)
    
    session.terminee_le = timezone.now()
    session.save()
    _invalidate_session_qr_cache(session)
    QRToken.objects.filter(session=session, actif=True).update(actif=False)

    # Check if all sessions of the module are terminated
    module = session.module
    remaining = module.sessions.filter(terminee_le__isnull=True).exclude(pk=session.pk).count()

    if remaining == 0:
        module.statut = 'TERMINEE'
        module.save(update_fields=['statut'])

    _log_audit(
        action=AuditLog.Action.SEANCE_STOP,
        request=request,
        formation=formation,
        extra=_session_audit_extra(session),
    )
    
    return Response({
        'detail': 'Séance terminée.',
        'session': SessionSerializer(session).data,
    })


@api_view(['POST'])
@permission_classes([IsSecretariatOrDFRC])
def session_create(request, formation_pk, module_pk):
    """Create a new session for a module of a formation."""
    try:
        formation = Formation.objects.get(pk=formation_pk)
        module = Module.objects.get(pk=module_pk, formation=formation)
    except Formation.DoesNotExist:
        return Response({'detail': 'Formation introuvable.'}, status=404)
    except Module.DoesNotExist:
        return Response({'detail': 'Module introuvable pour cette formation.'}, status=404)

    date_journee = request.data.get('date_journee')
    heure_debut = request.data.get('heure_debut_prevue')
    heure_fin = request.data.get('heure_fin_prevue')
    intitule = request.data.get('intitule', '')

    if not date_journee:
        return Response({'detail': 'date_journee est requis.'}, status=400)

    # Auto-calcul du numéro si non fourni
    if 'numero' in request.data:
        numero = int(request.data['numero'])
    else:
        last = SessionModule.objects.filter(
            module=module, date_journee=date_journee
        ).order_by('-numero').first()
        numero = (last.numero + 1) if last else 1

    from django.db import IntegrityError
    try:
        session = SessionModule.objects.create(
            module=module,
            date_journee=date_journee,
            numero=numero,
            heure_debut_prevue=heure_debut,
            heure_fin_prevue=heure_fin,
            intitule=intitule,
        )
    except IntegrityError:
        return Response(
            {'detail': f'Une séance n°{numero} existe déjà pour ce module à cette date.'},
            status=400,
        )

    _log_audit(
        action=AuditLog.Action.SEANCE_CREATE,
        request=request,
        formation=formation,
        extra=_session_audit_extra(session),
    )

    return Response({
        'detail': 'Séance créée.',
        'session': SessionSerializer(session).data,
    }, status=201)


@api_view(['DELETE'])
@permission_classes([IsDFRC])
def session_delete(request, formation_pk, session_pk):
    """Delete a session (only if not started)."""
    try:
        formation = Formation.objects.get(pk=formation_pk)
        session = SessionModule.objects.get(pk=session_pk, module__formation=formation)
    except (Formation.DoesNotExist, SessionModule.DoesNotExist):
        return Response({'detail': 'Formation ou séance introuvable.'}, status=404)
    
    if session.demarree_le:
        return Response({'detail': 'Impossible de supprimer une séance démarrée.'}, status=400)

    audit_extra = _session_audit_extra(session)
    session.delete()

    _log_audit(
        action=AuditLog.Action.SEANCE_DELETE,
        request=request,
        formation=formation,
        extra=audit_extra,
    )
    
    return Response({'detail': 'Séance supprimée.'}, status=204)


@api_view(['PATCH'])
@permission_classes([IsSecretariatOrDFRC])
def session_update(request, formation_pk, session_pk):
    """Update a session (intitule, date, heures). Not allowed if already terminated."""
    try:
        formation = Formation.objects.get(pk=formation_pk)
        session = SessionModule.objects.get(pk=session_pk, module__formation=formation)
    except (Formation.DoesNotExist, SessionModule.DoesNotExist):
        return Response({'detail': 'Formation ou séance introuvable.'}, status=404)

    if session.terminee_le:
        return Response({'detail': 'Impossible de modifier une séance terminée.'}, status=400)

    old_debut = session.heure_debut_prevue
    old_fin = session.heure_fin_prevue
    hours_changed = False

    if 'intitule' in request.data:
        session.intitule = request.data['intitule']
    if 'date_journee' in request.data:
        val = request.data['date_journee']
        if not val:
            return Response({'detail': 'La date de la séance est obligatoire.'}, status=400)
        session.date_journee = val
    if 'heure_debut_prevue' in request.data:
        session.heure_debut_prevue = request.data['heure_debut_prevue'] or None
        hours_changed = True
    if 'heure_fin_prevue' in request.data:
        session.heure_fin_prevue = request.data['heure_fin_prevue'] or None
        hours_changed = True

    conflict = SessionModule.objects.filter(
        module_id=session.module_id,
        date_journee=session.date_journee,
        numero=session.numero,
    ).exclude(pk=session.pk).first()
    if conflict:
        return Response(
            {'detail': _session_duplicate_detail(session, conflict=conflict)},
            status=400,
        )

    try:
        session.full_clean()
        auto_adjustment = None
        if hours_changed:
            auto_adjustment = apply_session_edit_with_edt_balance(
                session,
                old_debut=old_debut,
                old_fin=old_fin,
            )
        else:
            session.save()
    except SessionEdtBalanceError as e:
        return Response({'detail': str(e)}, status=400)
    except (DjangoValidationError, IntegrityError) as e:
        return Response(
            {'detail': _session_save_error_detail(e, session=session)},
            status=400,
        )
    except Exception as e:
        return Response({'detail': str(e)}, status=400)

    detail = 'Séance mise à jour.'
    if auto_adjustment and auto_adjustment.get('message'):
        detail = f"{detail} {auto_adjustment['message']}"

    payload = {
        'detail': detail,
        'session': SessionSerializer(session).data,
    }
    if auto_adjustment:
        payload['auto_adjustment'] = {
            'last_session_id': auto_adjustment.get('last_session_id'),
            'delta_minutes': auto_adjustment.get('delta_minutes'),
            'deleted_last': auto_adjustment.get('deleted_last', False),
        }

    _log_audit(
        action=AuditLog.Action.SEANCE_UPDATE,
        request=request,
        formation=formation,
        extra={
            **_session_audit_extra(session),
            'champs_modifies': list(request.data.keys()),
        },
    )
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def session_list(request, formation_pk):
    """List all sessions for a formation, grouped by module."""
    from .access import formation_accessible
    formation = formation_accessible(request.user, formation_pk)
    if not formation:
        return Response({'detail': 'Formation introuvable ou non autorisée.'}, status=404)

    # If module_id filter provided, return only that module's sessions
    module_id = request.query_params.get('module_id')
    if module_id:
        sessions = SessionModule.objects.filter(module_id=module_id).select_related('module')
        return Response(SessionSerializer(sessions, many=True).data)

    # Otherwise return modules with their sessions (filtered by secretariat scope if applicable)
    user = request.user
    if user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT') and user.secretariat:
        modules = formation.modules.filter(secretariat=user.secretariat).prefetch_related('sessions')
    elif user.role == 'ENCADRANT':
        modules = formation.modules.filter(superviseur=user).prefetch_related('sessions')
    else:
        modules = formation.modules.prefetch_related('sessions').all()

    return Response(ModuleSerializer(modules, many=True).data)
