"""
Vues API — Module Statistiques & Bilans (SYGEP-CPFAE).

Filtres disponibles sur GET /api/statistiques/ :
  ?formation_id=<id>     → stats pour une formation précise
  ?secretariat_id=<id>   → stats pour un secrétariat précis
  (combinables)
"""
from datetime import timedelta, date
import json

from django.db.models import Count, Q, Sum, F
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes

from formations.categorie_referentiel import resolve_categorie_ref
from formations.models import (
    Formation, Module, Participant, Formateur,
    ModuleParticipant, SessionModule, Secretariat,
)
from presences.models import Pointage

from .models import ConfigAlerteSeuil, Rapport, ObservationQualitative, SignatureRapport, NotificationRapport
from .bilans import (
    compute_bilans, compute_bilans_avec_tableaux, compute_bilan_effectifs_module,
    compute_bilan_effectifs_matiere,
    compute_bilan_effectifs_categorie, compute_bilan_periode_formation,
    compute_bilan_fac, list_bilan_fac_perimetre,
)
from .bilans_exports import build_bilans_export_response
from .bilan_fac_exports import build_bilan_fac_export_response
from .point_journalier import (
    compute_point_journalier, compute_point_journalier_avec_tableaux, get_tableau_detail,
)
from .point_journalier_exports import build_export_response
from .effectifs import (
    aggregation_seances_modules,
    count_sessions_comptabilisables,
    filter_sessions,
    module_ids_with_sessions_in_period,
    participant_ids_notoires,
    period_filter_active,
    q_pointage_present,
    session_ids_for_scope,
    sessions_in_period_qs,
)
from .rapport_notifications import (
    ADMIN_RAPPORT_ROLES, notifier_rapport, notifier_rapport_supprime,
    notifier_rapport_workflow,
)
from .access import (
    StatsScope,
    resolve_stats_scope,
    formations_liste_for_user,
    secretariats_liste_for_user,
    secretariats_stats_queryset,
    module_filter_kwargs,
    rapports_queryset_for_user,
    rapport_accessible,
    user_has_stats_access,
    user_secretariat_scope_locked,
    STATS_ACCESS_ROLES,
)

# ── Rôles ─────────────────────────────────────────────────────────────────────
STATS_ROLES = STATS_ACCESS_ROLES
VALIDATION_ROLES = {'ADMIN','DIRECTION','CHEF_INJS_ADMIN','INJS_ADMIN'}
GENERATION_ROLES = {'ADMIN','DIRECTION','CHEF_INJS_ADMIN','INJS_ADMIN',
                    'CHEF_SECRETARIAT','SECRETARIAT'}


def _check_role(user, allowed):
    return getattr(user, 'role', None) in allowed


def _taux(num, den):
    return round(num / den * 100, 1) if den else 0.0


def _count_formateurs_for_modules(module_ids, *, secretariat_id=None):
    """Formateurs assignés aux modules (principal + ModuleFormateur)."""
    from formations.models import Formateur, ModuleFormateur

    module_ids = list(module_ids or [])
    if not module_ids:
        return 0
    fids = set(
        Module.objects.filter(id__in=module_ids)
        .exclude(formateur=None)
        .values_list('formateur_id', flat=True)
    )
    fids.update(
        ModuleFormateur.objects.filter(module_id__in=module_ids)
        .values_list('formateur_id', flat=True)
    )
    if secretariat_id:
        fids &= set(
            Formateur.objects.filter(secretariats__id=secretariat_id)
            .values_list('id', flat=True)
        )
    return len(fids)


def _derniers_mois_cles(n=12):
    """Retourne les n derniers mois calendaires au format YYYY-MM (du plus ancien au plus récent)."""
    today = timezone.localdate().replace(day=1)
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f'{y:04d}-{m:02d}')
        m -= 1
        if m < 1:
            m = 12
            y -= 1
    out.reverse()
    return out


def _date_debut_mois(cle_mois):
    y, m = map(int, cle_mois.split('-'))
    return date(y, m, 1)


def _dict_par_mois(qs, date_field, agg=Count('id')):
    """Agrège un queryset par mois calendaire ; clé YYYY-MM."""
    return {
        (r['mois'].strftime('%Y-%m') if r['mois'] else ''): r['total']
        for r in qs.annotate(mois=TruncMonth(date_field)).values('mois').annotate(total=agg).order_by('mois')
    }


# ── Construction des filtres selon formation_id et/ou secretariat_id ──────────

def _filtres(formation_id=None, secretariat_id=None, module_ids=None):
    """
    Retourne un dict de 3 ensembles de filtres kwargs Django :
      mf  → sur ModuleParticipant (via module__)
      pf  → sur Pointage          (via session__module__)
      sm  → sur SessionModule     (via module__)
      mq  → sur Module directement
      pq  → sur Participant directement
    """
    mf, pf, sm, mq, pq = {}, {}, {}, {}, {}

    if formation_id:
        mf['module__formation_id'] = formation_id
        pf['session__module__formation_id'] = formation_id
        sm['module__formation_id'] = formation_id
        mq['formation_id'] = formation_id

    if secretariat_id:
        mf['module__secretariat_id'] = secretariat_id
        pf['session__module__secretariat_id'] = secretariat_id
        sm['module__secretariat_id'] = secretariat_id
        mq['secretariat_id'] = secretariat_id
        pq['secretariat_id'] = secretariat_id

    if module_ids is not None:
        mf['module_id__in'] = module_ids
        pf['session__module_id__in'] = module_ids
        sm['module_id__in'] = module_ids
        mq['id__in'] = module_ids
        if module_ids:
            pq['modules_inscrits__module_id__in'] = module_ids
        else:
            pq['pk__in'] = []

    return mf, pf, sm, mq, pq


def _scope_from_request(request, *, parse_module_id=False):
    def _int_key(key):
        v = request.query_params.get(key)
        if v is None and hasattr(request, 'data'):
            data = request.data
            if isinstance(data, dict):
                raw = data.get(key)
                v = raw if raw is not None else None
        return int(v) if v is not None and str(v).isdigit() else None

    scope, err = resolve_stats_scope(
        request.user,
        formation_id=_int_key('formation_id'),
        secretariat_id=_int_key('secretariat_id'),
        module_id=_int_key('module_id') if parse_module_id else None,
    )
    if err:
        return None, Response({'detail': err}, status=403)
    return scope, None


def _scope_compute_kwargs(scope):
    return {
        'formation_id': scope.formation_id,
        'secretariat_id': scope.secretariat_id,
        'module_ids': scope.module_ids,
    }


def _charge_formateurs(formation_id=None, secretariat_id=None, module_ids=None, limit=8):
    """
    Charge pédagogique : nombre de séances distinctes par formateur.
    Sources : pointages badge formateur, formateur principal du module,
    formateurs assignés via ModuleFormateur.
    """
    from collections import defaultdict

    _, pf, sm, _, _ = _filtres(formation_id, secretariat_id, module_ids)
    par_formateur = defaultdict(lambda: {'nom': '', 'sessions': set()})

    def _enregistrer(fid, nom, prenom, session_id):
        if not fid or not session_id:
            return
        ent = par_formateur[fid]
        if not ent['nom']:
            ent['nom'] = f"{prenom or ''} {nom or ''}".strip() or f"Formateur #{fid}"
        ent['sessions'].add(session_id)

    for r in Pointage.objects.filter(formateur__isnull=False, **pf).values(
        'formateur_id', 'formateur__nom', 'formateur__prenom', 'session_id',
    ):
        _enregistrer(
            r['formateur_id'], r['formateur__nom'], r['formateur__prenom'], r['session_id'],
        )

    for r in SessionModule.objects.filter(module__formateur__isnull=False, **sm).values(
        'id', 'module__formateur_id', 'module__formateur__nom', 'module__formateur__prenom',
    ):
        _enregistrer(
            r['module__formateur_id'],
            r['module__formateur__nom'],
            r['module__formateur__prenom'],
            r['id'],
        )

    for r in SessionModule.objects.filter(module__module_formateurs__isnull=False, **sm).values(
        'id',
        'module__module_formateurs__formateur_id',
        'module__module_formateurs__formateur__nom',
        'module__module_formateurs__formateur__prenom',
    ).distinct():
        _enregistrer(
            r['module__module_formateurs__formateur_id'],
            r['module__module_formateurs__formateur__nom'],
            r['module__module_formateurs__formateur__prenom'],
            r['id'],
        )

    rows = [
        {'nom': v['nom'], 'nb_sessions': len(v['sessions'])}
        for v in par_formateur.values()
        if v['sessions']
    ]
    rows.sort(key=lambda x: x['nb_sessions'], reverse=True)
    return rows[:limit]


