"""
Bilans & Rapports — index par Module, Catégorie ou Formation.

Structure préparée pour accueillir les tableaux CPFAE fournis progressivement.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.db.models import Q

from formations.categorie_referentiel import (
    libelles_ref_actifs,
    q_module_participant_categorie_ref,
    q_participant_categorie_ref,
)
from formations.models import Formation, Module, Participant, ModuleParticipant, SessionModule
from presences.models import Pointage

from .effectifs import (
    categories_for_scope,
    aggregation_seances_modules,
    count_auditeurs_notoires,
    effectifs_tableau_agrege,
    participant_ids_notoires,
    q_pointage_present,
    session_ids_for_scope,
)

User = get_user_model()

PERIODES_BILAN = [
    ('QUOTIDIEN', 'Quotidien'),
    ('HEBDOMADAIRE', 'Hebdomadaire'),
    ('MENSUEL', 'Mensuel'),
    ('TRIMESTRIEL', 'Trimestriel'),
    ('SEMESTRIEL', 'Semestriel'),
    ('ANNUEL', 'Annuel'),
    ('MI_PARCOURS', 'À mi-parcours'),
]


def _liste_categories(formation_id=None, secretariat_id=None, module_ids=None):
    return categories_for_scope(
        formation_id=formation_id,
        secretariat_id=secretariat_id,
        module_ids=module_ids,
    )


def _modules_queryset(
    formation_id=None,
    secretariat_id=None,
    categorie=None,
    module_id=None,
    module_ids=None,
    ref_module_id=None,
):
    mq = Q()
    if formation_id:
        mq &= Q(formation_id=formation_id)
    if secretariat_id:
        mq &= Q(secretariat_id=secretariat_id)
    if module_id:
        mq &= Q(id=module_id)
    elif module_ids is not None:
        mq &= Q(id__in=module_ids)
    if ref_module_id:
        mq &= Q(ref_module_id=ref_module_id)
    qs = Module.objects.filter(mq).select_related('formation', 'ref_module').order_by(
        'formation__formation', 'grade', 'groupe', 'ordre', 'intitule',
    )
    if categorie:
        qs = qs.filter(q_module_participant_categorie_ref(categorie)).distinct()
    return qs


def _formations_queryset(formation_id=None, secretariat_id=None, module_ids=None):
    fq = Formation.objects.all()
    if formation_id:
        fq = fq.filter(id=formation_id)
    if secretariat_id:
        fq = fq.filter(modules__secretariat_id=secretariat_id).distinct()
    if module_ids is not None:
        fq = fq.filter(modules__id__in=module_ids).distinct()
    return fq.order_by('formation')


def _pct(num, den, decimals=2):
    return round(num / den * 100, decimals) if den else 0.0


def _session_ids_module(module_id, annee=None, mois=None, calendrier=None):
    return session_ids_for_scope([module_id], annee, mois, calendrier)


def _session_ids_modules(module_ids, annee=None, mois=None, calendrier=None):
    return session_ids_for_scope(module_ids, annee, mois, calendrier)


def _effectifs_tableau(participants, session_ids, module_ids):
    """Calcule auditeurs inscrits, présents/absents et H/F (inscrits + présents) sur séances terminées."""
    if not session_ids:
        return None
    return effectifs_tableau_agrege(participants, session_ids, module_ids)


def _has_seances_comptabilisables(module_ids, annee=None, mois=None, calendrier=None):
    """Au moins une séance comptabilisable sur le périmètre et la période filtrée."""
    if not module_ids:
        return False
    return bool(_session_ids_modules(module_ids, annee, mois, calendrier))


def _module_ids_categorie(
    categorie,
    formation_id=None,
    secretariat_id=None,
    module_ids=None,
):
    mq = Module.objects.all()
    if formation_id:
        mq = mq.filter(formation_id=formation_id)
    if secretariat_id:
        mq = mq.filter(secretariat_id=secretariat_id)
    if module_ids is not None:
        mq = mq.filter(id__in=module_ids)
    return list(
        mq.filter(q_module_participant_categorie_ref(categorie))
        .distinct().values_list('id', flat=True)
    )


def compute_bilan_effectifs_module(
    module_id,
    categorie=None,
    annee=None,
    mois=None,
    calendrier=None,
    periode=None,
):
    """
    Tableau CPFAE « Bilan des effectifs module » :
    auditeurs, présents, répartition H/F, absents + pourcentages.
    """
    try:
        module = Module.objects.select_related('formation').get(pk=module_id)
    except Module.DoesNotExist:
        return None

    mp_qs = ModuleParticipant.objects.filter(module=module).select_related('participant')
    if categorie and categorie != '—':
        mp_qs = mp_qs.filter(q_participant_categorie_ref(categorie))

    participants = {mp.participant_id: mp.participant for mp in mp_qs}
    session_ids = _session_ids_module(module_id, annee, mois, calendrier)
    stats = _effectifs_tableau(participants, session_ids, [module_id])
    if stats is None:
        return None

    module_nom = (module.intitule or f'Module {module.id}').strip().upper()

    return {
        'type': 'effectifs_module',
        'titre': f'BILAN DES EFFECTIFS MODULE {module_nom}',
        'module_id': module.id,
        'module': module.intitule,
        'formation': str(module.formation),
        **stats,
        'periode_label': dict(PERIODES_BILAN).get(periode, '') if periode else '',
    }


def compute_bilan_effectifs_categorie(
    categorie,
    formation_id=None,
    secretariat_id=None,
    annee=None,
    mois=None,
    calendrier=None,
    periode=None,
    module_ids=None,
):
    """
    Tableau CPFAE « Bilan des effectifs catégorie » :
    auditeurs, présents, répartition H/F, absents + pourcentages.
    """
    if not categorie or categorie == '—':
        return None

    cat_label = categorie.strip().upper()
    mq = Module.objects.all()
    if formation_id:
        mq = mq.filter(formation_id=formation_id)
    if secretariat_id:
        mq = mq.filter(secretariat_id=secretariat_id)
    if module_ids is not None:
        mq = mq.filter(id__in=module_ids)
    module_ids = list(
        mq.filter(q_module_participant_categorie_ref(categorie))
        .distinct().values_list('id', flat=True)
    )

    mp_qs = ModuleParticipant.objects.filter(
        module_id__in=module_ids,
    ).filter(q_participant_categorie_ref(categorie)).select_related('participant')
    participants = {mp.participant_id: mp.participant for mp in mp_qs}

    session_ids = _session_ids_modules(module_ids, annee, mois, calendrier)
    stats = _effectifs_tableau(participants, session_ids, module_ids)
    if stats is None:
        return None

    return {
        'type': 'effectifs_categorie',
        'titre': f'BILAN DES EFFECTIFS CATEGORIE ({cat_label})',
        'categorie': categorie,
        **stats,
        'periode_label': dict(PERIODES_BILAN).get(periode, '') if periode else '',
    }


def _date_inscrits_label(calendrier=None):
    if calendrier:
        try:
            return date.fromisoformat(str(calendrier)).strftime('%d/%m/%Y')
        except ValueError:
            pass
    return date.today().strftime('%d/%m/%Y')


def _modules_formation_categorie(
    formation_id, categorie, grade=None, secretariat_id=None, module_ids=None,
):
    mq = Module.objects.filter(formation_id=formation_id)
    if secretariat_id:
        mq = mq.filter(secretariat_id=secretariat_id)
    if module_ids is not None:
        mq = mq.filter(id__in=module_ids)
    if grade:
        mq = mq.filter(grade=grade)
    if categorie:
        mq = mq.filter(q_module_participant_categorie_ref(categorie)).distinct()
    return mq


def _stats_ligne_formation(
    formation_id, categorie, grade, secretariat_id, annee, mois, calendrier, scope_module_ids=None,
):
    mq = _modules_formation_categorie(
        formation_id, categorie, grade, secretariat_id, scope_module_ids,
    )
    module_ids = list(mq.values_list('id', flat=True))

    nb_groupes = mq.exclude(groupe='').values('groupe').distinct().count()
    if not nb_groupes and module_ids:
        nb_groupes = len(module_ids)

    nb_encadrants = mq.exclude(superviseur=None).values('superviseur').distinct().count()

    sec_ids = mq.exclude(secretariat=None).values_list('secretariat_id', flat=True).distinct()
    effectif_secretariat = User.objects.filter(
        role__in=[User.Role.SECRETARIAT, User.Role.CHEF_SECRETARIAT],
        secretariat_id__in=sec_ids,
    ).distinct().count()

    mp_q = ModuleParticipant.objects.filter(module_id__in=module_ids)
    auditeurs_listes = mp_q.values('participant_id').distinct().count()

    ref_q = Participant.objects.filter(
        modules_inscrits__module__formation_id=formation_id,
    ).distinct()
    if categorie:
        ref_q = ref_q.filter(categorie__iexact=categorie)
    if secretariat_id:
        ref_q = ref_q.filter(secretariat_id=secretariat_id)
    if module_ids is not None:
        ref_q = ref_q.filter(modules_inscrits__module_id__in=module_ids).distinct()
    if grade:
        ref_q = ref_q.filter(modules_inscrits__module__grade=grade).distinct()
    inscrits_reference = ref_q.count()

    inscrits_actifs = auditeurs_listes
    inscrits_reference = max(inscrits_reference, inscrits_actifs)

    absents_notoires = count_auditeurs_notoires(
        module_ids=module_ids,
        formation_id=formation_id,
        secretariat_id=secretariat_id,
        grade=grade,
        categorie=categorie,
    )

    return {
        'grade': grade or '',
        'nb_groupes': nb_groupes,
        'nb_encadrants': nb_encadrants,
        'effectif_secretariat': effectif_secretariat,
        'inscrits_actifs': inscrits_actifs,
        'inscrits_reference': inscrits_reference,
        'pct_inscrits': _pct(inscrits_actifs, inscrits_reference),
        'auditeurs_listes': auditeurs_listes,
        'absents_notoires': absents_notoires,
        'pct_absents': _pct(absents_notoires, inscrits_reference),
    }


def _somme_lignes(lignes, keys):
    out = {}
    for k in keys:
        out[k] = sum(l.get(k, 0) or 0 for l in lignes)
    if out.get('inscrits_reference'):
        out['pct_inscrits'] = _pct(out.get('inscrits_actifs', 0), out['inscrits_reference'])
        out['pct_absents'] = _pct(out.get('absents_notoires', 0), out['inscrits_reference'])
    return out


def _ligne_categorie_formation(
    formation_id, categorie, secretariat_id, annee, mois, calendrier, module_ids=None,
):
    mq = Module.objects.filter(
        formation_id=formation_id,
    ).filter(q_module_participant_categorie_ref(categorie))
    if secretariat_id:
        mq = mq.filter(secretariat_id=secretariat_id)
    if module_ids is not None:
        mq = mq.filter(id__in=module_ids)
    grades = sorted({
        g for g in mq.exclude(grade='').values_list('grade', flat=True)
    })

    keys_sum = [
        'nb_groupes', 'nb_encadrants', 'effectif_secretariat',
        'inscrits_actifs', 'inscrits_reference', 'auditeurs_listes', 'absents_notoires',
    ]

    if len(grades) > 1:
        sous_lignes = [
            _stats_ligne_formation(
                formation_id, categorie, g, secretariat_id, annee, mois, calendrier, module_ids,
            )
            for g in grades
        ]
        totaux = _somme_lignes(sous_lignes, keys_sum)
        nb_enc = _stats_ligne_formation(
            formation_id, categorie, None, secretariat_id, annee, mois, calendrier, module_ids,
        )
        totaux['nb_encadrants'] = nb_enc['nb_encadrants']
        totaux['effectif_secretariat'] = nb_enc['effectif_secretariat']
        return {
            'categorie': categorie,
            'multi_grade': True,
            'sous_lignes': sous_lignes,
            'totaux': totaux,
        }

    grade = grades[0] if grades else None
    stats = _stats_ligne_formation(
        formation_id, categorie, grade, secretariat_id, annee, mois, calendrier, module_ids,
    )
    return {
        'categorie': categorie,
        'multi_grade': False,
        'sous_lignes': [],
        'totaux': stats,
    }


def compute_bilan_periode_formation(
    formation_id,
    annee=None,
    mois=None,
    calendrier=None,
    periode=None,
    secretariat_id=None,
    categorie_filter=None,
    module_ids=None,
):
    """Tableau CPFAE « Bilan période » par formation (catégories A–D)."""
    try:
        formation = Formation.objects.get(pk=formation_id)
    except Formation.DoesNotExist:
        return None

    annee = annee or date.today().year
    formation_nom = (formation.formation or f'Formation {formation.id}').strip().upper()
    titre = f'BILAN PERIODE {formation_nom} {annee}'

    categories_ref = libelles_ref_actifs()
    cats_data = _liste_categories(formation_id, secretariat_id, module_ids)
    categories = [c for c in categories_ref if c in cats_data] or sorted(cats_data)
    if categorie_filter:
        categories = [c for c in categories if c.upper() == categorie_filter.upper()]

    lignes = [
        _ligne_categorie_formation(
            formation_id, cat, secretariat_id, annee, mois, calendrier, module_ids,
        )
        for cat in categories
    ]

    keys_sum = [
        'nb_groupes', 'nb_encadrants', 'effectif_secretariat',
        'inscrits_actifs', 'inscrits_reference', 'auditeurs_listes', 'absents_notoires',
    ]
    total = _somme_lignes([l['totaux'] for l in lignes], keys_sum)

    return {
        'type': 'bilan_periode_formation',
        'titre': titre,
        'formation_id': formation.id,
        'formation': formation.formation,
        'annee': annee,
        'date_inscrits': _date_inscrits_label(calendrier),
        'periode_label': dict(PERIODES_BILAN).get(periode, '') if periode else '',
        'justificatifs': '',
        'lignes': lignes,
        'total': total,
    }


def _resume_module(module, categorie=None, annee=None, mois=None, calendrier=None):
    mq = ModuleParticipant.objects.filter(module=module)
    if categorie:
        mq = mq.filter(q_participant_categorie_ref(categorie))
    inscrits = mq.values('participant').distinct().count()
    sess_ids = session_ids_for_scope([module.id], annee, mois, calendrier)
    return {
        'inscrits': inscrits,
        'nb_seances_terminees': len(sess_ids),
        'nb_pointages': (
            Pointage.objects.filter(session_id__in=sess_ids).filter(q_pointage_present()).count()
            if sess_ids else 0
        ),
    }


def _matiere_bucket(module):
    """Clé d'agrégation matière : ref_module prioritaire, sinon intitulé normalisé."""
    if module.ref_module_id:
        label = (module.ref_module.intitule if module.ref_module else module.intitule or '').strip()
        return ('ref', module.ref_module_id, label)
    label = (module.intitule or f'Module {module.id}').strip()
    return ('intitule', label.upper(), label)


