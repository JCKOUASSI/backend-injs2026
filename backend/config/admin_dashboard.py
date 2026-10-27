"""Contexte enrichi pour la page d'accueil admin (style dashboard)."""

from django.db.models import Count
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
    from presences.models import Pointage
    from statistiques.views import _historique_mensuel

    historique = _historique_mensuel(mois=6)

    pointages_mensuels = build_histogram([
        {
            'label': _mois_label(item['mois']),
            'value': item['total'],
        }
        for item in historique['pointages_par_mois']
    ], color='#0b478a')

    taux_presence = build_stacked_bars([
        {
            'label': _mois_label(item['mois']),
            'presents': item['presents'],
            'absents': item['absents'],
            'display': f"{item['total']:.1f}".replace('.', ',') + '%',
            'detail': _('{p} présents / {a} absents').format(
                p=item['presents'],
                a=item['absents'],
            ),
        }
        for item in historique['taux_presence_par_mois']
    ])

    sessions_mensuelles = build_histogram([
        {
            'label': _mois_label(item['mois']),
            'value': item['total'],
        }
        for item in historique['sessions_par_mois']
    ], color='#0369a1')

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
    from formations.models import Formation, Module, Participant
    from presences.models import Pointage

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

    stats = [
        {
            'label': _('Formations'),
            'value': Formation.objects.count(),
            'icon': 'school',
            'link': 'admin:formations_formation_changelist',
            'highlight': True,
        },
        {
            'label': _('Modules'),
            'value': Module.objects.count(),
            'icon': 'menu_book',
            'link': 'admin:formations_module_changelist',
        },
        {
            'label': _('Étudiants'),
            'value': Participant.objects.count(),
            'icon': 'groups',
            'link': 'admin:formations_participant_changelist',
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
            'icon': 'smartphone',
            'link': 'admin:presences_devicebinding_changelist',
        },
    ]

    context['admin_greeting'] = greeting
    context['admin_user_name'] = first_name
    context['admin_stats'] = stats
    context['admin_charts'] = _build_admin_charts()
    return context
