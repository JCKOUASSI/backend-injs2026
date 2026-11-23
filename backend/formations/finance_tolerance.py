"""Évaluation des écarts planifié / réalisé avec marge de tolérance paramétrable."""


def tolerance_threshold_minutes(planned_minutes, settings):
    """Seuil de tolérance en minutes (max entre fixe et pourcentage)."""
    mins = float(getattr(settings, 'tolerance_minutes', 0) or 0)
    pct = float(getattr(settings, 'tolerance_pct', 0) or 0)
    planned = float(planned_minutes or 0)
    pct_min = planned * (pct / 100) if planned > 0 and pct > 0 else 0.0
    return max(mins, pct_min)


def evaluate_volume_tolerance(planned_minutes, realized_minutes, settings=None):
    """
    Évalue un écart volume horaire.

    Statuts (tolérance active) :
    - ``ok`` : réalisé ≥ planifié
    - ``alerte`` : déficit ≤ seuil de tolérance
    - ``anomalie`` : déficit > seuil

    Tolérance inactive : ``ecart`` si réalisé < planifié, sinon ``ok``.
    """
    from .models import FinanceSettings

    if settings is None:
        settings = FinanceSettings.get_solo()

    planned = float(planned_minutes or 0)
    realized = float(realized_minutes or 0)
    ecart = round(max(planned - realized, 0.0), 1)
    active = bool(getattr(settings, 'tolerance_active', False))

    result = {
        'tolerance_active': active,
        'ecart_minutes': ecart,
        'statut': 'ok',
        'statut_label': 'Conforme',
        'tolerance_minutes_applied': 0.0,
    }

    if planned <= 0:
        result['statut'] = 'na'
        result['statut_label'] = '—'
        return result

    if realized >= planned - 0.05:
        return result

    if not active:
        result['statut'] = 'ecart'
        result['statut_label'] = 'Écart constaté'
        return result

    threshold = tolerance_threshold_minutes(planned, settings)
    result['tolerance_minutes_applied'] = round(threshold, 1)
    if ecart <= threshold:
        result['statut'] = 'alerte'
        result['statut_label'] = 'Dans la tolérance'
    else:
        result['statut'] = 'anomalie'
        result['statut_label'] = 'Hors tolérance'
    return result


def tolerance_settings_payload(settings=None):
    from .models import FinanceSettings

    if settings is None:
        settings = FinanceSettings.get_solo()
    return {
        'tolerance_active': bool(getattr(settings, 'tolerance_active', False)),
        'tolerance_minutes': int(getattr(settings, 'tolerance_minutes', 0) or 0),
        'tolerance_pct': float(getattr(settings, 'tolerance_pct', 0) or 0),
    }