def _group_modules_by_matiere(modules):
    """Regroupe les modules d'une formation par matière (tous groupes)."""
    groups = {}
    for mod in modules:
        kind, key, label = _matiere_bucket(mod)
        bucket = (mod.formation_id, kind, key)
        if bucket not in groups:
            groups[bucket] = {'label': label, 'modules': [], 'ref_module_id': key if kind == 'ref' else None}
        groups[bucket]['modules'].append(mod)
    return groups


def _resume_matiere(module_ids, categorie=None, annee=None, mois=None, calendrier=None):
    """Inscrits uniques et présences valides sur tous les modules d'une matière."""
    mq = Q(module_id__in=module_ids)
    if categorie:
        mq &= q_participant_categorie_ref(categorie)
    inscrits = ModuleParticipant.objects.filter(mq).values('participant').distinct().count()
    sess_ids = session_ids_for_scope(module_ids, annee, mois, calendrier)
    return {
        'inscrits': inscrits,
        'nb_seances_terminees': len(sess_ids),
        'nb_pointages': (
            Pointage.objects.filter(session_id__in=sess_ids).filter(q_pointage_present()).count()
            if sess_ids else 0
        ),
    }


def compute_bilan_effectifs_matiere(
    formation_id,
    ref_module_id=None,
    matiere_intitule=None,
    categorie=None,
    secretariat_id=None,
    annee=None,
    mois=None,
    calendrier=None,
    periode=None,
    module_ids=None,
):
    """
    Tableau CPFAE « Bilan des effectifs matière » :
    agrégation tous groupes pour une même matière (ref_module ou intitulé).
    """
    if not formation_id:
        return None

    mq = Q(formation_id=formation_id)
    if secretariat_id:
        mq &= Q(secretariat_id=secretariat_id)
    if module_ids is not None:
        mq &= Q(id__in=module_ids)
    if ref_module_id:
        mq &= Q(ref_module_id=ref_module_id)
    elif matiere_intitule:
        mq &= Q(intitule__iexact=matiere_intitule.strip())
    else:
        return None

    modules = list(Module.objects.filter(mq).select_related('formation', 'ref_module'))
    if not modules:
        return None

    mod_ids = [m.id for m in modules]
    mp_qs = ModuleParticipant.objects.filter(module_id__in=mod_ids).select_related('participant')
    if categorie and categorie != '—':
        mp_qs = mp_qs.filter(q_participant_categorie_ref(categorie))

    participants = {}
    for mp in mp_qs:
        participants[mp.participant_id] = mp.participant

    session_ids = _session_ids_modules(mod_ids, annee, mois, calendrier)
    stats = _effectifs_tableau(participants, session_ids, mod_ids)
    if stats is None:
        return None

    formation = modules[0].formation
    matiere_nom = (
        (modules[0].ref_module.intitule if modules[0].ref_module else None)
        or modules[0].intitule
        or f'Matière {ref_module_id or matiere_intitule}'
    ).strip().upper()

    return {
        'type': 'effectifs_matiere',
        'titre': f'BILAN DES EFFECTIFS MATIÈRE {matiere_nom}',
        'matiere': matiere_nom,
        'ref_module_id': ref_module_id or modules[0].ref_module_id,
        'nb_groupes': len(modules),
        'module_ids': mod_ids,
        'formation_id': formation.id,
        'formation': str(formation),
        **stats,
        'periode_label': dict(PERIODES_BILAN).get(periode, '') if periode else '',
    }


