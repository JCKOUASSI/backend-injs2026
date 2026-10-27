# ══════════════════════════════════════════════════════════════════════════════
# ARCHIVE — vues dashboard web legacy (non montées dans urls.py)
#
# Ces vues ont été remplacées par le frontend React.
# Elles sont conservées ici à titre d'archive et ne doivent PAS être importées
# dans dashboard/urls.py.
# Les URL names référencés dans les templates (web-formation-detail, etc.)
# n'existent plus dans le routeur Django actif.
#
# Pour réactiver ces vues, remonter les routes dans dashboard/urls.py et
# s'assurer que les templates sont compatibles avec le modèle actuel
# (notamment Formation n'a plus grade/groupe/vague/superviseur → voir Module).
# ══════════════════════════════════════════════════════════════════════════════

from datetime import timedelta
from decimal import Decimal
from functools import wraps

from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Subquery, OuterRef, Value, IntegerField
from django.db import IntegrityError, transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from formations.models import Formation, Module, Participant, ModuleParticipant, ModuleFormateur, Formateur, QRToken, SessionModule, RefFormation, RefModule, RefSite, RefBatiment, RefSalle, RefCategorie, RefGrade, Secretariat
FormationParticipant = ModuleParticipant
FormationFormateur = ModuleFormateur
from presences.models import Pointage, AuditLog, _log_audit

User = get_user_model()


