"""
API views for the React frontend.
These views complement the existing DRF views with additional endpoints
needed for the frontend dashboard.
"""
from io import BytesIO
from datetime import timedelta, datetime, time, date
import calendar
import re
from django.core.cache import cache
from django.http import HttpResponse
from django.db.models import Count, Q, F, Prefetch, Case, When, Value, IntegerField
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from authentication.permissions import (
    IsDFRC,
    IsSecretariat,
    IsSecretariatOrDFRC,
    IsSecretariatOrEncadrantOrDFRC,
    CanManageModuleParticipant,
)
from authentication.role_groups import get_user_role
from suiviEvaluation.permissions import IsGestionNotes, IsGestionNotesOrReadOnly
from formations.models import Secretariat
from django.contrib.auth import get_user_model
from rest_framework.response import Response
from presences.models import Pointage, SessionModule as PresenceSessionModule, AuditLog, _log_audit
from presences.offline_cache import invalidate_offline_data_cache

from .models import Formation, Participant, Formateur, QRToken, SessionModule, ModuleParticipant, ModuleFormateur, RefFormation, RefModule, RefSite, RefBatiment, RefSalle, RefCategorie, RefGrade, RefTypeSecretariat, RefVague, Module, FinanceSettings, FinanceAjustement, NoteModule, NoteModuleColonne, NoteModuleSynthese, CorrectionNoteModule, NotificationModificationNote, NotificationFinanceAjustement
FormationParticipant = ModuleParticipant
FormationFormateur = ModuleFormateur
from .access import (
    can_archive_module,
    can_unarchive_module,
    formateurs_queryset_for_user,
    formation_accessible,
    module_operational_accessible,
    operational_modules_queryset,
    participants_queryset_for_user,
    participant_accessible,
)
from .formateur_privacy import (
    can_view_formateur_sensitive_data,
    can_edit_formateur_sensitive_data,
    formateur_sensitive_payload,
)
from .formateur_assignment import check_formateur_groupe_jour_conflict
from .api_access import (
    CanListParticipants,
    IsOperationalWebStaff,
    archived_module_or_response,
    module_for_notes_or_response,
    module_unarchive_or_response,
    deny_finance_operational_response,
    formation_or_response,
    module_or_response,
)
from .volume_horaire import compute_dashboard_volume_horaire
from .finance_encadrants import finance_encadrants_report
from .finance_ajustements import (
    propose_ajustement,
    valider_ajustement,
    rejeter_ajustement,
    serialize_ajustement,
    _log_finance_audit,
)
from .finance_notifications import (
    notifier_ajustement_propose,
    notifier_ajustement_valide,
    notifier_ajustement_rejete,
)
from .note_notifications import note_deja_enregistree, notifier_modification_note
from .note_workflow import appliquer_workflow, actions_valides
from .finance_tolerance import tolerance_settings_payload
from .serializers import (
    FormationListSerializer,
    FormationDetailSerializer,
    ParticipantSerializer,
    FormateurSerializer,
    ModuleSerializer,
    QRTokenSerializer,
)
from .qr_helpers import get_session_for_qr
from .referentiels_excel import (
    ReferentielExcelError,
    export_referentiel_xlsx,
    import_referentiel_xlsx,
)


def _normalize_groupe_value(value):
    """Normalise les variantes de groupe (1, 01, GROUPE 1) vers GROUPE N."""
    raw = str(value or '').strip()
    if not raw:
        return ''
    compact = re.sub(r'\s+', ' ', raw).strip()
    match = re.fullmatch(r'(?:GROUPE\s*)?0*(\d+)', compact, flags=re.IGNORECASE)
    if match:
        return f"GROUPE {int(match.group(1))}"
    return compact.upper()


def _groupe_sort_key(value):
    match = re.fullmatch(r'GROUPE (\d+)', value)
    if match:
        return (0, int(match.group(1)))
    return (1, value)


def _mention_from_note(note):
    """Calcule la mention à partir d'une note /20."""
    if note is None:
        return ''
    try:
        n = float(note)
    except (TypeError, ValueError):
        return ''
    if n >= 16:
        return NoteModuleSynthese.Mention.TRES_BIEN
    if n >= 14:
        return NoteModuleSynthese.Mention.BIEN
    if n >= 12:
        return NoteModuleSynthese.Mention.ASSEZ_BIEN
    if n >= 10:
        return NoteModuleSynthese.Mention.PASSABLE
    return NoteModuleSynthese.Mention.INSUFFISANT


def _mention_from_notes(notes):
    """Mention à partir de la moyenne de plusieurs notes."""
    vals = []
    for n in notes:
        if n is None or n == '':
            continue
        try:
            vals.append(float(n))
        except (TypeError, ValueError):
            continue
    if not vals:
        return ''
    return _mention_from_note(sum(vals) / len(vals))


def _user_display(user):
    if not user:
        return None
    return user.get_full_name() or user.username


def _ensure_colonnes(module):
    colonnes = list(NoteModuleColonne.objects.filter(module=module).order_by('ordre', 'id'))
    if colonnes:
        return colonnes
    colonne = NoteModuleColonne.objects.create(
        module=module,
        libelle='Note /20',
        ordre=0,
        note_max=20,
    )
    return [colonne]


def _serialize_colonne(colonne):
    return {
        'id': colonne.id,
        'libelle': colonne.libelle,
        'ordre': colonne.ordre,
        'note_max': float(colonne.note_max),
    }


def _get_module_in_formation(user, formation_pk, module_pk):
    return module_or_response(user, formation_pk, module_pk)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def dashboard_stats(request):
    """Return dashboard statistics, scoped by secretariat for SECRETARIAT role."""
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    from .api_cache import get_cached_response, request_cache_key, set_cached_response

    cache_key = request_cache_key('dash_stats', request)
    cached = get_cached_response(cache_key)
    if cached is not None:
        return Response(cached)

    modules_qs = operational_modules_queryset()
    participants_qs = Participant.objects.all()
    secretariat_filter = request.query_params.get('secretariat')
    reference_date_raw = request.query_params.get('reference_date')

    if request.user.is_authenticated and request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
        sec = request.user.secretariat
        modules_qs = modules_qs.filter(secretariat=sec)
        participants_qs = participants_qs.filter(secretariat=sec)
    elif request.user.is_authenticated and request.user.role == 'ENCADRANT':
        modules_qs = modules_qs.filter(superviseur=request.user)
        fp_ids = ModuleParticipant.objects.filter(module__superviseur=request.user).values_list('participant_id', flat=True)
        participants_qs = participants_qs.filter(id__in=fp_ids).distinct()
    elif request.user.is_authenticated and request.user.role in ('INJS_ADMIN', 'CHEF_INJS_ADMIN', 'DIRECTION', 'ARCHIVE') and secretariat_filter:
        modules_qs = modules_qs.filter(secretariat_id=secretariat_filter)
        participants_qs = participants_qs.filter(secretariat_id=secretariat_filter)

    today = timezone.localdate()
    if reference_date_raw:
        try:
            today = datetime.strptime(reference_date_raw, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'detail': 'Format de date invalide. Utilisez YYYY-MM-DD pour reference_date.'},
                status=400,
            )

    from formations.period_filter import parse_period_from_request, periode_api_payload

    period = parse_period_from_request(request)
    if period['error']:
        return Response({'detail': period['detail']}, status=400)
    date_debut = period['date_debut']
    date_fin = period['date_fin']

    total_formations = modules_qs.count()
    formations_actives = modules_qs.filter(statut='EN_COURS').count()
    formations_terminees = modules_qs.filter(statut='TERMINEE').count()
    formations_planifiees = modules_qs.filter(statut='PLANIFIEE').count()
    groupes_en_cours = modules_qs.filter(statut='EN_COURS', groupe__isnull=False).exclude(groupe='').values('groupe').distinct().count()
    total_participants = participants_qs.count()

    volume_horaire_effectue_heures, volume_horaire_total_heures, volume_horaire_effectue_taux = (
        compute_dashboard_volume_horaire(modules_qs, date_debut=date_debut, date_fin=date_fin)
    )

    formateurs_qs = Formateur.objects.all()
    if request.user.role == 'ENCADRANT':
        formateurs_qs = formateurs_qs.filter(modules_assignes__module__in=modules_qs).distinct()
    total_formateurs = formateurs_qs.count()

    seances_actives = PresenceSessionModule.objects.filter(
        module__in=modules_qs, demarree_le__isnull=False, terminee_le__isnull=True
    ).count()
    seances_planifiees_aujourd_hui = PresenceSessionModule.objects.filter(
        module__in=modules_qs,
        module__statut__in=['PLANIFIEE', 'EN_COURS'],
        date_journee=today,
        demarree_le__isnull=True,
    ).count()
    pointages_aujourd_hui = Pointage.objects.filter(
        session__module__in=modules_qs, date_journee=today
    ).count()
    pointages_ouverts = Pointage.objects.filter(
        session__module__in=modules_qs,
        date_journee=today,
        timestamp_sortie__isnull=True,
        timestamp_entree__isnull=False,
    )
    en_salle_now = (
        pointages_ouverts.filter(participant__isnull=False).values('participant').distinct().count()
        + pointages_ouverts.filter(formateur__isnull=False).values('formateur').distinct().count()
    )

    # Les indicateurs présence/absence du jour sont calculés sur les modules ayant
    # une séance aujourd'hui, qu'ils soient EN_COURS ou PLANIFIEE (première séance du jour).
    modules_avec_seance_aujourd_hui = modules_qs.filter(
        statut__in=['EN_COURS', 'PLANIFIEE'],
        sessions__date_journee=today,
    ).distinct()
    participants_attendus_jour = ModuleParticipant.objects.filter(
        module__in=modules_avec_seance_aujourd_hui
    ).values('participant').distinct().count()
    formateurs_attendus_jour = ModuleFormateur.objects.filter(
        module__in=modules_avec_seance_aujourd_hui
    ).values('formateur').distinct().count()
    total_attendus_jour = participants_attendus_jour + formateurs_attendus_jour

    participants_pointes = Pointage.objects.filter(
        session__module__in=modules_avec_seance_aujourd_hui,
        date_journee=today,
        participant__isnull=False,
    ).values('participant').distinct().count()
    formateurs_pointes = Pointage.objects.filter(
        session__module__in=modules_avec_seance_aujourd_hui,
        date_journee=today,
        formateur__isnull=False,
    ).values('formateur').distinct().count()
    presents_aujourd_hui = participants_pointes + formateurs_pointes

    absents_aujourd_hui = max(total_attendus_jour - presents_aujourd_hui, 0)
    taux_presence = round((presents_aujourd_hui / total_attendus_jour * 100), 1) if total_attendus_jour > 0 else 0
    taux_absence = round(100 - taux_presence, 1) if total_attendus_jour > 0 else 0

    # Indicateurs agrégés semaine / mois (même périmètre : modules EN_COURS)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    modules_avec_seance_semaine = modules_qs.filter(
        statut__in=['EN_COURS', 'PLANIFIEE'],
        sessions__date_journee__range=(week_start, week_end),
    ).distinct()
    participants_attendus_semaine = ModuleParticipant.objects.filter(
        module__in=modules_avec_seance_semaine
    ).values('participant').distinct().count()
    formateurs_attendus_semaine = ModuleFormateur.objects.filter(
        module__in=modules_avec_seance_semaine
    ).values('formateur').distinct().count()
    total_attendus_semaine = participants_attendus_semaine + formateurs_attendus_semaine
    participants_presents_semaine = Pointage.objects.filter(
        session__module__in=modules_avec_seance_semaine,
        date_journee__range=(week_start, week_end),
        participant__isnull=False,
    ).values('participant').distinct().count()
    formateurs_presents_semaine = Pointage.objects.filter(
        session__module__in=modules_avec_seance_semaine,
        date_journee__range=(week_start, week_end),
        formateur__isnull=False,
    ).values('formateur').distinct().count()
    presents_semaine = participants_presents_semaine + formateurs_presents_semaine
    taux_presence_semaine = round((presents_semaine / total_attendus_semaine * 100), 1) if total_attendus_semaine > 0 else 0

    modules_avec_seance_mois = modules_qs.filter(
        statut__in=['EN_COURS', 'PLANIFIEE'],
        sessions__date_journee__range=(month_start, today),
    ).distinct()
    participants_attendus_mois = ModuleParticipant.objects.filter(
        module__in=modules_avec_seance_mois
    ).values('participant').distinct().count()
    formateurs_attendus_mois = ModuleFormateur.objects.filter(
        module__in=modules_avec_seance_mois
    ).values('formateur').distinct().count()
    total_attendus_mois = participants_attendus_mois + formateurs_attendus_mois
    participants_presents_mois = Pointage.objects.filter(
        session__module__in=modules_avec_seance_mois,
        date_journee__range=(month_start, today),
        participant__isnull=False,
    ).values('participant').distinct().count()
    formateurs_presents_mois = Pointage.objects.filter(
        session__module__in=modules_avec_seance_mois,
        date_journee__range=(month_start, today),
        formateur__isnull=False,
    ).values('formateur').distinct().count()
    presents_mois = participants_presents_mois + formateurs_presents_mois
    taux_presence_mois = round((presents_mois / total_attendus_mois * 100), 1) if total_attendus_mois > 0 else 0

    modules_avec_seance_annee = modules_qs.filter(
        statut__in=['EN_COURS', 'PLANIFIEE'],
        sessions__date_journee__range=(year_start, today),
    ).distinct()
    participants_attendus_annee = ModuleParticipant.objects.filter(
        module__in=modules_avec_seance_annee
    ).values('participant').distinct().count()
    formateurs_attendus_annee = ModuleFormateur.objects.filter(
        module__in=modules_avec_seance_annee
    ).values('formateur').distinct().count()
    total_attendus_annee = participants_attendus_annee + formateurs_attendus_annee
    participants_presents_annee = Pointage.objects.filter(
        session__module__in=modules_avec_seance_annee,
        date_journee__range=(year_start, today),
        participant__isnull=False,
    ).values('participant').distinct().count()
    formateurs_presents_annee = Pointage.objects.filter(
        session__module__in=modules_avec_seance_annee,
        date_journee__range=(year_start, today),
        formateur__isnull=False,
    ).values('formateur').distinct().count()
    presents_annee = participants_presents_annee + formateurs_presents_annee
    taux_presence_annee = round((presents_annee / total_attendus_annee * 100), 1) if total_attendus_annee > 0 else 0

    # Retard moyen d'arrivée (minutes positives uniquement)
    retards = []
    current_tz = timezone.get_current_timezone()
    pointages_scope_today = Pointage.objects.filter(
        session__module__in=modules_avec_seance_aujourd_hui,
        date_journee=today,
    ).select_related('session').exclude(timestamp_entree__isnull=True)
    for pt in pointages_scope_today:
        if not pt.session or not pt.session.heure_debut_prevue:
            continue
        start_dt = timezone.make_aware(
            datetime.combine(pt.date_journee, pt.session.heure_debut_prevue),
            current_tz,
        )
        delay_minutes = (pt.timestamp_entree - start_dt).total_seconds() / 60
        if delay_minutes > 0:
            retards.append(delay_minutes)
    retard_moyen_minutes = round(sum(retards) / len(retards), 1) if retards else 0

    derniers_pointages = []
    for pt in Pointage.objects.filter(
        session__module__in=modules_qs,
        timestamp_entree__isnull=False,
    ).select_related('participant', 'formateur', 'encadrant', 'session__module').order_by('-timestamp_entree')[:8]:
        if pt.formateur_id:
            personne = pt.formateur
            type_personne = 'formateur'
        elif pt.encadrant_id:
            personne = pt.encadrant
            type_personne = 'encadrant'
        else:
            personne = pt.participant
            type_personne = 'participant'

        nom = '—'
        if personne:
            nom = (
                f"{getattr(personne, 'nom', '')} {getattr(personne, 'prenom', '')}".strip()
                or f"{getattr(personne, 'last_name', '')} {getattr(personne, 'first_name', '')}".strip()
                or getattr(personne, 'username', '')
                or '—'
            )
        derniers_pointages.append({
            'nom': nom,
            'matricule': (
                getattr(personne, 'numerobadge', None)
                or getattr(personne, 'matricule', None)
                or getattr(personne, 'numero', None)
                or '—'
            ),
            'type': type_personne,
            'module': pt.session.module.intitule or '',
            'date': pt.date_journee,
            'heure_entree': pt.timestamp_entree,
            'heure_sortie': pt.timestamp_sortie,
        })

    prochaines_seances = []
    now_local = timezone.localtime(timezone.now())
    midi = time(12, 0)
    tomorrow = today + timedelta(days=1)

    # Règle dashboard:
    # - Le matin: montrer les séances d'après-midi/soir du jour.
    # - La veille (après-midi/soir): montrer les séances du matin du lendemain.
    if now_local.time() < midi:
        prochaines_qs = PresenceSessionModule.objects.filter(
            module__in=modules_qs,
            date_journee=today,
            demarree_le__isnull=True,
        ).filter(
            Q(heure_debut_prevue__gte=midi) | Q(heure_debut_prevue__isnull=True)
        )
    else:
        prochaines_qs = PresenceSessionModule.objects.filter(
            module__in=modules_qs,
            date_journee=tomorrow,
            demarree_le__isnull=True,
        ).filter(
            Q(heure_debut_prevue__lt=midi) | Q(heure_debut_prevue__isnull=True)
        )

    prochaines_qs = prochaines_qs.select_related(
        'module', 'module__formation'
    ).order_by('date_journee', 'heure_debut_prevue', 'numero')

    # Fallback: si aucune séance ne correspond à la règle, prendre les plus proches.
    if not prochaines_qs.exists():
        prochaines_qs = PresenceSessionModule.objects.filter(
            module__in=modules_qs,
            date_journee__gte=today,
            demarree_le__isnull=True,
        ).select_related('module', 'module__formation').order_by(
            'date_journee', 'heure_debut_prevue', 'numero'
        )[:10]
    for sess in prochaines_qs:
        label = sess.intitule or f"Séance {sess.numero}"
        prochaines_seances.append({
            'session_id': sess.id,
            'module_id': sess.module_id,
            'formation_id': sess.module.formation_id,
            'module': sess.module.intitule,
            'formation': sess.module.formation.formation if sess.module.formation else '',
            'session_label': label,
            'date_journee': sess.date_journee,
            'heure_debut_prevue': sess.heure_debut_prevue,
        })

    payload = {
        'total_modules': total_formations,
        'modules_en_cours': formations_actives,
        'modules_termines': formations_terminees,
        'modules_planifies': formations_planifiees,
        'groupes_en_cours': groupes_en_cours,
        'total_participants': total_participants,
        'volume_horaire_total_heures': volume_horaire_total_heures,
        'volume_horaire_effectue_heures': volume_horaire_effectue_heures,
        'volume_horaire_effectue_taux': volume_horaire_effectue_taux,
        'total_formateurs': total_formateurs,
        'seances_actives': seances_actives,
        'seances_planifiees_aujourd_hui': seances_planifiees_aujourd_hui,
        'pointages_aujourd_hui': pointages_aujourd_hui,
        'en_salle_now': en_salle_now,
        'auditeurs_attendus_jour': participants_attendus_jour,
        'auditeurs_presents_jour': participants_pointes,
        'formateurs_attendus_jour': formateurs_attendus_jour,
        'formateurs_presents_jour': formateurs_pointes,
        'total_attendus_jour': total_attendus_jour,
        'presents_aujourd_hui': presents_aujourd_hui,
        'absents_aujourd_hui': absents_aujourd_hui,
        'taux_presence': taux_presence,
        'taux_absence': taux_absence,
        'total_attendus_semaine': total_attendus_semaine,
        'presents_semaine': presents_semaine,
        'taux_presence_semaine': taux_presence_semaine,
        'total_attendus_mois': total_attendus_mois,
        'presents_mois': presents_mois,
        'taux_presence_mois': taux_presence_mois,
        'total_attendus_annee': total_attendus_annee,
        'presents_annee': presents_annee,
        'taux_presence_annee': taux_presence_annee,
        'retard_moyen_minutes': retard_moyen_minutes,
        'prochaines_seances': prochaines_seances,
        'derniers_pointages': derniers_pointages,
        'periode': periode_api_payload(date_debut, date_fin, period['meta']),
    }
    set_cached_response(cache_key, payload, 45)
    return Response(payload)


def _filtered_modules_queryset(request, *, archives_only=False):
    """
    Queryset modules filtré et trié (sans annotations coûteuses ni pagination).
    Retourne (queryset, None) ou (None, Response) si paramètres invalides.
    """
    from .access import archived_modules_queryset, operational_modules_queryset

    base_qs = archived_modules_queryset() if archives_only else operational_modules_queryset()
    queryset = base_qs.select_related(
        'formation', 'secretariat__type', 'formateur', 'superviseur', 'creee_par', 'site',
    )

    if request.user.is_authenticated and request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
        if request.user.secretariat:
            queryset = queryset.filter(secretariat=request.user.secretariat)
        else:
            queryset = queryset.none()
    elif request.user.is_authenticated and request.user.role == 'ENCADRANT':
        queryset = queryset.filter(superviseur=request.user)

    statut = request.query_params.get('statut')
    if statut:
        queryset = queryset.filter(statut=statut)

    search = request.query_params.get('search')
    if search:
        queryset = queryset.filter(
            Q(intitule__icontains=search) | Q(formation__formation__icontains=search)
        ).distinct()

    module_filter = request.query_params.get('module')
    if module_filter:
        queryset = queryset.filter(intitule__icontains=module_filter)

    categorie = request.query_params.get('categorie')
    if categorie:
        queryset = queryset.filter(grade__istartswith=categorie)

    grade_param = (request.query_params.get('grade') or '').strip()
    if grade_param:
        queryset = queryset.filter(grade__iexact=grade_param)

    secretariat_type = request.query_params.get('secretariat_type')
    if secretariat_type:
        queryset = queryset.filter(secretariat__type_id=secretariat_type)

    secretariat_id = request.query_params.get('secretariat')
    if secretariat_id and request.user.role in ('INJS_ADMIN', 'CHEF_INJS_ADMIN', 'DIRECTION', 'ARCHIVE'):
        queryset = queryset.filter(secretariat_id=secretariat_id)

    vague_filter = request.query_params.get('vague')
    if vague_filter:
        queryset = queryset.filter(vague__iexact=vague_filter)

    formation_id_filter = request.query_params.get('formation_id')
    if formation_id_filter:
        queryset = queryset.filter(formation_id=formation_id_filter)

    annee_filter = request.query_params.get('annee')
    if annee_filter:
        try:
            annee_val = int(annee_filter)
            queryset = queryset.filter(
                Q(date_debut__year=annee_val) | Q(date_fin__year=annee_val)
            ).distinct()
        except (ValueError, TypeError):
            pass

    groupe_param = request.query_params.get('groupe')
    if groupe_param:
        groupe_normalise = _normalize_groupe_value(groupe_param)
        if groupe_normalise:
            matching_ids = [
                mid
                for mid, g in queryset.values_list('id', 'groupe')
                if _normalize_groupe_value(g) == groupe_normalise
            ]
            queryset = queryset.filter(id__in=matching_ids)

    actives_only = request.query_params.get('actives')
    if actives_only == 'true':
        queryset = queryset.filter(statut__in=['PLANIFIEE', 'EN_COURS'])

    seance_en_cours_only = request.query_params.get('seance_en_cours')
    if seance_en_cours_only == 'true':
        queryset = queryset.filter(
            sessions__demarree_le__isnull=False,
            sessions__terminee_le__isnull=True,
        ).distinct()

    date_mode = request.query_params.get('date_mode')
    date_value = request.query_params.get('date')
    if date_mode in ('today', 'date'):
        target_date = timezone.localdate()
        if date_mode == 'date':
            if not date_value:
                return None, Response({'detail': 'Le paramètre date est requis pour date_mode=date.'}, status=400)
            try:
                target_date = datetime.strptime(date_value, '%Y-%m-%d').date()
            except ValueError:
                return None, Response({'detail': 'Format de date invalide. Utilisez YYYY-MM-DD.'}, status=400)
        queryset = queryset.filter(sessions__date_journee=target_date).distinct()

    queryset = queryset.order_by(
        F('date_debut').asc(nulls_last=True),
        F('date_fin').asc(nulls_last=True),
        'id',
    )
    return queryset, None


