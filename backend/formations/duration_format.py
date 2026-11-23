"""Formatage canonique des durées (évite les affichages invalides type « 3h60 »)."""


def minutes_to_hours_minutes(minutes):
    """Convertit des minutes en couple (heures entières, minutes 0–59)."""
    total = int(round(float(minutes or 0)))
    return divmod(total, 60)


def format_duration_minutes(minutes):
    """Affiche une durée : ``4h``, ``3h 40min``, ``45min``."""
    h, m = minutes_to_hours_minutes(minutes)
    if h == 0 and m == 0:
        return '0h'
    if m == 0:
        return f'{h}h'
    if h == 0:
        return f'{m}min'
    return f'{h}h {m}min'