def compute_bilans(
    annee=None,
    mois=None,
    categorie=None,
    module_id=None,
    module_ids=None,
    formation_id=None,
    secretariat_id=None,
    periode=None,
    calendrier=None,
    dimension='formation',
    ref_module_id=None,
):
    """
    dimension : 'module' | 'matiere' | 'categorie' | 'formation'
    Retourne la liste des bilans disponibles + métadonnées filtres.
    """
    annee = annee or date.today().year
    dimension = (dimension or 'formation').lower()
    if dimension not in ('module', 'matiere', 'categorie', 'formation'):
        dimension = 'formation'

    if dimension == 'matiere' and module_id and not ref_module_id:
        try:
            mod_filter = Module.objects.only('ref_module_id').get(pk=module_id)
            if mod_filter.ref_module_id:
                ref_module_id = mod_filter.ref_module_id
                module_id = None
        except Module.DoesNotExist:
            pass

    categories = _liste_categories(formation_id, secretariat_id, module_ids)
    modules_qs = _modules_queryset(
        formation_id, secretariat_id, categorie, module_id, module_ids, ref_module_id,
    )
    modules_liste = [
        {'id': m.id, 'intitule': m.intitule, 'formation_id': m.formation_id, 'formation': str(m.formation)}
        for m in modules_qs[:500]
    ]

    matieres_liste = []
    seen_matiere = set()
    for m in modules_qs[:2000]:
        kind, key, label = _matiere_bucket(m)
        mat_key = (m.formation_id, kind, key)
        if mat_key in seen_matiere:
            continue
        seen_matiere.add(mat_key)
        matieres_liste.append({
            'ref_module_id': key if kind == 'ref' else None,
            'intitule': label,
            'formation_id': m.formation_id,
            'formation': str(m.formation),
        })
    matieres_liste.sort(key=lambda x: (x['formation'], x['intitule']))

    formations_qs = _formations_queryset(formation_id, secretariat_id, module_ids)
    formations_liste = [{'id': f.id, 'formation': f.formation} for f in formations_qs[:200]]

    periode_label = dict(PERIODES_BILAN).get(periode, 'Toutes périodes') if periode else 'Toutes périodes'
    filtres_actifs = {
        'annee': annee,
        'mois': mois,
        'categorie': categorie or '',
        'module_id': module_id,
        'module_ids': module_ids,
        'formation_id': formation_id,
        'secretariat_id': secretariat_id,
        'periode': periode or '',
        'periode_label': periode_label,
        'calendrier': calendrier or '',
        'dimension': dimension,
        'ref_module_id': ref_module_id,
    }

    bilans = []

    if dimension == 'formation':
        for f in formations_qs:
            bilans.append({
                'id': f'formation-{f.id}-{annee}-{periode or "all"}',
                'dimension': 'formation',
                'formation_id': f.id,
                'formation': f.formation,
                'module_id': None,
                'module': None,
                'categorie': categorie or '—',
                'libelle': f.formation,
                'sous_titre': f'Bilan formation · {periode_label} · {annee}',
                'annee': annee,
                'mois': mois,
                'periode': periode or '',
                'periode_label': periode_label,
                'calendrier': calendrier or '',
                'tableau_pret': True,
            })

    elif dimension == 'categorie':
        cats = [categorie] if categorie else categories
        if not cats:
            cats = ['—']
        for cat in cats:
            if not _has_seances_comptabilisables(
                _module_ids_categorie(cat, formation_id, secretariat_id, module_ids),
                annee, mois, calendrier,
            ):
                continue
            bilans.append({
                'id': f'categorie-{cat}-{annee}-{periode or "all"}',
                'dimension': 'categorie',
                'formation_id': formation_id,
                'formation': None,
                'module_id': None,
                'module': None,
                'categorie': cat,
                'libelle': f'Catégorie {cat}',
                'sous_titre': f'Bilan catégorie · {periode_label} · {annee}',
                'annee': annee,
                'mois': mois,
                'periode': periode or '',
                'periode_label': periode_label,
                'calendrier': calendrier or '',
                'tableau_pret': True,
            })

    elif dimension == 'module':
        for m in modules_qs:
            if not _has_seances_comptabilisables([m.id], annee, mois, calendrier):
                continue
            resume = _resume_module(m, categorie, annee, mois, calendrier)
            bilans.append({
                'id': f'module-{m.id}-{annee}-{periode or "all"}',
                'dimension': 'module',
                'formation_id': m.formation_id,
                'formation': str(m.formation),
                'module_id': m.id,
                'module': m.intitule,
                'categorie': categorie or '—',
                'libelle': m.intitule,
                'sous_titre': f'{m.formation} · {periode_label} · {annee}',
                'annee': annee,
                'mois': mois,
                'periode': periode or '',
                'periode_label': periode_label,
                'calendrier': calendrier or '',
                'grade': (m.grade or '').strip() or None,
                'groupe': (m.groupe or '').strip() or None,
                'inscrits': resume['inscrits'],
                'nb_pointages': resume['nb_pointages'],
                'tableau_pret': True,
            })

    elif dimension == 'matiere':
        modules_all = list(modules_qs)
        groups = _group_modules_by_matiere(modules_all)
        for bucket, info in sorted(
            groups.items(),
            key=lambda x: (x[0][0], x[1]['label']),
        ):
            fid, kind, key = bucket
            mods = info['modules']
            mod_ids = [m.id for m in mods]
            if not _has_seances_comptabilisables(mod_ids, annee, mois, calendrier):
                continue
            ref_id = info['ref_module_id']
            label = info['label']
            formation_nom = str(mods[0].formation)
            resume = _resume_matiere(mod_ids, categorie, annee, mois, calendrier)
            nb_groupes = len(mods)
            bilans.append({
                'id': f'matiere-{ref_id or label}-{fid}-{annee}-{periode or "all"}',
                'dimension': 'matiere',
                'formation_id': fid,
                'formation': formation_nom,
                'ref_module_id': ref_id,
                'matiere_intitule': label if not ref_id else None,
                'module_id': None,
                'module': label,
                'categorie': categorie or '—',
                'libelle': label,
                'sous_titre': (
                    f'{nb_groupes} groupe{"s" if nb_groupes > 1 else ""} · '
                    f'{formation_nom} · {periode_label} · {annee}'
                ),
                'annee': annee,
                'mois': mois,
                'periode': periode or '',
                'periode_label': periode_label,
                'calendrier': calendrier or '',
                'nb_groupes': nb_groupes,
                'inscrits': resume['inscrits'],
                'nb_pointages': resume['nb_pointages'],
                'tableau_pret': True,
            })

    return {
        'annee': annee,
        'mois': mois,
        'bilans': bilans,
        'total_bilans': len(bilans),
        'categories': categories,
        'modules': modules_liste,
        'matieres': matieres_liste,
        'formations': formations_liste,
        'periodes': [{'value': v, 'label': l} for v, l in PERIODES_BILAN],
        'filtres_actifs': filtres_actifs,
    }