def _serialize_module_list_item(module, *, nb_participants=0, nb_presents=0):
    formation = module.formation
    superviseur = module.superviseur
    creee_par = module.creee_par
    return {
        'id': formation.id,
        'module_id': module.id,
        'numero_formation': formation.numero_formation,
        'formation': formation.formation,
        'intitule': formation.formation,
        'module': module.intitule,
        'statut': module.statut,
        'grade': module.grade,
        'categorie': module.grade,
        'groupe': module.groupe,
        'vague': module.vague,
        'site': (module.site.nom if module.site else (module.site_legacy or '')),
        'site_id': module.site_id,
        'batiment': module.batiment,
        'salle': module.salle,
        'date_debut': module.date_debut,
        'date_fin': module.date_fin,
        'date_debut_prevue': module.date_debut,
        'date_fin_prevue': module.date_fin,
        'secretariat': module.secretariat_id,
        'secretariat_nom': module.secretariat.nom if module.secretariat else None,
        'secretariat_type': module.secretariat.type_id if module.secretariat else None,
        'secretariat_type_libelle': (
            module.secretariat.type.libelle if module.secretariat and module.secretariat.type else None
        ),
        'superviseur': superviseur.id if superviseur else None,
        'superviseur_nom': superviseur.get_full_name() if superviseur else None,
        'creee_par': creee_par.id if creee_par else None,
        'creee_par_nom': creee_par.get_full_name() if creee_par else None,
        'nb_participants': nb_participants,
        'nb_presents': nb_presents,
        'archived': module.archived,
        'created_at': formation.created_at,
        'updated_at': formation.updated_at,
    }


def _module_participant_counts(module_ids):
    if not module_ids:
        return {}
    rows = (
        ModuleParticipant.objects.filter(module_id__in=module_ids)
        .values('module_id')
        .annotate(c=Count('participant', distinct=True))
    )
    return {row['module_id']: row['c'] for row in rows}


def _moyenne_from_valeurs_map(valeurs_by_colonne):
    normalized = []
    for val in valeurs_by_colonne.values():
        if val and val.note is not None:
            note_max = float(val.colonne.note_max or 20)
            if note_max <= 0:
                note_max = 20.0
            normalized.append(float(val.note) * 20.0 / note_max)
    if not normalized:
        return None
    return round(sum(normalized) / len(normalized), 2)


def _batch_resume_module_participants(module, inscriptions, valeurs_map, criteres):
    """Résumés notes/présence pour tous les auditeurs d'un module (requêtes groupées)."""
    from django.db.models import Sum
    from suiviEvaluation.models import MoyenneModule
    from suiviEvaluation.services import est_admissible
    from formations.duree_prevue_resolve import resolve_module_volume_contractuel_heures

    participant_ids = [mp.participant_id for mp in inscriptions]
    if not participant_ids:
        return {}

    moyennes_map = {
        mm.participant_id: mm
        for mm in MoyenneModule.objects.filter(module=module, participant_id__in=participant_ids)
    }
    presence_minutes = {
        row['participant_id']: float(row['total'] or 0)
        for row in Pointage.objects.filter(
            session__module=module,
            participant_id__in=participant_ids,
            duree_presence_minutes__isnull=False,
        ).values('participant_id').annotate(total=Sum('duree_presence_minutes'))
    }
    heures_prevues_cache = {}
    default_heures_prevues, _ = resolve_module_volume_contractuel_heures(module)

    resumes = {}
    for mp in inscriptions:
        pid = mp.participant_id
        mm = moyennes_map.get(pid)
        if mm is not None:
            moyenne = float(mm.moyenne) if mm.moyenne is not None else None
            heures_presence = float(mm.heures_presence)
            heures_prevues = float(mm.heures_prevues)
            taux = float(mm.taux_presence) if mm.taux_presence is not None else None
        else:
            moyenne = _moyenne_from_valeurs_map(valeurs_map.get(pid, {}))
            participant = mp.participant
            cat_key = (getattr(participant, 'categorie', None) or '').strip() or None
            if cat_key not in heures_prevues_cache:
                heures_prevues_cache[cat_key], _ = resolve_module_volume_contractuel_heures(
                    module, participant=participant,
                )
            heures_prevues = heures_prevues_cache[cat_key] or default_heures_prevues
            minutes = presence_minutes.get(pid, 0)
            cap_minutes = heures_prevues * 60 if heures_prevues > 0 else 0
            if cap_minutes > 0:
                minutes = min(minutes, cap_minutes)
            heures_presence = round(minutes / 60.0, 2)
            taux = round((heures_presence / heures_prevues) * 100, 2) if heures_prevues > 0 else None

        resumes[pid] = {
            'moyenne': moyenne,
            'heures_presence': heures_presence,
            'heures_prevues': heures_prevues,
            'taux_presence': taux,
            'admissible': est_admissible(moyenne, taux, criteres),
        }
    return resumes


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def formation_list_api(request):
    """
    List modules (une ligne par module) with optional filtering.
    Query params: statut, search, module, categorie, grade, secretariat_type, vague, groupe, actives, page, page_size, date_mode, date
    """
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    page = int(request.query_params.get('page', 1))
    page_size = int(request.query_params.get('page_size', 50))

    queryset, err = _filtered_modules_queryset(request)
    if err:
        return err

    today = timezone.localdate()
    queryset = queryset.annotate(
        _nb_participants=Count('module_participants', distinct=True),
        _nb_presents=Count(
            'sessions__pointages__participant',
            filter=Q(
                sessions__pointages__date_journee=today,
                sessions__pointages__participant_id__isnull=False,
            ),
            distinct=True,
        ),
    )

    total_count = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    modules_page = queryset[start:end]

    results = [
        _serialize_module_list_item(
            m,
            nb_participants=m._nb_participants,
            nb_presents=m._nb_presents,
        )
        for m in modules_page
    ]

    return Response({
        'results': results,
        'count': total_count,
        'total_pages': (total_count + page_size - 1) // page_size,
        'current_page': page,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanListParticipants])
def participant_list_api(request):
    """
    List participants with optional search.
    Query params:
    - search: recherche textuelle (nom, prenom, matricule, email, concours, grade, groupe, secretariat)
    - secretariat: filtre par nom/type de secretariat
    - grade: filtre sur le grade
    - groupe: filtre sur le groupe
    - type_concours: filtre sur le type de concours
    - page: pagination
    """
    page = int(request.query_params.get('page', 1))
    page_size = int(request.query_params.get('page_size', 50))

    queryset = participants_queryset_for_user(request.user)

    scoped_queryset = queryset
    raw_groupes = (
        scoped_queryset.exclude(groupe__isnull=True)
        .exclude(groupe='')
        .values_list('groupe', flat=True)
    )
    groupes_normalises = sorted(
        {g for g in (_normalize_groupe_value(v) for v in raw_groupes) if g},
        key=_groupe_sort_key,
    )
    filter_options = {
        'secretariats': list(
            scoped_queryset.exclude(secretariat__nom__isnull=True)
            .exclude(secretariat__nom='')
            .values_list('secretariat__nom', flat=True)
            .distinct()
            .order_by('secretariat__nom')
        ),
        'grades': list(
            scoped_queryset.exclude(grade__isnull=True)
            .exclude(grade='')
            .values_list('grade', flat=True)
            .distinct()
            .order_by('grade')
        ),
        'groupes': groupes_normalises,
        'types_concours': list(
            scoped_queryset.exclude(type_concours__isnull=True)
            .exclude(type_concours='')
            .values_list('type_concours', flat=True)
            .distinct()
            .order_by('type_concours')
        ),
    }

    # Apply search
    search = request.query_params.get('search')
    if search:
        queryset = queryset.filter(
            Q(nom__icontains=search) |
            Q(prenom__icontains=search) |
            Q(matricule__icontains=search) |
            Q(email__icontains=search) |
            Q(type_concours__icontains=search) |
            Q(libelle_concours__icontains=search) |
            Q(grade__icontains=search) |
            Q(groupe__icontains=search) |
            Q(secretariat__nom__icontains=search) |
            Q(secretariat__type__libelle__icontains=search)
        )

    secretariat = request.query_params.get('secretariat')
    if secretariat:
        queryset = queryset.filter(
            Q(secretariat__nom__icontains=secretariat) |
            Q(secretariat__type__libelle__icontains=secretariat)
        )

    grade = request.query_params.get('grade')
    if grade:
        queryset = queryset.filter(grade__icontains=grade)

    groupe = request.query_params.get('groupe')
    if groupe:
        groupe_normalise = _normalize_groupe_value(groupe)
        matching_ids = [
            participant_id
            for participant_id, participant_groupe in queryset.values_list('id', 'groupe')
            if _normalize_groupe_value(participant_groupe) == groupe_normalise
        ]
        queryset = queryset.filter(id__in=matching_ids)

    type_concours = request.query_params.get('type_concours')
    if type_concours:
        queryset = queryset.filter(type_concours__icontains=type_concours)

    sexe = request.query_params.get('sexe')
    if sexe:
        queryset = queryset.filter(sexe=sexe)

    vague = request.query_params.get('vague')
    if vague:
        queryset = queryset.filter(vague__iexact=vague)

    queryset = queryset.order_by('nom', 'prenom')
    
    # Pagination
    total_count = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    participants = queryset[start:end]
    
    serializer = ParticipantSerializer(participants, many=True)
    
    return Response({
        'results': serializer.data,
        'count': total_count,
        'total_pages': (total_count + page_size - 1) // page_size,
        'current_page': page,
        'filter_options': filter_options,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, CanListParticipants])
def participant_formations_api(request, pk):
    """Return all modules a participant is enrolled in (with their formation)."""
    participant = participant_accessible(request.user, pk)
    if not participant:
        return Response({'error': 'Participant introuvable ou hors périmètre.'}, status=404)

    inscriptions = (
        ModuleParticipant.objects.filter(participant=participant)
        .select_related('module__formation', 'module__secretariat', 'module__site')
        .order_by('-inscrit_le')
    )

    data = []
    for ins in inscriptions:
        m = ins.module
        data.append({
            'id': m.id,
            'formation_id': m.formation_id,
            'formation': m.formation.formation if m.formation else '',
            'module': m.intitule,
            'grade': m.grade,
            'groupe': m.groupe,
            'vague': m.vague,
            'site': (m.site.nom if m.site else (m.site_legacy or '')),
            'site_id': m.site_id,
            'batiment': m.batiment,
            'salle': m.salle,
            'date_debut': m.date_debut,
            'date_fin': m.date_fin,
            'statut': m.statut,
            'secretariat_nom': m.secretariat.nom if m.secretariat else None,
            'inscrit_le': ins.inscrit_le.isoformat() if ins.inscrit_le else None,
            'duree_prevue_heures': float(m.duree_prevue_heures or 0),
        })
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def formateur_list_api(request):
    """
    List formateurs with optional search.
    Query params:
    - search: search in name
    - page: pagination
    - module_id: si fourni, indique assignable/conflit_assignation pour ce module
    """
    page = int(request.query_params.get('page', 1))
    page_size = int(request.query_params.get('page_size', 50))

    target_module = None
    module_id = request.query_params.get('module_id')
    if module_id:
        try:
            target_module = Module.objects.select_related('formation').get(pk=int(module_id))
        except (Module.DoesNotExist, ValueError, TypeError):
            return Response({'detail': 'Module introuvable.'}, status=404)
        if not formation_accessible(request.user, target_module.formation_id):
            return Response({'detail': 'Accès interdit.'}, status=403)

    queryset = formateurs_queryset_for_user(request.user)

    # Apply search
    search = request.query_params.get('search')
    if search:
        queryset = queryset.filter(
            Q(nom__icontains=search) |
            Q(prenom__icontains=search) |
            Q(specialite__icontains=search)
        )

    queryset = queryset.order_by('nom', 'prenom')

    # Pagination
    total_count = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    formateurs = queryset[start:end]

    serializer = FormateurSerializer(formateurs, many=True, context={'request': request})
    results = serializer.data
    if target_module:
        enriched = []
        for row, formateur in zip(results, formateurs):
            conflit = check_formateur_groupe_jour_conflict(formateur, target_module)
            row['assignable'] = conflit is None
            row['conflit_assignation'] = conflit
            enriched.append(row)
        results = enriched

    return Response({
        'results': results,
        'count': total_count,
        'total_pages': (total_count + page_size - 1) // page_size,
        'current_page': page,
    })


def _finance_session_slot_minutes(session):
    """Créneau EDT d'une séance (minutes) — plafond du réalisé, pas le planifié module."""
    from .volume_horaire import _session_prevu_minutes

    return round(float(_session_prevu_minutes(session) or 0), 1)


def _finance_module_planned_minutes(module, all_sessions, *, date_debut=None, date_fin=None, categorie_code=None):
    """Volume planifié = duree_prevue_heures contractuelle si renseignée, sinon Σ créneaux EDT.

    Si categorie_code est fourni, utilise le volume horaire spécifique à cette catégorie.
    Sinon, utilise la catégorie majoritaire des participants."""
    from .volume_horaire import module_planned_minutes_for_period

    sessions_in_period = [
        s for s in (all_sessions or [])
        if _finance_session_in_range(s, date_debut, date_fin)
    ]
    return round(module_planned_minutes_for_period(
        module,
        len(sessions_in_period),
        len(all_sessions or []),
        sessions_in_period,
        categorie_code,
    ), 1)


def _session_duration_minutes(session):
    """Alias conservé : créneau EDT (ne pas utiliser pour le planifié module)."""
    return _finance_session_slot_minutes(session)


def _finance_cap_module_realized(realized_minutes, planned_minutes):
    """Le réalisé module ne peut pas dépasser le planifié (Σ créneaux EDT de la période)."""
    realized = float(realized_minutes or 0)
    planned = float(planned_minutes or 0)
    if planned <= 0:
        return round(realized, 1)
    return round(min(realized, planned), 1)


def _finance_realized_minutes(realized_minutes, planned_minutes):
    """Temps réalisé retenu : 0 si pas d'horaire planifié, sinon plafonné à la durée de la séance."""
    planned = float(planned_minutes or 0)
    if planned <= 0:
        return 0.0
    return round(min(float(realized_minutes or 0), planned), 1)


# Alias conservé pour les imports existants
_finance_realized_for_taux = _finance_realized_minutes


def _finance_taux_realisation_pct(realized_for_taux_total, planned_for_taux_total):
    """Taux de réalisation (0–100 %), hors séances sans horaire, présence plafonnée par séance."""
    planned = float(planned_for_taux_total or 0)
    if planned <= 0:
        return 0.0
    realized = float(realized_for_taux_total or 0)
    return round(min((realized / planned) * 100, 100.0), 1)


def _finance_allowed_roles():
    return {'FINANCE', 'DIRECTION', 'ARCHIVE', 'ADMIN'}


def _check_finance_access(request):
    return request.user.is_authenticated and request.user.role in _finance_allowed_roles()


def _finance_normalize_label(label):
    """Normalise un libellé de formation pour la recherche de tarif."""
    s = (label or '').strip().lower()
    return re.sub(r'\s+', ' ', s)


def _finance_build_prix_map():
    """Dict intitulé formation normalisé → tarif horaire RefFormation."""
    prix_map = {}
    for ref in RefFormation.objects.exclude(prix_heure_realisee__isnull=True):
        key = _finance_normalize_label(ref.intitule)
        if key:
            prix_map[key] = float(ref.prix_heure_realisee or 0)
    return prix_map


def _finance_formation_label_candidates(formation_label=None, module_obj=None):
    """Libellés possibles pour retrouver le tarif d'une formation."""
    labels = []
    for raw in (formation_label,):
        if raw and str(raw).strip():
            labels.append(str(raw).strip())
    if module_obj:
        if getattr(module_obj, 'cycle', None) and str(module_obj.cycle).strip():
            labels.append(str(module_obj.cycle).strip())
        if module_obj.formation_id and module_obj.formation:
            f = (module_obj.formation.formation or '').strip()
            if f:
                labels.append(f)
    seen = set()
    ordered = []
    for lbl in labels:
        key = _finance_normalize_label(lbl)
        if key and key not in seen:
            seen.add(key)
            ordered.append(lbl)
    return ordered


def _finance_prix_heure_for_formation(formation_label, prix_map=None, module_obj=None):
    if prix_map is None:
        prix_map = _finance_build_prix_map()
    for raw in _finance_formation_label_candidates(formation_label, module_obj):
        key = _finance_normalize_label(raw)
        if key and key in prix_map:
            return prix_map[key]
    return 0.0


def _finance_module_formation_label(module_obj):
    if not module_obj:
        return ''
    if module_obj.formation_id and module_obj.formation:
        label = (module_obj.formation.formation or '').strip()
        if label:
            return label
    return (module_obj.cycle or '').strip()


def _finance_resolve_prix_heure(formation_label, *, prix_heure_override=None, prix_map=None, module_obj=None):
    if prix_heure_override is not None:
        return float(prix_heure_override or 0)
    return _finance_prix_heure_for_formation(
        formation_label, prix_map=prix_map, module_obj=module_obj,
    )


def _finance_montant_from_minutes(minutes, prix_heure):
    return round((float(minutes or 0) / 60) * float(prix_heure or 0), 2)


def _finance_session_in_range(session, date_debut, date_fin):
    """Filtre une séance par ``date_journee`` (intervalle inclusif)."""
    if date_debut is None and date_fin is None:
        return True
    d = session.date_journee
    if not d:
        return False
    if date_debut and d < date_debut:
        return False
    if date_fin and d > date_fin:
        return False
    return True


def _parse_finance_date_range(request):
    """
    Analyse les paramètres de période finance.

    Query params:
    - ``preset`` : ``tout`` | ``mois`` | ``trimestre`` | ``annee`` | ``custom``
    - ``mois`` : ``YYYY-MM`` (si preset=mois)
    - ``annee`` : ``YYYY`` (si preset=annee)
    - ``trimestre`` : ``YYYY-Q1`` … ``YYYY-Q4`` (si preset=trimestre)
    - ``date_debut``, ``date_fin`` : ``YYYY-MM-DD`` (si preset=custom ou dates seules)

    Retourne un dict avec ``error``, ``detail``, ``date_debut``, ``date_fin``, ``meta``.
    """
    preset = (request.query_params.get('preset') or '').strip().lower()
    date_debut_s = (request.query_params.get('date_debut') or '').strip()
    date_fin_s = (request.query_params.get('date_fin') or '').strip()
    today = timezone.localdate()

    if not preset and not date_debut_s and not date_fin_s:
        preset = 'tout'
    elif not preset and date_debut_s and date_fin_s:
        preset = 'custom'

    def _err(detail):
        return {'error': True, 'detail': detail, 'date_debut': None, 'date_fin': None, 'meta': {}}

    try:
        if preset == 'tout':
            return {
                'error': False,
                'detail': None,
                'date_debut': None,
                'date_fin': None,
                'meta': {
                    'preset': 'tout',
                    'type': 'tout',
                    'label': 'Toutes les périodes',
                    'description': (
                        'Cumul de toutes les séances enregistrées (aucun filtre de dates).'
                    ),
                },
            }

        if preset == 'mois':
            mois = (request.query_params.get('mois') or today.strftime('%Y-%m')).strip()
            parts = mois.split('-')
            if len(parts) != 2:
                return _err('Paramètre mois invalide (format YYYY-MM attendu).')
            year, month = int(parts[0]), int(parts[1])
            last_day = calendar.monthrange(year, month)[1]
            d0, d1 = date(year, month, 1), date(year, month, last_day)
            return {
                'error': False,
                'detail': None,
                'date_debut': d0,
                'date_fin': d1,
                'meta': {
                    'preset': 'mois',
                    'mois': mois,
                    'type': 'intervalle',
                    'label': f"Mois de {d0.strftime('%m/%Y')}",
                    'description': 'Séances dont la date est dans le mois sélectionné.',
                },
            }

        if preset == 'trimestre':
            trimestre = (request.query_params.get('trimestre') or '').strip()
            if trimestre and '-Q' in trimestre.upper():
                year_s, q_s = trimestre.upper().split('-Q', 1)
                year, q = int(year_s), int(q_s)
            else:
                year = int(request.query_params.get('annee') or today.year)
                q = (today.month - 1) // 3 + 1
            if q not in (1, 2, 3, 4):
                return _err('Trimestre invalide (1 à 4).')
            start_month = (q - 1) * 3 + 1
            end_month = start_month + 2
            last_day = calendar.monthrange(year, end_month)[1]
            d0 = date(year, start_month, 1)
            d1 = date(year, end_month, last_day)
            trimestre_key = f'{year}-Q{q}'
            return {
                'error': False,
                'detail': None,
                'date_debut': d0,
                'date_fin': d1,
                'meta': {
                    'preset': 'trimestre',
                    'trimestre': trimestre_key,
                    'type': 'intervalle',
                    'label': f'Trimestre {q} — {year}',
                    'description': 'Séances dont la date est dans le trimestre sélectionné.',
                },
            }

        if preset == 'annee':
            year = int(request.query_params.get('annee') or today.year)
            d0, d1 = date(year, 1, 1), date(year, 12, 31)
            return {
                'error': False,
                'detail': None,
                'date_debut': d0,
                'date_fin': d1,
                'meta': {
                    'preset': 'annee',
                    'annee': year,
                    'type': 'intervalle',
                    'label': f'Année {year}',
                    'description': 'Séances dont la date est dans l\'année sélectionnée.',
                },
            }

        if preset == 'custom':
            if not date_debut_s or not date_fin_s:
                return _err('date_debut et date_fin sont requis pour une période personnalisée.')
            d0 = date.fromisoformat(date_debut_s)
            d1 = date.fromisoformat(date_fin_s)
            if d0 > d1:
                return _err('La date de début doit être antérieure ou égale à la date de fin.')
            return {
                'error': False,
                'detail': None,
                'date_debut': d0,
                'date_fin': d1,
                'meta': {
                    'preset': 'custom',
                    'type': 'intervalle',
                    'label': 'Période personnalisée',
                    'description': 'Séances dont la date est dans l\'intervalle choisi.',
                },
            }

        return _err(f'Preset inconnu : {preset}.')
    except ValueError:
        return _err('Format de date invalide (attendu : YYYY-MM-DD ou YYYY-MM).')