def _auditeurs_notoires(formation_id=None, secretariat_id=None, module_ids=None):
    """
    Absents notoires : inscrits à au moins un module démarré du périmètre,
    sans aucune présence enregistrée, ou motif_notoire renseigné.
    """
    mf, _, _, _, _ = _filtres(formation_id, secretariat_id, module_ids)

    inscrits_pids = set(
        ModuleParticipant.objects.filter(**mf).values_list('participant_id', flat=True).distinct()
    )
    if not inscrits_pids:
        return {'total': 0, 'inscrits': 0, 'pct': 0.0, 'liste': []}

    notoire_ids = participant_ids_notoires(
        module_ids=module_ids,
        formation_id=formation_id,
        secretariat_id=secretariat_id,
    )
    notoire_ids &= inscrits_pids

    participants = (
        Participant.objects.filter(id__in=notoire_ids)
        .select_related('secretariat')
        .order_by('nom', 'prenom')
    )

    liste = []
    for p in participants:
        liste.append({
            'id': p.id,
            'matricule': p.matricule,
            'nom': p.nom,
            'prenom': p.prenom,
            'sexe': p.get_sexe_display() if p.sexe else '—',
            'categorie': p.categorie or '—',
            'grade': p.grade or '—',
            'groupe': p.groupe or '—',
            'vague': p.vague or '—',
            'secretariat': p.secretariat.nom if p.secretariat_id else '—',
            'secretariat_id': p.secretariat_id,
            'telephone': p.telephone or p.telephone2 or '—',
            'email': p.email or '—',
            'type_concours': p.type_concours or '—',
            'libelle_concours': p.libelle_concours or '—',
            'motif': (p.motif_notoire or '').strip() or 'Jamais badgé',
        })

    total_inscrits = len(inscrits_pids)
    total = len(liste)
    return {
        'total': total,
        'inscrits': total_inscrits,
        'pct': _taux(total, total_inscrits),
        'liste': liste,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _kpis_globaux(formation_id=None, secretariat_id=None, module_ids=None, date_debut=None, date_fin=None):
    mf, pf, sm, mq, pq = _filtres(formation_id, secretariat_id, module_ids)

    mod_ids_scope = list(Module.objects.filter(**mq).values_list('id', flat=True))
    period_active = period_filter_active(date_debut, date_fin)

    if period_active:
        mod_ids_active = module_ids_with_sessions_in_period(
            mod_ids_scope,
            date_debut=date_debut,
            date_fin=date_fin,
            extra_sm=sm,
        )
        mf_active = {**mf, 'module_id__in': mod_ids_active}
    else:
        mod_ids_active = mod_ids_scope
        mf_active = mf

    # Formations
    if formation_id:
        nb_formations = 1 if (not period_active or mod_ids_active) else 0
    elif module_ids is not None:
        nb_formations = (
            Module.objects.filter(id__in=mod_ids_active).values('formation').distinct().count()
            if mod_ids_active else 0
        )
    elif secretariat_id:
        nb_formations = (
            Module.objects.filter(secretariat_id=secretariat_id, id__in=mod_ids_active)
            .values('formation').distinct().count()
            if mod_ids_active else 0
        )
    else:
        if period_active:
            nb_formations = (
                Module.objects.filter(id__in=mod_ids_active).values('formation').distinct().count()
                if mod_ids_active else 0
            )
        else:
            nb_formations = Formation.objects.count()

    nb_modules = len(mod_ids_active) if period_active else Module.objects.filter(**mq).count()

    if period_active:
        nb_participants = (
            ModuleParticipant.objects.filter(**mf_active).values('participant').distinct().count()
            if mod_ids_active else 0
        )
    elif mf:
        nb_participants = ModuleParticipant.objects.filter(**mf).values('participant').distinct().count()
    elif pq:
        nb_participants = Participant.objects.filter(**pq).count()
    else:
        nb_participants = Participant.objects.count()

    if period_active:
        nb_formateurs = _count_formateurs_for_modules(
            mod_ids_active,
            secretariat_id=secretariat_id if secretariat_id and not formation_id else None,
        )
    elif secretariat_id and not formation_id:
        nb_formateurs = Formateur.objects.filter(secretariats__id=secretariat_id).distinct().count()
    elif formation_id:
        nb_formateurs = Module.objects.filter(**mq).exclude(formateur=None).values('formateur').distinct().count()
    else:
        nb_formateurs = Formateur.objects.count()

    if period_active:
        nb_sessions_total = sessions_in_period_qs(
            module_ids=mod_ids_scope,
            date_debut=date_debut,
            date_fin=date_fin,
            extra_sm=sm,
        ).count()
    else:
        nb_sessions_total = SessionModule.objects.filter(**sm).count()

    nb_sessions_terminees = count_sessions_comptabilisables(
        module_ids=mod_ids_scope,
        date_debut=date_debut,
        date_fin=date_fin,
    )

    sessions_en_cours_qs = SessionModule.objects.filter(
        demarree_le__isnull=False, terminee_le__isnull=True, **sm,
    )
    if period_active:
        if date_debut:
            sessions_en_cours_qs = sessions_en_cours_qs.filter(date_journee__gte=date_debut)
        if date_fin:
            sessions_en_cours_qs = sessions_en_cours_qs.filter(date_journee__lte=date_fin)
    nb_sessions_en_cours = sessions_en_cours_qs.count()

    if period_active:
        pf_period = dict(pf)
        if date_debut:
            pf_period['date_journee__gte'] = date_debut
        if date_fin:
            pf_period['date_journee__lte'] = date_fin
        nb_pointages = Pointage.objects.filter(**pf_period).count()
    else:
        nb_pointages = Pointage.objects.filter(**pf).count()

    from formations.volume_horaire import compute_volume_horaire_from_module_ids

    module_ids_scope = list(Module.objects.filter(**mq).values_list('id', flat=True))
    vh_totals = compute_volume_horaire_from_module_ids(
        module_ids_scope,
        date_debut=date_debut,
        date_fin=date_fin,
        integer_hours=True,
    )
    vh_prevu = vh_totals['prevu_heures']
    vh_realise_h = vh_totals['realise_heures']
    taux_execution_vh = vh_totals['taux_pct']

    return {
        'formations': nb_formations,
        'modules': nb_modules,
        'participants': nb_participants,
        'formateurs': nb_formateurs,
        'sessions_total': nb_sessions_total,
        'sessions_terminees': nb_sessions_terminees,
        'sessions_en_cours': nb_sessions_en_cours,
        'pointages': nb_pointages,
        'vh_prevu_heures': vh_prevu,
        'vh_realise_heures': vh_realise_h,
        'taux_execution_vh': taux_execution_vh,
    }


def _taux_par_modules(module_ids, date_debut=None, date_fin=None):
    """Taux de présence réel : places présentes / places attendues (séances comptabilisables)."""
    if not module_ids:
        return {'inscrits': 0, 'presents': 0, 'absents': 0, 'taux': 0.0}
    session_ids = session_ids_for_scope(module_ids, date_debut=date_debut, date_fin=date_fin)
    agg = aggregation_seances_modules(module_ids, session_ids=session_ids)
    return {
        'inscrits': agg['inscrits_distinct'],
        'presents': agg['presents_distinct'],
        'absents': agg['absents_distinct'],
        'taux': _taux(agg['places_presentes'], agg['places_attendues']),
        'places_attendues': agg['places_attendues'],
        'places_presentes': agg['places_presentes'],
    }


def _indicateurs_pedagogiques(
    formation_id=None, secretariat_id=None, module_ids=None, date_debut=None, date_fin=None,
):
    mf, pf, sm, mq, pq = _filtres(formation_id, secretariat_id, module_ids)

    module_ids = list(Module.objects.filter(**mq).values_list('id', flat=True))
    scope_session_ids = session_ids_for_scope(module_ids, date_debut=date_debut, date_fin=date_fin)
    agg_global = aggregation_seances_modules(module_ids, session_ids=scope_session_ids)

    total_inscrits = agg_global['inscrits_distinct']
    total_presents = agg_global['presents_distinct']
    total_absents = agg_global['absents_distinct']
    total_abandons = Pointage.objects.filter(
        statut__in=[Pointage.Statut.ABSENT_NON_BADGE, Pointage.Statut.HORS_LIGNE_SUSPECT],
        **pf,
    ).count()

    # Taux par formation (10 der. ou filtre spécifique)
    if secretariat_id and not formation_id:
        formations_qs = Formation.objects.filter(
            modules__secretariat_id=secretariat_id,
        ).distinct().order_by('-id')[:10]
    elif module_ids is not None:
        formations_qs = Formation.objects.filter(
            modules__id__in=module_ids,
        ).distinct().order_by('-id')[:10]
    elif formation_id:
        formations_qs = Formation.objects.filter(id=formation_id)
    else:
        formations_qs = Formation.objects.order_by('-id')[:10]

    taux_par_formation = []
    for f in formations_qs:
        f_mq = {'formation_id': f.id}
        if secretariat_id:
            f_mq['secretariat_id'] = secretariat_id
        if module_ids is not None:
            f_mod_ids = list(
                Module.objects.filter(**f_mq, id__in=module_ids).values_list('id', flat=True)
            )
        else:
            f_mod_ids = list(Module.objects.filter(**f_mq).values_list('id', flat=True))
        stats = _taux_par_modules(f_mod_ids, date_debut=date_debut, date_fin=date_fin)
        taux_par_formation.append({
            'formation': str(f),
            'formation_id': f.id,
            'inscrits': stats['inscrits'],
            'presents': stats['presents'],
            'taux': stats['taux'],
        })

    grade_qs = Module.objects.filter(**mq).exclude(grade='').values('grade').distinct().order_by('grade')
    taux_par_grade = []
    for row in grade_qs:
        grade = row['grade']
        g_mod_ids = list(Module.objects.filter(**mq, grade=grade).values_list('id', flat=True))
        stats = _taux_par_modules(g_mod_ids, date_debut=date_debut, date_fin=date_fin)
        taux_par_grade.append({
            'grade': grade,
            'inscrits': stats['inscrits'],
            'presents': stats['presents'],
            'taux': stats['taux'],
        })

    concours_qs = (
        Participant.objects.filter(**pq)
        .filter(modules_inscrits__module_id__in=module_ids)
        .exclude(type_concours='')
        .values('type_concours')
        .annotate(total=Count('id', distinct=True))
        .order_by('-total')[:8]
        if module_ids
        else Participant.objects.none()
    )
    par_type_concours = [{'type': r['type_concours'], 'total': r['total']} for r in concours_qs]

    taux_par_secretariat = []
    if not secretariat_id:
        sec_qs = Secretariat.objects.order_by('nom')
        if module_ids is not None:
            sec_ids = (
                Module.objects.filter(id__in=module_ids)
                .exclude(secretariat_id__isnull=True)
                .values_list('secretariat_id', flat=True)
                .distinct()
            )
            sec_qs = sec_qs.filter(pk__in=sec_ids)
        for s in sec_qs:
            s_mod_ids = list(
                Module.objects.filter(secretariat=s, **({'formation_id': formation_id} if formation_id else {}))
                .filter(**({'id__in': module_ids} if module_ids is not None else {}))
                .values_list('id', flat=True)
            )
            stats = _taux_par_modules(s_mod_ids, date_debut=date_debut, date_fin=date_fin)
            taux_par_secretariat.append({
                'secretariat': s.nom,
                'secretariat_id': s.id,
                'numero': s.numero,
                'inscrits': stats['inscrits'],
                'presents': stats['presents'],
                'taux': stats['taux'],
            })

    return {
        'total_inscrits': total_inscrits,
        'total_presents': total_presents,
        'total_absents': total_absents,
        'total_abandons': total_abandons,
        'places_attendues': agg_global['places_attendues'],
        'places_presentes': agg_global['places_presentes'],
        'places_absentes': agg_global['places_absentes'],
        'nb_seances_terminees': agg_global['nb_seances_terminees'],
        'taux_presence': _taux(agg_global['places_presentes'], agg_global['places_attendues']),
        'taux_absence': _taux(agg_global['places_absentes'], agg_global['places_attendues']),
        'taux_abandon': _taux(total_abandons, total_inscrits),
        'taux_couverture_auditeurs': _taux(total_presents, total_inscrits),
        'taux_achevement': _taux(total_presents, total_inscrits),  # compat. API — alias couverture
        'taux_par_formation': taux_par_formation,
        'taux_par_grade': taux_par_grade,
        'par_type_concours': par_type_concours,
        'taux_par_secretariat': taux_par_secretariat,
        'auditeurs_notoires': _auditeurs_notoires(formation_id, secretariat_id, module_ids),
    }


def _participants_par_categorie_ref(participants_qs, limit=8):
    """Répartition par libellé RefCategorie (mapping des valeurs brutes)."""
    counts = {}
    for raw in participants_qs.exclude(categorie='').values_list('categorie', flat=True):
        resolved = resolve_categorie_ref(raw)
        if not resolved:
            continue
        counts[resolved] = counts.get(resolved, 0) + 1
    return [
        {'categorie': cat, 'total': total}
        for cat, total in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _indicateurs_admin(
    formation_id=None, secretariat_id=None, module_ids=None, date_debut=None, date_fin=None,
):
    mf, pf, sm, mq, pq = _filtres(formation_id, secretariat_id, module_ids)

    mod_ids_scope = list(Module.objects.filter(**mq).values_list('id', flat=True))
    nb_groupes    = Module.objects.filter(**mq).exclude(groupe='').values('groupe').distinct().count()
    nb_encadrants = Module.objects.filter(**mq).exclude(superviseur=None).values('superviseur').distinct().count()
    nb_seances_annulees = SessionModule.objects.filter(
        demarree_le__isnull=True, date_journee__lt=date.today(), **sm,
    ).count()
    nb_seances_terminees = count_sessions_comptabilisables(
        module_ids=mod_ids_scope,
        date_debut=date_debut,
        date_fin=date_fin,
    )

    # H/F sur auditeurs inscrits aux modules du périmètre
    inscrits_pids = ModuleParticipant.objects.filter(**mf).values_list('participant_id', flat=True).distinct()
    p_inscrits = Participant.objects.filter(id__in=inscrits_pids)
    hommes = p_inscrits.filter(sexe='MASCULIN').count()
    femmes = p_inscrits.filter(sexe='FEMININ').count()
    total_hf = hommes + femmes

    inscrits_q = ModuleParticipant.objects.filter(**mf).values('participant').distinct().count()
    moy_par_groupe = round(inscrits_q / nb_groupes, 1) if nb_groupes else 0

    nb_absences_notoires = len(participant_ids_notoires(
        module_ids=module_ids,
        formation_id=formation_id,
        secretariat_id=secretariat_id,
    ))

    charge_formateurs = _charge_formateurs(formation_id, secretariat_id, module_ids)

    statuts = list(
        Pointage.objects.filter(**pf)
        .values('statut').annotate(total=Count('id')).order_by('-total')
    )

    # Stats par secrétariat — résumé opérationnel global
    stats_secretariats = []
    if not secretariat_id:
        sec_qs = Secretariat.objects.order_by('nom')
        if module_ids is not None:
            sec_ids = (
                Module.objects.filter(id__in=module_ids)
                .exclude(secretariat_id__isnull=True)
                .values_list('secretariat_id', flat=True)
                .distinct()
            )
            sec_qs = sec_qs.filter(pk__in=sec_ids)
        for s in sec_qs:
            s_sm = {**sm, 'module__secretariat': s}
            s_pf = {**pf, 'session__module__secretariat': s}
            stats_secretariats.append({
                'secretariat': s.nom, 'secretariat_id': s.id, 'numero': s.numero,
                'nb_modules': Module.objects.filter(
                    secretariat=s,
                    **({'formation_id': formation_id} if formation_id else {}),
                    **({'id__in': module_ids} if module_ids is not None else {}),
                ).count(),
                'nb_participants': Participant.objects.filter(secretariat=s).count(),
                'nb_sessions': SessionModule.objects.filter(**s_sm).count(),
                'nb_pointages': Pointage.objects.filter(**s_pf).count(),
                'nb_absences': len(participant_ids_notoires(
                    secretariat_id=s.id,
                    formation_id=formation_id,
                    module_ids=module_ids,
                )),
            })

    return {
        'nb_groupes': nb_groupes,
        'nb_encadrants': nb_encadrants,
        'nb_seances_annulees': nb_seances_annulees,
        'nb_seances_terminees': nb_seances_terminees,
        'nb_absences_notoires': nb_absences_notoires,
        'ratio_hf': {
            'hommes': hommes, 'femmes': femmes, 'total': total_hf,
            'pct_hommes': _taux(hommes, total_hf), 'pct_femmes': _taux(femmes, total_hf),
        },
        'moy_auditeurs_groupe': moy_par_groupe,
        'charge_formateurs': charge_formateurs,
        'pointages_par_statut': statuts,
        'participants_par_sexe': [{'sexe': 'Hommes', 'total': hommes}, {'sexe': 'Femmes', 'total': femmes}],
        'participants_par_categorie': _participants_par_categorie_ref(p_inscrits),
        'participants_par_vague': list(
            p_inscrits.exclude(vague='').values('vague').annotate(total=Count('id')).order_by('-total').values('vague', 'total')[:6]
        ),
        'participants_par_grade': list(
            p_inscrits.exclude(grade='').values('grade').annotate(total=Count('id')).order_by('-total').values('grade', 'total')[:8]
        ),
        'auditeurs_notoires': _auditeurs_notoires(formation_id, secretariat_id, module_ids),
        'stats_secretariats': stats_secretariats,
    }


def _historique_mensuel(mois=12, formation_id=None, secretariat_id=None, module_ids=None):
    _, pf, sm, mq, _ = _filtres(formation_id, secretariat_id, module_ids)
    mois_cles = _derniers_mois_cles(mois)
    date_debut = _date_debut_mois(mois_cles[0])
    module_ids = list(Module.objects.filter(**mq).values_list('id', flat=True))

    pt_total = _dict_par_mois(
        Pointage.objects.filter(date_journee__gte=date_debut, **pf), 'date_journee',
    )

    # Présences / absences par mois : places séance (inscrits × séances terminées)
    places_par_mois = {cle: {'attendues': 0, 'presentes': 0} for cle in mois_cles}
    if module_ids:
        from .effectifs import (
            participants_par_module,
            presents_par_session,
            rattrapages_par_session,
        )

        par_mod = participants_par_module(module_ids)
        sess_rows = list(
            filter_sessions(module_ids=module_ids)
            .filter(date_journee__gte=date_debut)
            .values_list('id', 'module_id', 'date_journee')
        )
        sess_ids = [r[0] for r in sess_rows]
        pres_map = presents_par_session(sess_ids)
        rattr_map = rattrapages_par_session(sess_ids)
        for sid, mid, d_jour in sess_rows:
            cle = d_jour.strftime('%Y-%m')
            if cle not in places_par_mois:
                continue
            pids = set(par_mod.get(mid, {}))
            attendus = pids | rattr_map.get(sid, set())
            places_par_mois[cle]['attendues'] += len(attendus)
            places_par_mois[cle]['presentes'] += len(pres_map.get(sid, set()) & attendus)

    pt_presents = {cle: v['presentes'] for cle, v in places_par_mois.items()}
    pt_absents = {
        cle: max(places_par_mois[cle]['attendues'] - places_par_mois[cle]['presentes'], 0)
        for cle in mois_cles
    }

    sessions = _dict_par_mois(
        filter_sessions(module_ids=module_ids).filter(date_journee__gte=date_debut, **sm),
        'date_journee',
    )
    modules_crees = _dict_par_mois(
        Module.objects.filter(created_at__date__gte=date_debut, **mq), 'created_at',
    )
    # Modules ayant eu au moins une séance ce mois-là (activité réelle)
    modules_actifs = {
        (r['mois'].strftime('%Y-%m') if r['mois'] else ''): r['total']
        for r in filter_sessions(module_ids=module_ids).filter(date_journee__gte=date_debut, **sm)
        .annotate(mois=TruncMonth('date_journee')).values('mois')
        .annotate(total=Count('module', distinct=True)).order_by('mois')
    }

    pointages_par_mois = []
    sessions_par_mois = []
    modules_par_mois = []
    taux_presence_par_mois = []
    cumul_modules = Module.objects.filter(
        created_at__date__lt=date_debut, **mq,
    ).count()

    for cle in mois_cles:
        total_pt = pt_total.get(cle, 0)
        presents = pt_presents.get(cle, 0)
        absents = pt_absents.get(cle, 0)
        denom = presents + absents
        pointages_par_mois.append({
            'mois': cle,
            'total': total_pt,
            'presents': presents,
            'absents': absents,
        })
        taux_presence_par_mois.append({
            'mois': cle,
            'total': _taux(presents, denom),
            'presents': presents,
            'absents': absents,
        })
        sessions_par_mois.append({'mois': cle, 'total': sessions.get(cle, 0)})
        cumul_modules += modules_crees.get(cle, 0)
        modules_par_mois.append({
            'mois': cle,
            'total': modules_crees.get(cle, 0),
            'actifs': modules_actifs.get(cle, 0),
            'cumul': cumul_modules,
        })

    # Synthèse pour cartes KPI
    totals_pt = [m['total'] for m in pointages_par_mois]
    totals_sess = [m['total'] for m in sessions_par_mois]
    taux_vals = [m['total'] for m in taux_presence_par_mois if m['presents'] + m['absents'] > 0]
    mois_avec_donnees = sum(1 for t in totals_pt if t > 0)

    def _variation(courant, precedent):
        if precedent == 0:
            return None if courant == 0 else 100.0
        return round((courant - precedent) / precedent * 100, 1)

    pt_courant, pt_prec = totals_pt[-1] if totals_pt else 0, totals_pt[-2] if len(totals_pt) > 1 else 0
    sess_courant, sess_prec = totals_sess[-1] if totals_sess else 0, totals_sess[-2] if len(totals_sess) > 1 else 0

    return {
        'mois_periode': mois_cles,
        'pointages_par_mois': pointages_par_mois,
        'taux_presence_par_mois': taux_presence_par_mois,
        'sessions_par_mois': sessions_par_mois,
        'modules_par_mois': modules_par_mois,
        'resume': {
            'total_pointages': sum(totals_pt),
            'moy_pointages_mois': round(sum(totals_pt) / mois_avec_donnees, 1) if mois_avec_donnees else 0,
            'total_sessions': sum(totals_sess),
            'moy_taux_presence': round(sum(taux_vals) / len(taux_vals), 1) if taux_vals else 0,
            'modules_actifs_dernier_mois': modules_par_mois[-1]['actifs'] if modules_par_mois else 0,
            'variation_pointages_pct': _variation(pt_courant, pt_prec),
            'variation_sessions_pct': _variation(sess_courant, sess_prec),
            'pointages_mois_courant': pt_courant,
            'sessions_mois_courant': sess_courant,
        },
    }


# Indicateurs affichés sur l'onglet « Vue d'ensemble » uniquement
ALERTES_OVERVIEW_CODES = (
    'taux_presence',
    'taux_execution_vh',
    'saturation_groupe',
)

SEUILS_DEFAUT = {
    'taux_presence':        {'seuil_avertissement': 75, 'seuil_critique': 60},
    'taux_absence':         {'seuil_avertissement': 20, 'seuil_critique': 35},
    'taux_abandon':         {'seuil_avertissement': 10, 'seuil_critique': 20},
    'taux_execution_vh':    {'seuil_avertissement': 70, 'seuil_critique': 50},
    'nb_absences_notoires': {'seuil_avertissement': 50, 'seuil_critique': 100},
    'saturation_groupe':    {'seuil_avertissement': 80, 'seuil_critique': 95},
}

INDICATEUR_META = {
    'taux_presence': {
        'libelle': 'Assiduité séance',
        'unite': '%',
        'inverse': False,
        'icone': 'bi-person-check',
        'couleur': '#2277C1',
        'aide': (
            'Places présentes ÷ places attendues sur les séances terminées du périmètre. '
            'Mesure l\'assiduité séance par séance (dashboard, alertes, historique).'
        ),
        'echelle_max': 100,
    },
    'taux_absence': {
        'libelle': "Taux d'absence",
        'unite': '%',
        'inverse': True,
        'icone': 'bi-person-x',
        'couleur': '#C62828',
        'aide': 'Part des absences enregistrées. Au-delà du seuil, une action corrective est recommandée.',
        'echelle_max': 100,
    },
    'taux_abandon': {
        'libelle': 'Événements absence / suspect',
        'unite': '%',
        'inverse': True,
        'icone': 'bi-box-arrow-right',
        'couleur': '#F5B100',
        'aide': (
            'Pointages « absent non badgé » ou « hors ligne suspect » rapportés aux inscrits. '
            'Distinct des absents notoires (jamais badgés).'
        ),
        'echelle_max': 100,
    },
    'taux_execution_vh': {
        'libelle': 'Avancement VH (sessions clôturées)',
        'unite': '%',
        'inverse': False,
        'icone': 'bi-clock-history',
        'couleur': '#1565C0',
        'aide': (
            'Heures réalisées ÷ heures prévues sur les séances clôturées du périmètre. '
            'Indique l\'avancement du volume horaire.'
        ),
        'echelle_max': 100,
    },
    'nb_absences_notoires': {
        'libelle': 'Absents notoires',
        'unite': '',
        'inverse': True,
        'icone': 'bi-exclamation-triangle',
        'couleur': '#AD1457',
        'aide': (
            'Nombre d\'inscrits à au moins un module démarré, sans aucune présence enregistrée, '
            'ou avec motif notoire renseigné. Aligné dashboard, bilans et Bilan FAC.'
        ),
        'echelle_max': None,
    },
    'saturation_groupe': {
        'libelle': 'Saturation des groupes',
        'unite': '%',
        'inverse': True,
        'icone': 'bi-people-fill',
        'couleur': '#7B1FA2',
        'aide': 'Remplissage moyen des groupes (référence 40 étudiants/groupe). Au-delà de 95 %, risque de surcharge.',
        'echelle_max': 100,
    },
}


def _init_seuils_defaut():
    """Crée les seuils CPFAE par défaut s'ils n'existent pas."""
    created = []
    for indicateur, vals in SEUILS_DEFAUT.items():
        obj, was_created = ConfigAlerteSeuil.objects.get_or_create(
            indicateur=indicateur,
            defaults={**vals, 'actif': True},
        )
        if was_created:
            created.append(indicateur)
    return created


def _valeurs_indicateurs_from(ped, adm, kpis):
    """Valeurs indicateurs à partir de blocs déjà calculés (évite les requêtes en double)."""
    capacite_ref = 40
    moy_groupe = adm.get('moy_auditeurs_groupe') or 0
    saturation = min(100.0, round(moy_groupe / capacite_ref * 100, 1)) if moy_groupe else 0.0

    return {
        'taux_presence': ped['taux_presence'],
        'taux_absence': ped['taux_absence'],
        'taux_abandon': ped['taux_abandon'],
        'taux_execution_vh': kpis['taux_execution_vh'],
        'nb_absences_notoires': adm['nb_absences_notoires'],
        'saturation_groupe': saturation,
    }


def _valeurs_indicateurs(formation_id=None, secretariat_id=None, module_ids=None):
    """Calcule les valeurs courantes de tous les indicateurs surveillés."""
    ped = _indicateurs_pedagogiques(formation_id, secretariat_id, module_ids)
    adm = _indicateurs_admin(formation_id, secretariat_id, module_ids)
    kpis = _kpis_globaux(formation_id, secretariat_id, module_ids)
    return _valeurs_indicateurs_from(ped, adm, kpis)


def _evaluer_niveau(valeur, seuil_avert, seuil_crit, inverse):
    if inverse:
        if valeur >= seuil_crit:
            return 'critique'
        if valeur >= seuil_avert:
            return 'avertissement'
    else:
        if valeur <= seuil_crit:
            return 'critique'
        if valeur <= seuil_avert:
            return 'avertissement'
    return 'ok'


def _indicateurs_suivi_from_valeurs(valeurs):
    """Liste complète des indicateurs à partir de valeurs déjà calculées."""
    seuils_map = {s.indicateur: s for s in ConfigAlerteSeuil.objects.all()}
    choices = dict(ConfigAlerteSeuil.Indicateur.choices)
    result = []

    for code in ConfigAlerteSeuil.Indicateur.values:
        meta = INDICATEUR_META.get(code, {})
        s = seuils_map.get(code)
        valeur = valeurs.get(code, 0)
        if s and s.actif:
            niveau = _evaluer_niveau(
                valeur, s.seuil_avertissement, s.seuil_critique, meta.get('inverse', False),
            )
        elif s:
            niveau = 'inactif'
        else:
            niveau = 'non_configure'

        result.append({
            'indicateur': code,
            'libelle': meta.get('libelle') or choices.get(code, code),
            'valeur': valeur,
            'unite': meta.get('unite', ''),
            'inverse': meta.get('inverse', False),
            'icone': meta.get('icone', 'bi-speedometer2'),
            'couleur': meta.get('couleur', '#64748b'),
            'aide': meta.get('aide', ''),
            'echelle_max': meta.get('echelle_max'),
            'niveau': niveau,
            'actif': bool(s and s.actif),
            'configure': bool(s),
            'seuil_avertissement': s.seuil_avertissement if s else SEUILS_DEFAUT.get(code, {}).get('seuil_avertissement'),
            'seuil_critique': s.seuil_critique if s else SEUILS_DEFAUT.get(code, {}).get('seuil_critique'),
        })
    return result


def _indicateurs_suivi(formation_id=None, secretariat_id=None, module_ids=None):
    """Liste complète des indicateurs avec valeur, seuils et statut visuel."""
    valeurs = _valeurs_indicateurs(formation_id, secretariat_id, module_ids)
    return _indicateurs_suivi_from_valeurs(valeurs)


def _alertes_overview_from_suivi(suivi):
    """Les 3 indicateurs clés pour le bandeau Vue d'ensemble."""
    by_code = {i['indicateur']: i for i in suivi}
    return [by_code[c] for c in ALERTES_OVERVIEW_CODES if c in by_code]


def _alertes_overview(formation_id=None, secretariat_id=None, module_ids=None):
    return _alertes_overview_from_suivi(_indicateurs_suivi(formation_id, secretariat_id, module_ids))


def _verifier_alertes_from_suivi(suivi):
    if not ConfigAlerteSeuil.objects.filter(actif=True).exists():
        return []

    alertes = []
    for ind in suivi:
        if ind['niveau'] in ('critique', 'avertissement'):
            alertes.append({
                'indicateur': ind['indicateur'],
                'libelle': ind['libelle'],
                'valeur': ind['valeur'],
                'unite': ind['unite'],
                'niveau': ind['niveau'],
                'seuil_avertissement': ind['seuil_avertissement'],
                'seuil_critique': ind['seuil_critique'],
            })
    return alertes


def _verifier_alertes(formation_id=None, secretariat_id=None, module_ids=None):
    return _verifier_alertes_from_suivi(_indicateurs_suivi(formation_id, secretariat_id, module_ids))


DASHBOARD_SECTIONS = frozenset({
    'kpis', 'pedagogiques', 'admin_operationnel', 'historique',
    'alertes', 'alertes_overview', 'formations_liste', 'secretariats_liste', 'filtre_actif',
})


def _parse_dashboard_sections(request):
    """Sections demandées via ?sections=kpis,pedagogiques (vide = tout)."""
    raw = (request.query_params.get('sections') or '').strip()
    if not raw:
        return set(DASHBOARD_SECTIONS)
    return {s.strip() for s in raw.split(',') if s.strip()} & DASHBOARD_SECTIONS


def _build_dashboard_payload(scope: StatsScope, sections, user, period=None):
    """Construit uniquement les blocs demandés (chargement par onglet)."""
    formation_id = scope.formation_id
    secretariat_id = scope.secretariat_id
    module_ids = scope.module_ids
    date_debut = period['date_debut'] if period else None
    date_fin = period['date_fin'] if period else None
    need_ped = bool(sections & {'pedagogiques', 'alertes', 'alertes_overview'})
    need_adm = bool(sections & {'admin_operationnel', 'alertes', 'alertes_overview'})
    need_kpis = bool(sections & {'kpis', 'alertes', 'alertes_overview'})
    need_alertes = bool(sections & {'alertes', 'alertes_overview'})

    ped = _indicateurs_pedagogiques(
        formation_id, secretariat_id, module_ids, date_debut, date_fin,
    ) if need_ped else None
    adm = _indicateurs_admin(
        formation_id, secretariat_id, module_ids, date_debut, date_fin,
    ) if need_adm else None
    kpis = _kpis_globaux(
        formation_id, secretariat_id, module_ids, date_debut, date_fin,
    ) if need_kpis else None

    payload = {}

    if period and (need_kpis or need_ped or need_adm):
        from formations.period_filter import periode_api_payload
        payload['periode'] = periode_api_payload(
            date_debut, date_fin, period['meta'],
        )

    if 'kpis' in sections and kpis is not None:
        payload['kpis'] = kpis
    if 'pedagogiques' in sections and ped is not None:
        payload['pedagogiques'] = ped
    if 'admin_operationnel' in sections and adm is not None:
        payload['admin_operationnel'] = adm
    if 'historique' in sections:
        payload['historique'] = _historique_mensuel(12, formation_id, secretariat_id, module_ids)

    if need_alertes and ped is not None and adm is not None and kpis is not None:
        suivi = _indicateurs_suivi_from_valeurs(_valeurs_indicateurs_from(ped, adm, kpis))
        if 'alertes' in sections:
            payload['alertes'] = _verifier_alertes_from_suivi(suivi)
        if 'alertes_overview' in sections:
            payload['alertes_overview'] = _alertes_overview_from_suivi(suivi)

    if 'formations_liste' in sections:
        payload['formations_liste'] = formations_liste_for_user(user)
    if 'secretariats_liste' in sections:
        payload['secretariats_liste'] = secretariats_liste_for_user(user)
    if 'filtre_actif' in sections:
        payload['filtre_actif'] = {
            'formation_id': formation_id,
            'secretariat_id': secretariat_id,
            'scope_locked': user_secretariat_scope_locked(user),
        }

    return payload


# ── Vues ──────────────────────────────────────────────────────────────────────

class DashboardView(APIView):
    """GET /api/statistiques/?formation_id=&secretariat_id="""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not user_has_stats_access(request.user):
            return Response({'detail': 'Accès non autorisé.'}, status=403)

        scope, err = _scope_from_request(request)
        if err:
            return err

        from formations.period_filter import parse_period_from_request

        period = parse_period_from_request(request)
        if period['error']:
            return Response({'detail': period['detail']}, status=400)

        sections = _parse_dashboard_sections(request)

        from .cache_utils import (
            get_stats_dashboard_cached,
            set_stats_dashboard_cached,
            stats_dashboard_cache_key,
        )

        cache_key = stats_dashboard_cache_key(request, sections, scope, period)
        cached = get_stats_dashboard_cached(cache_key)
        if cached is not None:
            return Response(cached)

        payload = _build_dashboard_payload(scope, sections, request.user, period=period)
        set_stats_dashboard_cached(cache_key, payload)
        return Response(payload)


def _build_secretariats_stats_payload(user, scope, period):
    """Calcule la synthèse KPIs par secrétariat."""
    from formations.period_filter import periode_api_payload

    formation_id = scope.formation_id
    module_ids = scope.module_ids
    mod_kw = module_filter_kwargs(scope)
    date_debut = period['date_debut']
    date_fin = period['date_fin']

    resultats = []

    global_an = _auditeurs_notoires(formation_id, scope.secretariat_id, module_ids)
    an_by_sec = {}
    for item in global_an.get('liste') or []:
        sid = item.get('secretariat_id')
        if sid is not None:
            an_by_sec.setdefault(sid, []).append(item)

    for s in secretariats_stats_queryset(user):
        mq = {'secretariat': s, **mod_kw}
        pf = {'session__module__secretariat': s, **({'session__module_id__in': module_ids} if module_ids is not None else {})}
        if formation_id:
            mq['formation_id'] = formation_id
            pf['session__module__formation_id'] = formation_id

        mod_ids = list(Module.objects.filter(**mq).values_list('id', flat=True))
        if period_filter_active(date_debut, date_fin):
            mod_ids = module_ids_with_sessions_in_period(
                mod_ids,
                date_debut=date_debut,
                date_fin=date_fin,
            )

        scope_session_ids = session_ids_for_scope(
            mod_ids, date_debut=date_debut, date_fin=date_fin,
        )
        agg = aggregation_seances_modules(mod_ids, session_ids=scope_session_ids)

        nb_modules = len(mod_ids)
        nb_inscrits = agg['inscrits_distinct']
        nb_presents = agg['presents_distinct']
        nb_absences = agg['places_absentes']
        nb_participants = nb_inscrits
        nb_sessions = agg['nb_seances_terminees']
        pf_present = dict(pf)
        if period_filter_active(date_debut, date_fin):
            if date_debut:
                pf_present['date_journee__gte'] = date_debut
            if date_fin:
                pf_present['date_journee__lte'] = date_fin
        nb_pointages = Pointage.objects.filter(**pf_present).filter(q_pointage_present()).count()

        inscrits_pids = ModuleParticipant.objects.filter(
            module_id__in=mod_ids,
        ).values_list('participant_id', flat=True).distinct()
        p_inscrits = Participant.objects.filter(id__in=inscrits_pids)
        hommes = p_inscrits.filter(sexe='MASCULIN').count()
        femmes = p_inscrits.filter(sexe='FEMININ').count()

        nb_formateurs = _count_formateurs_for_modules(mod_ids, secretariat_id=s.id)

        from formations.volume_horaire import compute_volume_horaire_from_module_ids

        vh_totals = compute_volume_horaire_from_module_ids(
            mod_ids, date_debut=date_debut, date_fin=date_fin,
            integer_hours=True,
        )
        vh_prevu = vh_totals['prevu_heures']
        vh_realise = vh_totals['realise_heures']

        an_list = an_by_sec.get(s.id, [])
        nb_auditeurs_notoires = len(an_list)

        resultats.append({
            'secretariat_id': s.id,
            'secretariat': s.nom,
            'numero': s.numero,
            'responsable': s.responsable.get_full_name() if s.responsable else None,
            'nb_modules': nb_modules,
            'nb_participants': nb_participants,
            'nb_formateurs': nb_formateurs,
            'nb_sessions': nb_sessions,
            'nb_pointages': nb_pointages,
            'nb_inscrits': nb_inscrits,
            'nb_presents': nb_presents,
            'nb_absences': nb_absences,
            'nb_auditeurs_notoires': nb_auditeurs_notoires,
            'pct_auditeurs_notoires': _taux(nb_auditeurs_notoires, nb_inscrits),
            'places_attendues': agg['places_attendues'],
            'places_presentes': agg['places_presentes'],
            'taux_presence': _taux(agg['places_presentes'], agg['places_attendues']),
            'taux_absence': _taux(agg['places_absentes'], agg['places_attendues']),
            'ratio_hf': {'hommes': hommes, 'femmes': femmes,
                         'pct_hommes': _taux(hommes, hommes + femmes),
                         'pct_femmes': _taux(femmes, hommes + femmes)},
            'vh_prevu': vh_prevu,
            'vh_realise': vh_realise,
            'taux_execution_vh': vh_totals['taux_pct'],
        })

    return {
        'secretariats': resultats,
        'total': len(resultats),
        'auditeurs_notoires': global_an,
        'periode': periode_api_payload(date_debut, date_fin, period['meta']),
    }


class SecretariatsStatsView(APIView):
    """GET /api/statistiques/secretariats/ — Synthèse KPIs par secrétariat."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not user_has_stats_access(request.user):
            return Response({'detail': 'Accès non autorisé.'}, status=403)

        scope, err = _scope_from_request(request)
        if err:
            return err

        from formations.period_filter import parse_period_from_request

        period = parse_period_from_request(request)
        if period['error']:
            return Response({'detail': period['detail']}, status=400)

        from .cache_utils import (
            get_stats_secretariats_cached,
            set_stats_secretariats_cached,
            stats_secretariats_cache_key,
        )

        cache_key = stats_secretariats_cache_key(request, scope, period)
        cached = get_stats_secretariats_cached(cache_key)
        if cached is not None:
            return Response(cached)

        payload = _build_secretariats_stats_payload(request.user, scope, period)
        set_stats_secretariats_cached(cache_key, payload)
        return Response(payload)


# ── Vues Alertes, Rapports (inchangées) ───────────────────────────────────────

class AlertesSeuilsView(APIView):
    permission_classes = [IsAuthenticated]

    def _scope(self, request):
        return _scope_from_request(request)

    def get(self, request):
        if not user_has_stats_access(request.user):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        scope, err = self._scope(request)
        if err:
            return err
        choices = dict(ConfigAlerteSeuil.Indicateur.choices)
        seuils = list(ConfigAlerteSeuil.objects.values('id', 'indicateur', 'seuil_avertissement', 'seuil_critique', 'actif'))
        for s in seuils:
            meta = INDICATEUR_META.get(s['indicateur'], {})
            s['libelle'] = meta.get('libelle') or choices.get(s['indicateur'], s['indicateur'])
            s['aide'] = meta.get('aide', '')
            s['icone'] = meta.get('icone', 'bi-speedometer2')
        indicateurs = _indicateurs_suivi(scope.formation_id, scope.secretariat_id, scope.module_ids)
        synthese = {
            'ok': sum(1 for i in indicateurs if i['niveau'] == 'ok'),
            'avertissement': sum(1 for i in indicateurs if i['niveau'] == 'avertissement'),
            'critique': sum(1 for i in indicateurs if i['niveau'] == 'critique'),
            'inactif': sum(1 for i in indicateurs if i['niveau'] == 'inactif'),
            'non_configure': sum(1 for i in indicateurs if i['niveau'] == 'non_configure'),
        }
        return Response({
            'seuils': seuils,
            'indicateurs': indicateurs,
            'synthese': synthese,
            'seuils_vides': len(seuils) == 0,
        })

    def post(self, request):
        """Initialise les seuils CPFAE par défaut."""
        if not _check_role(request.user, VALIDATION_ROLES):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        created = _init_seuils_defaut()
        scope, err = self._scope(request)
        if err:
            return err
        return Response({
            'detail': 'Seuils initialisés.' if created else 'Seuils déjà configurés.',
            'creees': created,
            'indicateurs': _indicateurs_suivi(scope.formation_id, scope.secretariat_id, scope.module_ids),
        })

    def put(self, request):
        if not _check_role(request.user, VALIDATION_ROLES):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        data = request.data
        items = data if isinstance(data, list) else data.get('seuils', [])
        for item in items:
            ConfigAlerteSeuil.objects.update_or_create(
                indicateur=item['indicateur'],
                defaults={
                    'seuil_avertissement': item['seuil_avertissement'],
                    'seuil_critique': item['seuil_critique'],
                    'actif': item.get('actif', True),
                },
            )
        scope, err = self._scope(request)
        if err:
            return err
        return Response({
            'detail': 'Seuils mis à jour.',
            'indicateurs': _indicateurs_suivi(scope.formation_id, scope.secretariat_id, scope.module_ids),
        })


class RapportsListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not user_has_stats_access(request.user):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        return Response(list(
            rapports_queryset_for_user(request.user)
            .select_related('generateur', 'validateur', 'formation', 'secretariat')
            .order_by('-created_at')
            .values(
                'id', 'titre', 'type', 'statut', 'periode_debut', 'periode_fin', 'commentaire',
                'created_at', 'updated_at', 'date_validation', 'date_publication',
                'generateur__username', 'validateur__username', 'formation__formation',
                'secretariat_id', 'secretariat__nom',
            )[:100]
        ))

    def post(self, request):
        if not _check_role(request.user, GENERATION_ROLES):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        scope, err = _scope_from_request(request)
        if err:
            return err
        formation_id = scope.formation_id
        secretariat_id = scope.secretariat_id
        module_ids = scope.module_ids
        snapshot = {
            'kpis':         _kpis_globaux(formation_id, secretariat_id, module_ids),
            'pedagogiques': _indicateurs_pedagogiques(formation_id, secretariat_id, module_ids),
            'admin_operationnel': _indicateurs_admin(formation_id, secretariat_id, module_ids),
            'historique':   _historique_mensuel(12, formation_id, secretariat_id, module_ids),
        }
        rapport = Rapport.objects.create(
            titre=request.data.get('titre') or f"Rapport {request.data.get('type','MENSUEL')} — {timezone.now().strftime('%d/%m/%Y')}",
            type=request.data.get('type', Rapport.Type.MENSUEL),
            statut=Rapport.Statut.BROUILLON,
            periode_debut=request.data.get('periode_debut', date.today().replace(day=1)),
            periode_fin=request.data.get('periode_fin', date.today()),
            formation_id=formation_id,
            secretariat_id=secretariat_id,
            generateur=request.user,
            commentaire=request.data.get('commentaire', ''),
            donnees_json=snapshot,
        )
        return Response({'id': rapport.id, 'titre': rapport.titre, 'statut': rapport.statut,
                         'created_at': rapport.created_at}, status=201)


class RapportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _data(self, rapport):
        return {
            'id': rapport.id, 'titre': rapport.titre, 'type': rapport.type,
            'statut': rapport.statut, 'periode_debut': rapport.periode_debut,
            'periode_fin': rapport.periode_fin, 'commentaire': rapport.commentaire,
            'donnees_json': rapport.donnees_json,
            'generateur': rapport.generateur.username if rapport.generateur else None,
            'validateur': rapport.validateur.username if rapport.validateur else None,
            'date_validation': rapport.date_validation, 'date_publication': rapport.date_publication,
            'created_at': rapport.created_at, 'updated_at': rapport.updated_at,
            'hash_donnees': rapport.hash_donnees,
            'observations': list(rapport.observations.values('id','type','description','auteur__username','created_at')),
            'signatures':   list(rapport.signatures.values('id','signataire__username','role_signataire','date_signature','commentaire')),
        }

    def get(self, request, rapport_id):
        if not user_has_stats_access(request.user):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        rapport = get_object_or_404(Rapport, id=rapport_id)
        if not rapport_accessible(request.user, rapport):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        return Response(self._data(rapport))

    def patch(self, request, rapport_id):
        rapport = get_object_or_404(Rapport, id=rapport_id)
        if not rapport_accessible(request.user, rapport):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        is_admin = _check_role(request.user, ADMIN_RAPPORT_ROLES)
        is_generator = _check_role(request.user, GENERATION_ROLES)

        if not is_admin and not is_generator:
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        if not is_admin and rapport.statut in (Rapport.Statut.PUBLIE, Rapport.Statut.VALIDE):
            return Response({'detail': 'Rapport validé/publié non modifiable.'}, status=400)

        old_titre = rapport.titre
        changes = []

        editable = ('titre', 'commentaire', 'type', 'periode_debut', 'periode_fin')
        for f in editable:
            if f not in request.data:
                continue
            new_val = request.data[f]
            old_val = getattr(rapport, f)
            if str(old_val) != str(new_val):
                setattr(rapport, f, new_val)
                changes.append(f)

        if not changes:
            return Response(self._data(rapport))

        rapport.save(update_fields=list(changes) + ['updated_at'])

        motif = (request.data.get('motif') or '').strip()
        msg_parts = [f'Le rapport « {old_titre} » a été modifié par {request.user.get_full_name() or request.user.username}.']
        if changes:
            msg_parts.append(f'Champs modifiés : {", ".join(changes)}.')
        if motif:
            msg_parts.append(f'Motif : {motif}')
        notifier_rapport(
            rapport,
            NotificationRapport.Evenement.MODIFIE,
            request.user,
            ' '.join(msg_parts),
        )
        return Response(self._data(rapport))

    def delete(self, request, rapport_id):
        if not _check_role(request.user, ADMIN_RAPPORT_ROLES):
            return Response({'detail': 'Accès réservé aux administrateurs.'}, status=403)

        rapport = get_object_or_404(Rapport, id=rapport_id)
        titre = rapport.titre
        rid = rapport.pk
        generateur = rapport.generateur
        validateur = rapport.validateur
        statut = rapport.get_statut_display()

        motif = (request.data.get('motif') if hasattr(request, 'data') else None) or request.query_params.get('motif') or ''
        motif = str(motif).strip()
        message = (
            f'Le rapport « {titre} » (statut : {statut}) a été supprimé par '
            f'{request.user.get_full_name() or request.user.username}.'
        )
        if motif:
            message += f' Motif : {motif}'

        notifier_rapport_supprime(titre, rid, generateur, validateur, request.user, message)
        rapport.delete()
        return Response(status=204)


class RapportNotificationsView(APIView):
    """GET /api/statistiques/rapports/notifications/ — notifications de l'utilisateur connecté."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not user_has_stats_access(request.user):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        qs = NotificationRapport.objects.filter(destinataire=request.user).select_related('auteur')
        items = list(qs[:50])
        return Response({
            'notifications': [
                {
                    'id': n.id,
                    'evenement': n.evenement,
                    'rapport_id': n.rapport_id,
                    'rapport_titre': n.rapport_titre,
                    'message': n.message,
                    'auteur': n.auteur.username if n.auteur else None,
                    'lu': n.lu,
                    'created_at': n.created_at,
                }
                for n in items
            ],
            'non_lues': qs.filter(lu=False).count(),
        })

    def patch(self, request):
        """Marquer des notifications comme lues : { "ids": [1,2] } ou { "tout": true }."""
        if not user_has_stats_access(request.user):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        if request.data.get('tout'):
            NotificationRapport.objects.filter(destinataire=request.user, lu=False).update(lu=True)
        else:
            ids = request.data.get('ids') or []
            NotificationRapport.objects.filter(
                destinataire=request.user, id__in=ids,
            ).update(lu=True)
        non_lues = NotificationRapport.objects.filter(destinataire=request.user, lu=False).count()
        return Response({'non_lues': non_lues})


class RapportWorkflowView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, rapport_id):
        rapport = get_object_or_404(Rapport, id=rapport_id)
        if not rapport_accessible(request.user, rapport):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        action  = request.data.get('action')
        TRANSITIONS = {
            'soumettre': (Rapport.Statut.BROUILLON,     Rapport.Statut.EN_VALIDATION, GENERATION_ROLES),
            'valider':   (Rapport.Statut.EN_VALIDATION, Rapport.Statut.VALIDE,         VALIDATION_ROLES),
            'publier':   (Rapport.Statut.VALIDE,         Rapport.Statut.PUBLIE,         VALIDATION_ROLES),
            'rejeter':   (Rapport.Statut.EN_VALIDATION, Rapport.Statut.REJETE,         VALIDATION_ROLES),
        }
        if action not in TRANSITIONS:
            return Response({'detail': 'Action invalide.'}, status=400)
        req_statut, cible, roles = TRANSITIONS[action]
        if not _check_role(request.user, roles):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        if rapport.statut != req_statut:
            return Response({'detail': f"Statut actuel incorrect ({rapport.statut})."}, status=400)

        rapport.statut = cible
        if action == 'valider':
            rapport.validateur = request.user
            rapport.date_validation = timezone.now()
        if action == 'publier':
            rapport.date_publication = timezone.now()
        rapport.save()

        if action in ('valider', 'publier'):
            SignatureRapport.objects.create(
                rapport=rapport, signataire=request.user,
                role_signataire=getattr(request.user, 'role', ''),
                commentaire=request.data.get('commentaire', ''),
                hash_rapport=rapport.hash_donnees,
            )
        notifier_rapport_workflow(
            rapport,
            action,
            request.user,
            commentaire=request.data.get('commentaire') or request.data.get('motif') or '',
        )
        return Response({'statut': rapport.statut})


class PointJournalierView(APIView):
    """
    GET /api/statistiques/point-journalier/
      ?annee=2026&mois=4&categorie=B&formation_id=&secretariat_id=
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not user_has_stats_access(request.user):
            return Response({'detail': 'Accès non autorisé.'}, status=403)

        scope, err = _scope_from_request(request)
        if err:
            return err

        def _int(key):
            v = request.query_params.get(key)
            return int(v) if v and v.isdigit() else None

        annee = _int('annee') or date.today().year
        mois = _int('mois')
        categorie = request.query_params.get('categorie') or None
        jour = request.query_params.get('jour') or None
        detail = request.query_params.get('detail', '').lower() in ('1', 'true', 'yes')
        tous_tableaux = request.query_params.get('tous_tableaux', '').lower() in ('1', 'true', 'yes')
        kw = _scope_compute_kwargs(scope)

        fmt = (request.query_params.get('export') or request.query_params.get('file_format') or '').lower()
        if fmt in ('xlsx', 'pdf', 'docx', 'word', 'excel'):
            fmt = 'xlsx' if fmt == 'excel' else fmt
            try:
                return build_export_response(
                    fmt, annee, mois=mois, categorie=categorie, jour=jour, **kw,
                )
            except ValueError as exc:
                return Response({'detail': str(exc)}, status=400)

        if detail and jour and scope.formation_id:
            grade = request.query_params.get('grade') or None
            tb = get_tableau_detail(
                annee, scope.formation_id, categorie or '—', jour, grade=grade, **kw,
            )
            if not tb:
                return Response({'detail': 'Tableau introuvable.'}, status=404)
            return Response({'tableau': tb})

        if tous_tableaux and not detail and not jour:
            return Response(compute_point_journalier_avec_tableaux(
                annee=annee, mois=mois, categorie=categorie, **kw,
            ))

        return Response(compute_point_journalier(
            annee=annee, mois=mois, categorie=categorie, jour=jour,
            index_only=True, **kw,
        ))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def point_journalier_export(request):
    """
    GET /api/statistiques/point-journalier-export/?export=xlsx|pdf|docx
    Retourne un fichier binaire (HttpResponse).
    """
    if not user_has_stats_access(request.user):
        return Response({'detail': 'Accès non autorisé.'}, status=403)

    def _int(key):
        v = request.query_params.get(key)
        return int(v) if v and v.isdigit() else None

    fmt = (request.query_params.get('export') or request.query_params.get('file_format') or 'xlsx').lower()

    annee = _int('annee') or date.today().year
    mois = _int('mois')
    categorie = request.query_params.get('categorie') or None
    jour = request.query_params.get('jour') or None
    grade = request.query_params.get('grade') or None

    scope, err = _scope_from_request(request)
    if err:
        return err
    kw = _scope_compute_kwargs(scope)

    try:
        raw = build_export_response(
            fmt, annee, mois=mois, categorie=categorie, jour=jour, grade=grade, **kw,
        )
        from django.http import HttpResponse as DjangoHttpResponse
        out = DjangoHttpResponse(raw.content, content_type=raw['Content-Type'], status=raw.status_code)
        if raw.get('Content-Disposition'):
            out['Content-Disposition'] = raw['Content-Disposition']
        return out
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    except Exception as exc:
        return Response({'detail': f'Erreur export : {exc}'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bilans_export(request):
    """
    GET /api/statistiques/bilans-export/?export=xlsx|pdf|docx
    """
    if not user_has_stats_access(request.user):
        return Response({'detail': 'Accès non autorisé.'}, status=403)

    def _int(key):
        v = request.query_params.get(key)
        return int(v) if v and v.isdigit() else None

    fmt = (request.query_params.get('export') or request.query_params.get('file_format') or 'xlsx').lower()
    dimension = request.query_params.get('dimension') or 'module'
    annee = _int('annee') or date.today().year
    mois = _int('mois')
    module_id = _int('module_id')
    ref_module_id = _int('ref_module_id')
    categorie = request.query_params.get('categorie') or None
    periode = request.query_params.get('periode') or None
    calendrier = request.query_params.get('calendrier') or None
    justificatifs_text = request.query_params.get('justificatifs') or None

    scope, err = _scope_from_request(request, parse_module_id=True)
    if err:
        return err
    kw = _scope_compute_kwargs(scope)

    try:
        raw = build_bilans_export_response(
            fmt, dimension, annee, mois=mois, categorie=categorie,
            module_id=module_id, periode=periode, calendrier=calendrier,
            ref_module_id=ref_module_id, justificatifs_text=justificatifs_text, **kw,
        )
        from django.http import HttpResponse as DjangoHttpResponse
        out = DjangoHttpResponse(raw.content, content_type=raw['Content-Type'], status=raw.status_code)
        if raw.get('Content-Disposition'):
            out['Content-Disposition'] = raw['Content-Disposition']
        return out
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    except Exception as exc:
        return Response({'detail': f'Erreur export : {exc}'}, status=500)


def _parse_bilans_query_params(request):
    def _int(key):
        v = request.query_params.get(key)
        return int(v) if v and v.isdigit() else None

    return {
        'annee': _int('annee') or date.today().year,
        'mois': _int('mois'),
        'module_id': _int('module_id'),
        'ref_module_id': _int('ref_module_id'),
        'formation_id_qp': _int('formation_id'),
        'categorie': request.query_params.get('categorie') or None,
        'periode': request.query_params.get('periode') or None,
        'calendrier': request.query_params.get('calendrier') or None,
        'dimension': request.query_params.get('dimension') or 'formation',
        'detail': request.query_params.get('detail', '').lower() in ('1', 'true', 'yes'),
        'tous_tableaux': request.query_params.get('tous_tableaux', '').lower() in ('1', 'true', 'yes'),
        'matiere_intitule': request.query_params.get('matiere_intitule') or None,
    }


def _build_bilans_payload(request, scope, kw, params):
    """
    Calcule le payload bilans. Retourne (payload, error_response).
    error_response est un Response DRF en cas d'erreur, sinon None.
    """
    annee = params['annee']
    mois = params['mois']
    module_id = params['module_id']
    ref_module_id = params['ref_module_id']
    categorie = params['categorie']
    periode = params['periode']
    calendrier = params['calendrier']
    dimension = params['dimension']
    detail = params['detail']
    tous_tableaux = params['tous_tableaux']
    formation_id = scope.formation_id
    secretariat_id = scope.secretariat_id

    if detail and dimension == 'categorie':
        if not categorie:
            return None, Response({'detail': 'Catégorie requise.'}, status=400)
        tableau = compute_bilan_effectifs_categorie(
            categorie, formation_id=formation_id, secretariat_id=secretariat_id,
            annee=annee, mois=mois, calendrier=calendrier, periode=periode,
            module_ids=kw.get('module_ids'),
        )
        if not tableau:
            return None, Response({
                'detail': 'Aucune séance comptabilisable sur la période filtrée.',
            }, status=404)
        return {'tableau': tableau}, None

    if detail and dimension == 'matiere':
        eff_formation = formation_id or params['formation_id_qp']
        if not eff_formation:
            return None, Response({'detail': 'Formation requise pour le bilan matière.'}, status=400)
        matiere_intitule = params['matiere_intitule']
        if not ref_module_id and not matiere_intitule:
            return None, Response({'detail': 'ref_module_id ou matiere_intitule requis.'}, status=400)
        tableau = compute_bilan_effectifs_matiere(
            eff_formation,
            ref_module_id=ref_module_id,
            matiere_intitule=matiere_intitule,
            categorie=categorie,
            secretariat_id=secretariat_id,
            annee=annee, mois=mois, calendrier=calendrier, periode=periode,
            module_ids=kw.get('module_ids'),
        )
        if not tableau:
            return None, Response({
                'detail': 'Aucune séance comptabilisable sur la période filtrée.',
            }, status=404)
        return {'tableau': tableau}, None

    if detail and module_id:
        tableau = compute_bilan_effectifs_module(
            module_id, categorie=categorie, annee=annee, mois=mois,
            calendrier=calendrier, periode=periode,
        )
        if not tableau:
            return None, Response({
                'detail': 'Aucune séance comptabilisable sur la période filtrée.',
            }, status=404)
        return {'tableau': tableau}, None

    if detail and formation_id:
        tableau = compute_bilan_periode_formation(
            formation_id, annee=annee, mois=mois, calendrier=calendrier,
            periode=periode, secretariat_id=secretariat_id, categorie_filter=categorie,
            module_ids=kw.get('module_ids'),
        )
        if not tableau:
            return None, Response({'detail': 'Formation introuvable.'}, status=404)
        return {'tableau': tableau}, None

    if tous_tableaux:
        return compute_bilans_avec_tableaux(
            annee=annee, mois=mois, categorie=categorie,
            module_id=module_id, periode=periode,
            calendrier=calendrier, dimension=dimension,
            ref_module_id=ref_module_id, **kw,
        ), None

    return compute_bilans(
        annee=annee, mois=mois, categorie=categorie,
        module_id=module_id, periode=periode,
        calendrier=calendrier, dimension=dimension,
        ref_module_id=ref_module_id, **kw,
    ), None


class BilansView(APIView):
    """
    GET /api/statistiques/bilans/
      ?annee=&mois=&categorie=&module_id=&formation_id=&secretariat_id=
      &periode=QUOTIDIEN|HEBDOMADAIRE|...&calendrier=YYYY-MM-DD
      &dimension=module|matiere|categorie|formation
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not user_has_stats_access(request.user):
            return Response({'detail': 'Accès non autorisé.'}, status=403)

        params = _parse_bilans_query_params(request)

        scope, err = _scope_from_request(request, parse_module_id=True)
        if err:
            return err
        kw = _scope_compute_kwargs(scope)

        from .cache_utils import (
            get_stats_bilans_cached,
            set_stats_bilans_cached,
            stats_bilans_cache_key,
        )

        cache_key = stats_bilans_cache_key(request, scope, params)
        cached = get_stats_bilans_cached(cache_key)
        if cached is not None:
            return Response(cached)

        payload, error_response = _build_bilans_payload(request, scope, kw, params)
        if error_response is not None:
            return error_response

        set_stats_bilans_cached(cache_key, payload)
        return Response(payload)


class ObservationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, rapport_id):
        if not user_has_stats_access(request.user):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        rapport = get_object_or_404(Rapport, id=rapport_id)
        if not rapport_accessible(request.user, rapport):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        return Response(list(rapport.observations.values(
            'id','type','description','auteur__username','created_at'
        )))

    def post(self, request, rapport_id):
        if not _check_role(request.user, GENERATION_ROLES):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        rapport = get_object_or_404(Rapport, id=rapport_id)
        if not rapport_accessible(request.user, rapport):
            return Response({'detail': 'Accès non autorisé.'}, status=403)
        obs = ObservationQualitative.objects.create(
            rapport=rapport,
            type=request.data.get('type', ObservationQualitative.Type.POINT_POSITIF),
            description=request.data.get('description', ''),
            auteur=request.user,
        )
        return Response({'id': obs.id, 'type': obs.type, 'description': obs.description,
                         'created_at': obs.created_at}, status=201)