def _tableau_pour_bilan(bilan, categorie=None, annee=None, mois=None, calendrier=None,
                        periode=None, formation_id=None, secretariat_id=None, module_ids=None):
    """Construit le tableau CPFAE détaillé pour une entrée de la liste bilans."""
    dim = bilan.get('dimension')
    cat = bilan.get('categorie')
    if cat in (None, '', '—'):
        cat = categorie

    if dim == 'module' and bilan.get('module_id'):
        return compute_bilan_effectifs_module(
            bilan['module_id'],
            categorie=cat,
            annee=annee,
            mois=mois,
            calendrier=calendrier,
            periode=periode,
        )
    if dim == 'matiere' and bilan.get('formation_id'):
        return compute_bilan_effectifs_matiere(
            bilan['formation_id'],
            ref_module_id=bilan.get('ref_module_id'),
            matiere_intitule=bilan.get('matiere_intitule'),
            categorie=cat,
            secretariat_id=secretariat_id,
            annee=annee,
            mois=mois,
            calendrier=calendrier,
            periode=periode,
            module_ids=module_ids,
        )
    if dim == 'formation' and bilan.get('formation_id'):
        return compute_bilan_periode_formation(
            bilan['formation_id'],
            annee=annee,
            mois=mois,
            calendrier=calendrier,
            periode=periode,
            secretariat_id=secretariat_id,
            categorie_filter=cat if cat and cat != '—' else None,
            module_ids=module_ids,
        )
    if dim == 'categorie' and cat and cat != '—':
        return compute_bilan_effectifs_categorie(
            cat,
            formation_id=formation_id or bilan.get('formation_id'),
            secretariat_id=secretariat_id,
            annee=annee,
            mois=mois,
            calendrier=calendrier,
            periode=periode,
            module_ids=module_ids,
        )
    return None


