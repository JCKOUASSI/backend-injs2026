"""Analyse des paramètres de période (preset / dates) partagée entre Finance, dashboard et statistiques."""
import calendar
from datetime import date

from django.utils import timezone


def parse_period_from_request(request):
    """
    Analyse les paramètres de période.

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


def periode_api_payload(date_debut, date_fin, meta, date_min=None, date_max=None):
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
