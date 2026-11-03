"""Contexte enrichi pour la page d'accueil admin (style dashboard).

Sources alignées sur la chaîne LMD — les mêmes compteurs que le tableau de
bord web (formations du référentiel, ECUE des maquettes actives, inscrits
validés de l'année). Les anciennes cartes lisaient les modèles hérités
``Formation``/``Module`` et les graphiques les séances ``SessionModule`` :
sur une base LMD, l'accueil admin affichait 0 formation, 0 module et des
taux de présence à 0,0 % (dénominateur absent) alors que le frontend
montre 16 formations, 779 ECUE et 3 516 inscrits.
"""

from datetime import date, timedelta

from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from config.admin_charts import build_donut, build_histogram, build_stacked_bars

_MOIS_FR = (
    'jan.', 'fév.', 'mars', 'avr.', 'mai', 'juin',
    'juil.', 'août', 'sep.', 'oct.', 'nov.', 'déc.',
)

_STATUT_COLORS = {
    'EN_COURS': '#0e58ab',
    'TERMINE': '#0b478a',
    'FORCE_DFRC': '#116ed6',
    'ABSENT_NON_BADGE': '#ea9d0c',
    'HORS_LIGNE_SUSPECT': '#dc2626',
    'SORTIE_AUTO': '#f9b116',
}


def _six_derniers_mois():
    """[(clé 'AAAA-MM', 1er jour), …] des 6 derniers mois, courant inclus."""
    aujourdhui = timezone.localdate()
    cles = []
    annee, mois = aujourdhui.year, aujourdhui.month
    for _ in range(6):
        cles.append((f'{annee:04d}-{mois:02d}', date(annee, mois, 1)))
        mois -= 1
        if mois == 0:
            mois, annee = 12, annee - 1
    return list(reversed(cles))


def _cle_mois(valeur):
    d = valeur.date() if hasattr(valeur, 'date') else valeur
    return f'{d.year:04d}-{d.month:02d}'


def _mois_label(cle_mois):
    year, month = map(int, cle_mois.split('-'))
    return f'{_MOIS_FR[month - 1]} {year}'


def auditeurs_mobile_breakdown():
    """Répartition auditeurs mobile : badgés, connectés sans badge, badgés sans liaison."""
    from formations.models import Participant

    connecte_ids = set(
        Participant.objects.filter(
            user__device_bindings__is_active=True,
        ).values_list('pk', flat=True)
    )
    badgeur_ids = set(
        Participant.objects.filter(
            pointages__device_id__gt='',
        ).values_list('pk', flat=True)
    )

    badge_et_connecte = len(connecte_ids & badgeur_ids)
    connecte_sans_badge = len(connecte_ids - badgeur_ids)
    badge_sans_liaison = len(badgeur_ids - connecte_ids)

    return {
        'badgeurs': len(badgeur_ids),
        'connectes': len(connecte_ids),
        'badge_et_connecte': badge_et_connecte,
        'connecte_sans_badge': connecte_sans_badge,
        'badge_sans_liaison': badge_sans_liaison,
    }


def auditeurs_mobile_counts():
    """Auditeurs liés à un appareil mobile vs auditeurs ayant badgé via l'app."""
    breakdown = auditeurs_mobile_breakdown()
    return breakdown['badgeurs'], breakdown['connectes']


def _build_auditeurs_mobile_donut():
    breakdown = auditeurs_mobile_breakdown()
    items = []

    if breakdown['badge_et_connecte']:
        items.append({
            'label': _('Badgé mobile'),
            'value': breakdown['badge_et_connecte'],
            'color': '#0b478a',
        })
    if breakdown['connecte_sans_badge']:
        items.append({
            'label': _('Appareil lié, sans badge'),
            'value': breakdown['connecte_sans_badge'],
            'color': '#0369a1',
        })
    if breakdown['badge_sans_liaison']:
        items.append({
            'label': _('Badgé, liaison inactive'),
            'value': breakdown['badge_sans_liaison'],
            'color': '#ea9d0c',
        })

    return build_donut(items)