def _finance_periode_payload(date_debut, date_fin, meta, date_min=None, date_max=None):
    """Construit la réponse ``periode`` pour le frontend."""
    if date_debut is None and date_fin is None:
        if date_min and date_max:
            plabel = f"Du {date_min.strftime('%d/%m/%Y')} au {date_max.strftime('%d/%m/%Y')}"
        elif date_min:
            plabel = f"Depuis le {date_min.strftime('%d/%m/%Y')}"
        else:
            plabel = 'Aucune séance enregistrée'
        return {
            **meta,
            'date_debut': date_min.isoformat() if date_min else None,
            'date_fin': date_max.isoformat() if date_max else None,
            'periode_label': plabel,
            'filtre_actif': False,
        }
    plabel = f"Du {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}"
    payload = {
        **meta,
        'date_debut': date_debut.isoformat(),
        'date_fin': date_fin.isoformat(),
        'periode_label': plabel,
        'filtre_actif': True,
    }
    if date_min and date_max:
        payload['donnees_effectives_debut'] = date_min.isoformat()
        payload['donnees_effectives_fin'] = date_max.isoformat()
    return payload


def _finance_secretariat_id_from_request(request):
    raw = (request.query_params.get('secretariat_id') or request.query_params.get('secretariat') or '').strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _finance_filter_formateur_queryset(queryset, secretariat_id):
    if not secretariat_id:
        return queryset
    return queryset.filter(
        Q(secretariats__id=secretariat_id) |
        Q(modules_assignes__module__secretariat_id=secretariat_id) |
        Q(modules__secretariat_id=secretariat_id),
    ).distinct()


def _finance_previous_period(date_debut, date_fin, meta):
    """Calcule la période immédiatement précédente (pour comparaison dashboard)."""
    preset = (meta or {}).get('preset')
    if preset == 'tout':
        return None
    today = timezone.localdate()
    try:
        if preset == 'mois':
            mois = (meta or {}).get('mois') or today.strftime('%Y-%m')
            year, month = [int(x) for x in mois.split('-')]
            if month == 1:
                year, month = year - 1, 12
            else:
                month -= 1
            last_day = calendar.monthrange(year, month)[1]
            d0, d1 = date(year, month, 1), date(year, month, last_day)
            prev_mois = f'{year}-{month:02d}'
            return {
                'error': False,
                'date_debut': d0,
                'date_fin': d1,
                'meta': {
                    'preset': 'mois',
                    'mois': prev_mois,
                    'type': 'intervalle',
                    'label': f"Mois de {d0.strftime('%m/%Y')}",
                    'description': 'Période de comparaison (mois précédent).',
                },
            }
        if preset == 'trimestre':
            trimestre = (meta or {}).get('trimestre') or f'{today.year}-Q{(today.month - 1) // 3 + 1}'
            year_s, q_s = trimestre.upper().split('-Q', 1)
            year, q = int(year_s), int(q_s)
            if q == 1:
                year, q = year - 1, 4
            else:
                q -= 1
            start_month = (q - 1) * 3 + 1
            end_month = start_month + 2
            last_day = calendar.monthrange(year, end_month)[1]
            d0 = date(year, start_month, 1)
            d1 = date(year, end_month, last_day)
            return {
                'error': False,
                'date_debut': d0,
                'date_fin': d1,
                'meta': {
                    'preset': 'trimestre',
                    'trimestre': f'{year}-Q{q}',
                    'type': 'intervalle',
                    'label': f'Trimestre {q} — {year}',
                    'description': 'Période de comparaison (trimestre précédent).',
                },
            }
        if preset == 'annee':
            year = int((meta or {}).get('annee') or today.year) - 1
            d0, d1 = date(year, 1, 1), date(year, 12, 31)
            return {
                'error': False,
                'date_debut': d0,
                'date_fin': d1,
                'meta': {
                    'preset': 'annee',
                    'annee': year,
                    'type': 'intervalle',
                    'label': f'Année {year}',
                    'description': 'Période de comparaison (année précédente).',
                },
            }
        if preset == 'custom' and date_debut and date_fin:
            span_days = (date_fin - date_debut).days
            prev_fin = date_debut - timedelta(days=1)
            prev_debut = prev_fin - timedelta(days=span_days)
            return {
                'error': False,
                'date_debut': prev_debut,
                'date_fin': prev_fin,
                'meta': {
                    'preset': 'custom',
                    'type': 'intervalle',
                    'label': 'Période précédente (même durée)',
                    'description': 'Intervalle de même longueur, immédiatement avant la période sélectionnée.',
                },
            }
    except (ValueError, TypeError):
        return None
    return None


def _finance_kpis_from_rows(rows):
    """Agrège les KPI dashboard à partir des lignes rapport finance."""
    total_formateurs = len(rows)
    formateurs_actifs = sum(1 for r in rows if (r.get('sessions_count') or 0) > 0)
    formateurs_inactifs = total_formateurs - formateurs_actifs
    total_sessions = sum(int(r.get('sessions_count') or 0) for r in rows)
    total_duree_minutes = round(sum(float(r.get('total_duree_minutes') or 0) for r in rows), 1)
    total_duree_heures = round(total_duree_minutes / 60, 2)
    total_duree_realisee_minutes = round(
        sum(float(r.get('total_duree_realisee_minutes') or 0) for r in rows), 1,
    )
    total_duree_realisee_heures = round(total_duree_realisee_minutes / 60, 2)
    total_montant_realise = round(sum(float(r.get('montant_total_realise') or 0) for r in rows), 2)
    taux_planned = sum(
        float((r.get('statistiques') or {}).get('taux_planned_minutes') or 0) for r in rows
    )
    taux_realized_capped = sum(
        float((r.get('statistiques') or {}).get('taux_realized_capped_minutes') or 0) for r in rows
    )
    taux_realisation_global = _finance_taux_realisation_pct(taux_realized_capped, taux_planned)
    sessions_avec_pointage = sum(
        int((r.get('statistiques') or {}).get('sessions_avec_pointage') or 0) for r in rows
    )
    tarifs_appliques = set()
    for r in rows:
        for mod in r.get('modules') or []:
            ph = mod.get('prix_heure_realisee')
            if ph is not None and float(ph) > 0:
                tarifs_appliques.add(float(ph))
    prix_heure_moyen_effectif = round(
        total_montant_realise / (total_duree_realisee_minutes / 60), 2,
    ) if total_duree_realisee_minutes > 0 else 0
    return {
        'total_formateurs': total_formateurs,
        'formateurs_actifs': formateurs_actifs,
        'formateurs_inactifs': formateurs_inactifs,
        'total_sessions': total_sessions,
        'sessions_avec_pointage': sessions_avec_pointage,
        'total_duree_minutes': total_duree_minutes,
        'total_duree_heures': total_duree_heures,
        'total_duree_realisee_minutes': total_duree_realisee_minutes,
        'total_duree_realisee_heures': total_duree_realisee_heures,
        'total_montant_realise': total_montant_realise,
        'prix_heure_realisee': prix_heure_moyen_effectif if total_duree_realisee_minutes > 0 else None,
        'tarifs_variables': True,
        'tarifs_appliques': sorted(tarifs_appliques),
        'prix_heure_moyen_effectif': prix_heure_moyen_effectif,
        'taux_realisation_global_pct': taux_realisation_global,
        'moyenne_heures_par_formateur': round(
            (total_duree_heures / formateurs_actifs), 2,
        ) if formateurs_actifs > 0 else 0,
        'moyenne_heures_realisees_par_formateur': round(
            (total_duree_realisee_heures / formateurs_actifs), 2,
        ) if formateurs_actifs > 0 else 0,
        'moyenne_montant_par_formateur_actif': round(
            (total_montant_realise / formateurs_actifs), 2,
        ) if formateurs_actifs > 0 else 0,
    }


def _finance_dashboard_modules_breakdown(rows, *, date_debut, date_fin, secretariat_id=None, additional_modules=None):
    """Ventilation dashboard par module (planifié unique, réalisé/coût cumulés formateurs).

    Si additional_modules est fourni, inclut aussi ces modules sans formateur.
    """
    meta_by_id = {}
    realise_by_id = {}
    montant_by_id = {}
    taux_planned_by_id = {}
    taux_realized_by_id = {}

    for row in rows:
        for mod in row.get('modules') or []:
            mid = mod.get('module_id')
            if not mid:
                continue
            if mid not in meta_by_id:
                meta_by_id[mid] = {
                    'module_id': mid,
                    'module_intitule': mod.get('module_intitule') or '',
                    'formation_intitule': mod.get('formation_intitule') or '',
                    'grade': mod.get('grade') or '',
                    'groupe': mod.get('groupe') or '',
                    'secretariat_nom': mod.get('secretariat_nom') or '',
                    'prix_heure_realisee': mod.get('prix_heure_realisee'),
                }
            realise_by_id[mid] = realise_by_id.get(mid, 0.0) + float(mod.get('total_duree_realisee_minutes') or 0)
            montant_by_id[mid] = montant_by_id.get(mid, 0.0) + float(mod.get('montant_realise') or 0)
            taux_planned_by_id[mid] = taux_planned_by_id.get(mid, 0.0) + float(mod.get('taux_planned_minutes') or 0)
            taux_realized_by_id[mid] = taux_realized_by_id.get(mid, 0.0) + float(
                mod.get('taux_realized_capped_minutes') or 0
            )

    # Ajouter les modules sans formateur (pas de réalisé, pas de montant)
    if additional_modules:
        for mod in additional_modules:
            mid = mod.get('module_id')
            if not mid or mid in meta_by_id:
                continue
            meta_by_id[mid] = {
                'module_id': mid,
                'module_intitule': mod.get('module_intitule') or '',
                'formation_intitule': mod.get('formation_intitule') or '',
                'grade': mod.get('grade') or '',
                'groupe': mod.get('groupe') or '',
                'secretariat_nom': mod.get('secretariat_nom') or '',
                'prix_heure_realisee': None,  # Pas de tarif car pas de formateur
            }
            # Pas de réalisé, pas de montant pour les modules sans formateur
            realise_by_id[mid] = 0.0
            montant_by_id[mid] = 0.0
            taux_planned_by_id[mid] = 0.0
            taux_realized_by_id[mid] = 0.0

    if not meta_by_id:
        return []

    prix_map = _finance_build_prix_map()
    module_ids = list(meta_by_id.keys())
    modules_by_id = {
        m.id: m for m in Module.objects.filter(id__in=module_ids).select_related(
            'formation', 'secretariat', 'ref_module',
        )
    }
    sessions_by_module = {}
    for session in SessionModule.objects.filter(module_id__in=module_ids).order_by('date_journee', 'numero'):
        sessions_by_module.setdefault(session.module_id, []).append(session)

    results = []
    for mid in module_ids:
        mod_obj = modules_by_id.get(mid)
        if secretariat_id and (not mod_obj or mod_obj.secretariat_id != secretariat_id):
            continue
        module_sessions = sessions_by_module.get(mid, [])
        sessions_in_period = [
            s for s in module_sessions
            if _finance_session_in_range(s, date_debut, date_fin)
        ]
        sessions_count = len(sessions_in_period)
        if not sessions_count:
            continue
        planned = _finance_module_planned_minutes(
            mod_obj, module_sessions, date_debut=date_debut, date_fin=date_fin,
        )
        meta = meta_by_id[mid]
        realized = _finance_cap_module_realized(realise_by_id.get(mid, 0.0), planned)
        prix_raw = meta.get('prix_heure_realisee')
        if prix_raw is not None:
            prix = float(prix_raw)
        elif mod_obj:
            prix = _finance_resolve_prix_heure(
                _finance_module_formation_label(mod_obj),
                prix_map=prix_map,
                module_obj=mod_obj,
            )
        else:
            prix = 0.0
        prix_display = prix if prix > 0 else None
        montant_prevu = _finance_montant_from_minutes(planned, prix)
        montant = (
            _finance_montant_from_minutes(realized, prix)
            if prix_display is not None
            else round(montant_by_id.get(mid, 0.0), 2)
        )
        taux = _finance_taux_realisation_pct(realized, planned)
        results.append({
            **meta,
            'prix_heure_realisee': prix_display,
            'sessions_count': sessions_count,
            'total_duree_minutes': round(planned, 1),
            'total_duree_heures': round(planned / 60, 2) if planned else 0,
            'total_duree_realisee_minutes': realized,
            'total_duree_realisee_heures': round(realized / 60, 2) if realized else 0,
            'taux_realisation_pct': taux,
            'montant_prevu': montant_prevu,
            'montant_realise': montant,
        })

    return sorted(results, key=lambda m: m.get('module_intitule') or '')


def _finance_total_montant_prevu_from_breakdown(breakdown):
    """Coût prévisionnel global = Σ (volume planifié module × tarif cycle)."""
    return round(sum(float(m.get('montant_prevu') or 0) for m in (breakdown or [])), 2)


def _finance_kpis_from_modules_breakdown(kpis, breakdown):
    """Aligne les KPI volume/coût sur la ventilation dédupliquée par module.

    Les lignes formateurs comptent le planifié une fois par formateur rattaché ;
    le détail modal et les volumes pédagogiques doivent compter chaque module une seule fois.
    """
    breakdown = breakdown or []
    planned = round(sum(float(m.get('total_duree_minutes') or 0) for m in breakdown), 1)
    realized = round(sum(float(m.get('total_duree_realisee_minutes') or 0) for m in breakdown), 1)
    montant_prevu = _finance_total_montant_prevu_from_breakdown(breakdown)
    montant_realise = round(sum(float(m.get('montant_realise') or 0) for m in breakdown), 2)
    sessions_count = sum(int(m.get('sessions_count') or 0) for m in breakdown)

    kpis = dict(kpis)
    kpis['total_duree_minutes'] = planned
    kpis['total_duree_heures'] = round(planned / 60, 2) if planned else 0
    kpis['total_duree_realisee_minutes'] = realized
    kpis['total_duree_realisee_heures'] = round(realized / 60, 2) if realized else 0
    kpis['total_montant_prevu'] = montant_prevu
    kpis['total_montant_realise'] = montant_realise
    kpis['total_sessions'] = sessions_count
    kpis['taux_realisation_global_pct'] = _finance_taux_realisation_pct(realized, planned)
    if kpis.get('formateurs_actifs', 0) > 0:
        kpis['moyenne_heures_par_formateur'] = round(
            kpis['total_duree_heures'] / kpis['formateurs_actifs'], 2,
        )
        kpis['moyenne_heures_realisees_par_formateur'] = round(
            kpis['total_duree_realisee_heures'] / kpis['formateurs_actifs'], 2,
        )
        kpis['moyenne_montant_par_formateur_actif'] = round(
            montant_realise / kpis['formateurs_actifs'], 2,
        )
    return kpis


def _finance_kpi_evolution(current, previous):
    """Écarts absolus et relatifs entre deux jeux de KPI."""
    keys = (
        'total_montant_realise',
        'total_montant_prevu',
        'total_duree_realisee_minutes',
        'total_duree_minutes',
        'total_sessions',
        'formateurs_actifs',
        'taux_realisation_global_pct',
    )
    evolution = {}
    for key in keys:
        c = float(current.get(key) or 0)
        p = float(previous.get(key) or 0)
        delta = round(c - p, 2)
        evolution[key] = {
            'delta': delta,
            'pourcent': round((delta / p) * 100, 1) if p else (100.0 if c else 0.0),
        }
    return evolution


def _finance_recap_sort_key(module_row):
    return (
        (module_row.get('grade') or '').strip(),
        (module_row.get('groupe') or '').strip(),
        (module_row.get('module_intitule') or '').strip(),
    )


def _finance_recap_par_module(modules):
    """Tri récap modules par grade, groupe, intitulé."""
    return sorted(modules or [], key=_finance_recap_sort_key)


def _finance_recap_modules_for_period(modules_list, *, date_debut=None, date_fin=None):
    """Récap paie / export : avec filtre de dates, exclut les modules sans séance dans l'intervalle."""
    modules = modules_list or []
    if date_debut is not None or date_fin is not None:
        modules = [m for m in modules if int(m.get('sessions_count') or 0) > 0]
    return _finance_recap_par_module(modules)


def _finance_modules_dispenses_label(modules_list, *, date_debut=None, date_fin=None):
    """Libellé synthèse : intitulés des modules dispensés sur la période."""
    modules = _finance_recap_modules_for_period(
        modules_list, date_debut=date_debut, date_fin=date_fin,
    )
    labels = []
    seen = set()
    for module in modules:
        label = str(module.get('module_intitule') or '').strip()
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        labels.append(label)
    return ', '.join(labels) if labels else '-'


def _finance_group_sessions_by_groupe(sessions):
    """Groupe les séances par grade/groupe avec sous-totaux."""
    groups = {}
    for sess in sessions or []:
        grade = (sess.get('grade') or '').strip()
        groupe = (sess.get('groupe') or '').strip()
        key = (grade, groupe)
        block = groups.setdefault(key, {
            'grade': grade,
            'groupe': groupe,
            'sessions': [],
            'sous_total': {
                'sessions_count': 0,
                'creneau_minutes': 0.0,
                'realise_minutes': 0.0,
                'montant': 0.0,
            },
        })
        block['sessions'].append(sess)
        st = block['sous_total']
        st['sessions_count'] += 1
        st['creneau_minutes'] = round(
            st['creneau_minutes'] + float(sess.get('duree_minutes') or 0), 1,
        )
        st['realise_minutes'] = round(
            st['realise_minutes'] + float(sess.get('duree_realisee_minutes') or 0), 1,
        )
        st['montant'] = round(st['montant'] + float(sess.get('montant_realise') or 0), 2)

    result = []
    for key in sorted(groups.keys()):
        block = groups[key]
        block['sessions'].sort(
            key=lambda s: (s.get('date_journee') or '', s.get('numero') or 0),
        )
        result.append(block)
    return result


def _finance_canonical_volume_kpis(*, date_debut=None, date_fin=None, secretariat_id=None):
    """Volumes prévu/réalisé agrégés (logique canonique dashboard / bilans)."""
    from .volume_horaire import compute_volume_horaire_from_modules

    qs = Module.objects.all()
    if secretariat_id:
        qs = qs.filter(secretariat_id=secretariat_id)
    totals = compute_volume_horaire_from_modules(
        qs,
        date_debut=date_debut,
        date_fin=date_fin,
        integer_hours=False,
    )
    return {
        'prevu_minutes': totals.get('prevu_minutes', 0),
        'realise_minutes': totals.get('realise_minutes', 0),
        'prevu_heures': totals.get('prevu_heures', 0),
        'realise_heures': totals.get('realise_heures', 0),
        'taux_pct': totals.get('taux_pct', 0),
    }


def _finance_join_unique_labels(values):
    """Concatène des libellés uniques (grade, groupe…) triés."""
    cleaned = sorted({str(v).strip() for v in values if v and str(v).strip()})
    return ', '.join(cleaned)


def _finance_build_statistiques(
    *,
    total_minutes,
    total_realized_minutes,
    session_count,
    sessions_with_pointage,
    session_dates,
    montant_total,
    prix_heure,
    taux_planned_minutes=0,
    taux_realized_capped_minutes=0,
):
    total_minutes = float(total_minutes or 0)
    total_realized = float(total_realized_minutes or 0)
    session_count = int(session_count or 0)
    sessions_with_pointage = int(sessions_with_pointage or 0)
    taux = _finance_taux_realisation_pct(taux_realized_capped_minutes, taux_planned_minutes)
    dates_sorted = sorted(d for d in session_dates if d)
    return {
        'taux_realisation_pct': taux,
        'taux_planned_minutes': round(float(taux_planned_minutes or 0), 1),
        'taux_realized_capped_minutes': round(float(taux_realized_capped_minutes or 0), 1),
        'sessions_avec_pointage': sessions_with_pointage,
        'sessions_sans_pointage': max(session_count - sessions_with_pointage, 0),
        'moyenne_duree_seance_minutes': round(total_minutes / session_count, 1) if session_count else 0,
        'moyenne_realisee_seance_minutes': round(total_realized / session_count, 1) if session_count else 0,
        'ecart_planifie_realise_minutes': round(total_minutes - total_realized, 1),
        'premiere_seance_date': dates_sorted[0].isoformat() if dates_sorted else None,
        'derniere_seance_date': dates_sorted[-1].isoformat() if dates_sorted else None,
        'moyenne_montant_par_seance': round(float(montant_total or 0) / session_count, 2) if session_count else 0,
        'prix_heure_applique': float(prix_heure or 0),
    }