def compute_bilans_avec_tableaux(
    annee=None,
    mois=None,
    categorie=None,
    module_id=None,
    module_ids=None,
    formation_id=None,
    secretariat_id=None,
    periode=None,
    calendrier=None,
    dimension='formation',
    ref_module_id=None,
):
    """Index bilans + tous les tableaux CPFAE correspondants (vue d'ensemble)."""
    data = compute_bilans(
        annee=annee,
        mois=mois,
        categorie=categorie,
        module_id=module_id,
        module_ids=module_ids,
        formation_id=formation_id,
        secretariat_id=secretariat_id,
        periode=periode,
        calendrier=calendrier,
        dimension=dimension,
        ref_module_id=ref_module_id,
    )
    tableaux_complets = []
    for b in data['bilans']:
        tableau = _tableau_pour_bilan(
            b,
            categorie=categorie,
            annee=annee,
            mois=mois,
            calendrier=calendrier,
            periode=periode,
            formation_id=formation_id,
            secretariat_id=secretariat_id,
            module_ids=module_ids,
        )
        if tableau:
            tableaux_complets.append({
                'bilan_id': b['id'],
                'bilan': b,
                'tableau': tableau,
            })
    data['tableaux_complets'] = tableaux_complets
    data['total_tableaux'] = len(tableaux_complets)
    return data