ALLOWED_WEB_ROLES = ('DIRECTION', 'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'CHEF_SECRETARIAT', 'SECRETARIAT', 'ENCADRANT')


def staff_required(view_func):
    """Décorateur : accès réservé aux rôles web autorisés."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('web-login')
        if request.user.role not in ALLOWED_WEB_ROLES:
            messages.error(request, "Accès réservé aux profils web autorisés.")
            return redirect('web-login')
        return view_func(request, *args, **kwargs)
    return wrapper


def dfrc_required(view_func):
    """Décorateur : accès réservé aux profils CPFAE/Secrétariat (mutations)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('web-login')
        if request.user.role not in ('INJS_ADMIN', 'CHEF_INJS_ADMIN', 'SECRETARIAT', 'CHEF_SECRETARIAT'):
            messages.error(request, "Accès réservé aux profils CPFAE/Secrétariat.")
            return redirect('web-dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_view_required(view_func):
    """Décorateur : accès en lecture pour Direction/CPFAE/Secrétariat."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('web-login')
        if request.user.role not in ('DIRECTION', 'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'SECRETARIAT', 'CHEF_SECRETARIAT'):
            messages.error(request, "Accès réservé à la Direction, CPFAE et Secrétariat.")
            return redirect('web-dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


ITEMS_PER_PAGE = 25


def _paginate(request, queryset, per_page=ITEMS_PER_PAGE):
    """Paginate a queryset and build query_params for template links."""
    paginator = Paginator(queryset, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    query_params = params.urlencode()
    return page_obj, query_params


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
# AUTH
# ──────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated and request.user.role in ALLOWED_WEB_ROLES:
        return redirect('web-dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user and user.role in ALLOWED_WEB_ROLES:
            login(request, user)
            _log_audit(
                action=AuditLog.Action.USER_LOGIN,
                request=request,
                cible_type='user',
                cible_numero=user.username,
                cible_nom=user.get_full_name() or user.username,
                extra={'role': user.role, 'via': 'web_legacy'},
            )
            return redirect('web-dashboard')
        elif user:
            return render(request, 'dashboard/login.html', {
                'error': 'Accès réservé à la Direction, CPFAE, Secrétariat et Encadrants.'
            })
        else:
            return render(request, 'dashboard/login.html', {
                'error': 'Identifiants invalides.'
            })
    return render(request, 'dashboard/login.html')


def logout_view(request):
    if request.user.is_authenticated:
        _log_audit(
            action=AuditLog.Action.USER_LOGOUT,
            request=request,
            cible_type='user',
            cible_numero=request.user.username,
            cible_nom=request.user.get_full_name() or request.user.username,
            extra={'via': 'web_legacy'},
        )
    logout(request)
    return redirect('web-login')


def badge_view(request):
    """Page publique de badgeage — pas de login requis."""
    return render(request, 'dashboard/badge.html')


# ──────────────────────────────────────────────
# HOME DASHBOARD
# ──────────────────────────────────────────────

@staff_required
def dashboard_home(request):
    is_sup = request.user.role == 'ENCADRANT'
    is_direction = request.user.role == 'DIRECTION'
    is_secretariat = request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT')

    today = timezone.localdate()

    if is_sup:
        module_scope = Module.objects.filter(superviseur=request.user)
    elif is_secretariat and request.user.secretariat:
        module_scope = Module.objects.filter(secretariat=request.user.secretariat)
    elif is_secretariat:
        module_scope = Module.objects.none()
    else:
        module_scope = Module.objects.all()

    cours_stats = module_scope.aggregate(
        total_cours=Count('id', distinct=True),
        cours_en_cours=Count('id', filter=Q(statut=Module.Statut.EN_COURS), distinct=True),
        cours_planifies=Count('id', filter=Q(statut=Module.Statut.PLANIFIEE), distinct=True),
        cours_termines=Count('id', filter=Q(statut=Module.Statut.TERMINEE), distinct=True),
    )

    en_cours_ids = Module.objects.filter(statut='EN_COURS').values_list('formation_id', flat=True).distinct()
    base_qs = Formation.objects.filter(id__in=en_cours_ids)
    if is_sup:
        base_qs = base_qs.filter(modules__superviseur=request.user)
    elif is_secretariat and request.user.secretariat:
        base_qs = base_qs.filter(modules__secretariat=request.user.secretariat)
    formations_en_cours = base_qs.distinct().annotate(
        nb_participants_jour=Count(
            'modules__module_participants__participant',
            filter=Q(modules__sessions__date_journee=today),
            distinct=True,
        ),
        nb_formateurs_jour=Count(
            'modules__module_formateurs__formateur',
            filter=Q(modules__sessions__date_journee=today),
            distinct=True,
        ),
    )
    # Compute nb_pointes per formation in a single query
    pointage_counts = {}
    for row in Pointage.objects.filter(
        session__module__formation__in=formations_en_cours, date_journee=today
    ).values('session__module__formation_id').annotate(
        nb_part=Count('participant', distinct=True),
        nb_fmt=Count('formateur', distinct=True),
    ):
        pointage_counts[row['session__module__formation_id']] = row['nb_part'] + row['nb_fmt']
    for f in formations_en_cours:
        f.nb_attendus = f.nb_participants_jour + f.nb_formateurs_jour
        f.nb_pointes = pointage_counts.get(f.id, 0)

    if is_sup:
        derniers_pointages = Pointage.objects.filter(
            session__module__superviseur=request.user
        ).select_related('participant', 'formateur', 'session__module__formation').order_by('-updated_at')[:10]
        my_module_ids = Module.objects.filter(superviseur=request.user).values_list('formation_id', flat=True).distinct()
        stats = {
            'total_formations': Formation.objects.filter(id__in=my_module_ids).count(),
            'en_cours': Module.objects.filter(superviseur=request.user, statut='EN_COURS').values('formation_id').distinct().count(),
            'total_participants': ModuleParticipant.objects.filter(
                module__superviseur=request.user
            ).values('participant').distinct().count(),
            'total_pointages': Pointage.objects.filter(
                session__module__superviseur=request.user
            ).count(),
            'total_cours': cours_stats['total_cours'],
            'cours_en_cours': cours_stats['cours_en_cours'],
            'cours_planifies': cours_stats['cours_planifies'],
            'cours_termines': cours_stats['cours_termines'],
        }
    elif is_secretariat and request.user.secretariat:
        sec = request.user.secretariat
        sec_formation_ids = Module.objects.filter(secretariat=sec).values_list('formation_id', flat=True).distinct()
        derniers_pointages = Pointage.objects.filter(
            session__module__secretariat=sec
        ).select_related('participant', 'formateur', 'session__module__formation').order_by('-updated_at')[:10]
        stats = {
            'total_formations': Formation.objects.filter(id__in=sec_formation_ids).count(),
            'en_cours': Module.objects.filter(secretariat=sec, statut='EN_COURS').values('formation_id').distinct().count(),
            'total_participants': Participant.objects.filter(secretariat=sec).count(),
            'total_formateurs': Formateur.objects.count(),
            'total_superviseurs': User.objects.filter(role='ENCADRANT').count(),
            'total_pointages': Pointage.objects.filter(session__module__secretariat=sec).count(),
            'total_cours': cours_stats['total_cours'],
            'cours_en_cours': cours_stats['cours_en_cours'],
            'cours_planifies': cours_stats['cours_planifies'],
            'cours_termines': cours_stats['cours_termines'],
        }
    else:
        derniers_pointages = Pointage.objects.select_related(
            'participant', 'formateur', 'session__module__formation'
        ).order_by('-updated_at')[:10]
        stats = {
            'total_formations': Formation.objects.count(),
            'en_cours': Module.objects.filter(statut='EN_COURS').values('formation_id').distinct().count(),
            'total_participants': Participant.objects.count(),
            'total_formateurs': Formateur.objects.count(),
            'total_superviseurs': User.objects.filter(role='ENCADRANT').count(),
            'total_pointages': Pointage.objects.count(),
            'total_cours': cours_stats['total_cours'],
            'cours_en_cours': cours_stats['cours_en_cours'],
            'cours_planifies': cours_stats['cours_planifies'],
            'cours_termines': cours_stats['cours_termines'],
        }

    if is_direction:
        return render(request, 'dashboard/direction_home.html', {
            'stats': stats,
            'formations_en_cours': formations_en_cours,
            'derniers_pointages': derniers_pointages,
        })

    return render(request, 'dashboard/home.html', {
        'stats': stats,
        'formations_en_cours': formations_en_cours,
        'derniers_pointages': derniers_pointages,
    })


# ──────────────────────────────────────────────
# FORMATIONS
# ──────────────────────────────────────────────

@staff_required
def formations_list(request):
    if request.user.role == 'ENCADRANT':
        qs = Formation.objects.filter(modules__superviseur=request.user).distinct()
    elif request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
        qs = Formation.objects.filter(modules__secretariat=request.user.secretariat).distinct() if request.user.secretariat else Formation.objects.none()
    else:
        qs = Formation.objects.all()
    qs = qs.annotate(
        nb_attendus=Count('modules__module_participants', distinct=True),
    ).order_by('-id')
    statut = request.GET.get('statut')
    if statut:
        qs = qs.filter(modules__statut=statut).distinct()
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(formation__icontains=q)
    page_obj, query_params = _paginate(request, qs)
    return render(request, 'dashboard/formations.html', {
        'formations': page_obj,
        'page_obj': page_obj,
        'query_params': query_params,
    })


@staff_required
def formation_detail(request, pk):
    formation = get_object_or_404(Formation, pk=pk)
    superviseurs = User.objects.filter(role='ENCADRANT', is_active=True)
    # QR tokens actifs par séance
    active_qr_tokens = QRToken.objects.filter(
        session__module__formation=formation, actif=True,
    ).select_related('session')
    qr_tokens_by_session = {}
    for qt in active_qr_tokens:
        if qt.is_valid:
            qr_tokens_by_session[qt.session_id] = qt
    all_participants = Participant.objects.all()
    all_formateurs = Formateur.objects.all()

    today = timezone.localdate()
    now = timezone.now()

    # ── Auto-démarrage : heure de début atteinte, encadrant n'a pas démarré ──
    from formations.session_views import (
        _session_debut_prevu_local,
        _should_auto_start_session,
        close_open_sessions_for_module,
    )

    local_now = timezone.localtime(now)
    auto_start_qs = SessionModule.objects.filter(
        module__formation=formation,
        date_journee=today,
        demarree_le__isnull=True,
        terminee_le__isnull=True,
        heure_debut_prevue__isnull=False,
    )
    for sess in auto_start_qs:
        if not _should_auto_start_session(sess, local_now):
            continue
        # Fermer les séances ouvertes du MÊME module avant d'en démarrer une
        # nouvelle. Ne pas toucher aux autres modules/groupes de la formation,
        # sinon on invaliderait les QR des autres groupes.
        close_open_sessions_for_module(sess.module, exclude_pks=[sess.pk], when=now)
        sess.demarree_le = _session_debut_prevu_local(sess)
        sess.save(update_fields=['demarree_le'])
        module = sess.module
        if module.statut != 'EN_COURS':
            module.statut = 'EN_COURS'
            module.save(update_fields=['statut'])

    # ── Auto-arrêt : heure de fin dépassée, encadrant n'a pas fermé, délai écoulé ──
    from formations.session_views import (
        _session_fin_prevue_local,
        _should_auto_close_session,
    )

    auto_stopped = False
    for sess in SessionModule.objects.filter(
        module__formation=formation,
        date_journee=today,
        demarree_le__isnull=False,
        terminee_le__isnull=True,
        heure_fin_prevue__isnull=False,
    ):
        if not _should_auto_close_session(sess, local_now):
            continue
        sess.terminee_le = _session_fin_prevue_local(sess)
        sess.save(update_fields=['terminee_le'])
        auto_stopped = True
    # Si plus aucune session ouverte après auto-arrêt, passer en SUSPENDUE
    if auto_stopped:
        has_open = SessionModule.objects.filter(
            module__formation=formation, demarree_le__isnull=False, terminee_le__isnull=True,
        ).exists()
        if not has_open:
            formation.modules.filter(statut='EN_COURS').update(statut='SUSPENDUE')

    all_pointages = Pointage.objects.filter(session__module__formation=formation, date_journee=today)

    from collections import defaultdict
    part_sessions_map = defaultdict(list)
    fmt_sessions_map = defaultdict(list)
    for pt in all_pointages:
        if pt.formateur_id:
            fmt_sessions_map[pt.formateur_id].append(pt)
        else:
            part_sessions_map[pt.participant_id].append(pt)

    def _build_entry(personne, sessions_map, pid):
        sessions = sessions_map.get(pid, [])
        session_ouverte = next((s for s in sessions if s.statut == 'EN_COURS'), None)
        sessions_terminees = [s for s in sessions if s.statut != 'EN_COURS']
        total_min = sum(float(s.duree_presence_minutes or 0) for s in sessions_terminees)
        if session_ouverte:
            total_min += round((now - session_ouverte.timestamp_entree).total_seconds() / 60, 1)
        return {
            'personne': personne,
            'sessions': sessions,
            'nb_sessions': len(sessions),
            'session_ouverte': session_ouverte,
            'total_minutes': round(total_min, 1),
            'has_pointage': len(sessions) > 0,
        }

    participants = []
    seen_dash = set()
    for fp in ModuleParticipant.objects.filter(module__formation=formation).select_related('participant'):
        if fp.participant_id in seen_dash:
            continue
        seen_dash.add(fp.participant_id)
        entry = _build_entry(fp.participant, part_sessions_map, fp.participant_id)
        entry['participant'] = fp.participant
        entry['type_personne'] = 'participant'
        participants.append(entry)

    formateurs = []
    seen_fmt_dash = set()
    for ff in ModuleFormateur.objects.filter(module__formation=formation).select_related('formateur'):
        if ff.formateur_id in seen_fmt_dash:
            continue
        seen_fmt_dash.add(ff.formateur_id)
        entry = _build_entry(ff.formateur, fmt_sessions_map, ff.formateur_id)
        entry['formateur'] = ff.formateur
        entry['type_personne'] = 'formateur'
        formateurs.append(entry)

    # Sessions de la journée et historique complet
    sessions_today = SessionModule.objects.filter(
        module__formation=formation, date_journee=today,
    ).order_by('numero')
    session_en_cours = sessions_today.filter(
        demarree_le__isnull=False, terminee_le__isnull=True,
    ).first()
    # Sessions à venir (planifiées mais pas encore démarrées) — aujourd'hui et futur
    sessions_planifiees = SessionModule.objects.filter(
        module__formation=formation, demarree_le__isnull=True, date_journee__gte=today,
    ).order_by('date_journee', 'numero')
    all_sessions = SessionModule.objects.filter(
        module__formation=formation,
    ).order_by('date_journee', 'numero')

    # Sessions disponibles pour la génération de QR (non terminées)
    sessions_for_qr = SessionModule.objects.filter(
        module__formation=formation,
    ).exclude(terminee_le__isnull=False).order_by('date_journee', 'numero')

    # Stats pour l'onglet historique
    all_sessions_list = list(all_sessions)
    nb_sessions_terminées = sum(1 for s in all_sessions_list if s.est_terminee)
    nb_sessions_en_cours = sum(1 for s in all_sessions_list if s.est_en_cours)
    nb_sessions_planifiées = sum(1 for s in all_sessions_list if s.est_planifiee)
    total_duree_sessions = round(sum(s.duree_minutes or 0 for s in all_sessions_list), 1)

    return render(request, 'dashboard/formation_detail.html', {
        'formation': formation,
        'superviseurs': superviseurs,
        'qr_tokens_by_session': qr_tokens_by_session,
        'participants': participants,
        'formateurs': formateurs,
        'all_participants': all_participants,
        'all_formateurs': all_formateurs,
        'sessions_today': sessions_today,
        'session_en_cours': session_en_cours,
        'sessions_planifiees': sessions_planifiees,
        'sessions_for_qr': sessions_for_qr,
        'all_sessions': all_sessions_list,
        'nb_sessions_terminées': nb_sessions_terminées,
        'nb_sessions_en_cours': nb_sessions_en_cours,
        'nb_sessions_planifiées': nb_sessions_planifiées,
        'total_duree_sessions': total_duree_sessions,
        'today': today,
    })


@staff_required
def sessions_history(request, pk):
    """Page dédiée à l'historique complet des séances d'une formation."""
    formation = get_object_or_404(Formation, pk=pk)
    today = timezone.localdate()

    all_sessions = list(
        SessionModule.objects.filter(module__formation=formation)
        .order_by('date_journee', 'numero')
    )

    nb_terminées = sum(1 for s in all_sessions if s.est_terminee)
    nb_en_cours = sum(1 for s in all_sessions if s.est_en_cours)
    nb_planifiées = sum(1 for s in all_sessions if s.est_planifiee)
    total_duree = round(sum(s.duree_minutes or 0 for s in all_sessions), 1)

    return render(request, 'dashboard/sessions_history.html', {
        'formation': formation,
        'all_sessions': all_sessions,
        'nb_terminées': nb_terminées,
        'nb_en_cours': nb_en_cours,
        'nb_planifiées': nb_planifiées,
        'total_duree': total_duree,
        'today': today,
    })


@staff_required
def session_presences(request, pk, session_id):
    """Page des présences pour une séance donnée."""
    formation = get_object_or_404(Formation, pk=pk)
    session = get_object_or_404(SessionModule, pk=session_id, module__formation=formation)

    pointages = Pointage.objects.filter(
        session=session,
    ).select_related('participant', 'formateur').order_by('timestamp_entree')

    # Séparer participants et formateurs
    pointages_participants = [p for p in pointages if p.participant_id]
    pointages_formateurs = [p for p in pointages if p.formateur_id]

    # Participants inscrits sans pointage pour cette séance
    inscrits_ids = set(
        ModuleParticipant.objects.filter(module__formation=formation)
        .values_list('participant_id', flat=True)
    )
    presents_ids = set(p.participant_id for p in pointages_participants)
    absents = Participant.objects.filter(id__in=inscrits_ids - presents_ids)

    nb_inscrits = len(inscrits_ids)
    nb_presents = len(presents_ids)
    nb_absents = len(inscrits_ids - presents_ids)
    taux = round(nb_presents / nb_inscrits * 100) if nb_inscrits else 0

    return render(request, 'dashboard/session_presences.html', {
        'formation': formation,
        'session': session,
        'pointages_participants': pointages_participants,
        'pointages_formateurs': pointages_formateurs,
        'absents': absents,
        'nb_inscrits': nb_inscrits,
        'nb_presents': nb_presents,
        'nb_absents': nb_absents,
        'taux': taux,
    })


@dfrc_required
def formation_create(request):
    superviseurs = User.objects.filter(role='ENCADRANT', is_active=True)
    all_formateurs = Formateur.objects.all()
    if request.method == 'POST':
        sup_id = request.POST.get('superviseur_id')
        grade = request.POST.get('grade', '')
        groupe = request.POST.get('groupe', '')
        formation = Formation.objects.create(
            formation=request.POST['formation'],
        )
        # Créer un module par défaut portant les champs métier
        module = Module.objects.create(
            formation=formation,
            intitule=request.POST.get('module_intitule') or request.POST['formation'],
            date_debut=request.POST.get('date_debut') or None,
            date_fin=request.POST.get('date_fin') or None,
            statut=request.POST.get('statut', 'PLANIFIEE'),
            grade=grade,
            groupe=groupe,
            superviseur_id=int(sup_id) if sup_id else None,
            ordre=1,
        )
        formateur_ids = request.POST.getlist('formateur_ids')
        for fid in formateur_ids:
            ModuleFormateur.objects.get_or_create(module=module, formateur_id=int(fid))
        messages.success(request, f"Formation « {formation.formation} » créée avec succès.")
        _log_audit(
            action=AuditLog.Action.FORMATION_CREATE,
            request=request,
            formation=formation,
            extra={'titre': formation.formation, 'statut': module.statut},
        )
        return redirect('web-formation-detail', pk=formation.id)
    return render(request, 'dashboard/formation_form.html', {
        'superviseurs': superviseurs,
        'all_formateurs': all_formateurs,
        'ref_formations': RefFormation.objects.filter(actif=True),
        'ref_modules': RefModule.objects.filter(actif=True),
        'ref_sites': RefSite.objects.filter(actif=True),
        'ref_batiments': list(RefBatiment.objects.filter(actif=True).values('id', 'nom', 'site_id')),
        'ref_salles': list(RefSalle.objects.filter(actif=True).values('id', 'nom', 'site_id', 'batiment_id')),
        'ref_categories': RefCategorie.objects.filter(actif=True),
        'ref_grades': list(RefGrade.objects.filter(actif=True).values('id', 'code', 'libelle', 'categorie_id')),
    })


@dfrc_required
def formation_edit(request, pk):
    formation = get_object_or_404(Formation, pk=pk)
    superviseurs = User.objects.filter(role='ENCADRANT', is_active=True)
    all_formateurs = Formateur.objects.all()
    first_module = formation.modules.order_by('ordre').first()
    if request.method == 'POST':
        formation.formation = request.POST['formation']
        formation.save(update_fields=['formation'])
        sup_id = request.POST.get('superviseur_id')
        if first_module:
            first_module.statut = request.POST.get('statut', first_module.statut)
            first_module.superviseur_id = int(sup_id) if sup_id else None
            first_module.save(update_fields=['statut', 'superviseur_id'])
        formateur_ids = set(map(int, request.POST.getlist('formateur_ids')))
        current_ids = set(ModuleFormateur.objects.filter(module__formation=formation).values_list('formateur_id', flat=True))
        if first_module:
            from formations.formateur_assignment import check_formateur_groupe_jour_conflict
            for fid in formateur_ids - current_ids:
                formateur = Formateur.objects.filter(pk=fid).first()
                if not formateur:
                    continue
                conflict = check_formateur_groupe_jour_conflict(formateur, first_module)
                if conflict:
                    messages.error(request, conflict)
                    return redirect('web-formation-edit', pk=formation.pk)
                ModuleFormateur.objects.create(module=first_module, formateur_id=fid)
        ModuleFormateur.objects.filter(module__formation=formation, formateur_id__in=current_ids - formateur_ids).delete()
        messages.success(request, f"Formation « {formation.formation} » modifiée.")
        _log_audit(
            action=AuditLog.Action.FORMATION_UPDATE,
            request=request,
            formation=formation,
            extra={'titre': formation.formation},
        )
        return redirect('web-formation-detail', pk=formation.id)

    date_debut_str = first_module.date_debut.strftime('%Y-%m-%d') if first_module and first_module.date_debut else ''
    date_fin_str = first_module.date_fin.strftime('%Y-%m-%d') if first_module and first_module.date_fin else ''
    selected_formateur_ids = list(ModuleFormateur.objects.filter(module__formation=formation).values_list('formateur_id', flat=True).distinct())

    return render(request, 'dashboard/formation_form.html', {
        'formation': formation,
        'first_module': first_module,
        'superviseurs': superviseurs,
        'all_formateurs': all_formateurs,
        'ref_formations': RefFormation.objects.filter(actif=True),
        'ref_modules': RefModule.objects.filter(actif=True),
        'ref_sites': RefSite.objects.filter(actif=True),
        'ref_batiments': list(RefBatiment.objects.filter(actif=True).values('id', 'nom', 'site_id')),
        'ref_salles': list(RefSalle.objects.filter(actif=True).values('id', 'nom', 'site_id', 'batiment_id')),
        'ref_categories': RefCategorie.objects.filter(actif=True),
        'ref_grades': list(RefGrade.objects.filter(actif=True).values('id', 'code', 'libelle', 'categorie_id')),
        'selected_formateur_ids': selected_formateur_ids,
        'date_debut_str': date_debut_str,
        'date_fin_str': date_fin_str,
    })


@staff_required
@require_POST
def formation_delete(request, pk):
    if request.user.role not in ('INJS_ADMIN', 'CHEF_INJS_ADMIN', 'SECRETARIAT', 'CHEF_SECRETARIAT'):
        messages.error(request, "Accès refusé.")
        return redirect('web-formations')
    formation = get_object_or_404(Formation, pk=pk)
    if request.user.role == 'SECRETARIAT':
        sec = getattr(request.user, 'secretariat', None)
        if not sec or not formation.modules.filter(secretariat=sec).exists():
            messages.error(request, "Vous ne pouvez supprimer que les formations de votre secrétariat.")
            return redirect('web-formations')
    titre = formation.formation
    formation_id = formation.id
    formation.delete()
    messages.success(request, f"Formation « {titre} » supprimée.")
    _log_audit(
        action=AuditLog.Action.FORMATION_DELETE,
        request=request,
        extra={'formation_id': formation_id, 'titre': titre},
    )
    return redirect('web-formations')


@staff_required
def formation_generate_qr(request, pk):
    """Superviseur ou INJS_ADMIN : générer un nouveau QR code pour une séance."""
    if request.user.role == 'DIRECTION':
        messages.error(request, "La Direction ne peut pas générer de QR codes.")
        return redirect('web-formation-detail', pk=pk)
    formation = get_object_or_404(Formation, pk=pk)
    if request.method == 'POST':
        # Lire la séance cible
        session_id = request.POST.get('session_id')
        session = None
        if session_id:
            session = get_object_or_404(SessionModule, pk=session_id, module__formation=formation)
            if session.est_terminee:
                messages.error(request, "Impossible de générer un QR pour une séance terminée.")
                return redirect('web-formation-detail', pk=pk)
        else:
            messages.error(request, "Veuillez sélectionner une séance.")
            return redirect('web-formation-detail', pk=pk)

        # Lire la durée d'expiration
        duree = int(request.POST.get('duree_expiration', 24))
        unite = request.POST.get('unite_expiration', 'heures')

        if unite == 'minutes':
            delta = timedelta(minutes=duree)
            label = f"{duree} minute{'s' if duree > 1 else ''}"
        elif unite == 'jours':
            delta = timedelta(days=duree)
            label = f"{duree} jour{'s' if duree > 1 else ''}"
        else:
            delta = timedelta(hours=duree)
            label = f"{duree} heure{'s' if duree > 1 else ''}"

        # Désactiver les anciens QR de cette séance
        QRToken.objects.filter(session=session, actif=True).update(actif=False)
        # Créer un nouveau
        qr_token = QRToken.objects.create(
            session=session,
            genere_par=request.user,
            expire_at=timezone.now() + delta,
        )
        session_label = session.intitule or f"Session {session.numero}"
        messages.success(request, f"QR code généré pour « {session_label} » (expire dans {label}).")
        _log_audit(
            action=AuditLog.Action.FORMATION_QR_GENERATE,
            request=request,
            formation=formation,
            extra={'session_id': session.id, 'session_label': session_label, 'expire_dans': label},
        )
    return redirect('web-formation-detail', pk=pk)


@staff_required
@require_POST
def formation_change_statut(request, pk):
    """
    Superviseur ou INJS_ADMIN : changer le statut de la formation.
    Flux : PLANIFIEE → EN_COURS (démarrer)
           EN_COURS → SUSPENDUE (suspendre / pause)
           SUSPENDUE → EN_COURS (reprendre)
           EN_COURS → TERMINEE (terminer définitivement)
           SUSPENDUE → TERMINEE (terminer définitivement)
    """
    formation = get_object_or_404(Formation, pk=pk)
    first_module = formation.modules.order_by('ordre').first()
    if request.user.role == 'ENCADRANT':
        if not formation.modules.filter(superviseur=request.user).exists():
            messages.error(request, "Vous n'\u00eates pas le superviseur de cette formation.")
            return redirect('web-formation-detail', pk=pk)
    if request.user.role == 'DIRECTION':
        messages.error(request, "La Direction ne peut pas changer le statut.")
        return redirect('web-formation-detail', pk=pk)

    new_statut = request.POST.get('statut')
    valid_statuts = [c[0] for c in Module.Statut.choices]
    if new_statut not in valid_statuts:
        messages.error(request, "Statut invalide.")
        return redirect('web-formation-detail', pk=pk)

    current_statut = first_module.statut if first_module else 'PLANIFIEE'
    transitions = {
        'PLANIFIEE': ['EN_COURS'],
        'EN_COURS': ['SUSPENDUE', 'TERMINEE'],
        'SUSPENDUE': ['EN_COURS', 'TERMINEE'],
        'TERMINEE': ['EN_COURS'],
    }
    if new_statut not in transitions.get(current_statut, []):
        messages.error(request, f"Transition {current_statut} \u2192 {new_statut} non autorisée.")
        return redirect('web-formation-detail', pk=pk)

    now = timezone.now()
    today = timezone.localdate()

    if new_statut == 'EN_COURS':
        _mod_statut = first_module
        last_num = SessionModule.objects.filter(
            module__formation=formation, date_journee=today,
        ).count()
        if _mod_statut:
            SessionModule.objects.create(
                module=_mod_statut,
                date_journee=today,
                numero=last_num + 1,
                demarree_le=now,
                demarree_par=request.user,
            )
            _mod_statut.statut = 'EN_COURS'
            _mod_statut.save(update_fields=['statut'])
        label = 'reprise' if current_statut in ('SUSPENDUE', 'TERMINEE') else 'démarrée'
        messages.success(request, f"Session {last_num + 1} {label} pour le {today.strftime('%d/%m/%Y')}.")
        _log_audit(
            action=AuditLog.Action.FORMATION_STATUT,
            request=request,
            formation=formation,
            extra={'nouveau_statut': new_statut, 'ancien_statut': current_statut},
        )

    elif new_statut == 'SUSPENDUE':
        session_ouverte = SessionModule.objects.filter(
            module__formation=formation, terminee_le__isnull=True,
        ).order_by('-demarree_le').first()
        if session_ouverte:
            session_ouverte.terminee_le = now
            session_ouverte.save(update_fields=['terminee_le'])
        formation.modules.filter(statut='EN_COURS').update(statut='SUSPENDUE')
        messages.success(request, "Module suspendu. Vous pourrez reprendre à tout moment.")
        _log_audit(
            action=AuditLog.Action.FORMATION_STATUT,
            request=request,
            formation=formation,
            extra={'nouveau_statut': 'SUSPENDUE'},
        )

    elif new_statut == 'TERMINEE':
        session_ouverte = SessionModule.objects.filter(
            module__formation=formation, terminee_le__isnull=True,
        ).order_by('-demarree_le').first()
        if session_ouverte:
            session_ouverte.terminee_le = now
            session_ouverte.save(update_fields=['terminee_le'])
        formation.modules.exclude(statut='TERMINEE').update(statut='TERMINEE')
        messages.success(request, "Formation terminée.")
        _log_audit(
            action=AuditLog.Action.FORMATION_STATUT,
            request=request,
            formation=formation,
        )

    return redirect('web-formation-detail', pk=pk)


@staff_required
@require_POST
def session_add(request, pk):
    """Ajouter une séance planifiée (à l'avance ou séance tenante)."""
    formation = get_object_or_404(Formation, pk=pk)
    if request.user.role == 'DIRECTION':
        messages.error(request, "La Direction ne peut pas modifier l'agenda.")
        return redirect('web-formation-detail', pk=pk)
    if request.user.role == 'ENCADRANT':
        if not formation.modules.filter(superviseur=request.user).exists():
            messages.error(request, "Vous n'\u00eates pas le superviseur de cette formation.")
            return redirect('web-formation-detail', pk=pk)

    date_str = request.POST.get('date_journee')
    intitule = request.POST.get('intitule', '').strip()
    heure_debut = request.POST.get('heure_debut_prevue') or None
    heure_fin = request.POST.get('heure_fin_prevue') or None
    auto_demarrage = bool(request.POST.get('auto_demarrage'))

    if not date_str:
        messages.error(request, "La date est obligatoire.")
        return redirect('web-formation-detail', pk=pk)

    if auto_demarrage and not heure_debut:
        messages.error(request, "L'heure de début est requise pour le démarrage automatique.")
        return redirect('web-formation-detail', pk=pk)

    from datetime import datetime as dt
    try:
        date_journee = dt.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, "Format de date invalide.")
        return redirect('web-formation-detail', pk=pk)

    _mod_add = formation.modules.order_by('ordre').first()
    last_num = SessionModule.objects.filter(
        module__formation=formation, date_journee=date_journee,
    ).count()

    if not _mod_add:
        messages.error(request, "Impossible de créer une séance : aucun module trouvé.")
        return redirect('web-formation-detail', pk=pk)
    SessionModule.objects.create(
        module=_mod_add,
        date_journee=date_journee,
        numero=last_num + 1,
        intitule=intitule,
        heure_debut_prevue=heure_debut or None,
        heure_fin_prevue=heure_fin or None,
        auto_demarrage=auto_demarrage,
    )
    label = intitule or f"Session {last_num + 1}"
    messages.success(request, f"Séance « {label} » planifiée pour le {date_journee.strftime('%d/%m/%Y')}.")
    _log_audit(
        action=AuditLog.Action.SEANCE_CREATE,
        request=request,
        formation=formation,
        extra={'label': label, 'date': str(date_journee)},
    )
    return redirect('web-formation-detail', pk=pk)


@staff_required
@require_POST
def session_start(request, pk, session_id):
    """Démarrer une séance planifiée (ou reprendre)."""
    formation = get_object_or_404(Formation, pk=pk)
    session = get_object_or_404(SessionModule, pk=session_id, module__formation=formation)
    if request.user.role == 'DIRECTION':
        messages.error(request, "La Direction ne peut pas démarrer une séance.")
        return redirect('web-formation-detail', pk=pk)
    if request.user.role == 'ENCADRANT':
        if not formation.modules.filter(superviseur=request.user).exists():
            messages.error(request, "Vous n'\u00eates pas le superviseur de cette formation.")
            return redirect('web-formation-detail', pk=pk)

    now = timezone.now()

    if session.demarree_le is None:
        # Nouveau démarrage : une seule séance ouverte par module.
        open_sessions = SessionModule.objects.filter(
            module=session.module,
            demarree_le__isnull=False,
            terminee_le__isnull=True,
        ).exclude(pk=session_id)
        for s in open_sessions:
            s.terminee_le = now
            s.save(update_fields=['terminee_le'])
        session.demarree_le = now
        session.demarree_par = request.user
        session.save(update_fields=['demarree_le', 'demarree_par'])
    elif session.terminee_le is not None:
        from formations.session_views import reactiver_session_et_qr

        reactiver_session_et_qr(session)

    # Passer le module en EN_COURS
    module = session.module
    if module.statut != 'EN_COURS':
        module.statut = 'EN_COURS'
        module.save(update_fields=['statut'])

    label = session.intitule or f"Session {session.numero}"
    messages.success(request, f"Séance « {label} » démarrée.")
    _log_audit(
        action=AuditLog.Action.SEANCE_START,
        request=request,
        formation=formation,
        extra={'session_id': session.id, 'label': label},
    )
    return redirect('web-formation-detail', pk=pk)


@staff_required
@require_POST
def session_stop(request, pk, session_id):
    """Terminer (suspendre) une séance en cours."""
    formation = get_object_or_404(Formation, pk=pk)
    session = get_object_or_404(SessionModule, pk=session_id, module__formation=formation)
    if request.user.role == 'DIRECTION':
        messages.error(request, "La Direction ne peut pas modifier une séance.")
        return redirect('web-formation-detail', pk=pk)
    if request.user.role == 'ENCADRANT':
        if not formation.modules.filter(superviseur=request.user).exists():
            messages.error(request, "Vous n'\u00eates pas le superviseur de cette formation.")
            return redirect('web-formation-detail', pk=pk)

    now = timezone.now()
    if session.demarree_le and not session.terminee_le:
        session.terminee_le = now
        session.save(update_fields=['terminee_le'])
        label = session.intitule or f"Session {session.numero}"
        messages.success(request, f"Séance « {label} » terminée.")
        _log_audit(
            action=AuditLog.Action.SEANCE_STOP,
            request=request,
            formation=formation,
            extra={'session_id': session.id, 'label': label},
        )
        # Vérifier s'il reste des sessions non terminées aujourd'hui
        has_open = SessionModule.objects.filter(
            module__formation=formation, demarree_le__isnull=False, terminee_le__isnull=True,
        ).exists()
        if not has_open:
            formation.modules.filter(statut='EN_COURS').update(statut='SUSPENDUE')
    return redirect('web-formation-detail', pk=pk)


@staff_required
@require_POST
def session_delete(request, pk, session_id):
    """Supprimer une séance planifiée (pas encore démarrée)."""
    formation = get_object_or_404(Formation, pk=pk)
    session = get_object_or_404(SessionModule, pk=session_id, module__formation=formation)
    if request.user.role == 'DIRECTION':
        messages.error(request, "La Direction ne peut pas supprimer une séance.")
        return redirect('web-formation-detail', pk=pk)
    if session.demarree_le is not None:
        messages.error(request, "Impossible de supprimer une séance déjà démarrée.")
        return redirect('web-formation-detail', pk=pk)
    label = session.intitule or f"Session {session.numero}"
    session_id = session.id
    session.delete()
    messages.success(request, f"Séance « {label} » supprimée.")
    _log_audit(
        action=AuditLog.Action.SEANCE_DELETE,
        request=request,
        formation=formation,
        extra={'session_id': session_id, 'label': label},
    )
    return redirect('web-formation-detail', pk=pk)


@dfrc_required
@require_POST
def formation_assign(request, pk):
    formation = get_object_or_404(Formation, pk=pk)
    sup_id = request.POST.get('superviseur_id')
    if sup_id:
        formation.modules.update(superviseur_id=int(sup_id))
        messages.success(request, "Superviseur assigné.")
        _log_audit(
            action=AuditLog.Action.FORMATION_ASSIGN_SUPERVISEUR,
            request=request,
            formation=formation,
            extra={'superviseur_id': int(sup_id)},
        )
    else:
        messages.warning(request, "Veuillez sélectionner un superviseur.")
    return redirect('web-formation-detail', pk=pk)


@dfrc_required
def formation_add_participant(request, pk):
    formation = get_object_or_404(Formation, pk=pk)
    if request.method == 'POST':
        participant_id = request.POST.get('participant_id')
        module_id = request.POST.get('module_id')
        if participant_id and module_id:
            participant = get_object_or_404(Participant, pk=participant_id)
            module = get_object_or_404(formation.modules, pk=module_id)
            _, created = ModuleParticipant.objects.get_or_create(
                module=module, participant=participant,
            )
            if created:
                messages.success(request, f"{participant.nom} {participant.prenom} inscrit.")
                _log_audit(
                    action=AuditLog.Action.PARTICIPANT_ADD_FORMATION,
                    request=request,
                    cible_type='participant',
                    cible_numero=participant.matricule,
                    cible_nom=f'{participant.nom} {participant.prenom}',
                    formation=formation,
                )
            else:
                messages.warning(request, "Ce participant est déjà inscrit.")
    return redirect('web-formation-detail', pk=pk)


@dfrc_required
@require_POST
def formation_remove_participant(request, pk, participant_id):
    p = Participant.objects.filter(pk=participant_id).first()
    ModuleParticipant.objects.filter(
        module__formation_id=pk, participant_id=participant_id
    ).delete()
    messages.success(request, "Participant retiré de la formation.")
    if p:
        formation = Formation.objects.filter(pk=pk).first()
        _log_audit(
            action=AuditLog.Action.PARTICIPANT_REMOVE_FORMATION,
            request=request,
            cible_type='participant',
            cible_numero=p.matricule,
            cible_nom=f'{p.nom} {p.prenom}',
            formation=formation,
        )
    return redirect('web-formation-detail', pk=pk)


# ──────────────────────────────────────────────
# FORMATION LIVE DASHBOARD
# ──────────────────────────────────────────────

@staff_required
def formation_live(request, pk):
    formation = get_object_or_404(Formation, pk=pk)
    today = timezone.localdate()

    pointages = Pointage.objects.filter(
        session__module__formation=formation, date_journee=today
    ).select_related('participant', 'formateur')

    from collections import defaultdict
    sessions_map = defaultdict(list)
    for pt in pointages:
        if pt.formateur_id:
            sessions_map[('formateur', pt.formateur_id)].append(pt)
        else:
            sessions_map[('participant', pt.participant_id)].append(pt)

    presents = []
    en_salle = []
    absents = []
    now = timezone.now()

    def _classify(personne, type_str):
        key = (type_str, personne.id)
        sessions = sessions_map.get(key, [])
        personne.type_personne = type_str

        if not sessions:
            absents.append(personne)
            return

        session_ouverte = next(
            (s for s in sessions if s.statut == 'EN_COURS'), None
        )
        sessions_terminees = [s for s in sessions if s.statut != 'EN_COURS']
        total_termine = sum(float(s.duree_presence_minutes or 0) for s in sessions_terminees)
        personne.nb_sessions = len(sessions)

        if session_ouverte:
            personne.timestamp_entree = session_ouverte.timestamp_entree
            duree_session = round(
                (now - session_ouverte.timestamp_entree).total_seconds() / 60, 1
            )
            personne.duree_actuelle_minutes = round(total_termine + duree_session, 1)
            en_salle.append(personne)
        else:
            derniere = max(sessions_terminees, key=lambda s: s.timestamp_sortie or s.timestamp_entree)
            personne.timestamp_entree = sessions[0].timestamp_entree
            personne.timestamp_sortie = derniere.timestamp_sortie
            personne.duree_presence_minutes = round(total_termine, 2)
            presents.append(personne)

    seen_detail = set()
    for insc in ModuleParticipant.objects.filter(module__formation=formation).select_related('participant'):
        if insc.participant_id in seen_detail:
            continue
        seen_detail.add(insc.participant_id)
        _classify(insc.participant, 'participant')

    seen_fmt_live = set()
    for insc in ModuleFormateur.objects.filter(module__formation=formation).select_related('formateur'):
        if insc.formateur_id in seen_fmt_live:
            continue
        seen_fmt_live.add(insc.formateur_id)
        _classify(insc.formateur, 'formateur')

    total_attendus = (
        ModuleParticipant.objects.filter(module__formation=formation).values('participant').distinct().count()
        + ModuleFormateur.objects.filter(module__formation=formation).values('formateur').distinct().count()
    )
    total_pointes = len(presents) + len(en_salle)
    taux_presence = round(total_pointes / total_attendus * 100, 1) if total_attendus > 0 else 0

    return render(request, 'dashboard/formation_live.html', {
        'formation': formation,
        'presents': presents,
        'en_salle': en_salle,
        'absents': absents,
        'total_attendus': total_attendus,
        'taux_presence': taux_presence,
    })


# ──────────────────────────────────────────────
# FORCE POINTAGE (R6)
# ──────────────────────────────────────────────

@staff_required
def force_pointage_view(request, pk):
    if request.method == 'POST':
        formation = get_object_or_404(Formation, pk=pk)
        action = request.POST.get('action')
        type_personne = request.POST.get('type_personne', 'participant')
        motif = (request.POST.get('motif') or '').strip()
        if not motif:
            messages.error(request, "Le motif est obligatoire pour forcer un badgeage.")
            referer = request.META.get('HTTP_REFERER', '')
            if 'live' in referer:
                return redirect('web-formation-live', pk=pk)
            return redirect('web-formation-detail', pk=pk)

        session_active = SessionModule.objects.filter(
            module__formation=formation, demarree_le__isnull=False, terminee_le__isnull=True,
        ).order_by('-demarree_le').first()
        if type_personne == 'formateur':
            personne = get_object_or_404(Formateur, pk=request.POST['personne_id'])
            filt_base = {'formateur': personne}
            create_base = {'formateur': personne}
        else:
            personne = get_object_or_404(Participant, pk=request.POST['personne_id'])
            filt_base = {'participant': personne}
            create_base = {'participant': personne}
        if session_active:
            create_base['session'] = session_active
            filt_base['session'] = session_active

        today = timezone.localdate()

        if action == 'ENTREE':
            session_ouverte = Pointage.objects.filter(
                **filt_base, date_journee=today, statut='EN_COURS',
            ).exists()
            if session_ouverte:
                messages.warning(request, "Une session est déjà en cours.")
            else:
                pt = Pointage.objects.create(
                    **create_base,
                    date_journee=today,
                    timestamp_entree=timezone.now(),
                    statut='FORCE_DFRC',
                )
                messages.success(request, f"Entrée forcée pour {personne.nom} {personne.prenom}.")
                _log_audit(
                    action=AuditLog.Action.FORCE_ENTREE,
                    request=request,
                    cible_type=type_personne,
                    cible_numero=getattr(personne, 'numero', None) or getattr(personne, 'matricule', ''),
                    cible_nom=f'{personne.nom} {personne.prenom}',
                    formation=formation,
                    pointage=pt,
                    extra={'source': 'web', 'acteur_role': request.user.role, 'motif': motif},
                )

        elif action == 'SORTIE':
            try:
                pointage = Pointage.objects.filter(
                    **filt_base,
                    date_journee=today,
                    statut__in=['EN_COURS', 'FORCE_DFRC'],
                    timestamp_sortie__isnull=True,
                ).latest('timestamp_entree')
                pointage.timestamp_sortie = timezone.now()
                pointage.statut = 'FORCE_DFRC'
                pointage.calculer_duree()
                pointage.save()
                messages.success(request, f"Sortie forcée pour {personne.nom} {personne.prenom}.")
                _log_audit(
                    action=AuditLog.Action.FORCE_SORTIE,
                    request=request,
                    cible_type=type_personne,
                    cible_numero=getattr(personne, 'numero', None) or getattr(personne, 'matricule', ''),
                    cible_nom=f'{personne.nom} {personne.prenom}',
                    formation=formation,
                    pointage=pointage,
                    extra={'source': 'web', 'acteur_role': request.user.role, 'duree_minutes': float(pointage.duree_presence_minutes or 0), 'motif': motif},
                )
            except Pointage.DoesNotExist:
                messages.warning(request, "Aucune session en cours aujourd'hui.")

    referer = request.META.get('HTTP_REFERER', '')
    if 'live' in referer:
        return redirect('web-formation-live', pk=pk)
    return redirect('web-formation-detail', pk=pk)


# ──────────────────────────────────────────────
# PARTICIPANTS
# ──────────────────────────────────────────────

@admin_view_required
def participants_list(request):
    qs = Participant.objects.annotate(
        nb_formations=Count('modules_inscrits', distinct=True)
    ).order_by('nom', 'prenom')
    if request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT') and request.user.secretariat:
        qs = qs.filter(secretariat=request.user.secretariat)
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(matricule__icontains=q)
        )
    page_obj, query_params = _paginate(request, qs)
    return render(request, 'dashboard/participants.html', {
        'participants': page_obj,
        'page_obj': page_obj,
        'query_params': query_params,
    })


@dfrc_required
def participant_create(request):
    if request.method == 'POST':
        sec = None
        if request.user.role in ('SECRETARIAT', 'CHEF_SECRETARIAT'):
            sec = request.user.secretariat
        matricule = request.POST.get('matricule', '').strip()
        if sec is None and matricule:
            sec = _resolve_secretariat_from_matricule(matricule)
        p = Participant.objects.create(
            matricule=matricule,
            nom=request.POST['nom'],
            prenom=request.POST['prenom'],
            email=request.POST.get('email', ''),
            telephone=request.POST.get('telephone', ''),
            secretariat=sec,
        )
        messages.success(request, "Participant créé.")
        _log_audit(
            action=AuditLog.Action.PARTICIPANT_CREATE,
            request=request,
            cible_type='participant',
            cible_numero=p.matricule,
            cible_nom=f'{p.nom} {p.prenom}',
        )
    return redirect('web-participants')


@dfrc_required
def participant_edit(request, pk):
    participant = get_object_or_404(Participant, pk=pk)
    if request.method == 'POST':
        from django.core.exceptions import ValidationError as DjangoValidationError
        from formations.participant_matricule import (
            normalize_matricule,
            secretariat_from_matricule_for_actor,
            sync_participant_user_after_matricule_change,
            validate_participant_matricule,
        )

        new_matricule = normalize_matricule(
            request.POST.get('matricule', participant.matricule),
        ) or participant.matricule
        try:
            validate_participant_matricule(
                new_matricule,
                participant_id=participant.pk,
                linked_user_id=participant.user_id,
            )
        except DjangoValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect('web-participants')

        matricule_changed = new_matricule != participant.matricule
        participant.matricule = new_matricule
        participant.nom = request.POST['nom']
        participant.prenom = request.POST['prenom']
        participant.email = request.POST.get('email', '')
        participant.telephone = request.POST.get('telephone', '')
        secretariat = secretariat_from_matricule_for_actor(participant.matricule, request.user)
        if secretariat is not None:
            participant.secretariat = secretariat
        try:
            with transaction.atomic():
                participant.save()
                if matricule_changed and participant.user_id:
                    sync_participant_user_after_matricule_change(participant)
        except IntegrityError:
            messages.error(request, 'Ce matricule est déjà utilisé.')
            return redirect('web-participants')
        messages.success(request, "Participant modifié.")
        _log_audit(
            action=AuditLog.Action.PARTICIPANT_UPDATE,
            request=request,
            cible_type='participant',
            cible_numero=participant.matricule,
            cible_nom=f'{participant.nom} {participant.prenom}',
        )
    return redirect('web-participants')


@dfrc_required
@require_POST
def participant_delete(request, pk):
    p = Participant.objects.filter(pk=pk).first()
    Participant.objects.filter(pk=pk).delete()
    messages.success(request, "Participant supprimé.")
    if p:
        _log_audit(
            action=AuditLog.Action.PARTICIPANT_DELETE,
            request=request,
            cible_type='participant',
            cible_numero=p.matricule,
            cible_nom=f'{p.nom} {p.prenom}',
        )
    return redirect('web-participants')


# ──────────────────────────────────────────────
# FORMATEURS
# ──────────────────────────────────────────────

@admin_view_required
def formateurs_list(request):
    qs = Formateur.objects.annotate(
        nb_formations=Count('modules_assignes', distinct=True)
    ).order_by('nom', 'prenom')
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(numero__icontains=q)
        )
    page_obj, query_params = _paginate(request, qs)
    return render(request, 'dashboard/formateurs.html', {
        'formateurs': page_obj,
        'page_obj': page_obj,
        'query_params': query_params,
    })