def _finance_report_rows(
    formateurs,
    *,
    include_sessions,
    prix_heure=None,
    global_aggregates=None,
    date_debut=None,
    date_fin=None,
    secretariat_id=None,
    include_all_modules=False,
):
    """Construit les lignes rapport finance pour une liste de Formateur (déjà résolus).

    Si include_all_modules=True, inclut aussi tous les modules du secrétariat
    (même ceux sans formateur assigné) dans les calculs de volume horaire.
    """
    from .volume_horaire import module_contractual_planned_minutes

    use_variable_rates = prix_heure is None
    if use_variable_rates:
        prix_map = _finance_build_prix_map()
        default_prix = 0.0
    else:
        default_prix = float(prix_heure or 0)
        prix_map = {}
    formateur_ids = [f.id for f in formateurs]

    module_formateur_map = {}
    if formateur_ids:
        for module_id, formateur_id in ModuleFormateur.objects.filter(
            formateur_id__in=formateur_ids
        ).values_list('module_id', 'formateur_id'):
            module_formateur_map.setdefault(formateur_id, set()).add(module_id)

        for module_id, formateur_id in Module.objects.filter(
            formateur_id__in=formateur_ids
        ).values_list('id', 'formateur_id'):
            module_formateur_map.setdefault(formateur_id, set()).add(module_id)

    # Récupérer tous les modules avec formateurs
    all_module_ids = sorted({
        mid
        for module_ids in module_formateur_map.values()
        for mid in module_ids
    })

    # Si demandé, ajouter tous les modules du secrétariat (même sans formateur)
    additional_module_ids = set()
    if include_all_modules:
        modules_qs = Module.objects.all()
        if secretariat_id:
            modules_qs = modules_qs.filter(secretariat_id=secretariat_id)
        # Exclure les modules déjà récupérés via les formateurs
        existing_ids = set(all_module_ids)
        additional_module_ids = set(
            modules_qs.exclude(id__in=existing_ids).values_list('id', flat=True)
        )
        all_module_ids = sorted(set(all_module_ids) | additional_module_ids)
    modules_by_id = {}
    if all_module_ids:
        for module in Module.objects.filter(id__in=all_module_ids).select_related(
            'formation', 'secretariat', 'site', 'ref_module',
        ):
            modules_by_id[module.id] = module
    sessions_by_module = {}
    if all_module_ids:
        for session in SessionModule.objects.filter(module_id__in=all_module_ids).select_related(
            'module',
            'module__formation',
        ).order_by('date_journee', 'numero'):
            sessions_by_module.setdefault(session.module_id, []).append(session)

    realized_by_formateur_session = {}
    if formateur_ids:
        now = timezone.now()
        pointages = Pointage.objects.filter(
            formateur_id__in=formateur_ids,
            session__module_id__in=all_module_ids,
            session_id__isnull=False,
        ).only('formateur_id', 'session_id', 'duree_presence_minutes', 'timestamp_entree', 'timestamp_sortie')
        for pt in pointages:
            minutes = 0.0
            if pt.duree_presence_minutes is not None:
                minutes = float(pt.duree_presence_minutes)
            elif pt.timestamp_entree and pt.timestamp_sortie:
                minutes = max((pt.timestamp_sortie - pt.timestamp_entree).total_seconds() / 60, 0)
            elif pt.timestamp_entree and not pt.timestamp_sortie:
                # Pointage encore ouvert: compter le temps écoulé jusqu'à maintenant.
                minutes = max((now - pt.timestamp_entree).total_seconds() / 60, 0)
            key = (pt.formateur_id, pt.session_id)
            realized_by_formateur_session[key] = realized_by_formateur_session.get(key, 0.0) + minutes

    results = []
    for formateur in formateurs:
        module_ids = sorted(module_formateur_map.get(formateur.id, set()))
        sessions_data = []
        modules_data = {}
        total_minutes = 0.0
        total_realized_minutes = 0.0
        taux_planned_minutes = 0.0
        taux_realized_capped_minutes = 0.0
        session_count = 0
        sessions_with_pointage = 0
        session_dates = []
        rates_used = set()
        grades_seen = set()
        groupes_seen = set()
        for module_id in module_ids:
            module_obj = modules_by_id.get(module_id)
            if secretariat_id and (
                not module_obj or module_obj.secretariat_id != secretariat_id
            ):
                continue
            module_formation_label = _finance_module_formation_label(module_obj)
            module_prix_heure = _finance_resolve_prix_heure(
                module_formation_label,
                prix_heure_override=None if use_variable_rates else default_prix,
                prix_map=prix_map,
                module_obj=module_obj,
            )
            module_sessions = sessions_by_module.get(module_id, [])
            sessions_in_period = [
                s for s in module_sessions
                if _finance_session_in_range(s, date_debut, date_fin)
            ]

            module_planned = (
                _finance_module_planned_minutes(
                    module_obj, module_sessions, date_debut=date_debut, date_fin=date_fin,
                )
                if sessions_in_period else 0.0
            )
            module_realized_sum = 0.0

            if module_obj:
                grade_val = (module_obj.grade or '').strip()
                groupe_val = (module_obj.groupe or '').strip()
                if grade_val:
                    grades_seen.add(grade_val)
                if groupe_val:
                    groupes_seen.add(groupe_val)

            contractual_minutes = (
                round(module_contractual_planned_minutes(module_obj), 1)
                if module_obj else 0.0
            )
            mod_entry = modules_data.setdefault(module_id, {
                'module_id': module_id,
                'module_intitule': module_obj.intitule if module_obj else '',
                'formation_intitule': (
                    module_obj.formation.formation if module_obj and module_obj.formation_id else ''
                ),
                'grade': module_obj.grade if module_obj else '',
                'groupe': module_obj.groupe if module_obj else '',
                'statut': module_obj.statut if module_obj else '',
                'site': (
                    module_obj.site.nom if module_obj and module_obj.site_id and module_obj.site
                    else (module_obj.site_legacy if module_obj else '')
                ),
                'salle': module_obj.salle if module_obj else '',
                'date_debut': module_obj.date_debut if module_obj else None,
                'date_fin': module_obj.date_fin if module_obj else None,
                'secretariat_nom': (
                    f"{module_obj.secretariat.nom} ({module_obj.secretariat.numero})"
                    if module_obj and module_obj.secretariat_id else ''
                ),
                'sessions_count': 0,
                'total_duree_minutes': 0.0,
                'total_duree_realisee_minutes': 0.0,
                'taux_planned_minutes': 0.0,
                'taux_realized_capped_minutes': 0.0,
                'montant_prevu': 0.0,
                'montant_realise': 0.0,
                'prix_heure_realisee': module_prix_heure,
                'volume_horaire_contractuel_minutes': contractual_minutes,
                'total_creneau_periode_minutes': 0.0,
            })

            module_creneau_sum = 0.0
            for session in sessions_in_period:
                session_count += 1
                session_slot = _finance_session_slot_minutes(session)
                module_creneau_sum += session_slot
                raw_realized_minutes = round(
                    realized_by_formateur_session.get((formateur.id, session.id), 0.0), 1,
                )
                if raw_realized_minutes <= 0:
                    from .volume_horaire import _session_realise_minutes

                    session_realized = round(_session_realise_minutes(session), 1)
                    if session_realized > 0:
                        raw_realized_minutes = session_realized
                realized_minutes = _finance_realized_minutes(
                    raw_realized_minutes, session_slot,
                )
                module_realized_sum += realized_minutes
                if raw_realized_minutes > 0:
                    sessions_with_pointage += 1
                if session.date_journee:
                    session_dates.append(session.date_journee)
                    if global_aggregates is not None:
                        d = session.date_journee
                        month_key = d.strftime('%Y-%m')
                        global_aggregates['activite_par_mois'][month_key] = (
                            global_aggregates['activite_par_mois'].get(month_key, 0.0) + realized_minutes
                        )
                        session_montant = _finance_montant_from_minutes(realized_minutes, module_prix_heure)
                        montant_par_mois = global_aggregates.setdefault('activite_montant_par_mois', {})
                        montant_par_mois[month_key] = montant_par_mois.get(month_key, 0.0) + session_montant
                        cur_min = global_aggregates.get('date_min')
                        cur_max = global_aggregates.get('date_max')
                        if cur_min is None or d < cur_min:
                            global_aggregates['date_min'] = d
                        if cur_max is None or d > cur_max:
                            global_aggregates['date_max'] = d
                mod_entry['sessions_count'] += 1
                if use_variable_rates and module_prix_heure is not None:
                    rates_used.add(module_prix_heure)
                if include_sessions:
                    taux_sess = (
                        _finance_taux_realisation_pct(realized_minutes, session_slot)
                        if session_slot > 0 else 0
                    )
                    sessions_data.append({
                        'session_id': session.id,
                        'date_journee': session.date_journee,
                        'numero': session.numero,
                        'intitule': session.intitule or f"Session {session.numero}",
                        'module_id': session.module_id,
                        'module_intitule': session.module.intitule,
                        'formation_id': session.module.formation_id,
                        'formation_intitule': (
                            session.module.formation.formation if session.module.formation else ''
                        ),
                        'grade': module_obj.grade if module_obj else '',
                        'groupe': module_obj.groupe if module_obj else '',
                        'duree_minutes': session_slot,
                        'duree_realisee_minutes': realized_minutes,
                        'montant_realise': _finance_montant_from_minutes(realized_minutes, module_prix_heure),
                        'prix_heure_realisee': module_prix_heure,
                        'taux_realisation_pct': taux_sess,
                        'a_pointage': raw_realized_minutes > 0,
                    })

            module_realized_capped = _finance_cap_module_realized(
                module_realized_sum, module_planned,
            )
            if sessions_in_period:
                total_minutes += module_planned
                taux_planned_minutes += module_planned
                total_realized_minutes += module_realized_capped
                taux_realized_capped_minutes += module_realized_capped
            mod_entry['total_duree_minutes'] = module_planned
            mod_entry['total_duree_realisee_minutes'] = module_realized_capped
            mod_entry['total_creneau_periode_minutes'] = round(module_creneau_sum, 1)
            mod_entry['taux_planned_minutes'] = module_planned
            mod_entry['taux_realized_capped_minutes'] = module_realized_capped
            mod_entry['montant_prevu'] = _finance_montant_from_minutes(
                module_planned, module_prix_heure,
            )
            mod_entry['montant_realise'] = _finance_montant_from_minutes(
                module_realized_capped, module_prix_heure,
            )
        modules_list = []
        for mid in module_ids:
            entry = modules_data.get(mid)
            if not entry:
                continue
            entry = dict(entry)
            entry['total_duree_minutes'] = round(entry['total_duree_minutes'], 1)
            entry['total_duree_realisee_minutes'] = round(entry['total_duree_realisee_minutes'], 1)
            entry['total_duree_heures'] = round(entry['total_duree_minutes'] / 60, 2)
            entry['total_duree_realisee_heures'] = round(entry['total_duree_realisee_minutes'] / 60, 2)
            if entry.get('date_debut'):
                entry['date_debut'] = entry['date_debut'].isoformat()
            if entry.get('date_fin'):
                entry['date_fin'] = entry['date_fin'].isoformat()
            entry['taux_realisation_pct'] = _finance_taux_realisation_pct(
                entry.get('taux_realized_capped_minutes', 0),
                entry.get('taux_planned_minutes', 0),
            )
            entry['taux_planned_minutes'] = round(float(entry.get('taux_planned_minutes') or 0), 1)
            entry['taux_realized_capped_minutes'] = round(float(entry.get('taux_realized_capped_minutes') or 0), 1)
            modules_list.append(entry)
        montant_total = round(sum(float(m.get('montant_realise') or 0) for m in modules_list), 2)
        if use_variable_rates:
            row_prix_heure = None
            tarifs_variables = bool(modules_list)
        else:
            row_prix_heure = default_prix
            tarifs_variables = False
        statistiques = _finance_build_statistiques(
            total_minutes=total_minutes,
            total_realized_minutes=total_realized_minutes,
            session_count=session_count,
            sessions_with_pointage=sessions_with_pointage,
            session_dates=session_dates,
            montant_total=montant_total,
            prix_heure=row_prix_heure if row_prix_heure is not None else default_prix,
            taux_planned_minutes=taux_planned_minutes,
            taux_realized_capped_minutes=taux_realized_capped_minutes,
        )
        row = {
            'id': formateur.id,
            'numerobadge': formateur.numerobadge,
            'nom': formateur.nom,
            'prenom': formateur.prenom,
            'email': formateur.email or '',
            'telephone': formateur.telephone or '',
            'specialite': formateur.specialite or '',
            'organisation': formateur.organisation or '',
            'grades': _finance_join_unique_labels(grades_seen) or '-',
            'groupes': _finance_join_unique_labels(groupes_seen) or '-',
            'secretariats_noms': [
                f"{s.nom} ({s.numero})" for s in formateur.secretariats.all()
            ],
            'numero_piece_identite': formateur.numero_piece_identite or '',
            'numero_compte_bancaire': formateur.numero_compte_bancaire or '',
            'observations': formateur.observations or '',
            'nb_formations': len(modules_list),
            'modules_dispenses': _finance_modules_dispenses_label(
                modules_list, date_debut=date_debut, date_fin=date_fin,
            ),
            'created_at': formateur.created_at,
            'prix_heure_realisee': row_prix_heure,
            'tarifs_variables': tarifs_variables,
            'montant_total_realise': montant_total,
            'total_duree_minutes': round(total_minutes, 1),
            'total_duree_heures': round(total_minutes / 60, 2),
            'total_duree_realisee_minutes': round(total_realized_minutes, 1),
            'total_duree_realisee_heures': round(total_realized_minutes / 60, 2),
            'sessions_count': session_count,
            'statistiques': statistiques,
            'modules': modules_list,
        }
        if include_sessions:
            row['sessions'] = sessions_data
            row['recap_modules'] = _finance_recap_modules_for_period(
                modules_list, date_debut=date_debut, date_fin=date_fin,
            )
            row['sessions_by_groupe'] = _finance_group_sessions_by_groupe(sessions_data)
        results.append(row)

    # Traiter les modules sans formateur (si include_all_modules=True)
    if include_all_modules and additional_module_ids and global_aggregates is not None:
        # Initialiser les compteurs pour les modules sans formateur
        additional_sessions_count = 0
        additional_planned_minutes = 0.0
        additional_modules_list = []

        for module_id in additional_module_ids:
            module_obj = modules_by_id.get(module_id)
            if not module_obj:
                continue
            if secretariat_id and module_obj.secretariat_id != secretariat_id:
                continue

            module_sessions = sessions_by_module.get(module_id, [])
            sessions_in_period = [
                s for s in module_sessions
                if _finance_session_in_range(s, date_debut, date_fin)
            ]
            if not sessions_in_period:
                continue

            # Calculer le volume pour ce module (sans formateur)
            module_planned = _finance_module_planned_minutes(
                module_obj, module_sessions, date_debut=date_debut, date_fin=date_fin,
            )

            # Accumuler les totaux
            additional_sessions_count += len(sessions_in_period)
            additional_planned_minutes += module_planned

            # Stocker les infos du module pour le détail
            additional_modules_list.append({
                'module_id': module_id,
                'module_intitule': module_obj.intitule or '',
                'formation_intitule': module_obj.formation.formation if module_obj.formation_id else '',
                'grade': module_obj.grade or '',
                'groupe': module_obj.groupe or '',
                'secretariat_nom': (
                    f"{module_obj.secretariat.nom} ({module_obj.secretariat.numero})"
                    if module_obj.secretariat_id else ''
                ),
            })

            # Agréger les données pour les KPIs globaux
            for session in sessions_in_period:
                if session.date_journee:
                    d = session.date_journee
                    month_key = d.strftime('%Y-%m')
                    # Pour le volume planifié (pas de réalisé car pas de formateur)
                    session_slot = _finance_session_slot_minutes(session)
                    global_aggregates['activite_par_mois'][month_key] = (
                        global_aggregates['activite_par_mois'].get(month_key, 0.0) + session_slot
                    )
                    cur_min = global_aggregates.get('date_min')
                    cur_max = global_aggregates.get('date_max')
                    if cur_min is None or d < cur_min:
                        global_aggregates['date_min'] = d
                    if cur_max is None or d > cur_max:
                        global_aggregates['date_max'] = d

        # Stocker les totaux et la liste des modules sans formateur dans global_aggregates
        global_aggregates['additional_sessions_count'] = additional_sessions_count
        global_aggregates['additional_planned_minutes'] = additional_planned_minutes
        global_aggregates['additional_modules'] = additional_modules_list

    return results


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def formateur_finance_report_api(request):
    """Rapport finance : temps de cours par formateur, par séance, + total.

    Query params:
    - ``formateur_id`` : si fourni, retourne une seule ligne avec le détail des séances (pagination ignorée).
    - ``include_sessions`` : pour la liste paginée, ``1`` / ``true`` inclut les séances (lourd). Par défaut ``0`` :
      totaux et ``sessions_count`` seulement.
    """
    allowed_roles = _finance_allowed_roles()
    if request.user.role not in allowed_roles:
        return Response({'detail': 'Accès réservé à la Direction et au service Finance.'}, status=403)

    period = _parse_finance_date_range(request)
    if period['error']:
        return Response({'detail': period['detail']}, status=400)

    secretariat_id = _finance_secretariat_id_from_request(request)

    formateur_id_raw = (request.query_params.get('formateur_id') or '').strip()
    if formateur_id_raw:
        try:
            fid = int(formateur_id_raw)
        except ValueError:
            return Response({'detail': 'formateur_id invalide.'}, status=400)
        try:
            formateur = Formateur.objects.prefetch_related('secretariats').get(pk=fid)
        except Formateur.DoesNotExist:
            return Response({'detail': 'Formateur introuvable.'}, status=404)
        global_agg = {'activite_par_mois': {}, 'date_min': None, 'date_max': None}
        results = _finance_report_rows(
            [formateur],
            include_sessions=True,
            date_debut=period['date_debut'],
            date_fin=period['date_fin'],
            global_aggregates=global_agg,
            secretariat_id=secretariat_id,
        )
        payload = {
            'results': results,
            'count': 1,
            'total_pages': 1,
            'current_page': 1,
            'periode': _finance_periode_payload(
                period['date_debut'],
                period['date_fin'],
                period['meta'],
                global_agg.get('date_min'),
                global_agg.get('date_max'),
            ),
        }
        if secretariat_id:
            try:
                sec = Secretariat.objects.get(pk=secretariat_id)
                payload['secretariat_filtre'] = {'id': sec.id, 'nom': sec.nom, 'numero': sec.numero}
            except Secretariat.DoesNotExist:
                pass
        if request.user.role not in ('FINANCE', 'ARCHIVE'):
            for row in results:
                row.pop('numero_piece_identite', None)
                row.pop('numero_compte_bancaire', None)
        return Response(payload)

    page = int(request.query_params.get('page', 1))
    page_size = int(request.query_params.get('page_size', 25))
    include_sessions = request.query_params.get('include_sessions', '0').lower() in ('1', 'true', 'yes')

    queryset = Formateur.objects.prefetch_related('secretariats')
    queryset = _finance_filter_formateur_queryset(queryset, secretariat_id)
    search = (request.query_params.get('search') or '').strip()
    if search:
        queryset = queryset.filter(
            Q(nom__icontains=search) |
            Q(prenom__icontains=search) |
            Q(specialite__icontains=search)
        )
    # Afficher en premier les formateurs qui dispensent des cours
    # (au moins un module assigné ou rattaché directement), puis l'ordre alphabétique.
    queryset = queryset.annotate(
        _nb_modules_assignes=Count('modules_assignes', distinct=True),
        _nb_modules_direct=Count('modules', distinct=True),
    ).annotate(
        _dispense_cours=Case(
            When(_nb_modules_assignes__gt=0, then=Value(1)),
            When(_nb_modules_direct__gt=0, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        ),
    ).order_by('-_dispense_cours', 'nom', 'prenom')

    total_count = queryset.count()
    start = (page - 1) * page_size
    end = start + page_size
    formateurs = list(queryset[start:end])
    results = _finance_report_rows(
        formateurs,
        include_sessions=include_sessions,
        date_debut=period['date_debut'],
        date_fin=period['date_fin'],
        secretariat_id=secretariat_id,
    )

    list_payload = {
        'results': results,
        'count': total_count,
        'total_pages': (total_count + page_size - 1) // page_size,
        'current_page': page,
        'periode': _finance_periode_payload(period['date_debut'], period['date_fin'], period['meta']),
    }
    if secretariat_id:
        try:
            sec = Secretariat.objects.get(pk=secretariat_id)
            list_payload['secretariat_filtre'] = {'id': sec.id, 'nom': sec.nom, 'numero': sec.numero}
        except Secretariat.DoesNotExist:
            pass
    if request.user.role not in ('FINANCE', 'ARCHIVE'):
        for row in results:
            row.pop('numero_piece_identite', None)
            row.pop('numero_compte_bancaire', None)
    return Response(list_payload)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def formateur_donnees_sensibles_api(request, pk):
    """Pièce d'identité et compte bancaire — visible/éditable par FINANCE ou le formateur lui-même."""
    try:
        formateur = Formateur.objects.get(pk=pk)
    except Formateur.DoesNotExist:
        return Response({'detail': 'Formateur introuvable.'}, status=404)

    if not can_view_formateur_sensitive_data(request.user, formateur):
        return Response({'detail': 'Accès interdit.'}, status=403)

    if request.method == 'GET':
        return Response(formateur_sensitive_payload(formateur))

    if not can_edit_formateur_sensitive_data(request.user, formateur):
        return Response({'detail': 'Modification interdite.'}, status=403)

    update_fields = []
    for field in ('numero_piece_identite', 'numero_compte_bancaire'):
        if field in request.data:
            setattr(formateur, field, str(request.data.get(field) or '').strip())
            update_fields.append(field)
    if update_fields:
        formateur.save(update_fields=update_fields)
    return Response(formateur_sensitive_payload(formateur))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def finance_dashboard_api(request):
    """Dashboard finance: agrégats globaux + top formateurs."""
    if request.user.role not in _finance_allowed_roles():
        return Response({'detail': 'Accès réservé à la direction et à la finance.'}, status=403)

    period = _parse_finance_date_range(request)
    if period['error']:
        return Response({'detail': period['detail']}, status=400)

    secretariat_id = _finance_secretariat_id_from_request(request)
    compare_previous = request.query_params.get('compare', '').lower() in ('1', 'true', 'yes')

    formateurs_qs = Formateur.objects.prefetch_related('secretariats').order_by('nom', 'prenom')
    formateurs_qs = _finance_filter_formateur_queryset(formateurs_qs, secretariat_id)
    formateurs = list(formateurs_qs)
    global_aggregates = {'activite_par_mois': {}, 'activite_montant_par_mois': {}, 'date_min': None, 'date_max': None}
    rows = _finance_report_rows(
        formateurs,
        include_sessions=False,
        global_aggregates=global_aggregates,
        date_debut=period['date_debut'],
        date_fin=period['date_fin'],
        secretariat_id=secretariat_id,
        include_all_modules=True,
    )

    date_min = global_aggregates.get('date_min')
    date_max = global_aggregates.get('date_max')

    kpis = _finance_kpis_from_rows(rows)

    montant_par_mois = global_aggregates.get('activite_montant_par_mois') or {}
    activite_par_mois = [
        {
            'mois': mois,
            'label': datetime.strptime(mois, '%Y-%m').strftime('%b %Y'),
            'minutes_realisees': round(minutes, 1),
            'heures_realisees': round(minutes / 60, 2),
            'montant': round(float(montant_par_mois.get(mois, 0.0)), 2),
        }
        for mois, minutes in sorted(global_aggregates['activite_par_mois'].items())
    ]

    # Unifier les spécialités en utilisant les intitulés canoniques de RefModule
    from formations.models import RefModule as _RefModule
    ref_modules_all = list(_RefModule.objects.values_list('intitule', flat=True))
    _ref_lower_map = {intit.strip().lower(): intit for intit in ref_modules_all}

    def _canonical_specialite(raw):
        s = (raw or '').strip()
        if not s:
            return 'Non renseignée'
        return _ref_lower_map.get(s.lower(), s)

    repartition_specialites = {}
    for r in rows:
        key = _canonical_specialite(r.get('specialite'))
        if key not in repartition_specialites:
            repartition_specialites[key] = {'count': 0, 'formateurs': []}
        repartition_specialites[key]['count'] += 1
        repartition_specialites[key]['formateurs'].append({
            'id': r.get('id'),
            'nom': r.get('nom') or '',
            'prenom': r.get('prenom') or '',
            'numerobadge': r.get('numerobadge') or '',
        })

    top_temps_planifie = sorted(rows, key=lambda r: float(r.get('total_duree_minutes') or 0), reverse=True)[:10]
    top_temps_realise = sorted(
        rows, key=lambda r: float(r.get('total_duree_realisee_minutes') or 0), reverse=True,
    )[:10]
    top_montants = sorted(rows, key=lambda r: float(r.get('montant_total_realise') or 0), reverse=True)[:10]

    periode_payload = _finance_periode_payload(
        period['date_debut'],
        period['date_fin'],
        period['meta'],
        date_min,
        date_max,
    )
    periode_payload['description'] = (
        period['meta'].get('description')
        or (
            'Le temps planifié est la somme des créneaux horaires des séances de la période '
            '(heure de fin − heure de début prévues sur l\'EDT). '
            'Le temps réalisé provient des pointages (badgeage), plafonné au créneau EDT '
            'de chaque séance puis au planifié du module (le réalisé ne peut pas dépasser '
            'le planifié). '
            'Le taux de réalisation compare le réalisé au planifié du module. '
            'Les montants sont calculés heure par heure selon le tarif du cycle de formation '
            'concerné (paramétrage Finance).'
        )
    )

    comparaison = None
    volumes_par_module = _finance_dashboard_modules_breakdown(
        rows,
        date_debut=period['date_debut'],
        date_fin=period['date_fin'],
        secretariat_id=secretariat_id,
        additional_modules=global_aggregates.get('additional_modules'),
    )
    kpis = _finance_kpis_from_modules_breakdown(kpis, volumes_par_module)

    if compare_previous and period['meta'].get('preset') != 'tout':
        prev_period = _finance_previous_period(
            period['date_debut'], period['date_fin'], period['meta'],
        )
        if prev_period:
            prev_global = {}
            prev_rows = _finance_report_rows(
                formateurs,
                include_sessions=False,
                global_aggregates=prev_global,
                date_debut=prev_period['date_debut'],
                date_fin=prev_period['date_fin'],
                secretariat_id=secretariat_id,
                include_all_modules=True,
            )
            prev_kpis = _finance_kpis_from_rows(prev_rows)
            prev_breakdown = _finance_dashboard_modules_breakdown(
                prev_rows,
                date_debut=prev_period['date_debut'],
                date_fin=prev_period['date_fin'],
                secretariat_id=secretariat_id,
                additional_modules=prev_global.get('additional_modules'),
            )
            prev_kpis = _finance_kpis_from_modules_breakdown(prev_kpis, prev_breakdown)
            comparaison = {
                'periode': _finance_periode_payload(
                    prev_period['date_debut'],
                    prev_period['date_fin'],
                    prev_period['meta'],
                ),
                'kpis': prev_kpis,
                'evolution': _finance_kpi_evolution(kpis, prev_kpis),
            }

    dashboard_payload = {
        'periode': periode_payload,
        'kpis': kpis,
        'volumes_par_module': volumes_par_module,
        'top_formateurs': top_temps_planifie,
        'top_temps_realise': top_temps_realise,
        'top_montants': top_montants,
        'activite_par_mois': activite_par_mois,
        'repartition_specialites': [
            {'specialite': k, 'count': v['count'], 'formateurs': v['formateurs']}
            for k, v in sorted(
                repartition_specialites.items(), key=lambda x: -x[1]['count'],
            )
        ],
        'synthese_formateurs': rows,
        'generated_at': timezone.now(),
    }
    if comparaison:
        dashboard_payload['comparaison'] = comparaison
    if secretariat_id:
        try:
            sec = Secretariat.objects.get(pk=secretariat_id)
            dashboard_payload['secretariat_filtre'] = {
                'id': sec.id, 'nom': sec.nom, 'numero': sec.numero,
            }
        except Secretariat.DoesNotExist:
            pass
    return Response(dashboard_payload)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def finance_settings_api(request):
    """Paramètres finance : tarifs horaires par formation (référentiel) et exports."""
    if not _check_finance_access(request):
        return Response({'detail': 'Accès réservé à la direction et à la finance.'}, status=403)

    settings_obj = FinanceSettings.get_solo()

    def _serialize_tarifs():
        tarifs = []
        for ref in RefFormation.objects.order_by('intitule'):
            tarifs.append({
                'id': ref.id,
                'intitule': ref.intitule,
                'actif': ref.actif,
                'prix_heure_realisee': (
                    float(ref.prix_heure_realisee) if ref.prix_heure_realisee is not None else None
                ),
            })
        return tarifs

    def _settings_payload():
        return {
            'tarifs_formations': _serialize_tarifs(),
            'afficher_montants_exports': bool(settings_obj.afficher_montants_exports),
            'export_titre_document': settings_obj.export_titre_document or '',
            'export_entete_ligne1': settings_obj.export_entete_ligne1 or '',
            'export_entete_ligne2': settings_obj.export_entete_ligne2 or '',
            'export_organisme': settings_obj.export_organisme or '',
            'export_adresse': settings_obj.export_adresse or '',
            'export_reference_prefix': settings_obj.export_reference_prefix or 'EFI',
            'export_mention_legale': settings_obj.export_mention_legale or '',
            'export_signataire_nom': settings_obj.export_signataire_nom or '',
            'export_signataire_fonction': settings_obj.export_signataire_fonction or '',
            'export_contacts': settings_obj.export_contacts or '',
            'export_pied_page_titre': settings_obj.export_pied_page_titre or '',
            'export_pied_page_texte': settings_obj.export_pied_page_texte or '',
            'updated_at': settings_obj.updated_at,
            'updated_by': (
                settings_obj.updated_by.get_full_name() or settings_obj.updated_by.username
            ) if settings_obj.updated_by else None,
            **tolerance_settings_payload(settings_obj),
        }

    if request.method == 'GET':
        return Response(_settings_payload())

    if request.user.role != 'FINANCE':
        return Response({'detail': 'Seul le service Finance peut modifier les paramètres.'}, status=403)

    updated = False

    tarifs = request.data.get('tarifs_formations')
    if tarifs is not None:
        if not isinstance(tarifs, list):
            return Response({'detail': 'tarifs_formations doit être une liste.'}, status=400)
        for item in tarifs:
            if not isinstance(item, dict) or 'id' not in item:
                return Response({'detail': 'Chaque tarif doit contenir un id.'}, status=400)
            try:
                ref = RefFormation.objects.get(pk=int(item['id']))
            except (RefFormation.DoesNotExist, TypeError, ValueError):
                return Response({'detail': f"Formation référentiel introuvable (id={item.get('id')})."}, status=400)
            raw_prix = item.get('prix_heure_realisee')
            if raw_prix is None or raw_prix == '':
                ref.prix_heure_realisee = None
            else:
                try:
                    prix_ref = float(raw_prix)
                except (TypeError, ValueError):
                    return Response({'detail': f"Tarif invalide pour {ref.intitule}."}, status=400)
                if prix_ref < 0:
                    return Response({'detail': f"Le tarif de {ref.intitule} doit être positif ou nul."}, status=400)
                ref.prix_heure_realisee = round(prix_ref, 2)
            ref.save(update_fields=['prix_heure_realisee'])
        updated = True

    export_bool_fields = ('afficher_montants_exports', 'tolerance_active')
    for field in export_bool_fields:
        if field in request.data:
            setattr(settings_obj, field, bool(request.data.get(field)))
            updated = True

    if 'tolerance_minutes' in request.data:
        try:
            mins = int(request.data.get('tolerance_minutes'))
        except (TypeError, ValueError):
            return Response({'detail': 'tolerance_minutes invalide.'}, status=400)
        if mins < 0:
            return Response({'detail': 'tolerance_minutes doit être positif ou nul.'}, status=400)
        settings_obj.tolerance_minutes = mins
        updated = True

    if 'tolerance_pct' in request.data:
        try:
            pct = float(request.data.get('tolerance_pct'))
        except (TypeError, ValueError):
            return Response({'detail': 'tolerance_pct invalide.'}, status=400)
        if pct < 0:
            return Response({'detail': 'tolerance_pct doit être positif ou nul.'}, status=400)
        settings_obj.tolerance_pct = round(pct, 2)
        updated = True

    export_text_fields = (
        'export_titre_document', 'export_entete_ligne1', 'export_entete_ligne2',
        'export_organisme', 'export_adresse', 'export_reference_prefix',
        'export_mention_legale', 'export_signataire_nom', 'export_signataire_fonction',
        'export_contacts', 'export_pied_page_titre', 'export_pied_page_texte',
    )
    for field in export_text_fields:
        if field in request.data:
            setattr(settings_obj, field, str(request.data.get(field) or '').strip())
            updated = True

    if not updated:
        return Response({'detail': 'Aucun paramètre à mettre à jour.'}, status=400)

    settings_obj.updated_by = request.user
    settings_obj.save()

    payload = _settings_payload()
    payload['updated_by'] = request.user.get_full_name() or request.user.username
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def finance_encadrants_api(request):
    """Rapport volumes horaires par encadrant (superviseur de module)."""
    if not _check_finance_access(request):
        return Response({'detail': 'Accès réservé à la direction et à la finance.'}, status=403)

    period = _parse_finance_date_range(request)
    if period.get('error'):
        return Response({'detail': period['detail']}, status=400)

    data = finance_encadrants_report(
        date_debut=period.get('date_debut'),
        date_fin=period.get('date_fin'),
        secretariat_id=_finance_secretariat_id_from_request(request),
    )
    return Response(data)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def finance_ajustements_api(request):
    """Liste ou proposition d'ajustements horaires sur séances terminées."""
    if not _check_finance_access(request):
        return Response({'detail': 'Accès réservé à la direction et à la finance.'}, status=403)

    if request.method == 'GET':
        qs = FinanceAjustement.objects.select_related(
            'session',
            'session__module',
            'session__module__formation',
            'formateur',
            'proposed_by',
            'validated_by',
            'rejected_by',
        ).order_by('-proposed_at')
        statut = (request.query_params.get('statut') or '').strip()
        if statut:
            qs = qs.filter(statut=statut)
        pending_count = FinanceAjustement.objects.filter(
            statut=FinanceAjustement.Statut.EN_ATTENTE,
        ).count()
        return Response({
            'items': [serialize_ajustement(a) for a in qs],
            'pending_count': pending_count,
        })

    session_id_raw = request.data.get('session_id')
    formateur_id_raw = request.data.get('formateur_id')
    minutes_delta_raw = request.data.get('minutes_delta')
    motif = request.data.get('motif')

    try:
        session = SessionModule.objects.select_related('module', 'module__formation').get(
            pk=int(session_id_raw),
        )
    except (SessionModule.DoesNotExist, TypeError, ValueError):
        return Response({'detail': 'Séance introuvable.'}, status=404)

    try:
        formateur = Formateur.objects.get(pk=int(formateur_id_raw))
    except (Formateur.DoesNotExist, TypeError, ValueError):
        return Response({'detail': 'Formateur introuvable.'}, status=404)

    ajustement, errors = propose_ajustement(
        session,
        formateur,
        minutes_delta_raw,
        motif,
        request.user,
    )
    if errors:
        return Response({'detail': errors[0], 'errors': errors}, status=400)

    _log_finance_audit('FINANCE_AJUSTEMENT_PROPOSE', request, ajustement)
    return Response(serialize_ajustement(ajustement), status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def finance_ajustement_valider_api(request, pk):
    """Valide un ajustement en attente et applique l'impact sur la séance."""
    if not _check_finance_access(request):
        return Response({'detail': 'Accès réservé à la direction et à la finance.'}, status=403)

    try:
        ajustement = FinanceAjustement.objects.select_related(
            'session', 'session__module', 'formateur',
        ).get(pk=pk)
    except FinanceAjustement.DoesNotExist:
        return Response({'detail': 'Ajustement introuvable.'}, status=404)

    ajustement, errors = valider_ajustement(ajustement, request.user, request=request)
    if errors:
        return Response({'detail': errors[0], 'errors': errors}, status=400)
    return Response(serialize_ajustement(ajustement))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def finance_ajustement_rejeter_api(request, pk):
    """Rejette un ajustement en attente sans modifier la séance."""
    if not _check_finance_access(request):
        return Response({'detail': 'Accès réservé à la direction et à la finance.'}, status=403)

    try:
        ajustement = FinanceAjustement.objects.select_related(
            'session', 'session__module', 'formateur',
        ).get(pk=pk)
    except FinanceAjustement.DoesNotExist:
        return Response({'detail': 'Ajustement introuvable.'}, status=404)

    motif = request.data.get('motif') or request.data.get('rejection_motif')
    ajustement, errors = rejeter_ajustement(
        ajustement, request.user, rejection_motif=motif, request=request,
    )
    if errors:
        return Response({'detail': errors[0], 'errors': errors}, status=400)
    return Response(serialize_ajustement(ajustement))


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def formation_detail_api(request, pk):
    """
    Get formation details by ID.
    """
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    formation, err = formation_or_response(request.user, pk)
    if err:
        return err

    from .serializer_querysets import annotate_modules_for_serializer
    from .models import ModuleParticipant

    formation = Formation.objects.prefetch_related(
        Prefetch(
            'modules',
            queryset=annotate_modules_for_serializer(
                Module.objects.order_by('ordre', 'intitule')
            ),
        ),
        Prefetch(
            'modules__module_participants',
            queryset=ModuleParticipant.objects.select_related('participant'),
        ),
    ).get(pk=pk)

    serializer = FormationDetailSerializer(formation)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrEncadrantOrDFRC])