# ── Bilan FAC ─────────────────────────────────────────────────────────────────

def _mq_bilan_fac_base(formation_id, categorie=None, secretariat_id=None, module_ids=None):
    mq = Module.objects.filter(formation_id=formation_id)
    if secretariat_id:
        mq = mq.filter(secretariat_id=secretariat_id)
    if module_ids is not None:
        mq = mq.filter(id__in=module_ids)
    if categorie:
        mq = mq.filter(q_module_participant_categorie_ref(categorie)).distinct()
    return mq


def _parse_groupes_filter(groupes_filter):
    """['A4|G1', 'A4:G2'] → {(grade, groupe), …}"""
    pairs = set()
    for raw in groupes_filter or []:
        if not raw:
            continue
        sep = '|' if '|' in raw else (':' if ':' in raw else None)
        if not sep:
            continue
        gr, grp = raw.split(sep, 1)
        gr_s, grp_s = gr.strip(), grp.strip()
        if gr_s and grp_s:
            pairs.add((gr_s, grp_s))
    return pairs


def _apply_bilan_fac_perimetre_filters(mq_base, grades_filter=None, groupes_filter=None):
    """Restreint le queryset aux grades / groupes cochés."""
    if grades_filter:
        grades_norm = {g.strip() for g in grades_filter if g and str(g).strip()}
        if grades_norm:
            rows = list(mq_base.values_list('id', 'grade'))
            ids = [mid for mid, gr in rows if gr and gr.strip() in grades_norm]
            mq_base = mq_base.filter(id__in=ids) if ids else mq_base.none()

    pairs = _parse_groupes_filter(groupes_filter)
    if pairs:
        rows = list(mq_base.values_list('id', 'grade', 'groupe'))
        ids = [
            mid for mid, gr, grp in rows
            if gr and grp and (gr.strip(), grp.strip()) in pairs
        ]
        mq_base = mq_base.filter(id__in=ids) if ids else mq_base.none()

    return mq_base


def list_bilan_fac_perimetre(
    formation_id,
    categorie=None,
    secretariat_id=None,
    module_ids=None,
):
    """Grades et groupes disponibles pour le Bilan FAC (cases à cocher)."""
    mq = _mq_bilan_fac_base(
        formation_id, categorie=categorie, secretariat_id=secretariat_id, module_ids=module_ids,
    )
    grades_set = set()
    groupes = []
    seen = set()
    for gr, grp in mq.exclude(grade='').values_list('grade', 'groupe').distinct():
        gr_s = (gr or '').strip()
        grp_s = (grp or '').strip()
        if not gr_s:
            continue
        grades_set.add(gr_s)
        if grp_s:
            key = (gr_s, grp_s)
            if key not in seen:
                seen.add(key)
                groupes.append({
                    'grade': gr_s,
                    'groupe': grp_s,
                    'id': f'{gr_s}|{grp_s}',
                })
    groupes.sort(key=lambda x: (x['grade'], x['groupe']))
    return {
        'grades': sorted(grades_set),
        'groupes': groupes,
    }


def _vh_grade_groupe(formation_id, grade, groupe=None, secretariat_id=None, module_ids=None):
    """VH prévu et réalisé (aligné dashboard via volume_horaire)."""
    from formations.volume_horaire import compute_volume_horaire_from_module_ids

    mq = Module.objects.filter(formation_id=formation_id, grade=grade)
    if secretariat_id:
        mq = mq.filter(secretariat_id=secretariat_id)
    if module_ids is not None:
        mq = mq.filter(id__in=module_ids)

    # Filtrage côté Python pour tolérer les espaces dans la base
    mod_ids_all = list(mq.values_list('id', 'groupe'))
    if groupe:
        mod_ids = [mid for mid, grp in mod_ids_all if grp and grp.strip() == groupe]
    else:
        mod_ids = [mid for mid, grp in mod_ids_all]
    vh = compute_volume_horaire_from_module_ids(mod_ids, integer_hours=True)
    vh_prevu = float(vh['prevu_heures'])
    vh_epuise = float(vh['realise_heures'])
    vh_restant = max(0.0, vh_prevu - vh_epuise)
    taux_execution = float(vh['taux_pct']) if vh_prevu else 100.0
    taux_restant = _pct(vh_restant, vh_prevu, decimals=4) if vh_prevu else 0.0
    return {
        'vh_prevu': vh_prevu,
        'vh_epuise': vh_epuise,
        'vh_restant': vh_restant,
        'taux_execution': round(taux_execution, 2),
        'taux_restant': round(taux_restant, 2),
    }