@dfrc_required
def formateur_create(request):
    if request.method == 'POST':
        f = Formateur.objects.create(
            nom=request.POST['nom'],
            prenom=request.POST['prenom'],
            email=request.POST.get('email', ''),
            telephone=request.POST.get('telephone', ''),
            specialite=request.POST.get('specialite', ''),
            organisation=request.POST.get('organisation', ''),
        )
        messages.success(request, "Formateur créé.")
        _log_audit(
            action=AuditLog.Action.FORMATEUR_CREATE,
            request=request,
            cible_type='formateur',
            cible_numero=f.numerobadge,
            cible_nom=f'{f.nom} {f.prenom}',
        )
    return redirect('web-formateurs')


@dfrc_required
def formateur_edit(request, pk):
    formateur = get_object_or_404(Formateur, pk=pk)
    if request.method == 'POST':
        formateur.nom = request.POST['nom']
        formateur.prenom = request.POST['prenom']
        formateur.email = request.POST.get('email', '')
        formateur.telephone = request.POST.get('telephone', '')
        formateur.specialite = request.POST.get('specialite', '')
        formateur.organisation = request.POST.get('organisation', '')
        formateur.save()
        messages.success(request, "Formateur modifié.")
        _log_audit(
            action=AuditLog.Action.FORMATEUR_UPDATE,
            request=request,
            cible_type='formateur',
            cible_numero=formateur.numerobadge,
            cible_nom=f'{formateur.nom} {formateur.prenom}',
        )
    return redirect('web-formateurs')