def api_generate_qr(request, formation_pk, session_pk=None):
    """
    Generate QR code for a session (module-scoped).
    Optional body: { module_id } — vérifie que la séance appartient au module affiché.
    """
    formation = formation_accessible(request.user, formation_pk)
    if not formation:
        return Response({'detail': 'Formation introuvable.'}, status=404)

    module_id = request.data.get('module_id')
    session, err = get_session_for_qr(
        formation=formation,
        session_id=session_pk,
        module_id=module_id,
    )
    if err:
        return err
    if session.est_terminee:
        return Response(
            {'detail': 'Impossible de générer un QR pour une séance terminée.'},
            status=400,
        )

    qr_filter = QRToken.objects.filter(session=session, actif=True)
    old_tokens = list(qr_filter.values_list('token', flat=True))
    qr_filter.update(actif=False)
    for old_token in old_tokens:
        invalidate_offline_data_cache(old_token)

    from django.conf import settings as django_settings
    lifetime_hours = getattr(django_settings, 'QR_TOKEN_LIFETIME_HOURS', 24)
    qr_token = QRToken.objects.create(
        session=session,
        genere_par=request.user,
        expire_at=timezone.now() + timedelta(hours=lifetime_hours),
    )

    payload = QRTokenSerializer(qr_token).data
    payload['detail'] = 'QR code généré.'
    payload['token'] = str(qr_token.token)
    payload['qr_url'] = (
        f'/api/formations/{formation_pk}/sessions/{session_pk}/qr-image/'
    )
    return Response(payload, status=201)


@api_view(['POST'])
@permission_classes([IsSecretariatOrDFRC])
@parser_classes([MultiPartParser])
def api_import_excel(request):
    """
    Import Excel (.xlsx) or CSV (.csv) file for formations, participants, or formateurs.
    Expects multipart form with 'file' and 'type' fields.
    Returns JSON with created count and errors.
    """
    uploaded = request.FILES.get('file')
    import_type = request.data.get('type', '')

    if not uploaded:
        return Response({'error': 'Veuillez fournir un fichier.'}, status=400)
    if import_type not in ('formations', 'participants', 'formateurs', 'seances', 'emploi_du_temps'):
        return Response({'error': 'Type invalide. Utilisez: formations, participants, formateurs, seances, emploi_du_temps.'}, status=400)

    # Vérification fine par type d'import — respecte les permissions réelles du groupe.
    _import_perm_map = {
        'formations':     'formations.add_formation',
        'participants':   'formations.add_participant',
        'formateurs':     'formations.add_formateur',
        'seances':        'formations.add_sessionmodule',
        'emploi_du_temps': 'formations.add_module',
    }
    required_perm = _import_perm_map.get(import_type)
    if required_perm and not request.user.has_perm(required_perm):
        return Response(
            {'error': f"Vous n'avez pas le droit d'importer des \"{import_type}\"."},
            status=403,
        )

    from .management.commands.import_excel import Command as ImportCommand

    cmd = ImportCommand()
    _logs = []
    class _Stdout:
        def write(self, msg): _logs.append(str(msg))
    cmd.stdout = _Stdout()

    errors = []
    stats = {}

    filename = uploaded.name.lower()
    is_csv = filename.endswith('.csv')
    file_content = uploaded.read()

    # Pour SECRETARIAT : utilise le secrétariat de l'user
    # Pour ADMIN/DFRC : secretariat=None → auto-affectation par catégorie dans _import_participants
    secretariat = request.user.secretariat if request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT') else None

    try:
        with transaction.atomic():
            if is_csv:
                ws = cmd._load_csv_from_bytes(file_content)
                if import_type == 'formations':
                    stats['created'], stats['updated'] = cmd._import_formations(ws, errors, secretariat=secretariat)
                elif import_type == 'participants':
                    stats['created'] = cmd._import_participants(ws, errors, secretariat=secretariat)
                elif import_type == 'formateurs':
                    stats['created'] = cmd._import_formateurs(ws, errors)
                elif import_type == 'emploi_du_temps':
                    stats['created'] = cmd._import_emploi_du_temps(ws, errors)
                elif import_type == 'seances':
                    stats['created'], stats['updated'] = cmd._import_seances(ws, errors)
            else:
                try:
                    from openpyxl import load_workbook
                except ImportError:
                    return Response({'error': 'openpyxl non installé sur le serveur.'}, status=500)

                try:
                    wb = load_workbook(BytesIO(file_content), read_only=True)
                except Exception as e:
                    return Response({'error': f'Impossible de lire le fichier: {e}'}, status=400)

                # Map type to expected sheet name
                sheet_map = {
                    'formations': 'Formations',
                    'participants': 'Participants',
                    'formateurs': 'Formateurs',
                    'seances': 'Séances',
                    'emploi_du_temps': 'Emploi du temps',
                }
                sheet_name = sheet_map[import_type]
                # Comme manage.py import_excel : feuille « Séances » ou « Seances » (sans accent).
                if import_type == 'seances' and sheet_name not in wb.sheetnames and 'Seances' in wb.sheetnames:
                    sheet_name = 'Seances'

                def _looks_like_participant_sheet(ws):
                    """Return True if the first row contains an inscription number column."""
                    try:
                        first_row = next(ws.iter_rows(values_only=True, max_row=1), None)
                        if not first_row:
                            return False
                        headers = [str(h).strip().lower() if h else '' for h in first_row]
                        keywords = ["d'inscription", "d inscription", "inscription", "fncp", "nom"]
                        return any(any(k in h for k in keywords) for h in headers)
                    except Exception:
                        return False

                if sheet_name not in wb.sheetnames:
                    if import_type == 'participants':
                        # Try RECAP first, then any sheet that looks like participant data
                        candidate_sheets = []
                        for sn in wb.sheetnames:
                            if sn.upper() in ('RECAP', 'RECAPITULATIF', 'PARTICIPANTS', 'LISTE'):
                                candidate_sheets.insert(0, sn)
                            elif _looks_like_participant_sheet(wb[sn]):
                                candidate_sheets.append(sn)
                        if not candidate_sheets:
                            wb.close()
                            return Response({'error': 'Aucune feuille de participants trouvée dans le fichier.'}, status=400)
                        total_created = 0
                        for sn in candidate_sheets:
                            total_created += cmd._import_participants(wb[sn], errors, secretariat=secretariat)
                        stats['created'] = total_created
                        wb.close()
                        debug_headers = [l for l in _logs if '[DEBUG]' in l]
                        return Response({
                            'created': stats.get('created', 0),
                            'errors': errors[:20],
                            'debug_headers': debug_headers,
                        })
                    else:
                        ws = wb.active
                        if ws is None:
                            wb.close()
                            return Response({'error': f'Feuille "{sheet_name}" introuvable dans le fichier.'}, status=400)
                        wb_sheets = {sheet_name: ws}
                else:
                    wb_sheets = {sheet_name: wb[sheet_name]}

                if import_type == 'formations':
                    stats['created'], stats['updated'] = cmd._import_formations(wb_sheets[sheet_name], errors, secretariat=secretariat)
                elif import_type == 'participants':
                    stats['created'] = cmd._import_participants(wb_sheets[sheet_name], errors, secretariat=secretariat)
                elif import_type == 'formateurs':
                    stats['created'] = cmd._import_formateurs(wb_sheets[sheet_name], errors)
                elif import_type == 'emploi_du_temps':
                    stats['created'] = cmd._import_emploi_du_temps(wb_sheets[sheet_name], errors)
                elif import_type == 'seances':
                    formation_id = request.data.get('formation_id')
                    if formation_id:
                        try:
                            formation = Formation.objects.get(pk=formation_id)
                            stats['created'] = cmd._import_seances_for_formation(wb_sheets[sheet_name], errors, formation)
                            stats['updated'] = 0
                        except Formation.DoesNotExist:
                            wb.close()
                            return Response({'error': 'Formation introuvable.'}, status=404)
                    else:
                        stats['created'], stats['updated'] = cmd._import_seances(wb_sheets[sheet_name], errors)

                wb.close()

    except Exception as e:
        return Response({'error': f"Erreur lors de l'import: {e}"}, status=500)

    debug_headers = [l for l in _logs if '[DEBUG]' in l]
    return Response({
        'created': stats.get('created', 0),
        'updated': stats.get('updated', 0),
        'errors': errors[:20],
        'debug_headers': debug_headers,
    })