def _taux_presence_formation(formation_id, grade=None, secretariat_id=None, annee=None, mois=None, calendrier=None, module_ids=None):
    """Taux de présence aux cours (places présentes / places attendues)."""
    mq = Module.objects.filter(formation_id=formation_id)
    if grade:
        mq = mq.filter(grade=grade)
    if secretariat_id:
        mq = mq.filter(secretariat_id=secretariat_id)
    if module_ids is not None:
        mq = mq.filter(id__in=module_ids)
    mod_ids = list(mq.values_list('id', flat=True))

    session_ids = _session_ids_modules(mod_ids, annee, mois, calendrier)
    agg = aggregation_seances_modules(mod_ids, session_ids=session_ids or None)
    places_attendues = agg['places_attendues']
    places_presentes = agg['places_presentes']
    places_absentes = agg['places_absentes']
    if not places_attendues:
        return {'taux_presence': 0.0, 'taux_absence': 0.0, 'nb_presents': 0, 'nb_absents': 0}

    taux_presence = places_presentes / places_attendues
    taux_absence = places_absentes / places_attendues
    return {
        'taux_presence': round(taux_presence, 4),
        'taux_absence': round(taux_absence, 4),
        'nb_presents': places_presentes,
        'nb_absents': places_absentes,
    }


def _groupes_termines_count(formation_id, grade, secretariat_id=None, module_ids=None):
    """Nombre de groupes pour lesquels tous les modules sont TERMINEE."""
    mq = Module.objects.filter(formation_id=formation_id, grade=grade)
    if secretariat_id:
        mq = mq.filter(secretariat_id=secretariat_id)
    if module_ids is not None:
        mq = mq.filter(id__in=module_ids)
    groupes = mq.exclude(groupe='').values_list('groupe', flat=True).distinct()
    termines = 0
    for grp in groupes:
        total = mq.filter(groupe=grp).count()
        done = mq.filter(groupe=grp, statut=Module.Statut.TERMINEE).count()
        if total > 0 and done == total:
            termines += 1
    return termines