@dfrc_required
@require_POST
def formateur_delete(request, pk):
    f = Formateur.objects.filter(pk=pk).first()
    Formateur.objects.filter(pk=pk).delete()
    messages.success(request, "Formateur supprimé.")
    if f:
        _log_audit(
            action=AuditLog.Action.FORMATEUR_DELETE,
            request=request,
            cible_type='formateur',
            cible_numero=f.numerobadge,
            cible_nom=f'{f.nom} {f.prenom}',
        )
    return redirect('web-formateurs')


@dfrc_required
def formation_add_formateur(request, pk):
    formation = get_object_or_404(Formation, pk=pk)
    if request.method == 'POST':
        formateur_id = request.POST.get('formateur_id')
        if formateur_id:
            formateur = get_object_or_404(Formateur, pk=formateur_id)
            _mod = formation.modules.order_by('ordre').first()
            if _mod:
                from formations.formateur_assignment import check_formateur_groupe_jour_conflict
                conflict = check_formateur_groupe_jour_conflict(formateur, _mod)
                if conflict:
                    messages.error(request, conflict)
                    return redirect('web-formation-detail', pk=pk)
                _, created = ModuleFormateur.objects.get_or_create(
                    module=_mod, formateur=formateur
                )
            else:
                created = False
            if created:
                messages.success(request, f"{formateur.nom} {formateur.prenom} assigné comme formateur.")
                _log_audit(
                    action=AuditLog.Action.FORMATEUR_ADD_FORMATION,
                    request=request,
                    cible_type='formateur',
                    cible_numero=formateur.numerobadge,
                    cible_nom=f'{formateur.nom} {formateur.prenom}',
                    formation=formation,
                )
            else:
                messages.warning(request, "Ce formateur est déjà assigné.")
    return redirect('web-formation-detail', pk=pk)