_REF_FORMATION_CHAMPS = ('code', 'type_diplome', 'domaine', 'mention', 'duree_annees',
                         'nb_semestres', 'nb_credites', 'description')


def _ref_formation_payload(obj):
    return {'id': obj.id, 'intitule': obj.intitule, 'actif': obj.actif,
            'prix_heure_realisee': obj.prix_heure_realisee,
            **{c: getattr(obj, c) for c in _REF_FORMATION_CHAMPS}}


def _ref_formation_nettoye(data, obj=None):
    """Validation légère du cycle référentiel (lot B) — retourne (payload, erreur)."""
    code = (data.get('code') or '').strip().upper()
    if code and RefFormation.objects.filter(code=code).exclude(
            pk=obj.pk if obj else None).exists():
        return None, {'error': f'Le code « {code} » est déjà utilisé par un autre cycle.'}
    intitule = (data.get('intitule') or '').strip()
    if not intitule:
        return None, {'error': '« intitule » est requis.'}
    type_diplome = (data.get('type_diplome') or '').strip().upper()
    valides = {c[0] for c in RefFormation.TypeDiplome.choices}
    if type_diplome and type_diplome not in valides:
        return None, {'error': 'Type de diplôme inconnu (LICENCE, MASTER, DOCTORAT, '
                              'DUT, PROFESSIONNALISANT, AUTRE).'}
    payload = {
        'intitule': intitule, 'code': code, 'type_diplome': type_diplome,
        'domaine': (data.get('domaine') or '').strip(),
        'mention': (data.get('mention') or '').strip(),
        'description': (data.get('description') or '').strip(),
        'duree_annees': data.get('duree_annees'),
        'nb_semestres': data.get('nb_semestres'),
        'nb_credites': data.get('nb_credites'),
        'actif': data.get('actif', True),
    }
    for cle in ('duree_annees', 'nb_semestres', 'nb_credites'):
        if payload[cle] in (None, '', 0, '0'):
            payload[cle] = None
        else:
            try:
                payload[cle] = int(payload[cle])
            except (TypeError, ValueError):
                return None, {'error': f'« {cle} » doit être un entier.'}
    return payload, None


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_formation_list(request):
    if request.method == 'GET':
        data = [_ref_formation_payload(o) for o in RefFormation.objects.all()]
        return Response(data)
    payload, err = _ref_formation_nettoye(request.data)
    if err:
        return Response(err, status=400)
    obj = RefFormation.objects.create(**payload)
    return Response(_ref_formation_payload(obj), status=201)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_formation_detail(request, pk):
    try:
        obj = RefFormation.objects.get(pk=pk)
    except RefFormation.DoesNotExist:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PUT':
        data = dict(request.data)
        # PUT à sémantique douce : champs absents conservés.
        for cle in ('code', 'type_diplome', 'domaine', 'mention', 'description',
                    'duree_annees', 'nb_semestres', 'nb_credites'):
            if cle not in data and getattr(obj, cle, None) not in (None, ''):
                data[cle] = getattr(obj, cle)
        if 'intitule' not in data:
            data['intitule'] = obj.intitule
        if 'actif' not in data:
            data['actif'] = obj.actif
        payload, err = _ref_formation_nettoye(data, obj=obj)
        if err:
            return Response(err, status=400)
        for cle, valeur in payload.items():
            setattr(obj, cle, valeur)
        obj.save()
        return Response(_ref_formation_payload(obj))
    if Formation.objects.filter(ref_formation=obj).exists():
        return Response({'error': 'Des sessions de formation s’appuient sur ce cycle : '
                                  'désactivez-le plutôt que de le supprimer.'}, status=409)
    obj.delete()
    return Response(status=204)


def _serialize_ref_module(obj):
    formation_ids = list(obj.formations.values_list('id', flat=True))
    formations = [
        {'id': f.id, 'intitule': f.intitule}
        for f in obj.formations.order_by('intitule')
    ]
    volumes_horaires = [
        {
            'formation_id': v.formation_id,
            'formation_intitule': v.formation.intitule if v.formation_id else '',
            'categorie_id': v.categorie_id,
            'categorie_libelle': v.categorie.libelle,
            'volume_horaire': v.volume_horaire,
        }
        for v in obj.volumes_horaires.select_related('formation', 'categorie').order_by(
            'formation__intitule', 'categorie__libelle',
        )
    ]
    # Compatibilité descendante
    volumes_par_categorie = volumes_horaires
    return {
        'id': obj.id,
        'intitule': obj.intitule,
        'volume_horaire': obj.volume_horaire,
        'volumes_horaires': volumes_horaires,
        'volumes_par_categorie': volumes_par_categorie,
        'actif': obj.actif,
        'formation_ids': formation_ids,
        'formations': formations,
    }


def _apply_ref_module_volumes_horaires(obj, volumes_horaires, formation_ids=None, *, required=False, replace=True):
    """Enregistre les volumes horaire (formation × catégorie)."""
    if volumes_horaires is None:
        if required:
            return Response(
                {'volumes_horaires': ['Renseignez au moins un volume (formation × catégorie).']},
                status=400,
            )
        return None
    if not isinstance(volumes_horaires, (list, tuple)):
        return Response({'volumes_horaires': ['Liste invalide.']}, status=400)
    allowed_formations = set(formation_ids or obj.formations.values_list('id', flat=True))
    if replace:
        obj.volumes_horaires.all().delete()
    created = 0
    for item in volumes_horaires:
        if not isinstance(item, dict):
            continue
        try:
            fid = int(item.get('formation_id'))
        except (TypeError, ValueError):
            if len(allowed_formations) == 1:
                fid = next(iter(allowed_formations))
            else:
                continue
        try:
            cid = int(item.get('categorie_id'))
        except (TypeError, ValueError):
            continue
        if allowed_formations and fid not in allowed_formations:
            return Response(
                {'volumes_horaires': ['Volume hors des formations sélectionnées.']},
                status=400,
            )
        raw_vh = item.get('volume_horaire')
        if raw_vh is None or raw_vh == '':
            continue
        try:
            vh = float(raw_vh)
        except (TypeError, ValueError):
            return Response({'volumes_horaires': ['Volume horaire invalide.']}, status=400)
        if vh < 0:
            return Response({'volumes_horaires': ['Volume horaire négatif.']}, status=400)
        if replace:
            obj.volumes_horaires.create(
                formation_id=fid,
                categorie_id=cid,
                volume_horaire=vh,
            )
        else:
            obj.volumes_horaires.update_or_create(
                formation_id=fid,
                categorie_id=cid,
                defaults={'volume_horaire': vh},
            )
        created += 1
    if required and created == 0:
        return Response(
            {'volumes_horaires': ['Renseignez au moins un volume (formation × catégorie).']},
            status=400,
        )
    return None


def _apply_ref_module_formations(obj, formation_ids, *, merge=False):
    """Associe une ou plusieurs formations au module référentiel."""
    if formation_ids is None:
        return None
    if not isinstance(formation_ids, (list, tuple)):
        return Response({'formations': ['Liste de formations invalide.']}, status=400)
    ids = []
    for raw in formation_ids:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            return Response({'formations': ['Identifiant de formation invalide.']}, status=400)
    if not ids:
        return Response({'formations': ['Au moins une formation est requise.']}, status=400)
    valid_ids = set(RefFormation.objects.filter(id__in=ids).values_list('id', flat=True))
    if len(valid_ids) != len(set(ids)):
        return Response({'formations': ['Une ou plusieurs formations sont introuvables.']}, status=400)
    if merge:
        current = set(obj.formations.values_list('id', flat=True))
        obj.formations.set(current | valid_ids)
    else:
        obj.formations.set(ids)
    return None


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_module_list(request):
    if request.method == 'GET':
        qs = RefModule.objects.order_by('intitule').prefetch_related(
            'formations',
            'volumes_horaires',
            'volumes_horaires__categorie',
            'volumes_horaires__formation',
        )
        return Response([_serialize_ref_module(m) for m in qs])
    intitule = RefModule.normalize_intitule(request.data.get('intitule', ''))
    if not intitule:
        return Response({'intitule': ['Intitulé obligatoire.']}, status=400)
    existing = RefModule.objects.filter(intitule__iexact=intitule).first()
    if existing:
        # Un intitulé = une entrée catalogue ; on rattache les formations supplémentaires.
        obj = existing
        if 'actif' in request.data:
            obj.actif = request.data.get('actif', obj.actif)
            obj.save(update_fields=['actif'])
        err = _apply_ref_module_formations(obj, request.data.get('formation_ids'), merge=True)
        if err:
            return err
        formation_ids = list(obj.formations.values_list('id', flat=True))
        err = _apply_ref_module_volumes_horaires(
            obj,
            request.data.get('volumes_horaires', request.data.get('volumes_par_categorie', [])),
            formation_ids=formation_ids,
            required=False,
            replace=False,
        )
        if err:
            return err
        obj = RefModule.objects.prefetch_related(
            'formations',
            'volumes_horaires',
            'volumes_horaires__categorie',
            'volumes_horaires__formation',
        ).get(pk=obj.pk)
        return Response(_serialize_ref_module(obj), status=200)
    obj = RefModule.objects.create(
        intitule=intitule,
        actif=request.data.get('actif', True),
    )
    err = _apply_ref_module_formations(obj, request.data.get('formation_ids'))
    if err:
        obj.delete()
        return err
    formation_ids = list(obj.formations.values_list('id', flat=True))
    err = _apply_ref_module_volumes_horaires(
        obj,
        request.data.get('volumes_horaires', request.data.get('volumes_par_categorie', [])),
        formation_ids=formation_ids,
        required=True,
    )
    if err:
        obj.delete()
        return err
    return Response(_serialize_ref_module(obj), status=201)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_module_detail(request, pk):
    try:
        obj = RefModule.objects.prefetch_related(
            'formations',
            'volumes_horaires',
            'volumes_horaires__categorie',
            'volumes_horaires__formation',
        ).get(pk=pk)
    except RefModule.DoesNotExist:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PUT':
        if 'intitule' in request.data:
            intitule = RefModule.normalize_intitule(request.data.get('intitule', ''))
            if not intitule:
                return Response({'intitule': ['Intitulé obligatoire.']}, status=400)
            if RefModule.objects.filter(intitule__iexact=intitule).exclude(pk=obj.pk).exists():
                return Response(
                    {'detail': (
                        f'Un module « {intitule} » existe déjà dans le référentiel. '
                        'Ouvrez cette entrée pour lui rattacher d’autres formations.'
                    )},
                    status=400,
                )
            obj.intitule = intitule
        obj.actif = request.data.get('actif', obj.actif)
        obj.save()

        if 'formation_ids' in request.data:
            err = _apply_ref_module_formations(obj, request.data.get('formation_ids'))
            if err:
                return err

        if 'volumes_horaires' in request.data or 'volumes_par_categorie' in request.data:
            formation_ids = list(obj.formations.values_list('id', flat=True))
            err = _apply_ref_module_volumes_horaires(
                obj,
                request.data.get('volumes_horaires') or request.data.get('volumes_par_categorie'),
                formation_ids=formation_ids,
            )
            if err:
                return err

        return Response(_serialize_ref_module(obj))
    obj.delete()
    return Response(status=204)


SITE_FIELDS = (
    'id', 'nom', 'actif',
    'geofence_latitude', 'geofence_longitude', 'geofence_rayon_m',
)


def _serialize_site(obj):
    return {
        'id': obj.id,
        'nom': obj.nom,
        'actif': obj.actif,
        'geofence_latitude': (
            float(obj.geofence_latitude) if obj.geofence_latitude is not None else None
        ),
        'geofence_longitude': (
            float(obj.geofence_longitude) if obj.geofence_longitude is not None else None
        ),
        'geofence_rayon_m': obj.geofence_rayon_m,
    }


def _coerce_decimal(value):
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_site_list(request):
    if request.method == 'GET':
        data = [_serialize_site(s) for s in RefSite.objects.all()]
        return Response(data)
    obj = RefSite.objects.create(
        nom=request.data.get('nom', ''),
        actif=request.data.get('actif', True),
        geofence_latitude=_coerce_decimal(request.data.get('geofence_latitude')),
        geofence_longitude=_coerce_decimal(request.data.get('geofence_longitude')),
        geofence_rayon_m=request.data.get('geofence_rayon_m', 200) or 200,
    )
    return Response(_serialize_site(obj), status=201)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_site_detail(request, pk):
    try:
        obj = RefSite.objects.get(pk=pk)
    except RefSite.DoesNotExist:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PUT':
        obj.nom = request.data.get('nom', obj.nom)
        obj.actif = request.data.get('actif', obj.actif)
        if 'geofence_latitude' in request.data:
            obj.geofence_latitude = _coerce_decimal(request.data.get('geofence_latitude'))
        if 'geofence_longitude' in request.data:
            obj.geofence_longitude = _coerce_decimal(request.data.get('geofence_longitude'))
        if 'geofence_rayon_m' in request.data:
            rayon = request.data.get('geofence_rayon_m')
            obj.geofence_rayon_m = int(rayon) if rayon not in (None, '') else 200
        obj.save()
        return Response(_serialize_site(obj))
    obj.delete()
    return Response(status=204)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_batiment_list(request):
    if request.method == 'GET':
        data = list(RefBatiment.objects.values('id', 'nom', 'site_id', 'actif'))
        return Response(data)
    obj = RefBatiment.objects.create(
        nom=request.data.get('nom', ''),
        site_id=request.data.get('site_id'),
        actif=request.data.get('actif', True),
    )
    return Response({'id': obj.id, 'nom': obj.nom, 'site_id': obj.site_id, 'actif': obj.actif}, status=201)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_batiment_detail(request, pk):
    try:
        obj = RefBatiment.objects.get(pk=pk)
    except RefBatiment.DoesNotExist:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PUT':
        obj.nom = request.data.get('nom', obj.nom)
        obj.site_id = request.data.get('site_id', obj.site_id)
        obj.actif = request.data.get('actif', obj.actif)
        obj.save()
        return Response({'id': obj.id, 'nom': obj.nom, 'site_id': obj.site_id, 'actif': obj.actif})
    obj.delete()
    return Response(status=204)


def _parse_optional_pk(value):
    if value in (None, '', False):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return False


def _serialize_ref_salle(obj):
    return {
        'id': obj.id,
        'nom': obj.nom,
        'site_id': obj.site_id,
        'batiment_id': obj.batiment_id,
        'type_lieu': obj.type_lieu,
        'capacite': obj.capacite,
        'equipements': obj.equipements,
        'indisponible_du': obj.indisponible_du,
        'indisponible_au': obj.indisponible_au,
        'actif': obj.actif,
    }


def _create_or_update_ref_salle(obj, data, *, exclude_pk=None):
    nom = ' '.join(str(data.get('nom') or '').split())
    if not nom:
        return None, Response({'detail': 'Le nom de la salle est obligatoire.'}, status=400)

    site_id = _parse_optional_pk(data.get('site_id'))
    if site_id is False:
        return None, Response({'detail': 'Site invalide.'}, status=400)
    if not site_id:
        return None, Response({'detail': 'Le site est obligatoire.'}, status=400)
    if not RefSite.objects.filter(pk=site_id).exists():
        return None, Response({'detail': 'Site introuvable.'}, status=400)

    batiment_id = _parse_optional_pk(data.get('batiment_id'))
    if batiment_id is False:
        return None, Response({'detail': 'Bâtiment invalide.'}, status=400)
    if batiment_id:
        batiment = RefBatiment.objects.filter(pk=batiment_id).first()
        if not batiment:
            return None, Response({'detail': 'Bâtiment introuvable.'}, status=400)
        if batiment.site_id != site_id:
            return None, Response(
                {'detail': 'Ce bâtiment n’appartient pas au site sélectionné.'},
                status=400,
            )
    else:
        batiment_id = None

    type_lieu = str(data.get('type_lieu') or RefSalle.TypeLieu.SALLE).strip().upper()
    if type_lieu not in RefSalle.TypeLieu.values:
        type_lieu = RefSalle.TypeLieu.SALLE

    capacite = data.get('capacite')
    if capacite in (None, ''):
        capacite = None
    else:
        try:
            capacite = int(capacite)
        except (TypeError, ValueError):
            return None, Response({'detail': 'Capacité invalide.'}, status=400)
        if capacite < 0:
            return None, Response({'detail': 'La capacité ne peut pas être négative.'}, status=400)

    equipements = str(data.get('equipements') or '')[:255]

    dup = RefSalle.objects.filter(site_id=site_id, nom__iexact=nom)
    if batiment_id:
        dup = dup.filter(batiment_id=batiment_id)
    else:
        dup = dup.filter(batiment_id__isnull=True)
    if exclude_pk:
        dup = dup.exclude(pk=exclude_pk)
    if dup.exists():
        lieu = 'ce bâtiment' if batiment_id else 'ce site'
        return None, Response(
            {'detail': f'Une salle « {nom} » existe déjà pour {lieu}.'},
            status=400,
        )

    actif = data.get('actif', True if obj is None else obj.actif)
    fields = dict(
        nom=nom,
        site_id=site_id,
        batiment_id=batiment_id,
        type_lieu=type_lieu,
        capacite=capacite,
        equipements=equipements,
        actif=actif,
        type_espace_id=data.get('type_espace_id') or None,
    )
    try:
        if obj is None:
            obj = RefSalle.objects.create(**fields)
        else:
            for key, value in fields.items():
                setattr(obj, key, value)
            obj.save()
    except IntegrityError as exc:
        err = str(exc).lower()
        if 'unique' in err or 'duplicate' in err:
            return None, Response(
                {'detail': f'Une salle « {nom} » existe déjà pour ce site.'},
                status=400,
            )
        return None, Response(
            {'detail': 'Impossible d’enregistrer cette salle. Vérifiez le site et le type de lieu.'},
            status=400,
        )
    return obj, None


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_salle_list(request):
    if request.method == 'GET':
        data = list(RefSalle.objects.values(
            'id', 'nom', 'site_id', 'batiment_id', 'type_lieu', 'capacite', 'equipements', 'actif',
            'type_espace_id',
        ))
        return Response(data)
    obj, err = _create_or_update_ref_salle(None, request.data)
    if err:
        return err
    return Response(_serialize_ref_salle(obj), status=201)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_salle_detail(request, pk):
    try:
        obj = RefSalle.objects.get(pk=pk)
    except RefSalle.DoesNotExist:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PUT':
        payload = {
            'nom': request.data.get('nom', obj.nom),
            'site_id': request.data.get('site_id', obj.site_id),
            'batiment_id': request.data.get('batiment_id') if 'batiment_id' in request.data else obj.batiment_id,
            'type_lieu': request.data.get('type_lieu', obj.type_lieu),
            'capacite': request.data.get('capacite', obj.capacite),
            'equipements': request.data.get('equipements', obj.equipements),
            'actif': request.data.get('actif', obj.actif),
        }
        obj, err = _create_or_update_ref_salle(obj, payload, exclude_pk=obj.pk)
        if err:
            return err
        return Response(_serialize_ref_salle(obj))
    obj.delete()
    return Response(status=204)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_categorie_list(request):
    if request.method == 'GET':
        data = list(RefCategorie.objects.values('id', 'libelle', 'actif'))
        return Response(data)
    obj = RefCategorie.objects.create(
        libelle=request.data.get('libelle', ''),
        actif=request.data.get('actif', True),
    )
    return Response({'id': obj.id, 'libelle': obj.libelle, 'actif': obj.actif}, status=201)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_categorie_detail(request, pk):
    try:
        obj = RefCategorie.objects.get(pk=pk)
    except RefCategorie.DoesNotExist:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PUT':
        obj.libelle = request.data.get('libelle', obj.libelle)
        obj.actif = request.data.get('actif', obj.actif)
        obj.save()
        return Response({'id': obj.id, 'libelle': obj.libelle, 'actif': obj.actif})
    obj.delete()
    return Response(status=204)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_grade_list(request):
    if request.method == 'GET':
        data = list(RefGrade.objects.values('id', 'libelle', 'categorie_id', 'actif'))
        return Response(data)
    obj = RefGrade.objects.create(
        libelle=request.data.get('libelle', ''),
        categorie_id=request.data.get('categorie_id') or None,
        actif=request.data.get('actif', True),
    )
    return Response({'id': obj.id, 'libelle': obj.libelle, 'categorie_id': obj.categorie_id, 'actif': obj.actif}, status=201)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_grade_detail(request, pk):
    try:
        obj = RefGrade.objects.get(pk=pk)
    except RefGrade.DoesNotExist:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PUT':
        obj.libelle = request.data.get('libelle', obj.libelle)
        obj.categorie_id = request.data.get('categorie_id') or None
        obj.actif = request.data.get('actif', obj.actif)
        obj.save()
        return Response({'id': obj.id, 'libelle': obj.libelle, 'categorie_id': obj.categorie_id, 'actif': obj.actif})
    obj.delete()
    return Response(status=204)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_type_secretariat_list(request):
    if request.method == 'GET':
        data = list(RefTypeSecretariat.objects.values('id', 'libelle', 'actif'))
        return Response(data)
    obj = RefTypeSecretariat.objects.create(
        libelle=request.data.get('libelle', ''),
        actif=request.data.get('actif', True),
    )
    return Response({'id': obj.id, 'libelle': obj.libelle, 'actif': obj.actif}, status=201)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsDFRC])
