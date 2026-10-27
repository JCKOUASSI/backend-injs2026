import json
import time
import uuid
from datetime import timedelta

from django.db import transaction
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from authentication.permissions import IsDFRC, IsDFRCOrEncadrant, IsSecretariatOrEncadrantOrDFRC, IsSecretariatOrDFRC
from authentication.role_groups import get_user_role, user_in_roles, user_is_mobile_encadrant
from authentication.throttles import ScanRateThrottle, OfflineDataRateThrottle
from formations.models import (
    Formation, Participant, Module, ModuleParticipant, ModuleFormateur,
    Formateur, QRToken, SessionModule, RefSite,
)
FormationParticipant = ModuleParticipant
FormationFormateur = ModuleFormateur
from formations.serializers import ParticipantSerializer, FormateurSerializer, FormationListSerializer
from formations.access import participant_fiche_accessible
from . import geofence  # noqa: F401  (source de vérité du contrôle de périmètre)
from .models import Pointage, DeviceBinding, AuditLog, Rattrapage, _log_audit
from .offline_cache import (
    OFFLINE_DATA_CACHE_TIMEOUT,
    OFFLINE_DATA_LOCK_TIMEOUT,
    offline_data_cache_key,
    offline_data_lock_key,
)
from .serializers import (
    PointageSerializer,
    ScanSerializer,
    SecureScanSerializer,
    SecureHeartbeatSerializer,
    ForcePointageSerializer,
    ForceBadgeageBulkAuditeursSerializer,
)

User = get_user_model()


def _password_change_required_response():
    return Response(
        {
            'code': 'PASSWORD_CHANGE_REQUIRED',
            'detail': 'Vous devez changer votre mot de passe avant de continuer.',
        },
        status=status.HTTP_403_FORBIDDEN,
    )


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _normalize_scan_identifier(value):
    """Normalise un identifiant saisi pour comparer les variantes de format."""
    return ''.join(ch for ch in (value or '').strip().upper() if ch.isalnum())


def _matricule_matches_value(stored, numero_upper, numero_compact):
    """Compare un matricule stocké à la saisie (casse / espaces / ponctuation tolérés)."""
    if not stored:
        return False
    val = stored.strip()
    if numero_upper and val.upper() == numero_upper:
        return True
    if numero_compact and _normalize_scan_identifier(val) == numero_compact:
        return True
    return False


def _formateur_badge_candidates(numero_upper, numero_compact):
    """Variantes acceptées pour un badge formateur (F0042, f0042, 42…)."""
    candidates = set()
    if numero_upper:
        candidates.add(numero_upper)
    if numero_compact:
        candidates.add(numero_compact)
    if numero_compact.isdigit():
        candidates.add(f"F{int(numero_compact):04d}")
    elif numero_compact.startswith('F') and numero_compact[1:].isdigit():
        candidates.add(f"F{int(numero_compact[1:]):04d}")
    return candidates


def _formateur_matches_badge(formateur, candidates):
    badge = (formateur.numerobadge or '').strip().upper()
    badge_compact = _normalize_scan_identifier(formateur.numerobadge)
    for candidate in candidates:
        c_upper = candidate.upper()
        if badge == c_upper:
            return True
        c_compact = _normalize_scan_identifier(candidate)
        if badge_compact and c_compact and badge_compact == c_compact:
            return True
    return False


def _module_scan_label(module):
    if module is None:
        return 'ce module'
    label = module.intitule or f'Module #{module.pk}'
    if module.groupe:
        return f'« {label} » ({module.groupe})'
    return f'« {label} »'


def _participant_personne_data(participant):
    return {
        'numero': participant.matricule,
        'nom': participant.nom,
        'prenom': participant.prenom,
    }


def _formateur_in_module_by_badge(module, formateur_candidates):
    """Formateur inscrit au module correspondant au badge scanné (lookup SQL)."""
    formateur_filters = Q()
    for candidate in formateur_candidates:
        formateur_filters |= Q(formateur__numerobadge__iexact=candidate)
    if not formateur_filters:
        return None
    mf = (
        ModuleFormateur.objects
        .filter(module=module)
        .filter(formateur_filters)
        .select_related('formateur')
        .first()
    )
    return mf.formateur if mf else None