@dfrc_required
@require_POST
def formation_remove_formateur(request, pk, formateur_id):
    f = Formateur.objects.filter(pk=formateur_id).first()
    ModuleFormateur.objects.filter(
        module__formation_id=pk, formateur_id=formateur_id
    ).delete()
    messages.success(request, "Formateur retiré de la formation.")
    if f:
        formation = Formation.objects.filter(pk=pk).first()
        _log_audit(
            action=AuditLog.Action.FORMATEUR_REMOVE_FORMATION,
            request=request,
            cible_type='formateur',
            cible_numero=f.numerobadge,
            cible_nom=f'{f.nom} {f.prenom}',
            formation=formation,
        )
    return redirect('web-formation-detail', pk=pk)


# ──────────────────────────────────────────────
# USERS
# ──────────────────────────────────────────────

@admin_view_required
def users_list(request):
    from authentication.permissions import get_subordinate_roles, get_creatable_roles
    subordinates = get_subordinate_roles(request.user.role)
    creatable_roles = get_creatable_roles(request.user.role)
    qs = User.objects.filter(role__in=subordinates).order_by('role', 'last_name')
    
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )
    role_filter = request.GET.get('role', '')
    if role_filter:
        qs = qs.filter(role=role_filter)
    page_obj, query_params = _paginate(request, qs)
    return render(request, 'dashboard/users.html', {
        'users': page_obj,
        'page_obj': page_obj,
        'query_params': query_params,
        'role_options': subordinates,
        'creatable_roles': creatable_roles,
        'role_labels': dict(User.Role.choices),
    })