def ref_type_secretariat_detail(request, pk):
    try:
        obj = RefTypeSecretariat.objects.get(pk=pk)
    except RefTypeSecretariat.DoesNotExist:
        return Response({'error': 'Introuvable'}, status=404)
    if request.method == 'PUT':
        obj.libelle = request.data.get('libelle', obj.libelle)
        obj.actif = request.data.get('actif', obj.actif)
        obj.save()
        return Response({'id': obj.id, 'libelle': obj.libelle, 'actif': obj.actif})
    obj.delete()
    return Response(status=204)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def module_list_api(request, formation_pk):
    """List or create modules for a formation."""
    formation, err = formation_or_response(request.user, formation_pk)
    if err:
        return err

    if request.method == 'GET':
        from .serializer_querysets import annotate_modules_for_serializer
        modules_qs = formation.modules.order_by('ordre', 'intitule')
        if request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT') and request.user.secretariat:
            modules_qs = modules_qs.filter(secretariat=request.user.secretariat)
        elif request.user.role == 'ENCADRANT':
            modules_qs = modules_qs.filter(superviseur=request.user)
        modules = annotate_modules_for_serializer(modules_qs)
        return Response(ModuleSerializer(modules, many=True).data)

    # POST — create module
    intitule = request.data.get('intitule', '').strip()
    if not intitule:
        return Response({'detail': 'intitule est requis.'}, status=400)
    duree = request.data.get('duree_prevue_heures', 0)
    ordre = request.data.get('ordre', formation.modules.count() + 1)
    from django.db import IntegrityError
    try:
        site_id = request.data.get('site_id')
        site_name = (request.data.get('site', '') or '').strip()
        site_obj = None
        if site_id not in (None, '', 0, '0'):
            try:
                site_obj = RefSite.objects.get(pk=int(site_id))
            except (RefSite.DoesNotExist, ValueError, TypeError):
                site_obj = None
        elif site_name:
            # On crée au besoin pour éviter un FK null qui casserait la géofence.
            site_obj, _ = RefSite.objects.get_or_create(nom=site_name, defaults={'actif': True})

        module = Module.objects.create(
            formation=formation,
            intitule=intitule,
            duree_prevue_heures=duree,
            ordre=ordre,
            grade=request.data.get('grade', ''),
            groupe=request.data.get('groupe', ''),
            vague=request.data.get('vague', ''),
            statut=request.data.get('statut', 'PLANIFIEE'),
            date_debut=request.data.get('date_debut') or None,
            date_fin=request.data.get('date_fin') or None,
            site=site_obj,
            site_legacy=site_name,
            batiment=request.data.get('batiment', ''),
            salle=request.data.get('salle', ''),
        )
    except IntegrityError:
        return Response({'detail': f'Un module "{intitule}" existe déjà pour cette formation.'}, status=400)
    return Response(ModuleSerializer(module).data, status=201)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def module_detail_api(request, formation_pk, module_pk):
    """Get, update or delete a module."""
    formation, module, err = module_or_response(request.user, formation_pk, module_pk)
    if err:
        return err

    if request.method == 'GET':
        return Response(ModuleSerializer(module).data)

    if request.method in ('PUT', 'PATCH'):
        fields = [
            'intitule', 'duree_prevue_heures', 'ordre', 'statut',
            'grade', 'groupe', 'vague',
            'site', 'site_id', 'batiment', 'salle',
            'date_debut', 'date_fin',
            'formateur', 'secretariat', 'superviseur',
        ]
        old_date_debut = module.date_debut  # avant modification
        # Champs dont une valeur vide doit être convertie en NULL
        nullable_fields = {'formateur', 'secretariat', 'superviseur', 'duree_prevue_heures',
                           'date_debut', 'date_fin', 'grade', 'groupe', 'vague'}

        # Champs texte qui stockent '' plutôt que NULL
        str_fields = {'batiment', 'salle', 'intitule', 'statut'}

        with transaction.atomic():
            for f in fields:
                if f in request.data:
                    val = request.data[f]
                    if f in ('site', 'site_id'):
                        # Normalisation: on accepte soit site_id, soit site (nom).
                        new_site = None
                        if 'site_id' in request.data:
                            raw_id = request.data.get('site_id')
                            if raw_id not in (None, '', 0, '0'):
                                try:
                                    new_site = RefSite.objects.get(pk=int(raw_id))
                                except (RefSite.DoesNotExist, ValueError, TypeError):
                                    new_site = None
                        if new_site is None and 'site' in request.data:
                            raw_name = (request.data.get('site') or '').strip()
                            if raw_name:
                                new_site, _ = RefSite.objects.get_or_create(
                                    nom=raw_name, defaults={'actif': True}
                                )
                                module.site_legacy = raw_name
                            else:
                                module.site_legacy = ''
                        module.site = new_site
                        continue
                    if f in nullable_fields and val in (None, '', ''):
                        val = None
                    elif f in str_fields and val is None:
                        val = ''
                    setattr(module, f, val)
            module.save()
            module.refresh_from_db()

            # Si date_debut a changé, décaler toutes les séances non démarrées
            # du même delta (préserve les écarts relatifs entre séances).
            new_date_debut = module.date_debut
            if (
                'date_debut' in request.data
                and old_date_debut and new_date_debut
                and old_date_debut != new_date_debut
            ):
                delta = new_date_debut - old_date_debut
                sessions_to_shift = list(
                    module.sessions.filter(demarree_le__isnull=True)
                )
                # Ordre descendant si décalage vers l'avant, ascendant sinon,
                # pour éviter les collisions temporaires sur unique_together
                # (module, date_journee, numero).
                sessions_to_shift.sort(
                    key=lambda s: (s.date_journee, s.numero),
                    reverse=(delta.days > 0),
                )
                for s in sessions_to_shift:
                    s.date_journee = s.date_journee + delta
                    s.save(update_fields=['date_journee'])

        return Response(ModuleSerializer(module).data)

    # DELETE
    if module.sessions.exists():
        return Response({'detail': 'Impossible de supprimer un module qui a des séances.'}, status=400)
    module.delete()
    return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def module_archive_api(request, formation_pk, module_pk):
    """Archive un module : masqué des listes opérationnelles, visible dans l'espace Archives."""
    if not can_archive_module(request.user):
        return Response({'detail': 'Action non autorisée.'}, status=403)

    formation, module, err = module_or_response(request.user, formation_pk, module_pk)
    if err:
        return err

    if module.archived:
        return Response({'detail': 'Ce module est déjà archivé.'}, status=400)

    if request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
        if not request.user.secretariat or module.secretariat_id != request.user.secretariat_id:
            return Response({'detail': 'Module hors de votre secrétariat.'}, status=403)

    active_sessions = module.sessions.filter(
        demarree_le__isnull=False,
        terminee_le__isnull=True,
    ).exists()
    if active_sessions:
        return Response(
            {'detail': 'Impossible d\'archiver un module avec une séance en cours.'},
            status=400,
        )

    now = timezone.now()
    module.archived = True
    module.archived_at = now
    module.archived_by = request.user
    module.save(update_fields=['archived', 'archived_at', 'archived_by'])

    _log_audit(
        action=AuditLog.Action.MODULE_ARCHIVE,
        request=request,
        formation=formation,
        extra={
            'module_id': module.pk,
            'module_intitule': module.intitule,
            'formation_id': formation.pk,
        },
    )

    return Response({
        'detail': 'Module archivé avec succès.',
        'archived': True,
        'archived_at': module.archived_at,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def module_unarchive_api(request, formation_pk, module_pk):
    """Désarchive un module : réintégré dans les listes opérationnelles."""
    if not can_unarchive_module(request.user):
        return Response({'detail': 'Action non autorisée.'}, status=403)

    formation, module, err = module_unarchive_or_response(request.user, formation_pk, module_pk)
    if err:
        return err

    if request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
        if not request.user.secretariat or module.secretariat_id != request.user.secretariat_id:
            return Response({'detail': 'Module hors de votre secrétariat.'}, status=403)

    module.archived = False
    module.archived_at = None
    module.archived_by = None
    module.save(update_fields=['archived', 'archived_at', 'archived_by'])

    _log_audit(
        action=AuditLog.Action.MODULE_UNARCHIVE,
        request=request,
        formation=formation,
        extra={
            'module_id': module.pk,
            'module_intitule': module.intitule,
            'formation_id': formation.pk,
        },
    )

    return Response({
        'detail': 'Module désarchivé avec succès.',
        'archived': False,
    })


def module_presences_cache_key(module_pk):
    return f"module_presences_v1_{module_pk}"


def _build_module_presences_list(module):
    """Liste sérialisée des pointages d'un module (participants, formateurs, encadrants)."""
    cache_key = module_presences_cache_key(module.pk)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    from presences.models import Pointage
    from presences.duree import duree_minutes_effective

    pointages_part_qs = Pointage.objects.filter(
        session__module=module, participant__isnull=False
    ).select_related('participant', 'session').order_by('date_journee', 'timestamp_entree')

    pointages_fmt_qs = Pointage.objects.filter(
        session__module=module, formateur__isnull=False
    ).select_related('formateur', 'session').order_by('date_journee', 'timestamp_entree')

    pointages_enc_qs = Pointage.objects.filter(
        session__module=module, encadrant__isnull=False
    ).select_related('encadrant', 'session').order_by('date_journee', 'timestamp_entree')

    presences = []
    for pt in pointages_part_qs:
        p = pt.participant
        s = pt.session
        presences.append({
            'type_personne': 'participant',
            'participant_id': p.id,
            'formateur_id': None,
            'nom': p.nom,
            'prenom': p.prenom,
            'matricule': p.matricule,
            'numerobadge': None,
            'date_journee': str(pt.date_journee),
            'session_id': pt.session_id,
            'session_date': str(s.date_journee) if s and s.date_journee else None,
            'session_intitule': s.intitule if s and s.intitule else (f'Séance {s.numero}' if s else ''),
            'session_numero': s.numero if s else None,
            'timestamp_entree': pt.timestamp_entree.isoformat() if pt.timestamp_entree else None,
            'timestamp_sortie': pt.timestamp_sortie.isoformat() if pt.timestamp_sortie else None,
            'duree_minutes': duree_minutes_effective(pt),
            'statut': pt.statut,
        })

    for pt in pointages_fmt_qs:
        f_obj = pt.formateur
        s = pt.session
        presences.append({
            'type_personne': 'formateur',
            'participant_id': None,
            'formateur_id': f_obj.id,
            'nom': f_obj.nom,
            'prenom': f_obj.prenom,
            'matricule': None,
            'numerobadge': f_obj.numerobadge,
            'date_journee': str(pt.date_journee),
            'session_id': pt.session_id,
            'session_date': str(s.date_journee) if s and s.date_journee else None,
            'session_intitule': s.intitule if s and s.intitule else (f'Séance {s.numero}' if s else ''),
            'session_numero': s.numero if s else None,
            'timestamp_entree': pt.timestamp_entree.isoformat() if pt.timestamp_entree else None,
            'timestamp_sortie': pt.timestamp_sortie.isoformat() if pt.timestamp_sortie else None,
            'duree_minutes': duree_minutes_effective(pt),
            'statut': pt.statut,
        })

    for pt in pointages_enc_qs:
        enc = pt.encadrant
        s = pt.session
        presences.append({
            'type_personne': 'encadrant',
            'participant_id': None,
            'formateur_id': None,
            'encadrant_id': enc.id if enc else None,
            'nom': (enc.last_name or '') if enc else '',
            'prenom': (enc.first_name or '') if enc else '',
            'matricule': enc.matricule if enc else '',
            'numerobadge': None,
            'date_journee': str(pt.date_journee),
            'session_id': pt.session_id,
            'session_date': str(s.date_journee) if s and s.date_journee else None,
            'session_intitule': s.intitule if s and s.intitule else (f'Séance {s.numero}' if s else ''),
            'session_numero': s.numero if s else None,
            'timestamp_entree': pt.timestamp_entree.isoformat() if pt.timestamp_entree else None,
            'timestamp_sortie': pt.timestamp_sortie.isoformat() if pt.timestamp_sortie else None,
            'duree_minutes': duree_minutes_effective(pt),
            'statut': pt.statut,
        })

    presences.sort(key=lambda x: (x['date_journee'] or '', x['timestamp_entree'] or ''))
    cache.set(module_presences_cache_key(module.pk), presences, timeout=60)
    return presences


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def module_presences_api(request, formation_pk, module_pk):
    """Présences d'un module uniquement (endpoint léger pour le polling)."""
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    _, module, err = module_or_response(request.user, formation_pk, module_pk)
    if err:
        return err

    return Response({'presences': _build_module_presences_list(module)})


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def module_full_detail_api(request, formation_pk, module_pk):
    """Retourne le détail complet d'un module : infos + séances + participants de la formation."""
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    formation, module, err = module_or_response(request.user, formation_pk, module_pk)
    if err:
        return err

    from .serializers import SessionSerializer, ParticipantSerializer
    from presences.models import Pointage
    from .duree_prevue_resolve import (
        module_edt_raw_hours,
        _ref_module_volume_hours,
        _get_module_participants_categories,
        resolve_module_volume_contractuel_heures,
    )
    module = Module.objects.select_related('secretariat', 'formateur', 'superviseur').get(pk=module_pk, formation=formation)
    from .serializer_querysets import annotate_sessions_for_serializer
    sessions = annotate_sessions_for_serializer(
        module.sessions.all().order_by('date_journee', 'numero')
    )
    participants = module.module_participants.select_related('participant').all()
    formateurs_assignes = module.module_formateurs.select_related('formateur').all()

    # Calculer les volumes horaires par catégorie
    cat_counts = _get_module_participants_categories(module)
    volumes_par_categorie = {}
    for cat in cat_counts.keys():
        vol = _ref_module_volume_hours(module, cat)
        volumes_par_categorie[cat] = vol if vol > 0 else None

    formateur_nom = None
    if module.formateur:
        formateur_nom = f"{module.formateur.prenom} {module.formateur.nom}".strip()

    presences = _build_module_presences_list(module)

    nb_presents = (
        Pointage.objects.filter(session__module=module, participant__isnull=False).values('participant').distinct().count()
        + Pointage.objects.filter(session__module=module, formateur__isnull=False).values('formateur').distinct().count()
        + Pointage.objects.filter(session__module=module, encadrant__isnull=False).values('encadrant').distinct().count()
    )

    encadrants = []
    if module.superviseur_id:
        sup = module.superviseur
        encadrants.append({
            'id': sup.id,
            'nom': sup.last_name or '',
            'prenom': sup.first_name or '',
            'matricule': sup.matricule or '',
            'email': sup.email or '',
            'telephone': sup.telephone or '',
            'username': sup.username,
        })

    # Volume contractuel : référentiel (formation × catégorie) prioritaire sur la fiche module
    contractuelle_val, _contractuelle_source = resolve_module_volume_contractuel_heures(module)
    contractuelle = contractuelle_val if contractuelle_val > 0 else None
    planifiee = module_edt_raw_hours(module) or None
    ecart = None
    if contractuelle and planifiee is not None:
        ecart = round(float(contractuelle) - float(planifiee), 2)
        if abs(ecart) < 0.01:
            ecart = 0

    return Response({
        'id': module.id,
        'intitule': module.intitule,
        'duree_prevue_heures': module.duree_prevue_heures,
        'duree_contractuelle_heures': contractuelle,
        'duree_contractuelle_par_categorie': volumes_par_categorie if len(volumes_par_categorie) > 1 else None,
        'duree_planifiee_heures': planifiee,
        'duree_ecart_heures': ecart,
        'duree_totale_heures': planifiee,
        'ordre': module.ordre,
        'statut': module.statut,
        'statut_label': module.get_statut_display(),
        'site':     (module.site.nom if module.site else (module.site_legacy or '')),
        'site_id':  module.site_id,
        'batiment': module.batiment,
        'salle':    module.salle,
        'date_debut': module.date_debut,
        'date_fin':   module.date_fin,
        'formateur_id':  module.formateur_id,
        'formateur_nom': formateur_nom,
        'formation_id': formation.id,
        'formation': formation.formation,
        'grade':     module.grade,
        'groupe':    module.groupe,
        'vague':     module.vague,
        'categorie': (lambda: (
            (lambda lib: lib.replace('FAB', '').strip()[:1].upper() if lib else '')(
                module.secretariat.type.libelle if module.secretariat and module.secretariat.type else ''
            )
            or (module.grade[:1].upper() if module.grade else '')
        ))(),
        'secretariat_id':  module.secretariat_id,
        'secretariat_nom': module.secretariat.nom if module.secretariat else None,
        'superviseur_id':  module.superviseur_id,
        'superviseur_nom': module.superviseur.get_full_name() if module.superviseur else None,
        'nb_participants': len(participants),
        'nb_presents': nb_presents,
        'archived': module.archived,
        'sessions': SessionSerializer(sessions, many=True).data,
        'participants': ParticipantSerializer(
            [fp.participant for fp in participants], many=True
        ).data,
        'presences': presences,
        'encadrants': encadrants,
        'formateurs': [
            {
                'id': mf.formateur.id,
                'nom': mf.formateur.nom,
                'prenom': mf.formateur.prenom,
                'numerobadge': mf.formateur.numerobadge,
                'specialite': mf.formateur.specialite,
                'email': mf.formateur.email,
            }
            for mf in formateurs_assignes
        ],
    })


@api_view(['GET'])
@permission_classes([IsGestionNotesOrReadOnly])
def module_notes_list_api(request, formation_pk, module_pk):
    """Liste les auditeurs inscrits au module avec leurs notes par colonne.

    Lecture seule autorisée pour les rôles de consultation (dont ARCHIVE), y
    compris sur les modules archivés consultés depuis l'espace Archives.
    """
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    _, module, err = module_for_notes_or_response(request.user, formation_pk, module_pk)
    if err:
        return err

    colonnes = _ensure_colonnes(module)
    colonne_ids = [c.id for c in colonnes]

    inscriptions = (
        ModuleParticipant.objects.filter(module=module)
        .select_related('participant')
        .order_by('participant__nom', 'participant__prenom')
    )
    valeurs = NoteModule.objects.filter(
        colonne_id__in=colonne_ids,
    ).select_related('saisie_par', 'colonne')
    valeurs_map = {}
    for v in valeurs:
        valeurs_map.setdefault(v.participant_id, {})[v.colonne_id] = v

    syntheses_map = {
        s.participant_id: s
        for s in NoteModuleSynthese.objects.filter(module=module).select_related('saisie_par')
    }

    from suiviEvaluation.services import _get_parametres

    criteres = _get_parametres(module.formation)
    inscriptions_list = list(inscriptions)
    resumes_map = _batch_resume_module_participants(module, inscriptions_list, valeurs_map, criteres)

    rows = []
    for mp in inscriptions_list:
        p = mp.participant
        synthese = syntheses_map.get(p.id)
        resume = resumes_map.get(p.id, {})
        notes_by_colonne = {}
        for cid in colonne_ids:
            val = valeurs_map.get(p.id, {}).get(cid)
            if val and val.note is not None:
                notes_by_colonne[str(cid)] = {
                    'note': float(val.note),
                    'saisie_par': _user_display(val.saisie_par),
                    'updated_at': val.updated_at.isoformat(),
                    'statut_validation': val.statut_validation,
                    'verrouillee': val.verrouillee,
                    'validation_par': _user_display(val.validation_par),
                    'validation_le': val.validation_le.isoformat() if val.validation_le else None,
                }
            else:
                notes_by_colonne[str(cid)] = {
                    'note': None,
                    'saisie_par': _user_display(val.saisie_par) if val else None,
                    'updated_at': val.updated_at.isoformat() if val else None,
                    'statut_validation': val.statut_validation if val else 'BROUILLON',
                    'verrouillee': val.verrouillee if val else False,
                    'validation_par': _user_display(val.validation_par) if val else None,
                    'validation_le': val.validation_le.isoformat() if val and val.validation_le else None,
                }
        rows.append({
            'participant_id': p.id,
            'nom': p.nom,
            'prenom': p.prenom,
            'matricule': p.matricule or '',
            'grade': p.grade or '',
            'notes': notes_by_colonne,
            'mention': synthese.mention if synthese else '',
            'observations': synthese.observations if synthese else '',
            'saisie_par': _user_display(synthese.saisie_par) if synthese else None,
            'updated_at': synthese.updated_at.isoformat() if synthese else None,
            'moyenne': resume['moyenne'],
            'heures_presence': resume['heures_presence'],
            'heures_prevues': resume['heures_prevues'],
            'taux_presence': resume['taux_presence'],
            'admissible': resume['admissible'],
        })

    return Response({
        'colonnes': [_serialize_colonne(c) for c in colonnes],
        'criteres': criteres,
        'rows': rows,
    })


@api_view(['GET', 'POST'])
@permission_classes([IsGestionNotes])
def module_notes_colonnes_api(request, formation_pk, module_pk):
    """Liste ou ajoute une colonne de notes pour le module."""
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    _, module, err = _get_module_in_formation(request.user, formation_pk, module_pk)
    if err:
        return err

    if request.method == 'GET':
        colonnes = _ensure_colonnes(module)
        return Response([_serialize_colonne(c) for c in colonnes])

    libelle = (request.data.get('libelle') or '').strip()
    if not libelle:
        return Response({'detail': 'Le libellé de la colonne est requis.'}, status=400)

    note_max_raw = request.data.get('note_max', 20)
    try:
        note_max = float(note_max_raw)
    except (TypeError, ValueError):
        return Response({'detail': 'note_max invalide.'}, status=400)
    if note_max <= 0 or note_max > 100:
        return Response({'detail': 'note_max doit être entre 0 et 100.'}, status=400)

    last_ordre = (
        NoteModuleColonne.objects.filter(module=module)
        .order_by('-ordre')
        .values_list('ordre', flat=True)
        .first()
    ) or 0
    colonne = NoteModuleColonne.objects.create(
        module=module,
        libelle=libelle,
        ordre=last_ordre + 1,
        note_max=note_max,
    )
    return Response(_serialize_colonne(colonne), status=201)


@api_view(['DELETE'])
@permission_classes([IsGestionNotes])
def module_notes_colonne_delete_api(request, formation_pk, module_pk, colonne_pk):
    """Supprime une colonne de notes (au moins une colonne doit rester)."""
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    _, module, err = _get_module_in_formation(request.user, formation_pk, module_pk)
    if err:
        return err

    try:
        colonne = NoteModuleColonne.objects.get(pk=colonne_pk, module=module)
    except NoteModuleColonne.DoesNotExist:
        return Response({'detail': 'Colonne introuvable.'}, status=404)

    if NoteModuleColonne.objects.filter(module=module).count() <= 1:
        return Response({'detail': 'Impossible de supprimer la dernière colonne.'}, status=400)

    colonne.delete()
    return Response(status=204)


@api_view(['POST'])
@permission_classes([IsGestionNotes])
def module_notes_bulk_api(request, formation_pk, module_pk):
    """Sauvegarde en masse les notes des auditeurs d'un module."""
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    _, module, err = _get_module_in_formation(request.user, formation_pk, module_pk)
    if err:
        return err

    colonnes = {c.id: c for c in _ensure_colonnes(module)}
    items = request.data.get('notes')
    if not isinstance(items, list):
        return Response({'detail': 'Le champ "notes" (liste) est requis.'}, status=400)

    syntheses_items = request.data.get('syntheses')
    if syntheses_items is not None and not isinstance(syntheses_items, list):
        return Response({'detail': 'Le champ "syntheses" doit être une liste.'}, status=400)

    enrolled_ids = set(
        ModuleParticipant.objects.filter(module=module).values_list('participant_id', flat=True)
    )
    participants_map = {
        p.id: p for p in Participant.objects.filter(id__in=enrolled_ids)
    }

    saved = 0
    errors = []
    participant_notes_for_mention = {}

    with transaction.atomic():
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append({'index': idx, 'detail': 'Entrée invalide.'})
                continue

            participant_id = item.get('participant_id')
            colonne_id = item.get('colonne_id')
            if not participant_id or not colonne_id:
                errors.append({'index': idx, 'detail': 'participant_id et colonne_id requis.'})
                continue

            try:
                participant_id = int(participant_id)
                colonne_id = int(colonne_id)
            except (TypeError, ValueError):
                errors.append({'index': idx, 'detail': 'participant_id ou colonne_id invalide.'})
                continue

            if participant_id not in enrolled_ids:
                errors.append({'index': idx, 'detail': 'Étudiant non inscrit à ce module.'})
                continue

            colonne = colonnes.get(colonne_id)
            if not colonne:
                errors.append({'index': idx, 'detail': 'Colonne introuvable.'})
                continue

            note_max = float(colonne.note_max)
            note_raw = item.get('note')
            note_val = None
            if note_raw is not None and note_raw != '':
                try:
                    note_val = float(note_raw)
                except (TypeError, ValueError):
                    errors.append({'index': idx, 'detail': 'Note invalide.'})
                    continue
                if note_val < 0 or note_val > note_max:
                    errors.append({'index': idx, 'detail': f'La note doit être entre 0 et {note_max}.'})
                    continue

            if note_val is None:
                existing = NoteModule.objects.filter(
                    colonne=colonne, participant_id=participant_id,
                ).first()
                if existing and existing.verrouillee:
                    errors.append({'index': idx, 'detail': 'Note verrouillée : utilisez une correction motivée.'})
                    continue
                if note_deja_enregistree(existing):
                    participant = participants_map.get(participant_id)
                    if participant:
                        notifier_modification_note(
                            request.user, participant, module, colonne,
                            existing.note, None,
                        )
                NoteModule.objects.filter(colonne=colonne, participant_id=participant_id).delete()
            else:
                existing = NoteModule.objects.filter(
                    colonne=colonne, participant_id=participant_id,
                ).first()
                if existing and existing.verrouillee:
                    errors.append({'index': idx, 'detail': 'Note verrouillée : utilisez une correction motivée.'})
                    continue
                if note_deja_enregistree(existing):
                    participant = participants_map.get(participant_id)
                    if participant:
                        notifier_modification_note(
                            request.user, participant, module, colonne,
                            existing.note, note_val,
                        )
                NoteModule.objects.update_or_create(
                    colonne=colonne,
                    participant_id=participant_id,
                    defaults={
                        'note': note_val,
                        'saisie_par': request.user,
                        # Toute modification en saisie invalide une soumission en cours.
                        'statut_validation': (
                            NoteModule.StatutValidation.BROUILLON
                            if existing and existing.statut_validation == NoteModule.StatutValidation.SOUMISE
                            else existing.statut_validation if existing else NoteModule.StatutValidation.BROUILLON
                        ),
                    },
                )
                note_max = float(colonne.note_max or 20)
                if note_max <= 0:
                    note_max = 20
                participant_notes_for_mention.setdefault(participant_id, []).append(
                    float(note_val) * 20 / note_max
                )
            saved += 1

        if syntheses_items:
            for idx, item in enumerate(syntheses_items):
                if not isinstance(item, dict):
                    errors.append({'index': f'synthese-{idx}', 'detail': 'Entrée invalide.'})
                    continue

                participant_id = item.get('participant_id')
                if not participant_id:
                    errors.append({'index': f'synthese-{idx}', 'detail': 'participant_id requis.'})
                    continue

                try:
                    participant_id = int(participant_id)
                except (TypeError, ValueError):
                    errors.append({'index': f'synthese-{idx}', 'detail': 'participant_id invalide.'})
                    continue

                if participant_id not in enrolled_ids:
                    errors.append({'index': f'synthese-{idx}', 'detail': 'Étudiant non inscrit.'})
                    continue

                observations = (item.get('observations') or '').strip()
                mention = (item.get('mention') or '').strip()

                if not mention:
                    existing_notes = list(participant_notes_for_mention.get(participant_id, []))
                    if not existing_notes:
                        for v in NoteModule.objects.filter(
                            colonne__module=module,
                            participant_id=participant_id,
                            note__isnull=False,
                        ).select_related('colonne'):
                            note_max = float(v.colonne.note_max or 20)
                            if note_max <= 0:
                                note_max = 20
                            existing_notes.append(float(v.note) * 20 / note_max)
                    mention = _mention_from_notes(existing_notes)

                if not mention and not observations:
                    NoteModuleSynthese.objects.filter(module=module, participant_id=participant_id).delete()
                    saved += 1
                    continue

                if mention and mention not in dict(NoteModuleSynthese.Mention.choices):
                    errors.append({'index': f'synthese-{idx}', 'detail': 'Mention invalide.'})
                    continue

                NoteModuleSynthese.objects.update_or_create(
                    module=module,
                    participant_id=participant_id,
                    defaults={
                        'mention': mention,
                        'observations': observations,
                        'saisie_par': request.user,
                    },
                )
                saved += 1

    from suiviEvaluation.services import calculer_moyennes_module_tous
    calculer_moyennes_module_tous(module)

    return Response({'saved': saved, 'errors': errors})


@api_view(['POST'])
@permission_classes([IsGestionNotes])
def module_notes_workflow_api(request, formation_pk, module_pk):
    """POST .../notes/workflow/ — cycle BROUILLON → SOUMISE → VALIDEE.

    Corps : ``{'action': 'soumettre'|'annuler'|'valider'|'deverrouiller'|'corriger',
    'items': [{'participant_id':…, 'colonne_id':…, 'note':…, 'motif':…}, …]}``.
    Une note ``VALIDEE`` est verrouillée : seule ``corriger`` (motif obligatoire)
    la modifie, avec trace append-only + AuditLog + JournalScolarite.
    """
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    _, module, err = _get_module_in_formation(request.user, formation_pk, module_pk)
    if err:
        return err

    action = (request.data.get('action') or '').strip()
    if action not in actions_valides():
        return Response({
            'detail': f'Action invalide. Actions possibles : {", ".join(actions_valides())}.',
        }, status=400)

    return Response(appliquer_workflow(module, action, request.data.get('items'), request.user))


@api_view(['GET'])
@permission_classes([IsGestionNotesOrReadOnly])
def module_notes_historique_api(request, formation_pk, module_pk):
    """GET .../notes/historique/ — corrections append-only des notes du module."""
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    _, module, err = module_for_notes_or_response(request.user, formation_pk, module_pk)
    if err:
        return err

    corrections = (
        CorrectionNoteModule.objects.filter(module=module)
        .select_related('colonne', 'participant', 'auteur')
        .order_by('-created_at')[:200]
    )
    return Response({
        'corrections': [
            {
                'id': c.id,
                'colonne': c.colonne.libelle,
                'participant_id': c.participant_id,
                'participant': (f"{c.participant.nom} {c.participant.prenom}").strip(),
                'ancienne_valeur': float(c.ancienne_valeur) if c.ancienne_valeur is not None else None,
                'nouvelle_valeur': float(c.nouvelle_valeur) if c.nouvelle_valeur is not None else None,
                'motif': c.motif,
                'auteur': _user_display(c.auteur),
                'created_at': c.created_at.isoformat(),
            }
            for c in corrections
        ],
    })


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def note_modifications_notifications_api(request):
    """GET/PATCH /api/formations/notes/notifications/ — notifications Direction (modifications de notes)."""
    if get_user_role(request.user) != get_user_model().Role.DIRECTION:
        return Response({'detail': 'Accès réservé à la Direction.'}, status=403)

    qs = NotificationModificationNote.objects.filter(
        destinataire=request.user,
    ).select_related('auteur', 'participant', 'module')

    if request.method == 'GET':
        items = list(qs[:50])
        return Response({
            'notifications': [
                {
                    'id': n.id,
                    'message': n.message,
                    'auteur': n.auteur.get_full_name() or n.auteur.username if n.auteur else None,
                    'auditeur': (
                        f'{n.participant.nom} {n.participant.prenom}'.strip()
                        if n.participant else None
                    ),
                    'module': n.module.intitule if n.module else None,
                    'colonne': n.colonne_libelle,
                    'ancienne_note': n.ancienne_note,
                    'nouvelle_note': n.nouvelle_note,
                    'lu': n.lu,
                    'created_at': n.created_at,
                }
                for n in items
            ],
            'non_lues': qs.filter(lu=False).count(),
        })

    if request.data.get('tout'):
        qs.filter(lu=False).update(lu=True)
    else:
        ids = request.data.get('ids') or []
        qs.filter(id__in=ids).update(lu=True)
    non_lues = NotificationModificationNote.objects.filter(
        destinataire=request.user, lu=False,
    ).count()
    return Response({'non_lues': non_lues})


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def finance_ajustements_notifications_api(request):
    """GET/PATCH /api/formations/finance/notifications/ — workflow ajustements."""
    if request.user.role not in {'FINANCE', 'DIRECTION'}:
        return Response({'detail': 'Accès réservé à la finance et à la direction.'}, status=403)

    qs = NotificationFinanceAjustement.objects.filter(
        destinataire=request.user,
    ).select_related('auteur', 'ajustement')

    if request.method == 'GET':
        items = list(qs[:50])
        return Response({
            'notifications': [
                {
                    'id': n.id,
                    'evenement': n.evenement,
                    'message': n.message,
                    'auteur': n.auteur.get_full_name() or n.auteur.username if n.auteur else None,
                    'ajustement_id': n.ajustement_id,
                    'lu': n.lu,
                    'created_at': n.created_at,
                }
                for n in items
            ],
            'non_lues': qs.filter(lu=False).count(),
        })

    if request.data.get('tout'):
        qs.filter(lu=False).update(lu=True)
    else:
        ids = request.data.get('ids') or []
        qs.filter(id__in=ids).update(lu=True)
    non_lues = NotificationFinanceAjustement.objects.filter(
        destinataire=request.user, lu=False,
    ).count()
    return Response({'non_lues': non_lues})


@api_view(['POST'])
@permission_classes([CanManageModuleParticipant])
def module_add_participant(request, formation_pk, module_pk):
    """Inscrire un participant à un module — respecte les permissions du groupe (add_moduleparticipant)."""
    try:
        module = Module.objects.get(pk=module_pk, formation_id=formation_pk)
    except Module.DoesNotExist:
        return Response({'detail': 'Module introuvable.'}, status=404)
    participant_id = request.data.get('participant_id')
    if not participant_id:
        return Response({'detail': 'participant_id requis.'}, status=400)
    try:
        participant = Participant.objects.get(pk=participant_id)
    except Participant.DoesNotExist:
        return Response({'detail': 'Participant introuvable.'}, status=404)
    if ModuleParticipant.objects.filter(module=module, participant=participant).exists():
        return Response({'detail': 'Déjà inscrit.'}, status=400)
    ModuleParticipant.objects.create(module=module, participant=participant)
    return Response({'detail': f'{participant} inscrit au module.'}, status=201)


@api_view(['DELETE'])
@permission_classes([CanManageModuleParticipant])
def module_remove_participant(request, formation_pk, module_pk, participant_id):
    """Retirer un participant d'un module — respecte les permissions du groupe (delete_moduleparticipant)."""
    try:
        module = Module.objects.get(pk=module_pk, formation_id=formation_pk)
        mp = ModuleParticipant.objects.get(module=module, participant_id=participant_id)
    except (Module.DoesNotExist, ModuleParticipant.DoesNotExist):
        return Response({'detail': 'Inscription introuvable.'}, status=404)
    mp.delete()
    return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def module_add_formateur(request, formation_pk, module_pk):
    """Assigner un formateur à un module."""
    _, module, err = module_or_response(request.user, formation_pk, module_pk)
    if err:
        return err
    formateur_id = request.data.get('formateur_id')
    if not formateur_id:
        return Response({'detail': 'formateur_id requis.'}, status=400)
    try:
        formateur = Formateur.objects.get(pk=formateur_id)
    except Formateur.DoesNotExist:
        return Response({'detail': 'Formateur introuvable.'}, status=404)
    if ModuleFormateur.objects.filter(module=module, formateur=formateur).exists():
        return Response({'detail': 'Déjà assigné.'}, status=400)
    conflict = check_formateur_groupe_jour_conflict(formateur, module)
    if conflict:
        return Response({'detail': conflict}, status=400)
    ModuleFormateur.objects.create(module=module, formateur=formateur)
    return Response({'detail': f'{formateur} assigné au module.'}, status=201)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, IsSecretariatOrDFRC])