def compute_bilan_fac(
    formation_id,
    annee=None,
    categorie=None,
    secretariat_id=None,
    calendrier=None,
    module_ids=None,
    grades_filter=None,
    groupes_filter=None,
):
    """
    Bilan FAC complet reprenant le format du fichier Excel BILAN FAC :

    - Point global (par catégorie/grade) : effectifs, VH, taux présence/absence, difficultés
    - Bilan Volume Horaire par groupe (par grade)
    - Absents notoires (liste nominative)

    Paramètres :
        formation_id    : ID Formation ciblée (obligatoire)
        annee           : Année de référence (défaut : année courante)
        categorie       : Filtre catégorie (ex. 'A', 'B' …) ; None = toutes
        secretariat_id  : Filtre secrétariat
        calendrier      : Date pivot YYYY-MM-DD (calendrier prévisionnel)
    """
    try:
        formation = Formation.objects.get(pk=formation_id)
    except Formation.DoesNotExist:
        return None

    annee = annee or date.today().year
    formation_nom = (formation.formation or f'Formation {formation.id}').strip().upper()

    # Modules de base
    mq_base = _mq_bilan_fac_base(
        formation_id, categorie=categorie, secretariat_id=secretariat_id, module_ids=module_ids,
    )
    mq_base = _apply_bilan_fac_perimetre_filters(
        mq_base, grades_filter=grades_filter, groupes_filter=groupes_filter,
    )
    scope_module_ids = list(mq_base.values_list('id', flat=True))

    # Grades disponibles (ex. A4, A3) — nettoyage et déduplication stricte
    grades_raw = mq_base.exclude(grade='').values_list('grade', flat=True).distinct()
    grades = sorted({g.strip() for g in grades_raw if g and g.strip()})
    cat_for_stats = categorie

    # ── Point global ──────────────────────────────────────────────────────────
    lignes_global = []
    for grade in grades:
        try:
            stats = _stats_ligne_formation(
                formation_id, cat_for_stats, grade, secretariat_id, annee, None, calendrier, scope_module_ids,
            )
        except Exception:
            stats = {
                'grade': grade, 'nb_groupes': 0, 'nb_encadrants': 0, 'effectif_secretariat': 0,
                'inscrits_actifs': 0, 'inscrits_reference': 0, 'pct_inscrits': 0,
                'auditeurs_listes': 0, 'absents_notoires': 0, 'pct_absents': 0,
            }

        vh_data = _vh_grade_groupe(
            formation_id, grade, secretariat_id=secretariat_id, module_ids=scope_module_ids,
        )
        pres = _taux_presence_formation(
            formation_id, grade, secretariat_id, annee, None, calendrier, scope_module_ids,
        )
        nb_inscrits = stats['inscrits_actifs'] or 1
        taux_participation = round(
            _pct(nb_inscrits - stats['absents_notoires'], nb_inscrits, decimals=4), 4
        )
        groupes_termines = _groupes_termines_count(
            formation_id, grade, secretariat_id, module_ids=scope_module_ids,
        )

        lignes_global.append({
            'grade': grade,
            'effectif_secretariat': stats['effectif_secretariat'],
            'nb_encadrants': stats['nb_encadrants'],
            'nb_groupes': stats['nb_groupes'],
            'effectif_auditeurs': stats['inscrits_actifs'],
            'absents_notoires': stats['absents_notoires'],
            'groupes_termines': groupes_termines,
            'justificatifs': '',
            'taux_participation': taux_participation,
            'taux_absents_notoires': round(stats['pct_absents'], 4),
            'vh_total': vh_data['vh_prevu'],
            'vh_epuise': vh_data['vh_epuise'],
            'taux_exec_vh': vh_data['taux_execution'],
            'taux_presence_cours': pres['taux_presence'],
            'taux_absence_cours': pres['taux_absence'],
            'difficultes': '',
        })

    # Totaux point global
    def _sum_keys(rows, *keys):
        return {k: sum(r.get(k, 0) or 0 for r in rows) for k in keys}

    total_keys = (
        'effectif_secretariat', 'nb_encadrants', 'nb_groupes',
        'effectif_auditeurs', 'absents_notoires', 'groupes_termines',
        'vh_total', 'vh_epuise',
    )
    totaux = _sum_keys(lignes_global, *total_keys)
    totaux['taux_exec_vh'] = round(
        _pct(totaux['vh_epuise'], totaux['vh_total'], decimals=4), 4
    ) if totaux['vh_total'] else 100.0

    # ── VH par groupe (par grade) ─────────────────────────────────────────────
    vh_par_grade = []
    for grade in grades:
        mq_g = mq_base.filter(grade=grade)
        # Nettoyage et déduplication stricte des groupes
        groupes_raw = mq_g.exclude(groupe='').values_list('groupe', flat=True).distinct()
        groupes_clean = sorted({g.strip() for g in groupes_raw if g and g.strip()})
        lignes_vh = []
        for grp in groupes_clean:
            vh_data = _vh_grade_groupe(
                formation_id, grade, groupe=grp, secretariat_id=secretariat_id, module_ids=scope_module_ids,
            )
            lignes_vh.append({'groupe': grp, **vh_data})

        recap_prevu = sum(l['vh_prevu'] for l in lignes_vh)
        recap_epuise = sum(l['vh_epuise'] for l in lignes_vh)
        recap_restant = max(0.0, recap_prevu - recap_epuise)
        vh_par_grade.append({
            'grade': grade,
            'groupes': lignes_vh,
            'recap': {
                'vh_prevu': recap_prevu,
                'vh_epuise': recap_epuise,
                'vh_restant': recap_restant,
                'taux_execution': round(_pct(recap_epuise, recap_prevu, decimals=4), 2) if recap_prevu else 100.0,
                'taux_restant': round(_pct(recap_restant, recap_prevu, decimals=4), 2) if recap_prevu else 0.0,
            },
        })

    # ── Absents notoires (liste nominative) ───────────────────────────────────
    notoire_ids = participant_ids_notoires(
        module_ids=scope_module_ids,
        formation_id=formation_id,
        secretariat_id=secretariat_id,
        categorie=categorie,
    )
    pq_notoires = Participant.objects.filter(id__in=notoire_ids).order_by('groupe', 'nom').values(
        'matricule', 'nom', 'prenom', 'libelle_concours', 'telephone', 'groupe', 'grade', 'motif_notoire',
    )
    absents_notoires = []
    for i, p in enumerate(pq_notoires, 1):
        motif = (p['motif_notoire'] or '').strip()
        absents_notoires.append({
            'numero': i,
            'matricule': p['matricule'],
            'nom': p['nom'],
            'prenom': p['prenom'],
            'libelle_concours': p['libelle_concours'],
            'contacts': p['telephone'],
            'groupe': p['groupe'],
            'grade': p['grade'],
            'observations': motif or 'Jamais badgé',
        })

    # ── Résumé modules (état d'avancement) ───────────────────────────────────
    from formations.volume_horaire import compute_volume_horaire_per_module_ids

    modules_qs = mq_base.select_related('formation').order_by('grade', 'groupe', 'intitule')
    mod_ids_list = list(modules_qs.values_list('id', flat=True))
    vh_by_module = compute_volume_horaire_per_module_ids(mod_ids_list, integer_hours=True)
    modules_statuts = []
    for m in modules_qs:
        vh = vh_by_module.get(m.id, {})
        vh_prevu = float(vh.get('prevu_heures', 0) or 0)
        vh_realise = float(vh.get('realise_heures', 0) or 0)
        modules_statuts.append({
            'id': m.id,
            'intitule': m.intitule,
            'grade': m.grade,
            'groupe': m.groupe,
            'statut': m.statut,
            'date_debut': m.date_debut.isoformat() if m.date_debut else None,
            'date_fin': m.date_fin.isoformat() if m.date_fin else None,
            'vh_prevu': vh_prevu,
            'vh_realise': vh_realise,
            'vh_restant': max(0.0, vh_prevu - vh_realise),
        })

    return {
        'type': 'bilan_fac',
        'titre': f'BILAN {annee} — {formation_nom}',
        'formation_id': formation.id,
        'formation': formation.formation,
        'annee': annee,
        'date_generation': date.today().strftime('%d/%m/%Y'),
        'grades': grades,
        'groupes_filtres': list(_parse_groupes_filter(groupes_filter)) if groupes_filter else [],
        'justificatifs': '',
        'point_global': {
            'lignes': lignes_global,
            'totaux': totaux,
        },
        'vh_par_grade': vh_par_grade,
        'absents_notoires': absents_notoires,
        'modules_statuts': modules_statuts,
    }