@staff_required
def user_create(request):
    if request.user.role not in ('INJS_ADMIN', 'CHEF_INJS_ADMIN', 'SECRETARIAT'):
        messages.error(request, "Accès refusé.")
        return redirect('web-dashboard')
    if request.method == 'POST':
        from authentication.permissions import get_subordinate_roles
        role = request.POST['role']
        if role not in get_subordinate_roles(request.user.role):
            messages.error(request, "Vous ne pouvez pas créer un utilisateur avec ce rôle.")
            return redirect('web-users')
        user = User(
            username=request.POST['username'],
            first_name=request.POST['first_name'],
            last_name=request.POST['last_name'],
            email=request.POST.get('email', ''),
            role=role,
            grade=request.POST.get('grade', ''),
            telephone=request.POST.get('telephone', ''),
            organisation=request.POST.get('organisation', ''),
        )
        user.set_password(request.POST['password'])
        if user.role in ('DIRECTION', 'INJS_ADMIN', 'SECRETARIAT'):
            user.is_staff = True
        if request.user.role == 'SECRETARIAT':
            user.secretariat = request.user.secretariat
        user.save()
        messages.success(request, f"Utilisateur {user.get_full_name()} créé.")
        _log_audit(
            action=AuditLog.Action.USER_CREATE,
            request=request,
            cible_nom=user.get_full_name() or user.username,
            extra={'username': user.username, 'role': user.role},
        )
    return redirect('web-users')