def module_remove_formateur(request, formation_pk, module_pk, formateur_id):
    """Retirer un formateur d'un module."""
    _, module, err = module_or_response(request.user, formation_pk, module_pk)
    if err:
        return err
    try:
        mf = ModuleFormateur.objects.get(module=module, formateur_id=formateur_id)
    except ModuleFormateur.DoesNotExist:
        return Response({'detail': 'Assignation introuvable.'}, status=404)
    mf.delete()
    return Response(status=204)


@api_view(['POST'])
@permission_classes([IsSecretariatOrDFRC])
def module_assign_superviseur(request, formation_pk, module_pk):
    """Assigner (ou retirer) un encadrant superviseur à un module.

    - Rôles autorisés : SECRETARIAT, CHEF_SECRETARIAT, INJS_ADMIN, CHEF_INJS_ADMIN.
    - Scope : SECRETARIAT/CHEF_SECRETARIAT ne peuvent agir que sur les modules
      de leur propre secrétariat.
    - Body : { "superviseur_id": <int|null> }  (null ou omis => retrait).
    """
    try:
        formation = Formation.objects.get(pk=formation_pk)
        module = Module.objects.select_related('secretariat', 'superviseur').get(
            pk=module_pk, formation=formation,
        )
    except Formation.DoesNotExist:
        return Response({'detail': 'Formation introuvable.'}, status=404)
    except Module.DoesNotExist:
        return Response({'detail': 'Module introuvable.'}, status=404)

    # Scope secrétariat
    user = request.user
    if user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
        if not user.secretariat or module.secretariat_id != user.secretariat_id:
            return Response(
                {'detail': "Ce module n'appartient pas à votre secrétariat."},
                status=403,
            )

    superviseur_id = request.data.get('superviseur_id')
    superviseur = None
    if superviseur_id not in (None, '', 0, '0'):
        from authentication.role_groups import user_is_mobile_encadrant
        User = get_user_model()
        try:
            superviseur = User.objects.get(pk=superviseur_id)
        except User.DoesNotExist:
            return Response(
                {'detail': 'Encadrant introuvable ou rôle incorrect.'},
                status=400,
            )
        if not user_is_mobile_encadrant(superviseur):
            return Response(
                {'detail': 'Encadrant introuvable ou rôle incorrect.'},
                status=400,
            )

    module.superviseur = superviseur
    module.save(update_fields=['superviseur'])

    _log_audit(
        action=AuditLog.Action.MODULE_ASSIGN_SUPERVISEUR,
        request=request,
        formation=formation,
        extra={
            'module_id': module.id,
            'module_intitule': module.intitule,
            'superviseur_id': superviseur.id if superviseur else None,
            'superviseur_nom': superviseur.get_full_name() if superviseur else None,
        },
    )

    return Response({
        'detail': (
            f'Encadrant {superviseur.get_full_name()} assigné au module.'
            if superviseur else 'Encadrant retiré du module.'
        ),
        'superviseur_id': superviseur.id if superviseur else None,
        'superviseur_nom': superviseur.get_full_name() if superviseur else None,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOperationalWebStaff])
def referentiels_api(request):
    """Retourne les référentiels prédéfinis pour les listes déroulantes."""
    denied = deny_finance_operational_response(request)
    if denied:
        return denied

    from .api_cache import get_cached_response, request_cache_key, referentiels_cache_version, set_cached_response

    cache_key = request_cache_key('ref_api', request, extra=(referentiels_cache_version(),))
    cached = get_cached_response(cache_key)
    if cached is not None:
        return Response(cached)

    formations = list(RefFormation.objects.filter(actif=True).values('id', 'intitule'))
    formations_reelles = list(Formation.objects.order_by('formation').values('id', 'formation'))
    modules = []
    for m in RefModule.objects.filter(actif=True).prefetch_related('formations'):
        modules.append({
            'id': m.id,
            'intitule': m.intitule,
            'volume_horaire': m.volume_horaire,
            'formation_ids': [f.id for f in m.formations.all()],
        })
    modules_actifs = list(
        Module.objects.values_list('intitule', flat=True).distinct().order_by('intitule')
    )
    sites = list(RefSite.objects.filter(actif=True).values('id', 'nom'))
    batiments = list(RefBatiment.objects.filter(actif=True).values('id', 'nom', 'site_id'))
    salles = list(RefSalle.objects.filter(actif=True).values('id', 'nom', 'site_id', 'batiment_id'))
    categories = list(RefCategorie.objects.filter(actif=True).values('id', 'libelle'))
    grades = list(RefGrade.objects.filter(actif=True).values('id', 'libelle', 'categorie_id'))
    types_secretariat = list(RefTypeSecretariat.objects.filter(actif=True).values('id', 'libelle'))
    vagues = list(RefVague.objects.filter(actif=True).order_by('ordre', 'libelle').values('id', 'libelle', 'ordre'))

    mods_groupes_qs = Module.objects.all()
    if request.user.is_authenticated and request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
        if request.user.secretariat:
            mods_groupes_qs = mods_groupes_qs.filter(secretariat=request.user.secretariat)
        else:
            mods_groupes_qs = mods_groupes_qs.none()
    elif request.user.is_authenticated and request.user.role == 'ENCADRANT':
        mods_groupes_qs = mods_groupes_qs.filter(superviseur=request.user)
    raw_module_groupes = (
        mods_groupes_qs.exclude(groupe__isnull=True)
        .exclude(groupe='')
        .values_list('groupe', flat=True)
    )
    groupes_modules = sorted(
        {g for g in (_normalize_groupe_value(v) for v in raw_module_groupes) if g},
        key=_groupe_sort_key,
    )

    raw_module_grades = (
        mods_groupes_qs.exclude(grade__isnull=True)
        .exclude(grade='')
        .values_list('grade', flat=True)
    )
    grades_modules = sorted(
        {str(v).strip() for v in raw_module_grades if str(v).strip()},
        key=lambda x: (x.lower(), x),
    )

    annees = set()
    for d_debut, d_fin in mods_groupes_qs.values_list('date_debut', 'date_fin'):
        if d_debut:
            annees.add(d_debut.year)
        if d_fin:
            annees.add(d_fin.year)
    annees = sorted(annees, reverse=True)

    payload = {
        'formations': formations,
        'formations_reelles': formations_reelles,
        'modules': modules,
        'modules_actifs': modules_actifs,
        'groupes': groupes_modules,
        'grades_modules': grades_modules,
        'sites': sites,
        'batiments': batiments,
        'salles': salles,
        'categories': categories,
        'grades': grades,
        'types_secretariat': types_secretariat,
        'vagues': vagues,
        'annees': annees,
    }
    set_cached_response(cache_key, payload, 300)
    return Response(payload)


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsDFRC])
def referentiels_gestion_api(request):
    """Toutes les tables référentielles (actifs + inactifs) — page admin Référentiels."""
    modules_data = []
    for m in RefModule.objects.order_by('intitule').prefetch_related(
        'formations', 'volumes_horaires', 'volumes_horaires__categorie',
    ):
        modules_data.append(_serialize_ref_module(m))

    return Response({
        'formations': list(RefFormation.objects.order_by('intitule').values('id', 'intitule', 'actif')),
        'modules': modules_data,
        'categories': list(RefCategorie.objects.order_by('libelle').values('id', 'libelle', 'actif')),
        'grades': list(RefGrade.objects.order_by('libelle').values('id', 'libelle', 'categorie_id', 'actif')),
        'vagues': list(RefVague.objects.order_by('ordre', 'libelle').values('id', 'libelle', 'ordre', 'actif')),
        'sites': list(RefSite.objects.order_by('nom').values(
            'id', 'nom', 'actif', 'geofence_latitude', 'geofence_longitude', 'geofence_rayon_m',
        )),
        'batiments': list(RefBatiment.objects.order_by('nom').values('id', 'nom', 'site_id', 'actif')),
        'salles': list(RefSalle.objects.order_by('nom').values(
            'id', 'nom', 'site_id', 'batiment_id', 'type_lieu', 'capacite', 'equipements', 'actif',
        )),
        'types_secretariat': list(RefTypeSecretariat.objects.order_by('libelle').values('id', 'libelle', 'actif')),
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsDFRC])
@parser_classes([MultiPartParser])
def referentiel_excel_api(request, kind):
    """Télécharge ou importe un classeur .xlsx pour un référentiel."""
    if request.method == 'GET':
        try:
            content = export_referentiel_xlsx(kind)
        except ReferentielExcelError as exc:
            return Response({'detail': str(exc)}, status=404)
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="referentiel_{kind}.xlsx"'
        return response

    uploaded = request.FILES.get('file')
    if not uploaded or not uploaded.name.lower().endswith('.xlsx'):
        return Response({'detail': 'Sélectionnez un fichier Excel au format .xlsx.'}, status=400)
    try:
        result = import_referentiel_xlsx(kind, uploaded)
    except ReferentielExcelError as exc:
        return Response({'detail': str(exc)}, status=400)
    return Response(result)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, IsDFRC])
def refvague_list_api(request):
    """Lister ou créer une vague dans le référentiel."""
    if request.method == 'GET':
        data = list(RefVague.objects.order_by('ordre', 'libelle').values('id', 'libelle', 'ordre', 'actif'))
        return Response(data)
    obj = RefVague.objects.create(
        libelle=request.data.get('libelle', ''),
        ordre=request.data.get('ordre', 1),
        actif=request.data.get('actif', True),
    )
    return Response({'id': obj.id, 'libelle': obj.libelle, 'ordre': obj.ordre, 'actif': obj.actif}, status=201)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated, IsDFRC])
def refvague_detail_api(request, pk):
    """Modifier ou supprimer une vague du référentiel."""
    try:
        obj = RefVague.objects.get(pk=pk)
    except RefVague.DoesNotExist:
        return Response({'detail': 'Vague introuvable.'}, status=404)
    if request.method == 'DELETE':
        obj.delete()
        return Response(status=204)
    obj.libelle = request.data.get('libelle', obj.libelle)
    obj.ordre = request.data.get('ordre', obj.ordre)
    obj.actif = request.data.get('actif', obj.actif)
    obj.save()
    return Response({'id': obj.id, 'libelle': obj.libelle, 'ordre': obj.ordre, 'actif': obj.actif})