def _build_admin_charts():
    from edts.models import AffectationCreneau
    from presences.models import Pointage

    mois_liste = _six_derniers_mois()
    debut_periode = mois_liste[0][1]
    cles = [cle for cle, _ in mois_liste]

    pointages_periode = Pointage.objects.filter(date_journee__gte=debut_periode)

    # Pointages par mois (chaîne de présence unique).
    par_mois = {cle: 0 for cle in cles}
    for row in (pointages_periode.annotate(mois=TruncMonth('date_journee'))
                .values('mois').annotate(n=Count('id'))):
        par_mois[_cle_mois(row['mois'])] = row['n']
    items_pointages = [
        {'label': _mois_label(cle), 'value': par_mois[cle]} for cle in cles
    ]
    # Aucune donnée → None : le gabarit affiche « Aucune donnée sur la
    # période. » plutôt qu'un histogramme vide sans explication.
    pointages_mensuels = (
        build_histogram(items_pointages, color='#0b478a')
        if any(i['value'] for i in items_pointages) else None
    )

    # Présents / absents par mois, depuis `statut_assiduite` (catégories de
    # la supervision LMD : présent ou en retard = présent ; absence
    # justifiée/excusée = absent ; NON_RENSEIGNE exclu du dénominateur).
    # Un mois sans pointage qualifié affiche « — » : JAMAIS « 0,0 % », qui
    # prétendrait que personne n'était présent.
    presence = {cle: {'presents': 0, 'absents': 0} for cle in cles}
    for row in (pointages_periode.annotate(mois=TruncMonth('date_journee'))
                .values('mois', 'statut_assiduite').annotate(n=Count('id'))):
        cellule = presence.get(_cle_mois(row['mois']))
        if cellule is None:
            continue
        if row['statut_assiduite'] in ('PRESENT', 'RETARD'):
            cellule['presents'] += row['n']
        elif row['statut_assiduite'] in ('ABSENT', 'ABSENCE_JUSTIFIEE', 'EXCUSE'):
            cellule['absents'] += row['n']

    lignes_taux = []
    for cle in cles:
        presents = presence[cle]['presents']
        absents = presence[cle]['absents']
        denominateur = presents + absents
        if denominateur:
            taux = round(presents / denominateur * 100, 1)
            display = f'{taux:.1f}'.replace('.', ',') + '%'
            detail = _('{p} présents / {a} absents').format(
                p=presents, a=absents)
        else:
            display = '—'
            detail = _('Aucun pointage qualifié ce mois-ci')
        lignes_taux.append({
            'label': _mois_label(cle),
            'presents': presents,
            'absents': absents,
            'display': display,
            'detail': detail,
        })
    taux_presence = build_stacked_bars(lignes_taux)

    # Séances EDT par mois (chaîne LMD) : occurrences réelles des créneaux
    # actifs, avec la même règle que la supervision des présences
    # (`presences.seances_edt_services.est_seance_du_jour`) — numéro de
    # semaine académique relatif au début de l'année + jour du créneau type.
    _jours_semaine = {'LUNDI': 0, 'MARDI': 1, 'MERCREDI': 2, 'JEUDI': 3,
                      'VENDREDI': 4, 'SAMEDI': 5, 'DIMANCHE': 6}
    compte_seances = {cle: 0 for cle in cles}
    for aff in (AffectationCreneau.objects.filter(actif=True)
                .select_related('creneau_template',
                                'emploi_du_temps__annee_academique')):
        annee_aca = getattr(aff.emploi_du_temps, 'annee_academique', None)
        if annee_aca is None or annee_aca.date_debut is None:
            continue
        jour = _jours_semaine.get(getattr(aff.creneau_template, 'jour', None))
        if jour is None:
            continue
        semaine_min = aff.semaine_debut or 1
        semaine_max = aff.semaine_fin or semaine_min
        for semaine in range(semaine_min, semaine_max + 1):
            debut_semaine = annee_aca.date_debut + timedelta(weeks=semaine - 1)
            occurrence = debut_semaine + timedelta(
                days=(jour - debut_semaine.weekday()) % 7)
            cle = f'{occurrence.year:04d}-{occurrence.month:02d}'
            if cle in compte_seances:
                compte_seances[cle] += 1
    items_creneaux = [
        {'label': _mois_label(cle), 'value': compte_seances[cle]} for cle in cles
    ]
    sessions_mensuelles = (
        build_histogram(items_creneaux, color='#0369a1')
        if any(i['value'] for i in items_creneaux) else None
    )

    statut_labels = dict(Pointage.Statut.choices)
    statut_rows = list(
        Pointage.objects.values('statut')
        .annotate(value=Count('id'))
        .order_by('-value')
    )
    pointages_par_statut = build_donut([
        {
            'label': statut_labels.get(row['statut'], row['statut']),
            'value': row['value'],
            'color': _STATUT_COLORS.get(row['statut'], '#64748b'),
        }
        for row in statut_rows
        if row['value']
    ])

    auditeurs_mobile = _build_auditeurs_mobile_donut()

    return {
        'pointages_mensuels': pointages_mensuels,
        'taux_presence': taux_presence,
        'sessions_mensuelles': sessions_mensuelles,
        'pointages_par_statut': pointages_par_statut,
        'auditeurs_mobile': auditeurs_mobile,
    }