@staff_required
@require_POST
def user_delete(request, pk):
    if request.user.role not in ('INJS_ADMIN', 'CHEF_INJS_ADMIN', 'SECRETARIAT'):
        messages.error(request, "Accès refusé.")
        return redirect('web-users')
    if pk != request.user.id:
        target_user = get_object_or_404(User, pk=pk)
        from authentication.permissions import ROLE_HIERARCHY as role_hierarchy
        current_user_level = role_hierarchy.index(request.user.role) if request.user.role in role_hierarchy else 999
        target_user_level = role_hierarchy.index(target_user.role) if target_user.role in role_hierarchy else 999
        
        if target_user_level <= current_user_level:
            messages.error(request, "Vous n'avez pas le droit de supprimer cet utilisateur.")
        else:
            target_user.delete()
            messages.success(request, "Utilisateur supprimé.")
            _log_audit(
                action=AuditLog.Action.USER_DELETE,
                request=request,
                cible_nom=target_user.get_full_name() or target_user.username,
                extra={'username': target_user.username, 'role': target_user.role},
            )
    return redirect('web-users')


# ──────────────────────────────────────────────
# IMPORT EMPLOI DU TEMPS (séances) depuis Excel
# ──────────────────────────────────────────────

@staff_required
@require_POST
def import_sessions_excel(request, pk):
    """Importer un emploi du temps (séances) depuis un fichier Excel."""
    formation = get_object_or_404(Formation, pk=pk)
    if request.user.role == 'DIRECTION':
        messages.error(request, "La Direction ne peut pas modifier l'agenda.")
        return redirect('web-formation-detail', pk=pk)
    if request.user.role == 'ENCADRANT':
        if not formation.modules.filter(superviseur=request.user).exists():
            messages.error(request, "Vous n'\u00eates pas le superviseur de cette formation.")
            return redirect('web-formation-detail', pk=pk)

    uploaded = request.FILES.get('file')
    if not uploaded:
        messages.error(request, "Veuillez sélectionner un fichier Excel.")
        return redirect('web-formation-detail', pk=pk)

    from io import BytesIO
    from openpyxl import load_workbook
    from datetime import datetime as dt, time as dt_time

    try:
        wb = load_workbook(BytesIO(uploaded.read()), read_only=True)
    except Exception as e:
        messages.error(request, f"Impossible de lire le fichier : {e}")
        return redirect('web-formation-detail', pk=pk)

    # Chercher la première feuille disponible
    ws = wb.active
    if ws is None:
        messages.error(request, "Aucune feuille trouvée dans le fichier.")
        wb.close()
        return redirect('web-formation-detail', pk=pk)

    rows = list(ws.iter_rows(min_row=2, values_only=True))  # skip header
    wb.close()

    if not rows:
        messages.error(request, "Le fichier est vide (aucune ligne de données).")
        return redirect('web-formation-detail', pk=pk)

    created = 0
    skipped = 0
    errors = []

    def _parse_date(val):
        if val is None:
            return None
        if hasattr(val, 'date'):
            return val.date() if callable(val.date) else val.date
        if hasattr(val, 'year'):
            return val
        s = str(val).strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                return dt.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    def _parse_time(val):
        if val is None:
            return None
        if isinstance(val, dt_time):
            return val
        if hasattr(val, 'time'):
            return val.time() if callable(val.time) else val.time
        if hasattr(val, 'hour'):
            return val
        s = str(val).strip()
        for fmt in ('%H:%M', '%H:%M:%S', '%Hh%M'):
            try:
                return dt.strptime(s, fmt).time()
            except ValueError:
                continue
        return None

    from django.db import transaction as db_transaction
    try:
        with db_transaction.atomic():
            for i, row in enumerate(rows, start=2):
                if not row or all(c is None for c in row):
                    continue

                # Colonnes: Date | Numéro | Intitulé | Heure début | Heure fin | Auto-démarrage
                date_val = row[0] if len(row) > 0 else None
                numero_val = row[1] if len(row) > 1 else None
                intitule_val = row[2] if len(row) > 2 else None
                heure_debut_val = row[3] if len(row) > 3 else None
                heure_fin_val = row[4] if len(row) > 4 else None
                auto_dem_val = row[5] if len(row) > 5 else None

                date_journee = _parse_date(date_val)
                if date_journee is None:
                    errors.append(f"Ligne {i} : date invalide « {date_val} »")
                    continue

                # Numéro : auto-incrément si non fourni
                if numero_val is not None:
                    try:
                        numero = int(numero_val)
                    except (ValueError, TypeError):
                        errors.append(f"Ligne {i} : numéro invalide « {numero_val} »")
                        continue
                else:
                    last = SessionModule.objects.filter(
                        module__formation=formation, date_journee=date_journee,
                    ).count()
                    numero = last + 1

                intitule = str(intitule_val).strip() if intitule_val else ''
                heure_debut = _parse_time(heure_debut_val)
                heure_fin = _parse_time(heure_fin_val)

                auto_demarrage = True
                if auto_dem_val is not None:
                    auto_str = str(auto_dem_val).strip().lower()
                    auto_demarrage = auto_str not in ('non', 'false', '0', 'no', 'faux')

                if auto_demarrage and not heure_debut:
                    errors.append(f"Ligne {i} : auto-démarrage nécessite une heure de début.")
                    continue

                _mod_import = formation.modules.order_by('ordre').first()
                if not _mod_import:
                    errors.append(f"Ligne {i} : aucun module pour cette formation.")
                    continue

                # Vérifier doublon
                if SessionModule.objects.filter(
                    module__formation=formation, date_journee=date_journee, numero=numero,
                ).exists():
                    skipped += 1
                    continue

                SessionModule.objects.create(
                    module=_mod_import,
                    date_journee=date_journee,
                    numero=numero,
                    intitule=intitule,
                    heure_debut_prevue=heure_debut,
                    heure_fin_prevue=heure_fin,
                    auto_demarrage=auto_demarrage,
                )
                created += 1

    except Exception as e:
        messages.error(request, f"Erreur lors de l'import : {e}")
        return redirect('web-formation-detail', pk=pk)

    # Messages de résultat
    parts = []
    if created:
        parts.append(f"{created} séance(s) créée(s)")
    if skipped:
        parts.append(f"{skipped} doublon(s) ignoré(s)")
    if errors:
        parts.append(f"{len(errors)} erreur(s)")

    if created and not errors:
        messages.success(request, f"Import réussi : {', '.join(parts)}.")
    elif created and errors:
        messages.warning(request, f"Import partiel : {', '.join(parts)}.")
        for err in errors[:10]:
            messages.warning(request, err)
    elif not created and not errors:
        messages.info(request, "Aucune nouvelle séance (toutes déjà en base).")
    else:
        messages.error(request, f"Import échoué : {', '.join(parts)}.")
        for err in errors[:10]:
            messages.error(request, err)

    if created:
        _log_audit(
            action=AuditLog.Action.SEANCE_IMPORT,
            request=request,
            formation=formation,
            extra={'created': created, 'skipped': skipped, 'errors': len(errors)},
        )

    return redirect('web-formation-detail', pk=pk)