def _resolve_personne(numero, formation, module=None, seance=None):
    """
    Résout un numéro (auditeur, formateur, encadrant) vers la personne et vérifie l'inscription.
    Retourne (personne, type_str, personne_data, error_response).
    Note: `personne_data` est volontairement "minimal" pour limiter la fuite de PII sur l'endpoint public.
    """
    numero_upper = (numero or '').strip().upper()
    numero_compact = _normalize_scan_identifier(numero)
    if not numero_upper and not numero_compact:
        return None, None, None, Response(
            {'code': 'PARTICIPANT_NOT_FOUND', 'detail': 'Étudiant introuvable.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    formateur_candidates = _formateur_badge_candidates(numero_upper, numero_compact)
    module_scope = module

    # 1. Priorité module : auditeurs inscrits sur la séance scannée (évite les faux négatifs).
    if module_scope is not None:
        from .participant_scope import participant_in_module_by_matricule

        p = participant_in_module_by_matricule(module_scope, numero_upper, numero_compact)
        if p:
            return p, 'participant', _participant_personne_data(p), None

        f = _formateur_in_module_by_badge(module_scope, formateur_candidates)
        if f:
            return f, 'formateur', {
                'numero': f.numerobadge,
                'nom': f.nom,
                'prenom': f.prenom,
            }, None

        if module_scope.superviseur_id:
            sup = module_scope.superviseur
            if sup and _matricule_matches_value(sup.matricule, numero_upper, numero_compact):
                return sup, 'encadrant', {
                    'numero': sup.matricule,
                    'nom': sup.last_name or '',
                    'prenom': sup.first_name or '',
                    'username': sup.username,
                }, None

    # 2. Formateur global — ne bloque pas si hors module (un matricule auditeur peut coïncider).
    formateur_filters = Q()
    for candidate in formateur_candidates:
        formateur_filters |= Q(numerobadge__iexact=candidate)
    formateur = Formateur.objects.filter(formateur_filters).first()
    if formateur is not None:
        formateur_in_scope = (
            ModuleFormateur.objects.filter(module=module_scope, formateur=formateur).exists()
            if module_scope is not None
            else ModuleFormateur.objects.filter(module__formation=formation, formateur=formateur).exists()
        )
        if formateur_in_scope:
            return formateur, 'formateur', {
                'numero': formateur.numerobadge,
                'nom': formateur.nom,
                'prenom': formateur.prenom,
            }, None

    # 3. Encadrant global (matricule tolérant sur casse / compact).
    encadrant = None
    if numero_upper or numero_compact:
        encadrant_filters = Q()
        if numero_upper:
            encadrant_filters |= Q(matricule__iexact=numero_upper)
        if numero_compact and numero_compact != numero_upper:
            encadrant_filters |= Q(matricule__iexact=numero_compact)
        encadrant = User.objects.filter(role='ENCADRANT').filter(encadrant_filters).first()
    if encadrant is not None:
        encadrant_in_scope = (
            bool(module_scope and module_scope.superviseur_id == encadrant.id)
            if module_scope is not None
            else Formation.objects.filter(pk=formation.pk, modules__superviseur=encadrant).exists()
        )
        if encadrant_in_scope:
            return encadrant, 'encadrant', {
                'numero': encadrant.matricule,
                'nom': encadrant.last_name or '',
                'prenom': encadrant.first_name or '',
                'username': encadrant.username,
            }, None

    # 4. Auditeur global puis contrôle d'inscription au module.
    participant = Participant.objects.filter(matricule__iexact=numero_upper).first()
    if participant is None and numero_compact and numero_compact != numero_upper:
        participant = Participant.objects.filter(matricule__iexact=numero_compact).first()
    if participant is None and numero_compact:
        enroll_filter = (
            {'module': module_scope}
            if module_scope is not None
            else {'module__formation': formation}
        )
        if module_scope is not None:
            from .participant_scope import participant_in_module_by_matricule
            participant = participant_in_module_by_matricule(
                module_scope, numero_upper, numero_compact
            )
        else:
            for insc in (
                ModuleParticipant.objects
                .filter(**enroll_filter)
                .select_related('participant')
                .only(
                    'participant__id',
                    'participant__matricule',
                    'participant__nom',
                    'participant__prenom',
                )
            ):
                p = insc.participant
                if p and _normalize_scan_identifier(p.matricule) == numero_compact:
                    participant = p
                    break
    if participant is None:
        return None, None, None, Response(
            {'code': 'PARTICIPANT_NOT_FOUND',
             'detail': 'Étudiant introuvable.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    participant_in_scope = (
        ModuleParticipant.objects.filter(module=module_scope, participant=participant).exists()
        if module_scope is not None
        else ModuleParticipant.objects.filter(module__formation=formation, participant=participant).exists()
    )
    if not participant_in_scope and module_scope is not None:
        # Autoriser un rattrapage inter-cohorte planifié sur ce module (l'étudiant
        # n'est pas inscrit mais dispose d'un rattrapage actif pour ce module).
        rattrapage_filter = {
            'participant': participant,
            'statut': Rattrapage.Statut.PLANIFIE,
        }
        if seance is not None:
            rattrapage_filter['seance_rattrapage'] = seance
        else:
            rattrapage_filter['seance_rattrapage__module'] = module_scope
        participant_in_scope = Rattrapage.objects.filter(**rattrapage_filter).exists()
    if not participant_in_scope:
        module_label = _module_scan_label(module_scope)
        return None, None, None, Response(
            {
                'code': 'PARTICIPANT_NOT_IN_LIST',
                'detail': (
                    f'Étudiant non autorisé pour {module_label}. '
                    f'Vérifiez le QR affiché (bon groupe / bon module) '
                    f'ou contactez le secrétariat.'
                ),
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return participant, 'participant', _participant_personne_data(participant), None


def _pointage_filter(personne, type_personne, formation, **extra):
    """Construit le filtre de pointage pour participant ou formateur."""
    base = {'session__module__formation': formation}
    if type_personne == 'formateur':
        base['formateur'] = personne
    elif type_personne == 'encadrant':
        base['encadrant'] = personne
    else:
        base['participant'] = personne
    base.update(extra)
    return base


def _daily_completed_sessions_stats(personne, type_personne, formation, date_journee):
    """Durée totale et nombre de sessions terminées pour la journée (agrégat SQL)."""
    stats = Pointage.objects.filter(
        **_pointage_filter(
            personne, type_personne, formation,
            date_journee=date_journee,
            timestamp_sortie__isnull=False,
        )
    ).aggregate(
        total_jour=Sum('duree_presence_minutes'),
        nb_sessions=Count('id'),
    )
    return float(stats['total_jour'] or 0), stats['nb_sessions'] or 0


def _should_log_heartbeat_audit(previous_heartbeat_at):
    """Réduit les écritures AuditLog : un heartbeat OK n'est tracé que périodiquement."""
    interval = int(getattr(settings, 'MOBILE_HEARTBEAT_AUDIT_INTERVAL_SECONDS', 600))
    if previous_heartbeat_at is None:
        return True
    return (timezone.now() - previous_heartbeat_at).total_seconds() >= interval


def _create_pointage_kwargs(personne, type_personne, session, **extra):
    """Construit les kwargs de création de pointage."""
    base = {'session': session}
    if type_personne == 'formateur':
        base['formateur'] = personne
    elif type_personne == 'encadrant':
        base['encadrant'] = personne
    else:
        base['participant'] = personne
    base.update(extra)
    return base


def _find_open_pointage_same_module_day(
    personne, type_personne, module, date_journee, exclude_session_id=None
):
    """
    Retourne le pointage ouvert d'une personne sur le même module et jour.
    Utilisé pour empêcher une nouvelle entrée sur une autre séance
    tant que la précédente n'est pas terminée.
    """
    filt = (
        {'formateur': personne}
        if type_personne == 'formateur'
        else {'encadrant': personne}
        if type_personne == 'encadrant'
        else {'participant': personne}
    )
    qs = Pointage.objects.select_for_update().filter(
        **filt,
        session__module=module,
        date_journee=date_journee,
        timestamp_sortie__isnull=True,
    )
    if exclude_session_id is not None:
        qs = qs.exclude(session_id=exclude_session_id)
    return qs.order_by('-timestamp_entree').first()


def _has_unfinished_previous_session(seance):
    """
    Retourne True si une séance précédente du même module et du même jour
    n'est pas encore terminée.
    """
    return SessionModule.objects.filter(
        module=seance.module,
        date_journee=seance.date_journee,
        numero__lt=seance.numero,
        terminee_le__isnull=True,
    ).exists()


def _get_accessible_formation(user, pk):
    """
    Récupère une formation accessible par l'utilisateur.
    Délègue à formations.access.formation_accessible pour une logique centralisée.
    """
    from formations.access import formation_accessible
    return formation_accessible(user, pk)


def _check_fenetre_entree(seance):
    """
    Vérifie que le scan d'entrée se fait dans la fenêtre autorisée :
      - Le jour du scan doit correspondre à seance.date_journee
      - L'heure courante ne doit pas dépasser heure_fin_prevue (si renseignée)
    Retourne None si OK, sinon une Response d'erreur.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    tz = ZoneInfo('Africa/Abidjan')
    now_local = timezone.localtime(timezone.now())
    today = now_local.date()

    # Mauvais jour
    if seance.date_journee and seance.date_journee != today:
        return Response(
            {'code': 'WRONG_DAY',
             'detail': f'Ce QR code est prévu pour le {seance.date_journee.strftime("%d/%m/%Y")}. Le badgeage n\'est pas autorisé aujourd\'hui.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Heure après la fin prévue de la séance
    if seance.heure_fin_prevue and now_local.time() > seance.heure_fin_prevue:
        return Response(
            {'code': 'SESSION_TIME_OVER',
             'detail': f'La fenêtre de badgeage est dépassée. La séance était prévue jusqu\'à {seance.heure_fin_prevue.strftime("%H:%M")}.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return None


def _clamp_to_seance(ts, seance):
    """Borne un timestamp aux heures prévues de la séance (règle commune ``presences.duree``)."""
    from .duree import clamp_to_seance
    return clamp_to_seance(ts, seance)


def _resolve_authenticated_personne(user, *, ensure_profile=False):
    """Retourne (personne, type_str, error_response).

    La résolution se fait d'abord par rôle utilisateur pour éviter qu'un encadrant
    ou formateur avec un profil auditeur résiduel soit traité comme participant.

    ``ensure_profile=True`` synchronise les fiches métier (login, my_fiche) ;
    le chemin scan/heartbeat l'omet volontairement pour limiter la charge DB.
    """
    if ensure_profile:
        from authentication.profile_sync import sync_user_profile_links
        sync_user_profile_links(user)

    if user_is_mobile_encadrant(user):
        matricule = (user.matricule or user.username or '').strip()
        if not matricule:
            return None, None, Response(
                {
                    'code': 'NO_MATRICULE',
                    'detail': 'Aucun matricule renseigné sur votre compte encadrant.',
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return user, 'encadrant', None

    if user_in_roles(user, {'FORMATEUR'}):
        formateur = Formateur.objects.filter(user_id=user.pk).first()
        if formateur:
            return formateur, 'formateur', None
        return None, None, Response(
            {
                'code': 'NO_PROFILE',
                'detail': 'Aucun profil formateur lié à ce compte.',
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    participant = Participant.objects.filter(user_id=user.pk).first()
    if participant is None:
        mat_filters = Q()
        for raw in (getattr(user, 'matricule', ''), getattr(user, 'username', '')):
            val = (raw or '').strip()
            if val:
                mat_filters |= Q(matricule__iexact=val)
        if mat_filters:
            participant = Participant.objects.filter(mat_filters).first()
    if participant:
        return participant, 'participant', None

    return None, None, Response(
        {
            'code': 'NO_PROFILE',
            'detail': 'Aucun profil étudiant, formateur ou encadrant lié à ce compte.',
        },
        status=status.HTTP_403_FORBIDDEN,
    )


def _encadrant_can_badge_module(user, module):
    """Encadrant autorisé s'il supervise le module ou si aucun encadrant n'est assigné."""
    if module.superviseur_id == user.pk:
        return True
    return module.superviseur_id is None


def _encadrant_not_in_list_response(module):
    return Response(
        {
            'code': 'NOT_IN_LIST',
            'detail': (
                "Vous n'êtes pas encadrant de ce module. "
                'Demandez au secrétariat de vous assigner au module '
                f'« {module.intitule} ».'
            ),
        },
        status=status.HTTP_403_FORBIDDEN,
    )


def _require_mobile_device_id(type_str, device_id):
    """device_id obligatoire pour auditeur/formateur (verrouillage appareil)."""
    if type_str not in ('participant', 'formateur'):
        return None
    if not (device_id or '').strip():
        return Response(
            {
                'code': 'DEVICE_REQUIRED',
                'detail': "L'identifiant appareil est requis pour le badgeage mobile.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _distance_meters(lat1, lon1, lat2, lon2):
    """Distance approximative en mètres (haversine)."""
    return geofence.distance_meters(lat1, lon1, lat2, lon2)


def _resolve_site_geofence(module):
    """
    Retourne (lat, lon, rayon_m) pour le site du module, ou (None, None, None)
    si aucun RefSite correspondant ne possède de geofence configurée.
    Le lien se fait préférentiellement par FK (Module.site → RefSite),
    avec fallback legacy par nom si nécessaire.
    """
    # Nouveau modèle: module.site est une FK.
    site_obj = getattr(module, 'site', None)
    if site_obj is not None:
        # Peut être un objet RefSite déjà chargé, ou juste un id.
        try:
            site_id = getattr(module, 'site_id', None)
        except Exception:
            site_id = None
        if site_id:
            site = RefSite.objects.filter(pk=site_id).first()
        elif getattr(site_obj, 'pk', None):
            site = site_obj
        else:
            site = None
    else:
        site = None

    if site is None:
        # Fallback legacy: match par texte
        site_name = (getattr(module, 'site_legacy', '') or '').strip()
        if not site_name:
            return None, None, None
        site = RefSite.objects.filter(nom__iexact=site_name).first()

    if geofence.site_non_localise(site):
        return None, None, None
    return site.geofence_latitude, site.geofence_longitude, geofence.rayon_du_site(site)


def _check_geofence(module, latitude, longitude, accuracy_m=None):
    """
    Vérifie si la position est dans la zone autorisée du site du module.
    Retourne (ok, code, detail, distance_m, rayon_m).

    Délégué à `presences.geofence`, module partagé avec le canal EDT
    (`seances_edt_services._controle_geofence_edt`) : les deux canaux appliquent
    ainsi strictement la même règle de périmètre.
    """
    return geofence.verifier_geofence_module(module, latitude, longitude, accuracy_m)


# ──────────────────────────────────────────────
# Empilement canal EDT/LMD — QR de séance planifiée
# ──────────────────────────────────────────────
# Un ``QRToken`` peut viser une séance **LMD** (``seance_edt``) au lieu d'une
# ``SessionModule`` legacy. Les endpoints mobiles existants servent alors le
# service des séances LMD (``presences.seances_edt_services``) : aucune seconde
# route, aucun second heartbeat n'est créé — l'application mobile interroge les
# mêmes URLs et le serveur route selon le jeton présenté.

def _coords_from_payload(donnees):
    """Télémétrie mobile → champs ``Pointage`` (position GPS + état appareil)."""
    coords = {}
    for cle, champ in (('latitude', 'last_latitude'), ('longitude', 'last_longitude'),
                       ('accuracy_m', 'last_accuracy_m'),
                       ('battery_level', 'last_battery_level'),
                       ('is_charging', 'last_is_charging')):
        if cle in (donnees or {}):
            coords[champ] = donnees.get(cle)
    return coords or None


def _jeton_lmd_pour_mobile(qr_token):
    """``(jeton, erreur)`` — suit un QR de séance LMD remplacé ou expiré.

    Un QR régénéré par l'enseignant invalide l'ancien jeton : le mobile qui
    présente encore l'ancien QR doit être redirigé vers le remplaçant actif
    tant que celui-ci est valide (sinon ``TOKEN_EXPIRED``).
    """
    from . import seances_edt_services as service

    if qr_token is not None and qr_token.is_valid:
        return qr_token, None
    return service.resoudre_jeton_lmd(getattr(qr_token, 'token', qr_token))


def _scan_seance_edt_mobile(*, request, qr_token, personne, type_str, device_id, donnees):
    """Badgeage mobile d'une séance LMD (QR d'affectation de créneau).

    Mêmes règles que le canal legacy : identité déduite du compte, autorisation
    serveur, géofence calculée côté serveur, 1 entrée + 1 sortie, journal
    d'audit. Le corps de réponse conserve les clés attendues par l'application
    mobile (``action``, ``heure_entree``, ``seance_intitule``…).
    """
    from . import seances_edt_services as service

    affectation = qr_token.seance_edt
    date = timezone.localdate()
    if not service.est_seance_du_jour(affectation, date):
        return Response({'code': 'HORS_SEANCE',
                         'detail': 'Ce créneau n’a pas séance aujourd’hui.'},
                        status=status.HTTP_400_BAD_REQUEST)

    autorise, code, detail, http = service.autorisation_badgeage(
        request.user, personne, type_str, affectation)
    if not autorise:
        return Response({'code': code, 'detail': detail},
                        status=http or status.HTTP_403_FORBIDDEN)

    label = affectation.intitule or str(affectation.creneau_template)
    action, pointage, erreur = service.badger_scan(
        request, personne=personne, affectation=affectation, date=date,
        device_id=device_id, coords=_coords_from_payload(donnees),
        type_personne=type_str)
    if erreur:
        return Response(erreur, status=status.HTTP_400_BAD_REQUEST)

    numero, nom, prenom = service.libelle_personne(personne, type_str)
    personne_data = {'numero': numero, 'nom': nom, 'prenom': prenom}
    return Response({
        'action': action,
        'canal': 'EDT_LMD',
        'type_personne': type_str,
        'participant': personne_data if type_str == 'participant' else None,
        'formateur': personne_data if type_str == 'formateur' else None,
        'encadrant': personne_data if type_str == 'encadrant' else None,
        'seance': {'id': affectation.pk, 'intitule': label, 'date': date.isoformat()},
        'seance_intitule': label,
        'date': date.isoformat(),
        'pointage_id': pointage.pk,
        'statut': pointage.statut,
        'statut_assiduite': pointage.statut_assiduite,
        'timestamp': (pointage.timestamp_sortie if action == 'SORTIE'
                      else pointage.timestamp_entree),
        'heure_entree': timezone.localtime(pointage.timestamp_entree).strftime('%H:%M'),
        'duree_session_minutes': (float(pointage.duree_presence_minutes)
                                  if pointage.duree_presence_minutes is not None else None),
        'message': f'{action} enregistrée ({label}).',
    }, status=(status.HTTP_201_CREATED if action == 'ENTREE' else status.HTTP_200_OK))


def _heartbeat_seance_edt_mobile(*, request, qr_token, personne, type_str, device_id, donnees):
    """Heartbeat mobile d'une séance LMD (même endpoint que le canal legacy)."""
    from . import seances_edt_services as service

    charge, erreur = service.heartbeat_seance(
        request, personne=personne, affectation=qr_token.seance_edt,
        date=timezone.localdate(), device_id=device_id,
        coords=_coords_from_payload(donnees), type_personne=type_str)
    if erreur:
        return Response(erreur, status=status.HTTP_400_BAD_REQUEST)
    return Response(charge)


def _check_status_seance_edt_mobile(*, request, qr_token, personne, type_str):
    """État du badgeage LMD pour ``/api/scan/secure/check-status/``.

    La position éventuellement jointe par le client (query string) sert
    uniquement à **afficher** l'état de périmètre ; le calcul reste serveur.
    """
    from . import seances_edt_services as service

    def _nombre(brut):
        try:
            return float(brut) if brut not in (None, '') else None
        except (TypeError, ValueError):
            return None

    coords = {
        'last_latitude': _nombre(request.GET.get('latitude')),
        'last_longitude': _nombre(request.GET.get('longitude')),
        'last_accuracy_m': _nombre(request.GET.get('accuracy_m')),
    }
    return Response(service.etat_badgeage_seance(
        request, personne=personne, affectation=qr_token.seance_edt,
        date=timezone.localdate(), type_personne=type_str,
        coords={cle: val for cle, val in coords.items() if val is not None} or None))


# ──────────────────────────────────────────────
# ENDPOINT /api/scan/ — Participants & Formateurs
# ──────────────────────────────────────────────

def _public_scan_disabled_response():
    return Response(
        {
            'code': 'SCAN_DISABLED',
            'detail': (
                'Le badgeage public est désactivé. '
                'Utilisez l\'application mobile QR Badge pour pointer.'
            ),
        },
        status=status.HTTP_403_FORBIDDEN,
    )


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([ScanRateThrottle])
def scan_view(request):
    """
    Endpoint de scan QR — gère ENTREE et SORTIE pour participants (P0001) et formateurs (F0001).

    body: { token_qr, numero_participant, device_id }

    Désactivé en production sauf PUBLIC_QR_SCAN_ENABLED=True (voir settings).
    Préférer /api/scan/secure/ (JWT + profil lié + géofence) pour l'app mobile.
    """
    if not settings.PUBLIC_QR_SCAN_ENABLED:
        return _public_scan_disabled_response()
    serializer = ScanSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    # 1. Vérifier token QR valide
    try:
        qr_token = QRToken.objects.select_related('session__module__formation').get(
            token=data['token_qr']
        )
    except QRToken.DoesNotExist:
        return Response(
            {'code': 'INVALID_TOKEN', 'detail': 'QR code invalide.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if qr_token.is_expired:
        return Response(
            {'code': 'TOKEN_EXPIRED', 'detail': 'QR code expiré.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Si le token a été remplacé (regeneration QR), utiliser le token actif courant
    if not qr_token.actif:
        replacement = QRToken.objects.filter(
            session=qr_token.session,
            actif=True,
        ).order_by('-created_at').first()
        if replacement and replacement.is_valid:
            qr_token = replacement
        else:
            return Response(
                {'code': 'TOKEN_EXPIRED', 'detail': 'QR code désactivé. Aucun QR actif pour cette séance.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    seance = qr_token.session
    if not seance:
        return Response({'code': 'NO_SESSION', 'detail': 'Ce QR code n\'est pas lié à une séance.'}, status=status.HTTP_400_BAD_REQUEST)
    if seance.est_terminee:
        return Response(
            {'code': 'TOKEN_EXPIRED', 'detail': 'QR code désactivé. Cette séance est terminée.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    formation = seance.module.formation

    # 2. Résoudre la personne (participant ou formateur)
    personne, type_str, personne_data, err = _resolve_personne(
        data['numero_participant'], formation, seance.module, seance=seance
    )
    if err:
        return err

    role_map = {
        'participant': 'Participant',
        'formateur': 'Formateur',
        'encadrant': 'Encadrant',
    }
    role_label = role_map.get(type_str, 'Participant')

    # 3. Chercher une session ouverte aujourd'hui (transaction + verrou)
    today = timezone.localdate()
    device_id = data.get('device_id', '')

    with transaction.atomic():
        if type_str == 'formateur':
            Formateur.objects.select_for_update().get(pk=personne.pk)
        elif type_str == 'encadrant':
            User.objects.select_for_update().get(pk=personne.pk)
        else:
            Participant.objects.select_for_update().get(pk=personne.pk)

        # Filtres de base pour cette séance
        session_filter = _pointage_filter(personne, type_str, formation, date_journee=today)
        session_filter['session'] = seance

        # Vérifier si un pointage TERMINÉ existe déjà pour cette séance → bloquer
        pointage_termine = Pointage.objects.filter(
            **session_filter, timestamp_sortie__isnull=False,
        ).exists()
        if pointage_termine:
            seance_label = seance.intitule or f"Séance {seance.numero}"
            return Response({
                'code': 'ALREADY_SCANNED',
                'detail': f'Vous avez déjà pointé (entrée + sortie) pour « {seance_label} ».',
            }, status=status.HTTP_400_BAD_REQUEST)

        # "Ouverte" = timestamp_sortie NULL
        pointage_ouvert = Pointage.objects.select_for_update().filter(
            **session_filter, timestamp_sortie__isnull=True,
        ).order_by('-timestamp_entree').first()

        if pointage_ouvert:
            pointage_ouvert.timestamp_sortie = _clamp_to_seance(timezone.now(), seance)
            pointage_ouvert.statut = Pointage.Statut.TERMINE
            pointage_ouvert.calculer_duree()
            pointage_ouvert.save()

            _log_audit(
                action=AuditLog.Action.SCAN_SORTIE,
                request=request,
                cible_type=type_str,
                cible_numero=personne_data['numero'],
                cible_nom=f"{personne_data['nom']} {personne_data['prenom']}",
                pointage=pointage_ouvert,
                device_id=device_id,
                extra={'duree_minutes': float(pointage_ouvert.duree_presence_minutes or 0)},
            )

            total_jour, nb_sessions = _daily_completed_sessions_stats(
                personne, type_str, formation, today
            )

            return Response({
                'action': 'SORTIE',
                'type_personne': type_str,
                'participant': personne_data if type_str == 'participant' else None,
                'formateur': personne_data if type_str == 'formateur' else None,
                'encadrant': personne_data if type_str == 'encadrant' else None,
                'date': str(today),
                'timestamp': pointage_ouvert.timestamp_sortie,
                'duree_session_minutes': pointage_ouvert.duree_presence_minutes,
                'duree_total_jour_minutes': round(total_jour, 2),
                'nb_sessions': nb_sessions,
                'message': (
                    f'Sortie enregistrée ({role_label}). '
                    f'Session : {pointage_ouvert.duree_presence_minutes} min | '
                    f'Total jour : {round(total_jour)} min ({nb_sessions} session(s)).'
                ),
            })

        pointage_ouvert_autre_seance = _find_open_pointage_same_module_day(
            personne=personne,
            type_personne=type_str,
            module=seance.module,
            date_journee=today,
            exclude_session_id=seance.id,
        )
        if pointage_ouvert_autre_seance:
            seance_label = (
                pointage_ouvert_autre_seance.session.intitule
                or f"Séance {pointage_ouvert_autre_seance.session.numero}"
            )
            return Response(
                {
                    'code': 'SESSION_ALREADY_OPEN',
                    'detail': (
                        f'Une autre session est déjà en cours sur ce module '
                        f'({seance_label}). Terminez-la d’abord.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if _has_unfinished_previous_session(seance):
            return Response(
                {
                    'code': 'PREVIOUS_SESSION_NOT_TERMINATED',
                    'detail': (
                        'Impossible de badger cette séance tant que la '
                        'séance précédente du même jour n’est pas terminée.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        nb_sessions_existantes = Pointage.objects.filter(
            **_pointage_filter(
                personne, type_str, formation,
                date_journee=today,
                timestamp_sortie__isnull=False,
            )
        ).count()

        # Block new ENTREE if the session is already terminated
        if seance.est_terminee:
            return Response(
                {'code': 'SESSION_TERMINATED', 'detail': 'La séance est terminée. Aucune nouvelle entrée possible.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Vérifier la fenêtre horaire et le jour
        fenetre_err = _check_fenetre_entree(seance)
        if fenetre_err:
            return fenetre_err

        timestamp_entree = _clamp_to_seance(timezone.now(), seance)
        create_kwargs = _create_pointage_kwargs(
            personne, type_str, seance,
            date_journee=today,
            device_id=device_id,
            timestamp_entree=timestamp_entree,
            statut=Pointage.Statut.EN_COURS,
        )

        pointage = Pointage.objects.create(**create_kwargs)

        if type_str == 'participant':
            from .rattrapage_service import lier_rattrapage_au_badge
            lier_rattrapage_au_badge(personne, seance, pointage, request=request)

        _log_audit(
            action=AuditLog.Action.SCAN_ENTREE,
            request=request,
            cible_type=type_str,
            cible_numero=personne_data['numero'],
            cible_nom=f"{personne_data['nom']} {personne_data['prenom']}",
            formation=formation,
            pointage=pointage,
            device_id=device_id,
        )

        return Response({
            'action': 'ENTREE',
            'type_personne': type_str,
            'participant': personne_data if type_str == 'participant' else None,
            'formateur': personne_data if type_str == 'formateur' else None,
            'encadrant': personne_data if type_str == 'encadrant' else None,
            'date': str(today),
            'timestamp': pointage.timestamp_entree,
            'duree_presence_minutes': None,
            'nb_sessions': nb_sessions_existantes + 1,
            'message': f'Entrée enregistrée ({role_label}).',
        }, status=status.HTTP_201_CREATED)


# ──────────────────────────────────────────────
# ENDPOINT /api/scan/secure/ — App mobile (anti-fraude)
# Le numéro est déduit du user connecté : impossible de badger pour autrui.
# ──────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScanRateThrottle])
def secure_scan_view(request):
    """
    Scan sécurisé pour l'app mobile.
    Le participant/formateur doit être authentifié.
    Son numéro est automatiquement déduit de son profil — anti-fraude.

    body: { token_qr, device_id }
    """
    serializer = SecureScanSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    user = request.user
    if getattr(user, 'must_change_password', False):
        return _password_change_required_response()

    # 1. Résoudre le profil participant/formateur/encadrant lié au user
    personne, type_str, err = _resolve_authenticated_personne(user)
    if err:
        return err

    device_err = _require_mobile_device_id(type_str, data.get('device_id', ''))
    if device_err:
        return device_err

    # 1b. Vérifier que l'appareil est bien lié à ce user
    device_id = data.get('device_id', '')
    if device_id and type_str in ('participant', 'formateur'):
        binding = DeviceBinding.objects.filter(
            device_id=device_id, is_active=True
        ).first()
        if binding and binding.user_id != user.id:
            return Response(
                {'code': 'DEVICE_MISMATCH',
                 'detail': 'Cet appareil est lié à un autre compte. '
                           'Contactez votre superviseur.'},
                status=status.HTTP_403_FORBIDDEN,
            )

    # 2. Vérifier token QR valide
    try:
        qr_token = QRToken.objects.select_related(
            'session__module__formation', 'seance_edt__creneau_template',
            'seance_edt__emploi_du_temps__annee_academique', 'seance_edt__groupe',
        ).get(
            token=data['token_qr']
        )
    except QRToken.DoesNotExist:
        return Response(
            {'code': 'INVALID_TOKEN', 'detail': 'QR code invalide.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Empilement canal EDT/LMD : un QR de séance planifiée est traité par le
    # service des séances LMD (aucune seconde route, aucun second heartbeat).
    if qr_token.seance_edt_id is not None:
        jeton, erreur = _jeton_lmd_pour_mobile(qr_token)
        if erreur is not None:
            return Response(erreur, status=status.HTTP_400_BAD_REQUEST)
        return _scan_seance_edt_mobile(
            request=request, qr_token=jeton, personne=personne, type_str=type_str,
            device_id=device_id, donnees=data,
        )

    if qr_token.is_expired:
        return Response(
            {'code': 'TOKEN_EXPIRED', 'detail': 'QR code expiré.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Si le token a été remplacé (regeneration QR), utiliser le token actif courant
    if not qr_token.actif:
        replacement = QRToken.objects.filter(
            session=qr_token.session,
            actif=True,
        ).order_by('-created_at').first()
        if replacement and replacement.is_valid:
            qr_token = replacement
        else:
            return Response(
                {'code': 'TOKEN_EXPIRED', 'detail': 'QR code désactivé. Aucun QR actif pour cette séance.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    seance = qr_token.session
    if not seance:
        return Response({'code': 'NO_SESSION', 'detail': 'Ce QR code n\'est pas lié à une séance.'}, status=status.HTTP_400_BAD_REQUEST)
    if seance.est_terminee:
        return Response(
            {'code': 'TOKEN_EXPIRED', 'detail': 'QR code désactivé. Cette séance est terminée.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    formation = seance.module.formation

    # 3. Vérifier inscription à la formation
    if type_str == 'formateur':
        if not ModuleFormateur.objects.filter(
            module=seance.module, formateur=personne
        ).exists():
            return Response(
                {'code': 'NOT_IN_LIST',
                 'detail': 'Vous n\'êtes pas assigné(e) à ce module.'},
                status=status.HTTP_403_FORBIDDEN,
            )
    elif type_str == 'encadrant':
        if not _encadrant_can_badge_module(user, seance.module):
            return _encadrant_not_in_list_response(seance.module)
    else:
        from .participant_scope import participant_for_module
        inscrit = participant_for_module(user, seance.module, seance=seance)
        if inscrit is None:
            return Response(
                {'code': 'NOT_IN_LIST',
                 'detail': 'Vous n\'êtes pas inscrit(e) à ce module.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        # On badge sur la fiche réellement inscrite (gère un compte rattaché à une autre fiche).
        personne = inscrit

    personne_data = {
        'numero': (
            getattr(personne, 'matricule', None)
            or getattr(personne, 'numerobadge', None)
            or getattr(personne, 'numero', '')
        ),
        'nom': getattr(personne, 'nom', None) or getattr(personne, 'last_name', '') or '',
        'prenom': getattr(personne, 'prenom', None) or getattr(personne, 'first_name', '') or '',
    }
    role_map = {
        'participant': 'Participant',
        'formateur': 'Formateur',
        'encadrant': 'Encadrant',
    }
    role_label = role_map.get(type_str, 'Participant')

    # 4. Logique entrée/sortie — 1 entrée + 1 sortie par séance
    today = timezone.localdate()

    with transaction.atomic():
        if type_str == 'formateur':
            Formateur.objects.select_for_update().get(pk=personne.pk)
        elif type_str == 'encadrant':
            User.objects.select_for_update().get(pk=personne.pk)
        else:
            Participant.objects.select_for_update().get(pk=personne.pk)

        # Filtres de base pour cette séance
        session_filter = _pointage_filter(personne, type_str, formation, date_journee=today)
        session_filter['session'] = seance

        # Vérifier si un pointage TERMINÉ existe déjà pour cette séance → bloquer
        pointage_termine = Pointage.objects.filter(
            **session_filter, timestamp_sortie__isnull=False,
        ).exists()
        if pointage_termine:
            seance_label = seance.intitule or f"Séance {seance.numero}"
            return Response({
                'code': 'ALREADY_SCANNED',
                'detail': f'Vous avez déjà pointé (entrée + sortie) pour « {seance_label} ».',
            }, status=status.HTTP_400_BAD_REQUEST)

        # "Ouverte" = timestamp_sortie NULL
        pointage_ouvert = Pointage.objects.select_for_update().filter(
            **session_filter, timestamp_sortie__isnull=True,
        ).order_by('-timestamp_entree').first()

        if pointage_ouvert:
            pointage_ouvert.timestamp_sortie = _clamp_to_seance(timezone.now(), seance)
            pointage_ouvert.statut = Pointage.Statut.TERMINE
            pointage_ouvert.calculer_duree()
            pointage_ouvert.save()

            _log_audit(
                action=AuditLog.Action.SCAN_SECURE_SORTIE,
                request=request,
                cible_type=type_str,
                cible_numero=personne_data['numero'],
                cible_nom=f"{personne_data['nom']} {personne_data['prenom']}",
                formation=formation,
                pointage=pointage_ouvert,
                device_id=device_id,
                extra={'duree_minutes': float(pointage_ouvert.duree_presence_minutes or 0)},
            )

            total_jour, nb_sessions = _daily_completed_sessions_stats(
                personne, type_str, formation, today
            )

            return Response({
                'action': 'SORTIE',
                'type_personne': type_str,
                'participant': personne_data if type_str == 'participant' else None,
                'formateur': personne_data if type_str == 'formateur' else None,
                'encadrant': personne_data if type_str == 'encadrant' else None,
                'formation': {'id': formation.id, 'titre': formation.formation},
                'date': str(today),
                'timestamp': pointage_ouvert.timestamp_sortie,
                'duree_session_minutes': pointage_ouvert.duree_presence_minutes,
                'duree_total_jour_minutes': round(total_jour, 2),
                'nb_sessions': nb_sessions,
                'message': (
                    f'Sortie enregistrée ({role_label}). '
                    f'Session : {pointage_ouvert.duree_presence_minutes} min | '
                    f'Total jour : {round(total_jour)} min ({nb_sessions} session(s)).'
                ),
            })

        pointage_ouvert_autre_seance = _find_open_pointage_same_module_day(
            personne=personne,
            type_personne=type_str,
            module=seance.module,
            date_journee=today,
            exclude_session_id=seance.id,
        )
        if pointage_ouvert_autre_seance:
            seance_label = (
                pointage_ouvert_autre_seance.session.intitule
                or f"Séance {pointage_ouvert_autre_seance.session.numero}"
            )
            return Response(
                {
                    'code': 'SESSION_ALREADY_OPEN',
                    'detail': (
                        f'Une autre session est déjà en cours sur ce module '
                        f'({seance_label}). Terminez-la d’abord.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if _has_unfinished_previous_session(seance):
            return Response(
                {
                    'code': 'PREVIOUS_SESSION_NOT_TERMINATED',
                    'detail': (
                        'Impossible de badger cette séance tant que la '
                        'séance précédente du même jour n’est pas terminée.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        nb_sessions_existantes = Pointage.objects.filter(
            **_pointage_filter(
                personne, type_str, formation,
                date_journee=today,
                timestamp_sortie__isnull=False,
            )
        ).count()

        # Block new ENTREE if the session is already terminated
        if seance.est_terminee:
            return Response(
                {'code': 'SESSION_TERMINATED', 'detail': 'La séance est terminée. Aucune nouvelle entrée possible.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Vérifier la fenêtre horaire et le jour
        fenetre_err = _check_fenetre_entree(seance)
        if fenetre_err:
            return fenetre_err

        latitude = data.get('latitude')
        longitude = data.get('longitude')
        accuracy_m = data.get('accuracy_m')
        battery_level = data.get('battery_level')
        is_charging = data.get('is_charging')

        if (latitude is None) ^ (longitude is None):
            return Response(
                {
                    'code': 'LOCATION_INVALID',
                    'detail': 'latitude et longitude doivent être fournis ensemble.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        site_lat_cfg, site_lon_cfg, _site_rayon = _resolve_site_geofence(seance.module)
        if site_lat_cfg is not None and latitude is None:
            return Response(
                {
                    'code': 'LOCATION_REQUIRED',
                    'detail': 'La géolocalisation est obligatoire pour badger cette séance.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        distance_m = None
        rayon_m = None
        if latitude is not None and longitude is not None:
            geo_ok, geo_code, geo_detail, distance_m, rayon_m = _check_geofence(
                seance.module, latitude, longitude, accuracy_m
            )
            if not geo_ok:
                return Response({'code': geo_code, 'detail': geo_detail}, status=status.HTTP_400_BAD_REQUEST)

        timestamp_entree = _clamp_to_seance(timezone.now(), seance)
        create_kwargs = _create_pointage_kwargs(
            personne, type_str, seance,
            date_journee=today,
            device_id=device_id,
            last_heartbeat_at=timezone.now(),
            last_latitude=latitude,
            last_longitude=longitude,
            last_accuracy_m=accuracy_m,
            last_battery_level=battery_level,
            last_is_charging=is_charging,
            timestamp_entree=timestamp_entree,
            statut=Pointage.Statut.EN_COURS,
        )

        pointage = Pointage.objects.create(**create_kwargs)

        if type_str == 'participant':
            from .rattrapage_service import lier_rattrapage_au_badge
            lier_rattrapage_au_badge(personne, seance, pointage, request=request)

        _log_audit(
            action=AuditLog.Action.SCAN_SECURE_ENTREE,
            request=request,
            cible_type=type_str,
            cible_numero=personne_data['numero'],
            cible_nom=f"{personne_data['nom']} {personne_data['prenom']}",
            formation=formation,
            pointage=pointage,
            device_id=device_id,
            extra={
                'distance_m': round(distance_m, 1) if distance_m is not None else None,
                'rayon_m': round(rayon_m, 1) if rayon_m is not None else None,
                'accuracy_m': accuracy_m,
                'battery_level': battery_level,
                'is_charging': is_charging,
            },
        )

        return Response({
            'action': 'ENTREE',
            'type_personne': type_str,
            'participant': personne_data if type_str == 'participant' else None,
            'formateur': personne_data if type_str == 'formateur' else None,
            'encadrant': personne_data if type_str == 'encadrant' else None,
            'formation': {'id': formation.id, 'titre': formation.formation},
            'date': str(today),
            'timestamp': pointage.timestamp_entree,
            'duree_presence_minutes': None,
            'nb_sessions': nb_sessions_existantes + 1,
            'message': f'Entrée enregistrée ({role_label}).',
        }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ScanRateThrottle])
def secure_scan_heartbeat(request):
    """
    Heartbeat mobile sécurisé pendant une session ouverte.
    body: { token_qr, device_id, latitude, longitude, accuracy_m?, battery_level?, is_charging? }
    """
    serializer = SecureHeartbeatSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    user = request.user
    if getattr(user, 'must_change_password', False):
        return _password_change_required_response()
    personne, type_str, err = _resolve_authenticated_personne(user)
    if err:
        return err

    device_err = _require_mobile_device_id(type_str, data.get('device_id', ''))
    if device_err:
        return device_err

    device_id = data.get('device_id', '')
    if device_id and type_str in ('participant', 'formateur'):
        binding = DeviceBinding.objects.filter(
            device_id=device_id, is_active=True
        ).first()
        if binding and binding.user_id != user.id:
            return Response(
                {
                    'code': 'DEVICE_MISMATCH',
                    'detail': 'Cet appareil est lié à un autre compte. Contactez votre superviseur.',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

    try:
        qr_token = QRToken.objects.select_related(
            'session__module__formation', 'seance_edt__creneau_template',
            'seance_edt__emploi_du_temps__annee_academique', 'seance_edt__groupe',
        ).get(
            token=data['token_qr']
        )
    except QRToken.DoesNotExist:
        return Response(
            {'code': 'INVALID_TOKEN', 'detail': 'QR code invalide.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Empilement canal EDT/LMD : le heartbeat d'une séance planifiée est traité
    # par le service des séances LMD, sur ce même endpoint (aucun second
    # mécanisme de heartbeat n'existe dans le projet).
    if qr_token.seance_edt_id is not None:
        jeton, erreur = _jeton_lmd_pour_mobile(qr_token)
        if erreur is not None:
            return Response(erreur, status=status.HTTP_400_BAD_REQUEST)
        return _heartbeat_seance_edt_mobile(
            request=request, qr_token=jeton, personne=personne, type_str=type_str,
            device_id=device_id, donnees=data,
        )

    if qr_token.is_expired:
        return Response(
            {'code': 'TOKEN_EXPIRED', 'detail': 'QR code expiré.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not qr_token.actif:
        replacement = QRToken.objects.filter(
            session=qr_token.session,
            actif=True,
        ).order_by('-created_at').first()
        if replacement and replacement.is_valid:
            qr_token = replacement
        else:
            return Response(
                {'code': 'TOKEN_EXPIRED', 'detail': 'QR code désactivé. Aucun QR actif pour cette séance.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    seance = qr_token.session
    if not seance:
        return Response({'code': 'NO_SESSION', 'detail': "Ce QR code n'est pas lié à une séance."}, status=status.HTTP_400_BAD_REQUEST)
    if seance.est_terminee:
        return Response(
            {'code': 'SESSION_TERMINATED', 'detail': 'La séance est terminée.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    formation = seance.module.formation

    if type_str == 'formateur':
        if not ModuleFormateur.objects.filter(module=seance.module, formateur=personne).exists():
            return Response({'code': 'NOT_IN_LIST', 'detail': "Vous n'êtes pas assigné(e) à ce module."}, status=status.HTTP_403_FORBIDDEN)
    elif type_str == 'encadrant':
        if not _encadrant_can_badge_module(user, seance.module):
            return _encadrant_not_in_list_response(seance.module)
    else:
        from .participant_scope import participant_for_module
        inscrit = participant_for_module(user, seance.module, seance=seance)
        if inscrit is None:
            return Response({'code': 'NOT_IN_LIST', 'detail': "Vous n'êtes pas inscrit(e) à ce module."}, status=status.HTTP_403_FORBIDDEN)
        personne = inscrit

    today = timezone.localdate()
    session_filter = _pointage_filter(personne, type_str, formation, date_journee=today)
    session_filter['session'] = seance
    pointage = Pointage.objects.filter(
        **session_filter, timestamp_sortie__isnull=True
    ).order_by('-timestamp_entree').first()
    if not pointage:
        return Response(
            {
                'code': 'NO_OPEN_SESSION',
                'detail': 'Aucune session ouverte à mettre à jour pour ce QR.',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    latitude = data['latitude']
    longitude = data['longitude']
    accuracy_m = data.get('accuracy_m')
    battery_level = data.get('battery_level')
    is_charging = data.get('is_charging')

    geo_ok, geo_code, geo_detail, distance_m, rayon_m = _check_geofence(
        seance.module, latitude, longitude, accuracy_m
    )
    outside_limit = max(1, int(getattr(settings, 'MOBILE_GEOFENCE_OUTSIDE_CONFIRMATIONS', 2)))
    previous_heartbeat_at = pointage.last_heartbeat_at

    pointage.last_heartbeat_at = timezone.now()
    pointage.last_latitude = latitude
    pointage.last_longitude = longitude
    pointage.last_accuracy_m = accuracy_m
    pointage.last_battery_level = battery_level
    pointage.last_is_charging = is_charging
    if geo_ok:
        pointage.outside_geofence_count = 0
        if pointage.statut == Pointage.Statut.HORS_LIGNE_SUSPECT:
            pointage.statut = Pointage.Statut.EN_COURS
        pointage.save(
            update_fields=[
                'last_heartbeat_at',
                'last_latitude',
                'last_longitude',
                'last_accuracy_m',
                'last_battery_level',
                'last_is_charging',
                'outside_geofence_count',
                'statut',
                'updated_at',
            ]
        )
        if _should_log_heartbeat_audit(previous_heartbeat_at):
            _log_audit(
                action=AuditLog.Action.SCAN_HEARTBEAT,
                request=request,
                cible_type=type_str,
                cible_numero=getattr(personne, 'matricule', None) or getattr(personne, 'numerobadge', None) or '',
                cible_nom=(getattr(personne, 'nom', None) or getattr(personne, 'last_name', '') or '') + ' ' + (getattr(personne, 'prenom', None) or getattr(personne, 'first_name', '') or ''),
                formation=formation,
                pointage=pointage,
                device_id=device_id,
                extra={
                    'distance_m': round(distance_m, 1) if distance_m is not None else None,
                    'rayon_m': round(rayon_m, 1) if rayon_m is not None else None,
                    'accuracy_m': accuracy_m,
                    'battery_level': battery_level,
                    'is_charging': is_charging,
                },
            )
        return Response(
            {
                'detail': 'Heartbeat enregistré.',
                'statut': pointage.statut,
                'outside_geofence_count': pointage.outside_geofence_count,
                'distance_m': round(distance_m, 1) if distance_m is not None else None,
                'rayon_m': round(rayon_m, 1) if rayon_m is not None else None,
            }
        )

    pointage.outside_geofence_count = (pointage.outside_geofence_count or 0) + 1
    if pointage.outside_geofence_count >= outside_limit:
        pointage.timestamp_sortie = _clamp_to_seance(timezone.now(), seance)
        pointage.statut = Pointage.Statut.SORTIE_AUTO
        pointage.calculer_duree()
        pointage.save(
            update_fields=[
                'timestamp_sortie',
                'statut',
                'duree_presence_minutes',
                'last_heartbeat_at',
                'last_latitude',
                'last_longitude',
                'last_accuracy_m',
                'last_battery_level',
                'last_is_charging',
                'outside_geofence_count',
                'updated_at',
            ]
        )
        extra = {
            'motif': 'OUT_OF_GEOFENCE',
            'distance_m': round(distance_m, 1) if distance_m is not None else None,
            'rayon_m': round(rayon_m, 1) if rayon_m is not None else None,
            'accuracy_m': accuracy_m,
            'battery_level': battery_level,
            'is_charging': is_charging,
            'outside_geofence_count': pointage.outside_geofence_count,
            'outside_geofence_limit': outside_limit,
        }
        _log_audit(
            action=AuditLog.Action.OUT_OF_GEOFENCE,
            request=request,
            cible_type=type_str,
            cible_numero=getattr(personne, 'matricule', None) or getattr(personne, 'numerobadge', None) or '',
            cible_nom=(getattr(personne, 'nom', None) or getattr(personne, 'last_name', '') or '') + ' ' + (getattr(personne, 'prenom', None) or getattr(personne, 'first_name', '') or ''),
            formation=formation,
            pointage=pointage,
            device_id=device_id,
            extra=extra,
        )
        _log_audit(
            action=AuditLog.Action.AUTO_EXIT,
            request=request,
            cible_type=type_str,
            cible_numero=getattr(personne, 'matricule', None) or getattr(personne, 'numerobadge', None) or '',
            cible_nom=(getattr(personne, 'nom', None) or getattr(personne, 'last_name', '') or '') + ' ' + (getattr(personne, 'prenom', None) or getattr(personne, 'first_name', '') or ''),
            formation=formation,
            pointage=pointage,
            device_id=device_id,
            extra=extra,
        )
        return Response(
            {
                'detail': 'Sortie automatique déclenchée (hors périmètre).',
                'action': 'SORTIE_AUTO',
                'statut': pointage.statut,
                'timestamp_sortie': pointage.timestamp_sortie,
                'duree_session_minutes': pointage.duree_presence_minutes,
                'motif': 'OUT_OF_GEOFENCE',
            }
        )

    pointage.statut = Pointage.Statut.HORS_LIGNE_SUSPECT
    pointage.save(
        update_fields=[
            'last_heartbeat_at',
            'last_latitude',
            'last_longitude',
            'last_accuracy_m',
            'last_battery_level',
            'last_is_charging',
            'outside_geofence_count',
            'statut',
            'updated_at',
        ]
    )

    if _should_log_heartbeat_audit(previous_heartbeat_at):
        _log_audit(
            action=AuditLog.Action.SCAN_HEARTBEAT,
            request=request,
            cible_type=type_str,
            cible_numero=getattr(personne, 'matricule', None) or getattr(personne, 'numerobadge', None) or '',
            cible_nom=(getattr(personne, 'nom', None) or getattr(personne, 'last_name', '') or '') + ' ' + (getattr(personne, 'prenom', None) or getattr(personne, 'first_name', '') or ''),
            formation=formation,
            pointage=pointage,
            device_id=device_id,
            extra={
                'geofence_code': geo_code,
                'geofence_detail': geo_detail,
                'distance_m': round(distance_m, 1) if distance_m is not None else None,
                'rayon_m': round(rayon_m, 1) if rayon_m is not None else None,
                'accuracy_m': accuracy_m,
                'battery_level': battery_level,
                'is_charging': is_charging,
                'outside_geofence_count': pointage.outside_geofence_count,
                'outside_geofence_limit': outside_limit,
            },
        )

    return Response(
        {
            'detail': geo_detail,
            'statut': pointage.statut,
            'outside_geofence_count': pointage.outside_geofence_count,
            'outside_geofence_limit': outside_limit,
            'distance_m': round(distance_m, 1) if distance_m is not None else None,
            'rayon_m': round(rayon_m, 1) if rayon_m is not None else None,
        },
        status=status.HTTP_202_ACCEPTED,
    )


# ──────────────────────────────────────────────
# Config app mobile (heartbeat, etc.)
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mobile_config(request):
    """
    Paramètres runtime pour l'app mobile (sans mise à jour store).

    MOBILE_HEARTBEAT_DISABLED=true côté serveur → heartbeat_enabled=false.
    """
    disabled = getattr(settings, 'MOBILE_HEARTBEAT_DISABLED', False)
    interval = getattr(settings, 'MOBILE_HEARTBEAT_INTERVAL_SECONDS', 60)
    interval = max(30, min(600, int(interval)))
    role = get_user_role(request.user)
    return Response({
        'heartbeat_enabled': not disabled,
        'heartbeat_interval_seconds': interval,
        'role': role,
        'evaluations_enabled': role == 'AUDITEUR',
    })


# ──────────────────────────────────────────────
# Historique personnel (app mobile)
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_historique(request):
    """Historique des pointages du user connecté (participant, formateur ou encadrant)."""
    user = request.user
    if getattr(user, 'must_change_password', False):
        return _password_change_required_response()
    personne, type_str, err = _resolve_authenticated_personne(user)
    if err:
        return err

    pointages_qs = _pointages_queryset_for_personne(personne, type_str, user=user)
    pointages = pointages_qs.select_related(
        'session__module__formation',
        'seance_edt__creneau_template', 'seance_edt__groupe', 'seance_edt__formation',
        'ecue_lmd',
    )

    data = [_pointage_historique_item(pt) for pt in pointages]

    modules_data = _modules_for_personne(personne, type_str, user=user)
    stats = _compute_fiche_stats(pointages_qs)
    stats.update(_compute_volume_horaire_stats(modules_data, pointages_qs))

    return Response({
        'type_personne': type_str,
        'personne_id': personne.pk,
        'numero': (
            getattr(personne, 'matricule', None)
            or getattr(personne, 'numerobadge', None)
            or getattr(personne, 'numero', '')
        ),
        'nom': getattr(personne, 'nom', None) or getattr(personne, 'last_name', '') or '',
        'prenom': getattr(personne, 'prenom', None) or getattr(personne, 'first_name', '') or '',
        'pointages': data,
        'modules': modules_data,
        'stats': stats,
    })


def _module_fiche_payload(module, inscrit_le=None, participant=None):
    from formations.duree_prevue_resolve import resolve_module_volume_contractuel_heures

    site_label = module.site.nom if module.site_id else (module.site_legacy or '')
    duree_contractuelle, duree_source = resolve_module_volume_contractuel_heures(
        module, participant=participant,
    )
    nb_seances_planifiees = module.sessions.count()
    return {
        'id': module.id,
        'formation_id': module.formation_id,
        'formation': module.formation.formation if module.formation_id else '',
        'module': module.intitule,
        'grade': module.grade or '',
        'groupe': module.groupe or '',
        'vague': module.vague or '',
        'site': site_label,
        'date_debut': str(module.date_debut) if module.date_debut else None,
        'date_fin': str(module.date_fin) if module.date_fin else None,
        'statut': module.statut,
        'secretariat_nom': module.secretariat.nom if module.secretariat_id else None,
        'inscrit_le': inscrit_le.isoformat() if inscrit_le else None,
        'duree_prevue_heures': duree_contractuelle,
        'duree_contractuelle_heures': duree_contractuelle,
        'duree_prevue_source': duree_source,
        'nb_seances_planifiees': nb_seances_planifiees,
    }


def _modules_for_personne(personne, type_str, user=None):
    modules_data = []
    if type_str == 'participant':
        participant_ids = [personne.pk]
        if user is not None:
            from .participant_scope import participant_ids_for_user
            linked_ids = participant_ids_for_user(user)
            if linked_ids:
                participant_ids = list(linked_ids)
        inscriptions = (
            ModuleParticipant.objects.filter(participant_id__in=participant_ids)
            .select_related('module__formation', 'module__secretariat', 'module__site')
            .order_by('-inscrit_le')
        )
        for ins in inscriptions:
            modules_data.append(_module_fiche_payload(ins.module, ins.inscrit_le, participant=personne))
    elif type_str == 'formateur':
        inscriptions = (
            ModuleFormateur.objects.filter(formateur=personne)
            .select_related('module__formation', 'module__secretariat', 'module__site')
            .order_by('-inscrit_le')
        )
        for ins in inscriptions:
            modules_data.append(_module_fiche_payload(ins.module, ins.inscrit_le))
    elif type_str == 'encadrant':
        modules = (
            Module.objects.filter(superviseur=personne)
            .select_related('formation', 'secretariat', 'site')
            .order_by('-created_at')
        )
        for module in modules:
            modules_data.append(_module_fiche_payload(module))
    return modules_data


def _pointages_queryset_for_personne(personne, type_str, user=None):
    if type_str == 'formateur':
        return Pointage.objects.filter(formateur=personne)
    if type_str == 'encadrant':
        return Pointage.objects.filter(encadrant=personne)
    if user is not None:
        from .participant_scope import participant_ids_for_user
        participant_ids = participant_ids_for_user(user)
        if participant_ids:
            return Pointage.objects.filter(participant_id__in=participant_ids)
    return Pointage.objects.filter(participant=personne)


def _pointage_historique_item(pt):
    module = pt.session.module if pt.session_id else None
    formation = module.formation if module and module.formation_id else None
    session = pt.session if pt.session_id else None
    seance_edt = pt.seance_edt if pt.seance_edt_id else None
    seance_edt_intitule = ''
    groupe_edt_libelle = ''
    ecue_libelle = ''
    if seance_edt is not None:
        seance_edt_intitule = seance_edt.intitule or str(seance_edt.creneau_template)
        groupe = getattr(seance_edt, 'groupe', None)
        groupe_edt_libelle = (getattr(groupe, 'nom', '') or getattr(groupe, 'libelle', ''))
        ecue = pt.ecue_lmd if pt.ecue_lmd_id else None
        ecue_libelle = (getattr(ecue, 'intitule', '') or getattr(ecue, 'code', '')) if ecue else ''
    return {
        'id': pt.id,
        'canal': 'EDT_LMD' if seance_edt is not None else 'SESSION_MODULE',
        'formation_id': formation.pk if formation else None,
        'formation_titre': formation.formation if formation else '',
        'module_id': module.pk if module else None,
        'module_intitule': module.intitule if module else ecue_libelle,
        'seance_numero': session.numero if session else None,
        'seance_intitule': session.intitule if session else seance_edt_intitule,
        # Séance planifiée (EDT/LMD) : ni module ni SessionModule côté legacy.
        'seance_edt': {
            'id': seance_edt.pk,
            'intitule': seance_edt_intitule,
            'date': str(pt.date_journee),
            'salle': seance_edt.salle_nom,
            'groupe': groupe_edt_libelle,
            'ecue': ecue_libelle,
        } if seance_edt is not None else None,
        'date_journee': str(pt.date_journee),
        'timestamp_entree': pt.timestamp_entree.isoformat() if pt.timestamp_entree else None,
        'timestamp_sortie': pt.timestamp_sortie.isoformat() if pt.timestamp_sortie else None,
        'duree_presence_minutes': float(pt.duree_presence_minutes) if pt.duree_presence_minutes else None,
        'statut': pt.statut,
        'statut_label': pt.get_statut_display(),
        # ── Détails du badgeage ──
        'device_id': pt.device_id or None,
        'geolocalisation': {
            'latitude': pt.last_latitude,
            'longitude': pt.last_longitude,
            'precision_m': pt.last_accuracy_m,
        } if pt.last_latitude is not None else None,
        'appareil': {
            'batterie_pct': pt.last_battery_level,
            'en_charge': pt.last_is_charging,
        } if pt.last_battery_level is not None else None,
        # ── Détails de présence ──
        'last_heartbeat_at': pt.last_heartbeat_at.isoformat() if pt.last_heartbeat_at else None,
        'sorties_geofence_count': pt.outside_geofence_count,
        # ── Détails du temps de cours (séance) ──
        'temps_cours': {
            'heure_debut_prevue': session.heure_debut_prevue.isoformat() if session and session.heure_debut_prevue else None,
            'heure_fin_prevue': session.heure_fin_prevue.isoformat() if session and session.heure_fin_prevue else None,
            'demarree_le': session.demarree_le.isoformat() if session and session.demarree_le else None,
            'terminee_le': session.terminee_le.isoformat() if session and session.terminee_le else None,
            'auto_demarrage': session.auto_demarrage if session else None,
        } if session else None,
    }


def _compute_fiche_stats(pointages_qs):
    pointages = list(
        pointages_qs.select_related('session__module__formation').order_by('-timestamp_entree')
    )
    total_minutes = 0.0
    terminees = 0
    en_cours = 0
    a_verifier = 0
    dernier = None
    formations_ids = set()
    modules_ids = set()

    alert_statuts = {
        Pointage.Statut.HORS_LIGNE_SUSPECT,
        Pointage.Statut.ABSENT_NON_BADGE,
        Pointage.Statut.SORTIE_AUTO,
    }

    for pt in pointages:
        if pt.duree_presence_minutes is not None:
            total_minutes += float(pt.duree_presence_minutes)
        if pt.timestamp_sortie:
            terminees += 1
        elif pt.statut == Pointage.Statut.EN_COURS:
            en_cours += 1
        if pt.statut in alert_statuts or (
            pt.statut == Pointage.Statut.EN_COURS and not pt.timestamp_sortie
        ):
            a_verifier += 1
        if dernier is None or pt.timestamp_entree > dernier:
            dernier = pt.timestamp_entree
        if pt.session_id and pt.session.module_id:
            modules_ids.add(pt.session.module_id)
            if pt.session.module.formation_id:
                formations_ids.add(pt.session.module.formation_id)

    return {
        'nb_badgeages': len(pointages),
        'nb_seances_terminees': terminees,
        'nb_seances_en_cours': en_cours,
        'nb_a_verifier': a_verifier,
        'nb_sans_probleme': max(0, len(pointages) - a_verifier),
        'total_minutes_presence': round(total_minutes, 1),
        'nb_formations': len(formations_ids),
        'nb_modules_badges': len(modules_ids),
        'dernier_badgeage': dernier.isoformat() if dernier else None,
    }


def _compute_volume_horaire_stats(modules_data, pointages_qs):
    """Volume horaire effectué (présence badgeée) / total prévu (modules inscrits).

    Seuls les badgeages sur les modules inscrits sont comptés, plafonnés à
    duree_prevue_heures par module — l'effectué ne peut pas dépasser le prévu.
    """
    module_cap_minutes = {}
    for m in modules_data:
        mid = m.get('id')
        if mid is None:
            continue
        heures = float(m.get('duree_prevue_heures') or 0)
        cap = heures * 60
        module_cap_minutes[mid] = max(module_cap_minutes.get(mid, 0.0), cap)

    total_heures_r = round(sum(module_cap_minutes.values()) / 60, 1)

    module_accum = {mid: 0.0 for mid in module_cap_minutes}
    effectue_minutes = 0.0

    for pt in pointages_qs.select_related('session__module'):
        mins = float(pt.duree_presence_minutes or 0)
        if mins <= 0:
            continue
        mid = pt.session.module_id if pt.session_id else None
        if mid not in module_cap_minutes:
            continue
        remaining = module_cap_minutes[mid] - module_accum[mid]
        if remaining <= 0:
            continue
        counted = min(mins, remaining)
        module_accum[mid] += counted
        effectue_minutes += counted

    effectue_heures = round(effectue_minutes / 60, 1)
    if total_heures_r > 0:
        effectue_heures = min(effectue_heures, total_heures_r)
        taux = min(100.0, round((effectue_heures / total_heures_r) * 100, 1))
    else:
        effectue_heures = 0.0
        taux = 0.0

    return {
        'volume_horaire_total_heures': total_heures_r,
        'volume_horaire_effectue_heures': effectue_heures,
        'volume_horaire_effectue_taux': taux,
    }


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def my_fiche(request):
    """Fiche personnelle mobile : profil, modules inscrits et statistiques de badgeage."""
    from authentication.serializers import UserSerializer
    from formations.formateur_privacy import (
        can_edit_formateur_sensitive_data,
        formateur_sensitive_payload,
    )

    user = request.user
    if getattr(user, 'must_change_password', False):
        return _password_change_required_response()

    personne, type_str, err = _resolve_authenticated_personne(user, ensure_profile=True)
    if err:
        return err

    if request.method == 'PATCH':
        if type_str != 'formateur':
            return Response({'detail': 'Modification réservée aux formateurs.'}, status=403)
        if not can_edit_formateur_sensitive_data(user, personne):
            return Response({'detail': 'Modification interdite.'}, status=403)
        update_fields = []
        for field in ('numero_piece_identite', 'numero_compte_bancaire'):
            if field in request.data:
                setattr(personne, field, str(request.data.get(field) or '').strip())
                update_fields.append(field)
        if update_fields:
            personne.save(update_fields=update_fields)
        return Response({'profil': {**formateur_sensitive_payload(personne), 'updated': True}})

    modules_data = _modules_for_personne(personne, type_str, user=user)
    pointages_qs = _pointages_queryset_for_personne(personne, type_str, user=user)
    stats = _compute_fiche_stats(pointages_qs)
    stats.update(_compute_volume_horaire_stats(modules_data, pointages_qs))
    stats['nb_modules_inscrits'] = len({m.get('id') for m in modules_data if m.get('id') is not None})

    profil = {
        'id': personne.pk,
        'type_personne': type_str,
        'numero': (
            getattr(personne, 'matricule', None)
            or getattr(personne, 'numerobadge', None)
            or getattr(user, 'matricule', None)
            or ''
        ),
        'nom': getattr(personne, 'nom', None) or getattr(personne, 'last_name', '') or '',
        'prenom': getattr(personne, 'prenom', None) or getattr(personne, 'first_name', '') or '',
    }
    if type_str == 'participant':
        profil['pointages'] = [_pointage_historique_item(pt) for pt in pointages_qs.select_related('session__module__formation')]
    if type_str == 'formateur':
        profil['specialite'] = getattr(personne, 'specialite', '') or ''
        from formations.formateur_privacy import can_view_formateur_sensitive_data, formateur_sensitive_payload
        if can_view_formateur_sensitive_data(user, personne):
            profil.update(formateur_sensitive_payload(personne))

    return Response({
        'utilisateur': UserSerializer(user).data,
        'profil': profil,
        'modules': modules_data,
        'stats': stats,
    })


# ──────────────────────────────────────────────
# Gestion des liaisons appareils (superviseur / DFRC)
# ──────────────────────────────────────────────

@api_view(['DELETE'])
@permission_classes([IsDFRCOrEncadrant])
def unbind_device(request, device_id):
    """Superviseur / DFRC : délier un appareil pour permettre un changement de compte."""
    try:
        binding = DeviceBinding.objects.get(device_id=device_id, is_active=True)
        binding.is_active = False
        binding.save(update_fields=['is_active'])
        _log_audit(
            action=AuditLog.Action.DEVICE_UNBIND,
            request=request,
            cible_nom=binding.user.get_full_name() or binding.user.username,
            device_id=device_id,
            extra={'unbound_user_id': binding.user_id, 'device_info': binding.device_info},
        )
        return Response({'detail': f'Appareil délié de {binding.user.get_full_name()}.'})
    except DeviceBinding.DoesNotExist:
        return Response(
            {'detail': 'Aucune liaison active trouvée pour cet appareil.'},
            status=status.HTTP_404_NOT_FOUND,
        )


@api_view(['GET'])
@permission_classes([IsDFRCOrEncadrant])
def list_device_bindings(request):
    """Liste toutes les liaisons appareils actives."""
    bindings = DeviceBinding.objects.filter(is_active=True).select_related('user')
    data = [{
        'device_id': b.device_id,
        'user_id': b.user_id,
        'username': b.user.username,
        'full_name': b.user.get_full_name(),
        'bound_at': b.bound_at.isoformat(),
        'device_info': b.device_info,
    } for b in bindings]
    return Response(data)


# ──────────────────────────────────────────────
# DFRC — Dashboard temps réel (polling)
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def formation_dashboard(request, pk):
    """Dashboard de suivi d'une formation (présents / absents / en salle) — participants + formateurs + encadrants."""
    formation = _get_accessible_formation(request.user, pk)
    if not formation:
        return Response(
            {'detail': 'Formation introuvable.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    date_str = request.GET.get('date')
    if date_str:
        try:
            from datetime import datetime as dt
            jour = dt.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            jour = timezone.localdate()
    else:
        jour = timezone.localdate()

    from collections import defaultdict
    from formations.models import SessionModule as SF
    now = timezone.now()

    # Filtre optionnel par séance
    session_id = request.GET.get('session_id')
    seance_selectionnee = None
    if session_id:
        try:
            seance_selectionnee = SF.objects.get(pk=session_id, module__formation=formation)
            jour = seance_selectionnee.date_journee
        except SF.DoesNotExist:
            seance_selectionnee = None

    pointages_qs = Pointage.objects.filter(
        session__module__formation=formation, date_journee=jour
    ).select_related('participant', 'formateur', 'encadrant', 'session')

    # Séances du jour (sert aussi à déterminer le périmètre module du dashboard)
    seances_jour = SF.objects.filter(
        module__formation=formation,
        date_journee=jour,
    ).order_by('heure_debut_prevue', 'numero')

    if seance_selectionnee:
        module_ids_scope = {seance_selectionnee.module_id}
    else:
        module_ids_scope = set(seances_jour.values_list('module_id', flat=True))

    if seance_selectionnee:
        from django.db.models import Q
        q = Q(session=seance_selectionnee)
        # Inclure aussi les pointages sans session liée dont l'heure d'entrée
        # tombe dans la plage horaire de la séance (forçage après fin de séance, QR sans session…)
        if seance_selectionnee.heure_debut_prevue and seance_selectionnee.heure_fin_prevue:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            tz = ZoneInfo('Africa/Abidjan')
            dt_debut = datetime.combine(seance_selectionnee.date_journee, seance_selectionnee.heure_debut_prevue, tzinfo=tz)
            dt_fin = datetime.combine(seance_selectionnee.date_journee, seance_selectionnee.heure_fin_prevue, tzinfo=tz)
            q |= Q(session__isnull=True, timestamp_entree__gte=dt_debut, timestamp_entree__lte=dt_fin)
        elif seance_selectionnee.demarree_le:
            # Pas d'horaire prévu : utiliser les horodatages réels de démarrage/fin
            q_null = Q(session__isnull=True, timestamp_entree__gte=seance_selectionnee.demarree_le)
            if seance_selectionnee.terminee_le:
                q_null &= Q(timestamp_entree__lte=seance_selectionnee.terminee_le)
            q |= q_null
        pointages_qs = pointages_qs.filter(q)

    pointages = list(pointages_qs)

    # Index sessions par (type, id)
    sessions_map = defaultdict(list)
    for pt in pointages:
        if pt.formateur_id:
            sessions_map[('formateur', pt.formateur_id)].append(pt)
        elif pt.encadrant_id:
            sessions_map[('encadrant', pt.encadrant_id)].append(pt)
        else:
            sessions_map[('participant', pt.participant_id)].append(pt)

    def _classify(personne, type_str, serializer_cls):
        key = (type_str, personne.id)
        sessions = sessions_map.get(key, [])
        p_data = serializer_cls(personne).data
        p_data['type_personne'] = type_str

        if not sessions:
            return 'absent', p_data

        # "Ouverte" = timestamp_sortie NULL
        session_ouverte = next(
            (s for s in sessions if s.timestamp_sortie is None), None
        )
        sessions_terminees = [s for s in sessions if s.timestamp_sortie is not None]
        # Exclure les pointages sans présence réelle (absent forcé, non badgé)
        sessions_presentes = [
            s for s in sessions_terminees
            if s.statut not in (Pointage.Statut.ABSENT_NON_BADGE,)
            and float(s.duree_presence_minutes or 0) > 0
        ]
        total_termine = sum(float(s.duree_presence_minutes or 0) for s in sessions_presentes)
        p_data['nb_sessions'] = len(sessions)

        if session_ouverte:
            from .duree import pointage_minutes_clampees
            duree_session = pointage_minutes_clampees(session_ouverte, now=now)
            p_data['timestamp_entree'] = session_ouverte.timestamp_entree
            p_data['duree_actuelle_minutes'] = round(total_termine + duree_session, 2)
            return 'en_salle', p_data
        elif sessions_presentes:
            derniere = max(sessions_presentes, key=lambda s: s.timestamp_sortie or s.timestamp_entree)
            p_data['timestamp_entree'] = sessions_presentes[0].timestamp_entree
            p_data['timestamp_sortie'] = derniere.timestamp_sortie
            p_data['duree_presence_minutes'] = round(total_termine, 2)
            return 'present', p_data
        else:
            return 'absent', p_data

    presents, en_salle, absents = [], [], []

    def _encadrant_data(enc):
        nom = (enc.last_name or '').strip()
        prenom = (enc.first_name or '').strip()
        if not nom and not prenom:
            nom = enc.username or ''
        return {
            'id': enc.id,
            'nom': nom,
            'prenom': prenom,
            'matricule': enc.matricule or '',
            'email': enc.email or '',
            'telephone': enc.telephone or '',
            'site': '',
            'grade': enc.grade or '',
        }

    class _InlineEncadrantSerializer:
        def __init__(self, obj):
            self.data = _encadrant_data(obj)

    # Participants (périmètre: modules du dashboard, pas toute la formation)
    seen_p = set()
    for insc in ModuleParticipant.objects.filter(module_id__in=module_ids_scope).select_related('participant'):
        if insc.participant_id in seen_p:
            continue
        seen_p.add(insc.participant_id)
        cat, data = _classify(insc.participant, 'participant', ParticipantSerializer)
        {'present': presents, 'en_salle': en_salle, 'absent': absents}[cat].append(data)

    # Auditeurs en rattrapage sur les séances d'accueil du périmètre : non inscrits
    # à la cohorte, mais attendus/présents sur CE créneau précis (l'effectif de la
    # séance d'accueil augmente sans modifier les inscrits de la cohorte).
    rattrapage_scope = Rattrapage.objects.filter(
        statut__in=[Rattrapage.Statut.PLANIFIE, Rattrapage.Statut.EFFECTUE],
        seance_rattrapage__module_id__in=module_ids_scope,
        seance_rattrapage__date_journee=jour,
    ).select_related('participant')
    if seance_selectionnee:
        rattrapage_scope = rattrapage_scope.filter(seance_rattrapage=seance_selectionnee)

    nb_rattrapage_places = 0
    for r in rattrapage_scope:
        nb_rattrapage_places += 1
        p = r.participant
        if p.id in seen_p:
            continue
        seen_p.add(p.id)
        cat, data = _classify(p, 'participant', ParticipantSerializer)
        data['rattrapage'] = True
        {'present': presents, 'en_salle': en_salle, 'absent': absents}[cat].append(data)

    # Formateurs (périmètre: modules du dashboard)
    seen_fmt = set()
    for insc in ModuleFormateur.objects.filter(module_id__in=module_ids_scope).select_related('formateur'):
        if insc.formateur_id in seen_fmt:
            continue
        seen_fmt.add(insc.formateur_id)
        cat, data = _classify(insc.formateur, 'formateur', FormateurSerializer)
        {'present': presents, 'en_salle': en_salle, 'absent': absents}[cat].append(data)

    # Encadrants (superviseurs de modules de la formation)
    seen_enc = set()
    # Inclure:
    # 1) les encadrants actuellement assignés à au moins un module de la formation
    # 2) les encadrants ayant déjà pointé sur la formation à la date demandée
    encadrants_qs = User.objects.filter(
        role='ENCADRANT',
    ).filter(
        Q(modules_supervises__id__in=module_ids_scope)
        | Q(
            pointages_encadrant__session__module_id__in=module_ids_scope,
            pointages_encadrant__date_journee=jour,
        )
    ).distinct()

    for enc in encadrants_qs:
        if enc.id in seen_enc:
            continue
        seen_enc.add(enc.id)
        cat, data = _classify(enc, 'encadrant', _InlineEncadrantSerializer)
        {'present': presents, 'en_salle': en_salle, 'absent': absents}[cat].append(data)

    # Séances du jour (pour le sélecteur frontend)
    seances_jour_data = [
        {
            'id': s.id,
            'numero': s.numero,
            'intitule': s.intitule or f'Séance {s.numero}',
            'heure_debut': s.heure_debut_prevue.strftime('%H:%M') if s.heure_debut_prevue else None,
            'heure_fin': s.heure_fin_prevue.strftime('%H:%M') if s.heure_fin_prevue else None,
            'en_cours': s.est_en_cours,
            'terminee': s.est_terminee,
        }
        for s in seances_jour
    ]

    nb_seances_jour = len(seances_jour_data) if seances_jour_data else 1

    nb_inscrits_participants = ModuleParticipant.objects.filter(module_id__in=module_ids_scope).values('participant').distinct().count()
    nb_inscrits_formateurs = ModuleFormateur.objects.filter(module_id__in=module_ids_scope).values('formateur').distinct().count()
    nb_inscrits_encadrants = encadrants_qs.count()
    nb_inscrits = nb_inscrits_participants + nb_inscrits_formateurs + nb_inscrits_encadrants

    # Si filtre séance : total attendus = inscrits, sinon inscrits × nb séances.
    # Chaque rattrapage ajoute une place attendue sur la séance d'accueil.
    if seance_selectionnee:
        total = nb_inscrits + nb_rattrapage_places
    else:
        total = nb_inscrits * nb_seances_jour + nb_rattrapage_places

    total_pointes = sum(
        1 for pts in sessions_map.values()
        for pt in pts
        if pt.statut not in (Pointage.Statut.ABSENT_NON_BADGE,)
        and float(pt.duree_presence_minutes or 0) > 0
    )
    taux = round((total_pointes / total * 100), 1) if total > 0 else 0

    # Historique chronologique
    historique = []
    for pt in sorted(pointages, key=lambda p: p.timestamp_entree):
        personne = pt.formateur or pt.participant or pt.encadrant
        if personne:
            nom = (
                f"{getattr(personne, 'nom', '')} {getattr(personne, 'prenom', '')}".strip()
                or f"{getattr(personne, 'last_name', '')} {getattr(personne, 'first_name', '')}".strip()
                or getattr(personne, 'username', '—')
            )
        else:
            nom = '—'
        numero = (
            getattr(personne, 'numerobadge', None)
            or getattr(personne, 'matricule', None)
            or getattr(personne, 'numero', '—')
        ) if personne else '—'
        type_p = 'formateur' if pt.formateur_id else 'encadrant' if pt.encadrant_id else 'participant'
        historique.append({
            'nom': nom,
            'numero': numero,
            'type_personne': type_p,
            'action': 'ENTREE',
            'timestamp': pt.timestamp_entree,
            'statut': pt.statut,
        })
        if pt.timestamp_sortie:
            historique.append({
                'nom': nom,
                'numero': numero,
                'type_personne': type_p,
                'action': 'SORTIE',
                'timestamp': pt.timestamp_sortie,
                'duree_minutes': float(pt.duree_presence_minutes or 0),
                'statut': pt.statut,
            })
    historique.sort(key=lambda x: x['timestamp'])

    return Response({
        'formation': FormationListSerializer(formation).data,
        'presents': presents,
        'en_salle': en_salle,
        'absents': absents,
        'taux_presence': taux,
        'total_attendus': total,
        'total_pointes': total_pointes,
        'nb_inscrits': nb_inscrits,
        'nb_seances_jour': nb_seances_jour,
        'seances_jour': seances_jour_data,
        'seance_selectionnee_id': seance_selectionnee.id if seance_selectionnee else None,
        'historique': historique,
    })


# ──────────────────────────────────────────────
# DFRC — Liste des présences d'une formation
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def formation_presences(request, pk):
    """Liste des pointages d'une formation."""
    user = request.user
    formation = _get_accessible_formation(user, pk)
    if not formation:
        return Response(
            {'detail': 'Formation introuvable ou non autorisée.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    base_qs = Pointage.objects.filter(
        session__module__formation=formation,
    ).select_related('participant', 'formateur', 'encadrant', 'session__module__formation')

    if user.role == 'ENCADRANT':
        pointages = base_qs.filter(session__module__superviseur=user)
    elif user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT') and user.secretariat:
        pointages = base_qs.filter(session__module__secretariat=user.secretariat)
    else:
        pointages = base_qs

    pointages = pointages.order_by('-date_journee', '-timestamp_entree', '-id')

    legacy_array = request.query_params.get('legacy') == '1'
    if legacy_array:
        serializer = PointageSerializer(pointages, many=True)
        return Response(serializer.data)

    page = max(int(request.query_params.get('page', 1)), 1)
    page_size = min(max(int(request.query_params.get('page_size', 50)), 1), 200)
    total_count = pointages.count()
    start = (page - 1) * page_size
    page_qs = pointages[start:start + page_size]
    serializer = PointageSerializer(page_qs, many=True)
    return Response({
        'results': serializer.data,
        'count': total_count,
        'total_pages': (total_count + page_size - 1) // page_size if total_count else 0,
        'current_page': page,
    })


# ──────────────────────────────────────────────
# SUPERVISEUR / DFRC — Fermer session ouverte d'un participant
# ──────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def close_session(request, pk):
    """
    Secrétariat / Superviseur / DFRC : fermer la session ouverte d'un participant/formateur/encadrant
    qui a oublié de scanner sa sortie.
    body: { personne_id, type_personne }  (type_personne default: 'participant')
    """
    personne_id = request.data.get('personne_id')
    type_personne = request.data.get('type_personne', 'participant')

    if not personne_id:
        return Response({'detail': 'personne_id est requis.'}, status=status.HTTP_400_BAD_REQUEST)

    # Superviseur ne peut agir que sur sa formation
    formation = _get_accessible_formation(request.user, pk)
    if not formation:
        return Response({'detail': 'Formation introuvable ou non autorisée.'}, status=status.HTTP_404_NOT_FOUND)

    if type_personne == 'formateur':
        try:
            personne = Formateur.objects.get(pk=personne_id)
        except Formateur.DoesNotExist:
            return Response({'detail': 'Formateur introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        filt = {'session__module__formation': formation, 'formateur': personne, 'timestamp_sortie__isnull': True}
    elif type_personne == 'encadrant':
        try:
            personne = User.objects.get(pk=personne_id, role='ENCADRANT')
        except User.DoesNotExist:
            return Response({'detail': 'Encadrant introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        filt = {'session__module__formation': formation, 'encadrant': personne, 'timestamp_sortie__isnull': True}
    else:
        try:
            personne = Participant.objects.get(pk=personne_id)
        except Participant.DoesNotExist:
            return Response({'detail': 'Auditeur introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        filt = {'session__module__formation': formation, 'participant': personne, 'timestamp_sortie__isnull': True}

    try:
        pointage = Pointage.objects.filter(**filt).latest('timestamp_entree')
    except Pointage.DoesNotExist:
        return Response({'detail': 'Aucune session ouverte pour cette personne.'}, status=status.HTTP_400_BAD_REQUEST)

    if type_personne == 'participant' and pointage.statut == Pointage.Statut.FORCE_DFRC:
        from .bulk_force_auditeurs import force_sortie_pointage

        pointage, err = force_sortie_pointage(
            formation,
            pointage,
            pointage.session,
            personne,
            type_personne,
            'Fermeture session (présence forcée)',
            request=request,
            creneau_complet=True,
        )
        if err:
            return Response({'detail': err}, status=status.HTTP_400_BAD_REQUEST)
    else:
        pointage.timestamp_sortie = timezone.now()
        pointage.statut = Pointage.Statut.FORCE_DFRC
        pointage.calculer_duree()
        pointage.save()
    personne_label = (
        f"{getattr(personne, 'nom', '')} {getattr(personne, 'prenom', '')}".strip()
        or f"{getattr(personne, 'last_name', '')} {getattr(personne, 'first_name', '')}".strip()
        or getattr(personne, 'username', '—')
    )

    _log_audit(
        action=AuditLog.Action.CLOSE_SESSION,
        request=request,
        cible_type=type_personne,
        cible_numero=getattr(personne, 'numero', None) or getattr(personne, 'numerobadge', None) or getattr(personne, 'matricule', ''),
        cible_nom=personne_label,
        formation=formation,
        pointage=pointage,
        extra={'duree_minutes': float(pointage.duree_presence_minutes or 0)},
    )

    return Response({
        'detail': f'Session fermée pour {personne_label} ({round(float(pointage.duree_presence_minutes or 0))} min).',
        'pointage_id': pointage.id,
        'duree_minutes': float(pointage.duree_presence_minutes or 0),
    })


# ──────────────────────────────────────────────
# DFRC / SUPERVISEUR — Pointage forcé (R6)
# ──────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def force_pointage(request, pk):
    """Secrétariat / Superviseur / DFRC : forcer un pointage entrée ou sortie pour participant, formateur ou encadrant (R6)."""
    with transaction.atomic():
        return _force_pointage_impl(request, pk)


def _force_pointage_impl(request, pk):
    serializer = ForcePointageSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    formation = _get_accessible_formation(request.user, pk)
    if not formation:
        return Response(
            {'detail': 'Formation introuvable ou non autorisée.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Jour cible : utiliser date_journee du body si fourni (forçage rétroactif), sinon aujourd'hui
    date_journee = data.get('date_journee') or timezone.localdate()

    type_str = data.get('type_personne', 'participant')
    if type_str == 'formateur':
        try:
            personne = Formateur.objects.get(pk=data['personne_id'])
        except Formateur.DoesNotExist:
            return Response({'detail': 'Formateur introuvable.'}, status=status.HTTP_404_NOT_FOUND)
    elif type_str == 'encadrant':
        try:
            personne = User.objects.get(pk=data['personne_id'], role='ENCADRANT')
        except User.DoesNotExist:
            return Response({'detail': 'Encadrant introuvable.'}, status=status.HTTP_404_NOT_FOUND)
    else:
        try:
            personne = Participant.objects.get(pk=data['personne_id'])
        except Participant.DoesNotExist:
            return Response({'detail': 'Auditeur introuvable.'}, status=status.HTTP_404_NOT_FOUND)

    if data['action'] == 'ENTREE':
        seance_qs = SessionModule.objects.filter(
            module__formation=formation,
            date_journee=date_journee,
            demarree_le__isnull=False,
            terminee_le__isnull=True,
        )
        module_id = data.get('module_id')
        if module_id:
            seance_qs = seance_qs.filter(module_id=module_id)
        if type_str == 'encadrant':
            seance_qs = seance_qs.filter(module__superviseur=personne)
        seance_active = seance_qs.first()
        if not seance_active:
            return Response({'detail': 'Aucune séance active pour ce module ce jour.'}, status=status.HTTP_400_BAD_REQUEST)
        if _has_unfinished_previous_session(seance_active):
            return Response(
                {
                    'detail': (
                        'Impossible de forcer un badgeage sur cette séance tant que '
                        'la séance précédente du même jour n’est pas terminée.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        pointage_ouvert = _find_open_pointage_same_module_day(
            personne=personne,
            type_personne=type_str,
            module=seance_active.module,
            date_journee=date_journee,
        )
        if pointage_ouvert:
            return Response(
                {'detail': 'Une session est déjà en cours sur ce module pour ce jour.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        motif = data.get('motif', '')
        if type_str == 'participant':
            from .bulk_force_auditeurs import force_presence_auditeur, force_sortie_pointage

            pointage, err = force_presence_auditeur(
                formation,
                seance_active,
                personne,
                date_journee,
                motif,
                request=request,
                timestamp_entree=data.get('timestamp_entree'),
                timestamp_sortie=data.get('timestamp_sortie'),
            )
            if err:
                return Response({'detail': err}, status=status.HTTP_400_BAD_REQUEST)
            return Response({
                'action': 'ENTREE',
                'detail': 'Présence forcée enregistrée (durée planifiée de la séance).',
                'pointage': PointageSerializer(pointage).data,
            }, status=status.HTTP_201_CREATED)

        ts_entree_raw = data.get('timestamp_entree') or timezone.now()
        timestamp_entree = _clamp_to_seance(ts_entree_raw, seance_active)
        pointage = Pointage.objects.create(
            **_create_pointage_kwargs(
                personne, type_str, seance_active,
                date_journee=date_journee,
                timestamp_entree=timestamp_entree,
                statut=Pointage.Statut.FORCE_DFRC,
                device_id='FORCE_DFRC',
            )
        )
        _log_audit(
            action=AuditLog.Action.FORCE_ENTREE,
            request=request,
            cible_type=type_str,
            cible_numero=getattr(personne, 'numero', None) or getattr(personne, 'numerobadge', None) or getattr(personne, 'matricule', ''),
            cible_nom=(
                f"{getattr(personne, 'nom', '')} {getattr(personne, 'prenom', '')}".strip()
                or f"{getattr(personne, 'last_name', '')} {getattr(personne, 'first_name', '')}".strip()
                or getattr(personne, 'username', '—')
            ),
            formation=formation,
            pointage=pointage,
            extra={'acteur_role': request.user.role, 'motif': data.get('motif', '')},
        )
        return Response({
            'action': 'ENTREE',
            'detail': 'Entrée forcée enregistrée.',
            'pointage': PointageSerializer(pointage).data,
        }, status=status.HTTP_201_CREATED)

    elif data['action'] == 'SORTIE':
        filt_ouvert = _pointage_filter(personne, type_str, formation, date_journee=date_journee, timestamp_sortie__isnull=True)
        try:
            pointage = Pointage.objects.filter(**filt_ouvert).latest('timestamp_entree')
        except Pointage.DoesNotExist:
            return Response(
                {'detail': 'Aucune session ouverte pour cette personne ce jour.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        motif = data.get('motif', '')
        if type_str == 'participant':
            from .bulk_force_auditeurs import force_sortie_pointage

            pointage, err = force_sortie_pointage(
                formation,
                pointage,
                pointage.session,
                personne,
                type_str,
                motif,
                request=request,
                timestamp_sortie=data.get('timestamp_sortie'),
                creneau_complet=pointage.statut == Pointage.Statut.FORCE_DFRC,
            )
            if err:
                return Response({'detail': err}, status=status.HTTP_400_BAD_REQUEST)
            return Response({
                'action': 'SORTIE',
                'detail': 'Sortie forcée enregistrée.',
                'pointage': PointageSerializer(pointage).data,
            })

        ts_sortie_raw = data.get('timestamp_sortie') or timezone.now()
        pointage.timestamp_sortie = _clamp_to_seance(ts_sortie_raw, pointage.session)
        pointage.statut = Pointage.Statut.FORCE_DFRC
        pointage.calculer_duree()
        pointage.save()
        _log_audit(
            action=AuditLog.Action.FORCE_SORTIE,
            request=request,
            cible_type=type_str,
            cible_numero=getattr(personne, 'numero', None) or getattr(personne, 'numerobadge', None) or getattr(personne, 'matricule', ''),
            cible_nom=(
                f"{getattr(personne, 'nom', '')} {getattr(personne, 'prenom', '')}".strip()
                or f"{getattr(personne, 'last_name', '')} {getattr(personne, 'first_name', '')}".strip()
                or getattr(personne, 'username', '—')
            ),
            formation=formation,
            pointage=pointage,
            extra={'duree_minutes': float(pointage.duree_presence_minutes or 0), 'acteur_role': request.user.role, 'motif': data.get('motif', '')},
        )
        return Response({
            'action': 'SORTIE',
            'detail': 'Sortie forcée enregistrée.',
            'pointage': PointageSerializer(pointage).data,
        })

    return Response({'detail': 'Action non reconnue.'}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsSecretariatOrEncadrantOrDFRC])
def force_badgeage_auditeurs_bulk(request, pk):
    """
    Forcer l'entrée+sortie d'un sous-ensemble aléatoire d'auditeurs absents par séance (80–95 %).
    Chaque auditeur reçoit la durée du créneau planifié (heure_debut → heure_fin).
    Secrétariat / Superviseur / DFRC uniquement.
    """
    from django.conf import settings
    from .bulk_force_auditeurs import run_bulk_force_badgeage_auditeurs

    serializer = ForceBadgeageBulkAuditeursSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    formation = _get_accessible_formation(request.user, pk)
    if not formation:
        return Response(
            {'detail': 'Formation introuvable ou non autorisée.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    date_journee = data.get('date_journee') or timezone.localdate()
    module_id = data['module_id']
    try:
        module = Module.objects.get(pk=module_id, formation=formation)
    except Module.DoesNotExist:
        return Response({'detail': 'Module introuvable.'}, status=status.HTTP_404_NOT_FOUND)

    ignore_constraints = bool(data.get('ignore_constraints'))
    if ignore_constraints and not (request.user.is_superuser or getattr(settings, 'DEBUG', False)):
        return Response(
            {'detail': 'Le mode ignore_constraints est réservé aux tests (superuser ou DEBUG).'},
            status=status.HTTP_403_FORBIDDEN,
        )

    session_id = data.get('session_id')
    if session_id and not ignore_constraints:
        try:
            seance = SessionModule.objects.get(pk=session_id, module=module, date_journee=date_journee)
        except SessionModule.DoesNotExist:
            return Response({'detail': 'Séance introuvable pour ce module et cette date.'}, status=status.HTTP_404_NOT_FOUND)
        if not seance.demarree_le or seance.terminee_le:
            return Response(
                {'detail': 'La séance doit être démarrée et non terminée.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    result, status_hint = run_bulk_force_badgeage_auditeurs(
        formation,
        module,
        motif=data['motif'],
        request=request,
        date_journee=date_journee,
        session_id=session_id,
        all_sessions=bool(data.get('all_sessions')),
        ignore_constraints=ignore_constraints,
    )
    return Response(result, status=status.HTTP_201_CREATED if status_hint == 201 else status.HTTP_400_BAD_REQUEST)


# ──────────────────────────────────────────────
# PARTICIPANT — Historique personnel
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def participant_historique(request, pk):
    """Historique des présences d'un participant."""
    if request.user.role != User.Role.AUDITEUR:
        return Response({'detail': 'Acces interdit.'}, status=status.HTTP_403_FORBIDDEN)

    from .participant_scope import link_user_to_primary_participant, participant_ids_for_user

    participant = link_user_to_primary_participant(request.user)
    if participant is None:
        return Response({'detail': 'Auditeur introuvable.'}, status=status.HTTP_404_NOT_FOUND)

    if pk not in participant_ids_for_user(request.user):
        return Response({'detail': 'Acces interdit.'}, status=status.HTTP_403_FORBIDDEN)

    pointages = Pointage.objects.filter(
        participant_id__in=participant_ids_for_user(request.user)
    ).select_related('session__module__formation')
    serializer = PointageSerializer(pointages, many=True)
    return Response({
        'participant': ParticipantSerializer(participant).data,
        'pointages': serializer.data,
    })


# ──────────────────────────────────────────────
# PARTICIPANT — Fiche complète (Secrétariat / Direction)
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def participant_fiche_admin(request, pk):
    """Fiche complète d'un participant avec historique détaillé (badgeage, présence, temps de cours).

    Accès : ADMIN, SECRETARIAT, CHEF_SECRETARIAT, INJS_ADMIN, CHEF_INJS_ADMIN, ENCADRANT (complet).
    Lecture seule : DIRECTION, FINANCE.
    """
    user = request.user
    role = getattr(user, 'role', None)

    # Permissions : accès complet ou lecture seule
    full_access_roles = {'ADMIN', 'SECRETARIAT', 'CHEF_SECRETARIAT', 'INJS_ADMIN', 'CHEF_INJS_ADMIN', 'ENCADRANT'}
    read_only_roles = {'DIRECTION', 'FINANCE', 'ARCHIVE'}

    if role not in full_access_roles and role not in read_only_roles:
        return Response({'detail': 'Accès interdit.'}, status=status.HTTP_403_FORBIDDEN)

    participant = participant_fiche_accessible(user, pk)
    if not participant:
        return Response({'detail': 'Auditeur introuvable ou hors périmètre.'}, status=status.HTTP_404_NOT_FOUND)

    # Récupérer les modules inscrits
    from formations.models import ModuleParticipant
    inscriptions = (
        ModuleParticipant.objects.filter(participant=participant)
        .select_related('module__formation', 'module__secretariat', 'module__site')
        .order_by('-inscrit_le')
    )
    modules_data = []
    for ins in inscriptions:
        modules_data.append(_module_fiche_payload(ins.module, ins.inscrit_le, participant=participant))

    # Récupérer tous les pointages avec les détails complets
    pointages_qs = Pointage.objects.filter(participant=participant).select_related('session__module__formation')
    pointages_data = [_pointage_historique_item(pt) for pt in pointages_qs]

    # Statistiques
    stats = _compute_fiche_stats(pointages_qs)
    stats.update(_compute_volume_horaire_stats(modules_data, pointages_qs))
    stats['nb_modules_inscrits'] = len(modules_data)

    payload = {
        'participant': ParticipantSerializer(participant).data,
        'modules': modules_data,
        'pointages': pointages_data,
        'stats': stats,
    }

    from suiviEvaluation.permissions import ROLES_GESTION_NOTES
    if role in ROLES_GESTION_NOTES:
        payload['notes_fiche'] = _build_notes_fiche_payload(participant, inscriptions)

    return Response(payload)


def _resolve_participant_fiche_admin(request, pk):
    """Résout un participant pour les fiches admin (périmètre secrétariat inclus)."""
    user = request.user
    role = getattr(user, 'role', None)

    full_access_roles = {'ADMIN', 'SECRETARIAT', 'CHEF_SECRETARIAT', 'INJS_ADMIN', 'CHEF_INJS_ADMIN', 'ENCADRANT'}
    read_only_roles = {'DIRECTION', 'FINANCE', 'ARCHIVE'}

    if role not in full_access_roles and role not in read_only_roles:
        return None, Response({'detail': 'Accès interdit.'}, status=status.HTTP_403_FORBIDDEN)

    participant = participant_fiche_accessible(user, pk)
    if not participant:
        return None, Response(
            {'detail': 'Auditeur introuvable ou hors périmètre.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return participant, None


def _serialize_participant_module_notes(module, participant):
    """Résumé notes + assiduité pour un auditeur sur un module."""
    from formations.api_views import _ensure_colonnes
    from formations.models import NoteModuleSynthese
    from suiviEvaluation.services import resume_module_participant

    colonnes = _ensure_colonnes(module)
    resume = resume_module_participant(module, participant)
    synthese = NoteModuleSynthese.objects.filter(module=module, participant=participant).first()

    return {
        'module_id': module.id,
        'formation_id': module.formation_id,
        'colonne_id': colonnes[0].id if colonnes else None,
        'moyenne': resume['moyenne'],
        'heures_presence': resume['heures_presence'],
        'heures_prevues': resume['heures_prevues'],
        'taux_presence': resume['taux_presence'],
        'admissible': resume['admissible'],
        'mention': synthese.mention if synthese else '',
    }


def _build_notes_fiche_payload(participant, inscriptions):
    """Payload notes + décisions pour un auditeur (tous ses cours).

    La décision OFFICIELLE (`jurys.DecisionJury`, moteur LMD/ECTS) prime
    toujours. Le verdict `suiviEvaluation.DecisionPedagogique` est conservé
    sous le nom explicite `verdict_operationnel` : il n'est pas une autorité
    académique et ne doit jamais être présenté comme telle.
    """
    from suiviEvaluation.models import DecisionPedagogique
    from suiviEvaluation.academic_views import _serialize_decision
    from suiviEvaluation.services import _get_parametres
    from jurys.services import decision_officielle_pour

    modules_notes = [
        _serialize_participant_module_notes(ins.module, participant)
        for ins in inscriptions
    ]

    formation_ids = {
        ins.module.formation_id
        for ins in inscriptions
        if ins.module.formation_id
    }
    formations_map = {
        f.id: f
        for f in Formation.objects.filter(pk__in=formation_ids)
    }
    decisions_qs = DecisionPedagogique.objects.filter(
        participant=participant,
        formation_id__in=formation_ids,
    ).select_related('validee_par', 'formation')
    decisions_map = {d.formation_id: d for d in decisions_qs}

    # Décision officielle INJS-LMD (unique source de vérité).
    officielle = decision_officielle_pour(participant)

    formations_data = []
    for fid in sorted(formation_ids):
        formation = formations_map.get(fid)
        if not formation:
            continue
        dec = decisions_map.get(fid)
        formations_data.append({
            'formation_id': fid,
            'formation_libelle': formation.formation,
            'criteres': _get_parametres(formation),
            # Décision officielle : celle affichée comme telle.
            'decision': (
                {
                    'decision': officielle.decision,
                    'moyenne_generale': (
                        float(officielle.moyenne_generale)
                        if officielle.moyenne_generale is not None else None
                    ),
                    'credits_acquis': officielle.credits_acquis,
                    'mention': officielle.mention,
                    'validee_le': (
                        officielle.decide_le.isoformat()
                        if getattr(officielle, 'decide_le', None) else None
                    ),
                    'autorite': 'officielle',
                    'source': 'jurys.DecisionJury',
                }
                if officielle is not None else None
            ),
            # Verdict opérationnel : jamais une décision, toujours étiqueté.
            'verdict_operationnel': _serialize_decision(dec) if dec else None,
        })

    return {
        'modules': modules_notes,
        'formations': formations_data,
        'decision_officielle': (
            {
                'decision': officielle.decision,
                'credits_acquis': officielle.credits_acquis,
                'mention': officielle.mention,
            }
            if officielle is not None else None
        ),
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def participant_notes_fiche(request, pk):
    """Notes et décisions d'un auditeur — une requête pour tous ses cours."""
    from suiviEvaluation.permissions import ROLES_CONSULTATION

    role = getattr(request.user, 'role', None)
    if role not in ROLES_CONSULTATION:
        return Response({'detail': 'Accès interdit.'}, status=status.HTTP_403_FORBIDDEN)

    participant, err = _resolve_participant_fiche_admin(request, pk)
    if err:
        return err

    inscriptions = (
        ModuleParticipant.objects.filter(participant=participant)
        .select_related('module__formation')
        .order_by('-inscrit_le')
    )

    return Response(_build_notes_fiche_payload(participant, inscriptions))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def participant_notes_fiche_export(request, pk, fmt):
    """Export PDF ou Excel du relevé de notes avec décision finale."""
    from django.http import HttpResponse
    from suiviEvaluation.permissions import ROLES_FICHE_EXPORT
    from .notes_exports import (
        build_releve_notes_export_data,
        export_releve_notes_pdf,
        export_releve_notes_excel,
    )

    role = getattr(request.user, 'role', None)
    # Lot L1/L3 — un étudiant peut exporter son propre relevé de notes
    # (Participant lié au compte authentifié).
    propre_participant = getattr(request.user, 'participant_profile', None)
    if role not in ROLES_FICHE_EXPORT and not (
        propre_participant is not None and propre_participant.pk == pk
    ):
        return Response({'detail': 'Accès interdit.'}, status=status.HTTP_403_FORBIDDEN)

    participant, err = _resolve_participant_fiche_admin(request, pk)
    if err:
        return err

    fmt = (fmt or '').lower()
    if fmt not in ('pdf', 'xlsx'):
        return Response({'detail': 'Format invalide (pdf ou xlsx).'}, status=status.HTTP_400_BAD_REQUEST)

    inscriptions = (
        ModuleParticipant.objects.filter(participant=participant)
        .select_related('module__formation')
        .order_by('-inscrit_le')
    )
    notes_payload = _build_notes_fiche_payload(participant, inscriptions)
    export_data = build_releve_notes_export_data(participant, inscriptions, notes_payload)

    safe_name = f"{participant.nom}_{participant.prenom}".replace(' ', '_')
    try:
        if fmt == 'pdf':
            buffer = export_releve_notes_pdf(export_data)
            content_type = 'application/pdf'
            filename = f"releve_notes_{safe_name}_{participant.pk}.pdf"
        else:
            buffer = export_releve_notes_excel(export_data)
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            filename = f"releve_notes_{safe_name}_{participant.pk}.xlsx"
    except RuntimeError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    response = HttpResponse(buffer.getvalue(), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ──────────────────────────────────────────────
# PARTICIPANT — Lookup par numéro (pour app mobile R7)
# ──────────────────────────────────────────────

class OfflineDataError(Exception):
    """Erreur métier pour la préparation des données hors-ligne."""

    def __init__(self, detail, status_code):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def _compute_offline_data_json(token):
    """Calcule et sérialise le payload offline-data (≈450 KB)."""
    payload = _get_formation_offline_data_payload(token)
    return json.dumps(
        payload, cls=DjangoJSONEncoder, separators=(',', ':'), ensure_ascii=False,
    )


def _cached_offline_data_response(token):
    """
    Renvoie les données hors-ligne (≈450 KB) en servant le JSON déjà sérialisé
    depuis le cache. Sur un cache hit, aucune re-sérialisation DRF n'a lieu :
    on renvoie directement les octets JSON via un HttpResponse brut, ce qui
    élimine le coût CPU de rendu à chaque requête.

    Un verrou Redis (cache.add) protège contre la ruée vers le cache (thundering
    herd) : une seule requête regénère le payload, les autres attendent le résultat.
    """
    cache_key = offline_data_cache_key(token)
    cached_json = cache.get(cache_key)
    if cached_json is not None:
        return HttpResponse(cached_json, content_type='application/json')

    lock_key = offline_data_lock_key(token)
    lock_acquired = cache.add(lock_key, True, timeout=OFFLINE_DATA_LOCK_TIMEOUT)

    if lock_acquired:
        try:
            cached_json = cache.get(cache_key)
            if cached_json is None:
                try:
                    cached_json = _compute_offline_data_json(token)
                except OfflineDataError as exc:
                    return Response({'detail': exc.detail}, status=exc.status_code)
                cache.set(cache_key, cached_json, timeout=OFFLINE_DATA_CACHE_TIMEOUT)
        finally:
            cache.delete(lock_key)
        return HttpResponse(cached_json, content_type='application/json')

    # Attente passive si un autre worker regénère déjà le payload.
    deadline = time.monotonic() + OFFLINE_DATA_LOCK_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(0.1)
        cached_json = cache.get(cache_key)
        if cached_json is not None:
            return HttpResponse(cached_json, content_type='application/json')

    # Dernier recours : regénérer localement si le verrou a été abandonné.
    try:
        cached_json = _compute_offline_data_json(token)
    except OfflineDataError as exc:
        return Response({'detail': exc.detail}, status=exc.status_code)
    cache.set(cache_key, cached_json, timeout=OFFLINE_DATA_CACHE_TIMEOUT)
    return HttpResponse(cached_json, content_type='application/json')


def _get_formation_offline_data_payload(token):
    """Données hors-ligne pour un token QR (UUID). Retourne un dict sérialisable."""
    try:
        qr_token = QRToken.objects.select_related(
            'session__module__formation',
            'session__module__superviseur',
        ).get(token=token)
    except QRToken.DoesNotExist:
        raise OfflineDataError('Token invalide.', status.HTTP_404_NOT_FOUND)

    if qr_token.is_expired:
        raise OfflineDataError('Token expiré.', status.HTTP_400_BAD_REQUEST)

    # Si le token a été remplacé (regeneration QR), utiliser le token actif courant
    if not qr_token.actif:
        replacement = QRToken.objects.filter(
            session=qr_token.session,
            actif=True,
        ).order_by('-created_at').first()
        if replacement and replacement.is_valid:
            qr_token = replacement
        else:
            raise OfflineDataError(
                'Token désactivé. Aucun QR actif pour cette séance.',
                status.HTTP_400_BAD_REQUEST,
            )

    if not qr_token.session:
        raise OfflineDataError(
            'Ce token n\'est pas lié à une séance.',
            status.HTTP_400_BAD_REQUEST,
        )
    if qr_token.session.est_terminee:
        raise OfflineDataError(
            'Token désactivé. Cette séance est terminée.',
            status.HTTP_400_BAD_REQUEST,
        )
    formation = qr_token.session.module.formation
    scan_module = qr_token.session.module

    participants = [
        {'numero': matricule, 'nom': nom, 'prenom': prenom}
        for matricule, nom, prenom in (
            Participant.objects.filter(
                modules_inscrits__module=scan_module,
            )
            .distinct()
            .values_list('matricule', 'nom', 'prenom')
        )
    ]

    formateurs = [
        {'numero': numerobadge, 'nom': nom, 'prenom': prenom}
        for numerobadge, nom, prenom in (
            Formateur.objects.filter(
                modules_assignes__module=scan_module,
            )
            .distinct()
            .values_list('numerobadge', 'nom', 'prenom')
        )
    ]

    encadrants = []
    if scan_module.superviseur_id:
        sup = scan_module.superviseur
        encadrants.append({
            'numero': sup.matricule or '',
            'nom': sup.last_name or '',
            'prenom': sup.first_name or '',
            'username': sup.username,
        })

    module = scan_module
    site     = ((module.site.nom if getattr(module, 'site', None) else getattr(module, 'site_legacy', '')) if module else '')
    batiment = (module.batiment if module else '')
    salle    = (module.salle    if module else '')

    return {
        'formation': {
            'id': formation.id,
            'titre': formation.formation,
            'site': site,
            'batiment': batiment,
            'salle': salle,
        },
        'token': str(qr_token.token),
        'participants': participants,
        'formateurs': formateurs,
        'encadrants': encadrants,
    }


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([OfflineDataRateThrottle])
def scan_offline_data(request):
    """
    Données hors-ligne pour la page badge (token QR en query string).

    GET /api/scan/offline-data/?token=<uuid>

    Les données sont mises en cache Redis (1 h) car quasi-statiques.
    """
    if not settings.PUBLIC_QR_SCAN_ENABLED:
        return _public_scan_disabled_response()
    token_str = (request.query_params.get('token') or '').strip()
    if not token_str:
        return Response(
            {'detail': 'Paramètre "token" requis (UUID du QR code).'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        token = uuid.UUID(token_str)
    except ValueError:
        return Response(
            {'detail': 'Token QR invalide (UUID attendu, pas un ID formation).'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return _cached_offline_data_response(token)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([OfflineDataRateThrottle])
def formation_offline_data(request, token):
    """
    Données hors-ligne (legacy) — token QR dans le chemin.

    Préférer ``GET /api/scan/offline-data/?token=…``.

    Les données sont mises en cache Redis (1 h) car quasi-statiques.
    """
    if not settings.PUBLIC_QR_SCAN_ENABLED:
        return _public_scan_disabled_response()

    return _cached_offline_data_response(token)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def participant_lookup(request):
    """Recherche participant par numéro (R7 — pas besoin de compte)."""
    numero = request.query_params.get('numero', '')
    if not numero:
        return Response(
            {'detail': 'Paramètre "numero" requis.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if request.user.role != User.Role.AUDITEUR:
        return Response({'detail': 'Acces interdit.'}, status=status.HTTP_403_FORBIDDEN)

    try:
        participant = request.user.participant_profile
    except Participant.DoesNotExist:
        return Response({'detail': 'Auditeur introuvable.'}, status=status.HTTP_404_NOT_FOUND)

    if participant.matricule != numero:
        return Response(
            {'detail': 'Auditeur introuvable.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(ParticipantSerializer(participant).data)


# ──────────────────────────────────────────────
# DFRC / ENCADRANT — Journal d'audit
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsDFRCOrEncadrant])
def audit_log_list(request):
    """
    Journal d'audit de toutes les actions critiques.
    Filtres disponibles (query params) :
      - formation_id : int
      - action       : code action (ex: FORCE_ENTREE)
      - acteur_id    : int (user qui a agi)
      - cible_numero : numéro participant/formateur
      - date_debut   : YYYY-MM-DD
      - date_fin     : YYYY-MM-DD
    """
    qs = AuditLog.objects.select_related('acteur', 'formation', 'pointage').order_by('-timestamp')

    formation_id = request.query_params.get('formation_id')
    if formation_id:
        qs = qs.filter(formation_id=formation_id)

    action = request.query_params.get('action')
    if action:
        qs = qs.filter(action=action)

    acteur_id = request.query_params.get('acteur_id')
    if acteur_id:
        qs = qs.filter(acteur_id=acteur_id)

    cible_numero = request.query_params.get('cible_numero')
    if cible_numero:
        qs = qs.filter(cible_numero__icontains=cible_numero)

    date_debut = request.query_params.get('date_debut')
    if date_debut:
        qs = qs.filter(timestamp__date__gte=date_debut)

    date_fin = request.query_params.get('date_fin')
    if date_fin:
        qs = qs.filter(timestamp__date__lte=date_fin)

    # Encadrant : restreindre aux formations dont il est superviseur
    if request.user.role == 'ENCADRANT':
        qs = qs.filter(formation__modules__superviseur=request.user)

    data = []
    for log in qs[:500]:
        data.append({
            'id': log.id,
            'timestamp': log.timestamp.isoformat(),
            'action': log.action,
            'action_label': log.get_action_display(),
            'acteur_id': log.acteur_id,
            'acteur_label': log.acteur_label or 'Anonyme',
            'acteur_role': log.acteur.role if log.acteur else None,
            'cible_type': log.cible_type,
            'cible_numero': log.cible_numero,
            'cible_nom': log.cible_nom,
            'formation_id': log.formation_id,
            'formation_titre': log.formation_titre,
            'pointage_id': log.pointage_id,
            'ip_address': log.ip_address,
            'device_id': log.device_id,
            'extra': log.extra,
        })

    return Response({'count': len(data), 'results': data})


# ──────────────────────────────────────────────
# Vérification statut badgeage sécurisé (app mobile, authentifié)
# ──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def secure_check_badge_status(request):
    """
    Indique si le prochain scan de l'utilisateur authentifié sera une ENTREE ou
    une SORTIE pour le QR donné (ou s'il a déjà terminé cette séance).

    GET ?token_qr=<uuid>
    Retour : { statut: 'ABSENT'|'EN_SALLE'|'TERMINE'|'INCONNU',
               action_suivante: 'ENTREE'|'SORTIE'|null,
               heure_entree: 'HH:MM'|null,
               seance_intitule: str|null }
    """
    token_qr = request.GET.get('token_qr', '').strip()
    if not token_qr:
        return Response(
            {'code': 'MISSING_TOKEN', 'detail': 'token_qr requis.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = request.user
    if getattr(user, 'must_change_password', False):
        return _password_change_required_response()

    personne, type_str, err = _resolve_authenticated_personne(user)
    if err:
        return err

    try:
        qr_token = QRToken.objects.select_related(
            'session__module__formation', 'seance_edt__creneau_template',
            'seance_edt__emploi_du_temps__annee_academique', 'seance_edt__groupe',
        ).get(
            token=token_qr,
        )
    except (QRToken.DoesNotExist, ValueError):
        return Response({'statut': 'INCONNU', 'action_suivante': 'ENTREE'})

    # Empilement canal EDT/LMD : état de badgeage d'une séance planifiée, avec
    # l'état de périmètre calculé côté serveur (l'appli n'en décide jamais).
    if qr_token.seance_edt_id is not None:
        return _check_status_seance_edt_mobile(
            request=request, qr_token=qr_token, personne=personne, type_str=type_str)

    if not qr_token.is_valid and qr_token.actif:
        return Response({'statut': 'INCONNU', 'action_suivante': 'ENTREE'})

    # QR remplacé mais valide : suivre le remplaçant
    if not qr_token.actif:
        replacement = QRToken.objects.filter(
            session=qr_token.session, actif=True,
        ).order_by('-created_at').first()
        if replacement and replacement.is_valid:
            qr_token = replacement
        else:
            return Response({'statut': 'INCONNU', 'action_suivante': 'ENTREE'})

    seance = qr_token.session
    if not seance:
        return Response({'statut': 'INCONNU', 'action_suivante': 'ENTREE'})

    formation = seance.module.formation

    # Aligne sur la fiche réellement inscrite au module (compte rattaché à une autre fiche).
    if type_str == 'participant':
        from .participant_scope import participant_for_module
        inscrit = participant_for_module(user, seance.module, seance=seance)
        if inscrit is not None:
            personne = inscrit
    elif type_str == 'encadrant':
        if not _encadrant_can_badge_module(user, seance.module):
            return _encadrant_not_in_list_response(seance.module)

    today = timezone.localdate()
    session_filter = _pointage_filter(personne, type_str, formation, date_journee=today)
    session_filter['session'] = seance

    seance_label = seance.intitule or f'Séance {seance.numero}'

    # Informations de géofence pour permettre au client d'afficher la position.
    module = seance.module
    site_lat, site_lon, site_rayon = _resolve_site_geofence(module)
    geofence_info = {
        'geofence_configured': site_lat is not None and site_lon is not None,
        'geofence_latitude': float(site_lat) if site_lat is not None else None,
        'geofence_longitude': float(site_lon) if site_lon is not None else None,
        'geofence_rayon_m': float(site_rayon) if site_rayon is not None else None,
        'distance_m': None,
        'in_geofence': None,
        'accuracy_ok': None,
        'accuracy_max_m': float(getattr(settings, 'MOBILE_GEOFENCE_MAX_ACCURACY_M', 80)),
    }

    # Si le client envoie sa position, calculer la distance et l'état geofence.
    lat_raw = request.GET.get('latitude')
    lon_raw = request.GET.get('longitude')
    acc_raw = request.GET.get('accuracy_m')
    try:
        lat = float(lat_raw) if lat_raw not in (None, '') else None
        lon = float(lon_raw) if lon_raw not in (None, '') else None
        acc = float(acc_raw) if acc_raw not in (None, '') else None
    except (TypeError, ValueError):
        lat = lon = acc = None

    if lat is not None and lon is not None and geofence_info['geofence_configured']:
        distance = _distance_meters(lat, lon, site_lat, site_lon)
        geofence_info['distance_m'] = round(distance, 1)
        geofence_info['in_geofence'] = distance <= geofence_info['geofence_rayon_m']

    if acc is not None:
        geofence_info['accuracy_ok'] = acc <= geofence_info['accuracy_max_m']

    pointage_ouvert = Pointage.objects.filter(
        **session_filter, timestamp_sortie__isnull=True,
    ).order_by('-timestamp_entree').first()
    if pointage_ouvert:
        heure = timezone.localtime(pointage_ouvert.timestamp_entree).strftime('%H:%M')
        return Response({
            'statut': 'EN_SALLE',
            'action_suivante': 'SORTIE',
            'heure_entree': heure,
            'seance_intitule': seance_label,
            **geofence_info,
        })

    pointage_termine = Pointage.objects.filter(
        **session_filter, timestamp_sortie__isnull=False,
    ).exists()
    if pointage_termine:
        return Response({
            'statut': 'TERMINE',
            'action_suivante': None,
            'heure_entree': None,
            'seance_intitule': seance_label,
            **geofence_info,
        })

    return Response({
        'statut': 'ABSENT',
        'action_suivante': 'ENTREE',
        'heure_entree': None,
        'seance_intitule': seance_label,
        **geofence_info,
    })


# ──────────────────────────────────────────────
# Vérification statut badgeage avant confirmation (endpoint public)
# ──────────────────────────────────────────────

@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def check_badge_status(request):
    """
    Vérifie l'état actuel du badgeage pour un participant/formateur/encadrant sur un token QR.
    GET ?token_qr=<uuid>&numero=<matricule>
    Retourne : { statut: 'ABSENT'|'EN_SALLE'|'TERMINE', action_suivante: 'ENTREE'|'SORTIE'|null,
                 nom, prenom, timestamp_entree, heure_entree }
    Endpoint public (lecture seule, pas de mutation).
    Désactivé si PUBLIC_QR_SCAN_ENABLED=False.
    """
    if not settings.PUBLIC_QR_SCAN_ENABLED:
        return _public_scan_disabled_response()

    token_qr = request.GET.get('token_qr', '').strip()
    numero = request.GET.get('numero', '').strip()

    if not token_qr or not numero:
        return Response({'statut': 'INCONNU', 'action_suivante': 'ENTREE'})

    try:
        qr_token = QRToken.objects.select_related('session__module__formation').get(token=token_qr)
    except QRToken.DoesNotExist:
        return Response({'statut': 'INCONNU', 'action_suivante': 'ENTREE'})

    if not qr_token.is_valid:
        return Response({'statut': 'INCONNU', 'action_suivante': 'ENTREE'})

    if not qr_token.session:
        return Response({'statut': 'INCONNU', 'action_suivante': 'ENTREE'})
    formation = qr_token.session.module.formation
    today = timezone.localdate()

    personne, type_str, _, err = _resolve_personne(numero, formation, qr_token.session.module)
    if err:
        return Response({
            'statut': 'NON_AUTORISE',
            'action_suivante': None,
            'code': err.data.get('code'),
            'detail': err.data.get('detail'),
        })

    seance = qr_token.session
    session_filter = _pointage_filter(personne, type_str, formation, date_journee=today)
    session_filter['session'] = seance

    pointage_ouvert = Pointage.objects.filter(
        **session_filter, timestamp_sortie__isnull=True,
    ).order_by('-timestamp_entree').first()

    if pointage_ouvert:
        heure = timezone.localtime(pointage_ouvert.timestamp_entree).strftime('%H:%M')
        return Response({
            'statut': 'EN_SALLE',
            'action_suivante': 'SORTIE',
            'type_personne': type_str,
            'nom': getattr(personne, 'nom', None) or getattr(personne, 'last_name', '') or '',
            'prenom': getattr(personne, 'prenom', None) or getattr(personne, 'first_name', '') or '',
            'heure_entree': heure,
        })

    pointage_termine = Pointage.objects.filter(
        **session_filter, timestamp_sortie__isnull=False,
    ).exists()

    if pointage_termine:
        return Response({
            'statut': 'TERMINE',
            'action_suivante': None,
            'type_personne': type_str,
            'nom': getattr(personne, 'nom', None) or getattr(personne, 'last_name', '') or '',
            'prenom': getattr(personne, 'prenom', None) or getattr(personne, 'first_name', '') or '',
        })

    return Response({
        'statut': 'ABSENT',
        'action_suivante': 'ENTREE',
        'type_personne': type_str,
        'nom': getattr(personne, 'nom', None) or getattr(personne, 'last_name', '') or '',
        'prenom': getattr(personne, 'prenom', None) or getattr(personne, 'first_name', '') or '',
    })