def admin_dashboard_callback(request, context):
    from formations.models import RefFormation
    from presences.models import Pointage
    from scolarite.models import (
        AnneeAcademique, ECUE, InscriptionAdministrative, Maquette,
    )

    user = request.user
    first_name = (user.first_name or user.get_username()).split('@')[0]

    hour = timezone.localtime().hour
    if hour < 12:
        greeting = _('Bonjour')
    elif hour < 18:
        greeting = _('Bon après-midi')
    else:
        greeting = _('Bonsoir')

    badgeurs_mobile, connectes_mobile = auditeurs_mobile_counts()

    # Mêmes définitions que le tableau de bord web (« Vue d'ensemble ») :
    # formations ACTIVES du référentiel, ECUE des maquettes ACTIVES de
    # l'année courante, inscriptions VALIDÉES de l'année courante. Les
    # modèles hérités (Formation, Module) restent dans la navigation.
    annee = (AnneeAcademique.courante_ou_none()
             or AnneeAcademique.objects.order_by('-libelle').first())
    ecues_qs = ECUE.objects.filter(ue__maquette__statut=Maquette.Statut.ACTIVE)
    inscrits_qs = InscriptionAdministrative.objects.filter(
        statut=InscriptionAdministrative.Statut.VALIDEE)
    if annee is not None:
        ecues_qs = ecues_qs.filter(ue__maquette__annee_academique=annee)
        inscrits_qs = inscrits_qs.filter(annee_academique=annee)

    stats = [
        {
            'label': _('Formations LMD'),
            'value': RefFormation.objects.filter(actif=True).count(),
            'icon': 'school',
            'link': 'admin:formations_refformation_changelist',
            'highlight': True,
        },
        {
            'label': _('ECUE enseignés'),
            'value': ecues_qs.distinct().count(),
            'icon': 'menu_book',
            'link': 'admin:scolarite_ecue_changelist',
        },
        {
            'label': _('Étudiants inscrits'),
            'value': inscrits_qs.count(),
            'icon': 'groups',
            'link': 'admin:scolarite_inscriptionadministrative_changelist',
        },
        {
            'label': _('Pointages'),
            'value': Pointage.objects.count(),
            'icon': 'fingerprint',
            'link': 'admin:presences_pointage_changelist',
        },
        {
            'label': _('Étudiants mobile'),
            'value': f'{badgeurs_mobile} / {connectes_mobile}',
            'detail': _('badgeage · appareil lié'),
            'icon': 'mobile',
            'link': 'admin:presences_devicebinding_changelist',
        },
    ]

    context['admin_greeting'] = greeting
    context['admin_user_name'] = first_name
    context['admin_stats'] = stats
    context['admin_charts'] = _build_admin_charts()
    return context