@staff_required
def download_sessions_template(request, pk):
    """Télécharger un modèle Excel pour l'emploi du temps des séances."""
    formation = get_object_or_404(Formation, pk=pk)

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Emploi du temps"

    # En-têtes
    headers = ['Date', 'Numéro', 'Intitulé', 'Heure début', 'Heure fin', 'Auto-démarrage']
    header_fill = PatternFill(start_color='093F70', end_color='093F70', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin'),
    )

    for col, title in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border

    # Exemple de données
    from datetime import date as dt_date, time as dt_time
    # Convertir en date naïve (openpyxl n'accepte pas les objets avec tzinfo)
    raw_date = formation.date_debut
    if hasattr(raw_date, 'date') and callable(raw_date.date):
        start_date = raw_date.date()
    elif hasattr(raw_date, 'replace') and hasattr(raw_date, 'tzinfo') and raw_date.tzinfo is not None:
        start_date = raw_date.replace(tzinfo=None)
    else:
        start_date = raw_date or dt_date.today()
    examples = [
        (start_date, 1, 'Matin', dt_time(8, 30), dt_time(12, 0), 'Oui'),
        (start_date, 2, 'Après-midi', dt_time(14, 0), dt_time(17, 30), 'Oui'),
    ]
    for r, row_data in enumerate(examples, 2):
        for c, val in enumerate(row_data, 1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center')

    # Largeur des colonnes
    widths = [14, 10, 20, 14, 14, 16]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w

    # Note explicative
    ws.cell(row=5, column=1, value="Instructions :").font = Font(bold=True, size=10)
    ws.cell(row=6, column=1, value="• Date : format JJ/MM/AAAA ou AAAA-MM-JJ").font = Font(size=9)
    ws.cell(row=7, column=1, value="• Numéro : ordre dans la journée (1, 2, 3…). Laissez vide pour auto.").font = Font(size=9)
    ws.cell(row=8, column=1, value="• Heure début/fin : format HH:MM (ex: 08:30)").font = Font(size=9)
    ws.cell(row=9, column=1, value="• Auto-démarrage : Oui/Non — nécessite une heure de début").font = Font(size=9)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    safe_titre = formation.formation.replace(' ', '_')[:30]
    response['Content-Disposition'] = f'attachment; filename="emploi_du_temps_{safe_titre}.xlsx"'
    wb.save(response)
    return response


# ──────────────────────────────────────────────
# IMPORT EXCEL
# ──────────────────────────────────────────────

@dfrc_required
def import_excel_view(request):
    results = None
    errors = []

    if request.method == 'POST' and request.FILES.get('file'):
        from io import BytesIO
        from openpyxl import load_workbook
        from formations.management.commands.import_excel import Command as ImportCommand

        uploaded = request.FILES['file']
        file_type = request.POST.get('type', '')

        try:
            wb = load_workbook(BytesIO(uploaded.read()), read_only=True)
        except Exception as e:
            messages.error(request, f"Impossible de lire le fichier : {e}")
            return render(request, 'dashboard/import_excel.html', {})

        cmd = ImportCommand()
        cmd.stdout = _StringIO()
        stats = {}
        errors = []

        from django.db import transaction
        try:
            with transaction.atomic():
                if file_type == 'formations' and 'Formations' in wb.sheetnames:
                    _fc, _fu = cmd._import_formations(wb['Formations'], errors)
                    stats['Formations'] = _fc
                elif file_type == 'formateurs' and 'Formateurs' in wb.sheetnames:
                    stats['Formateurs'] = cmd._import_formateurs(wb['Formateurs'], errors)
                elif file_type == 'participants' and 'Participants' in wb.sheetnames:
                    stats['Participants'] = cmd._import_participants(wb['Participants'], errors)
                else:
                    messages.error(request, f"Feuille attendue introuvable dans le fichier.")
                    wb.close()
                    return render(request, 'dashboard/import_excel.html', {})
        except Exception as e:
            messages.error(request, f"Erreur lors de l'import : {e}")
            wb.close()
            return render(request, 'dashboard/import_excel.html', {})

        wb.close()
        results = stats

        total = sum(stats.values())
        if total > 0 and not errors:
            messages.success(request, f"Import réussi : {total} enregistrement(s) créé(s).")
        elif total > 0:
            messages.warning(request, f"{total} enregistrement(s) créé(s) avec {len(errors)} erreur(s).")
        elif not errors:
            messages.info(request, "Aucun nouvel enregistrement (données déjà en base).")
        if total > 0:
            action_map = {
                'formations': AuditLog.Action.FORMATION_CREATE,
                'formateurs': AuditLog.Action.FORMATEUR_IMPORT,
                'participants': AuditLog.Action.PARTICIPANT_IMPORT,
            }
            audit_action = action_map.get(file_type, AuditLog.Action.IMPORT_EXCEL)
            _log_audit(
                action=audit_action,
                request=request,
                extra={'type': file_type, 'total': total, 'errors': len(errors)},
            )

    return render(request, 'dashboard/import_excel.html', {
        'results': results,
        'errors': errors,
    })


class _StringIO:
    """Minimal stdout replacement for the management command."""
    def write(self, msg):
        pass