class BilanFACView(APIView):
    """
    GET /api/statistiques/bilan-fac/
      ?formation_id=<id>&annee=<yyyy>&categorie=<A|B|C|D>&secretariat_id=<id>&calendrier=<YYYY-MM-DD>
      &grades=A4,B&groupes=A4|G1,A4|G2

    Retourne le Bilan FAC complet :
      - point_global    : tableau de synthèse par grade (effectifs, VH, taux…)
      - vh_par_grade    : VH par groupe pour chaque grade
      - absents_notoires: liste nominative des auditeurs notoires
      - modules_statuts : état d'avancement des modules
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not user_has_stats_access(request.user):
            return Response({'detail': 'Accès non autorisé.'}, status=403)

        def _int(key):
            v = request.query_params.get(key)
            return int(v) if v and v.isdigit() else None

        formation_id = _int('formation_id')
        scope, err = _scope_from_request(request)
        if err:
            return err
        if not formation_id:
            formation_id = scope.formation_id

        if not formation_id:
            return Response({'detail': 'Paramètre formation_id requis.'}, status=400)

        annee = _int('annee') or date.today().year
        categorie = request.query_params.get('categorie') or None
        secretariat_id = _int('secretariat_id') or scope.secretariat_id
        calendrier = request.query_params.get('calendrier') or None

        grades_raw = (request.query_params.get('grades') or '').strip()
        grades_filter = [g.strip() for g in grades_raw.split(',') if g.strip()] or None
        groupes_raw = (request.query_params.get('groupes') or '').strip()
        groupes_filter = [g.strip() for g in groupes_raw.split(',') if g.strip()] or None

        data = compute_bilan_fac(
            formation_id=formation_id,
            annee=annee,
            categorie=categorie,
            secretariat_id=secretariat_id,
            calendrier=calendrier,
            module_ids=scope.module_ids,
            grades_filter=grades_filter,
            groupes_filter=groupes_filter,
        )
        if not data:
            return Response({'detail': 'Formation introuvable.'}, status=404)
        return Response(data)


class BilanFACPerimetreView(APIView):
    """GET /api/statistiques/bilan-fac/perimetre/ — grades et groupes cochables."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not user_has_stats_access(request.user):
            return Response({'detail': 'Accès non autorisé.'}, status=403)

        def _int(key):
            v = request.query_params.get(key)
            return int(v) if v and v.isdigit() else None

        formation_id = _int('formation_id')
        scope, err = _scope_from_request(request)
        if err:
            return err
        if not formation_id:
            formation_id = scope.formation_id
        if not formation_id:
            return Response({'detail': 'Paramètre formation_id requis.'}, status=400)

        categorie = request.query_params.get('categorie') or None
        secretariat_id = _int('secretariat_id') or scope.secretariat_id

        return Response(list_bilan_fac_perimetre(
            formation_id=formation_id,
            categorie=categorie,
            secretariat_id=secretariat_id,
            module_ids=scope.module_ids,
        ))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bilan_fac_export(request):
    """
    GET /api/statistiques/bilan-fac-export/?export=xlsx|pdf|docx
    """
    if not user_has_stats_access(request.user):
        return Response({'detail': 'Accès non autorisé.'}, status=403)

    def _int(key):
        v = request.query_params.get(key)
        return int(v) if v and v.isdigit() else None

    fmt = (request.query_params.get('export') or request.query_params.get('file_format') or 'xlsx').lower()
    formation_id = _int('formation_id')
    scope, err = _scope_from_request(request)
    if err:
        return err
    if not formation_id:
        formation_id = scope.formation_id
    if not formation_id:
        return Response({'detail': 'Paramètre formation_id requis.'}, status=400)

    annee = _int('annee') or date.today().year
    categorie = request.query_params.get('categorie') or None
    secretariat_id = _int('secretariat_id') or scope.secretariat_id
    calendrier = request.query_params.get('calendrier') or None

    grades_raw = (request.query_params.get('grades') or '').strip()
    grades_filter = [g.strip() for g in grades_raw.split(',') if g.strip()] or None
    groupes_raw = (request.query_params.get('groupes') or '').strip()
    groupes_filter = [g.strip() for g in groupes_raw.split(',') if g.strip()] or None

    meta_raw = request.query_params.get('meta') or ''
    meta = None
    if meta_raw:
        try:
            meta = json.loads(meta_raw)
        except json.JSONDecodeError:
            return Response({'detail': 'Paramètre meta invalide (JSON attendu).'}, status=400)

    try:
        raw = build_bilan_fac_export_response(
            fmt,
            formation_id=formation_id,
            annee=annee,
            categorie=categorie,
            secretariat_id=secretariat_id,
            calendrier=calendrier,
            module_ids=scope.module_ids,
            grades_filter=grades_filter,
            groupes_filter=groupes_filter,
            meta=meta,
        )
        from django.http import HttpResponse as DjangoHttpResponse
        out = DjangoHttpResponse(raw.content, content_type=raw['Content-Type'], status=raw.status_code)
        if raw.get('Content-Disposition'):
            out['Content-Disposition'] = raw['Content-Disposition']
        return out
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    except Exception as exc:
        return Response({'detail': f'Erreur export : {exc}'}, status=500)
