"""Génération de données SVG pour les graphiques de l'accueil admin."""

import math


def build_histogram(items, *, height=150, color='#0b478a', value_key='value'):
    """Histogramme vertical (barres) — retourne dimensions et barres SVG."""
    if not items:
        return None

    values = [item.get(value_key, 0) for item in items]
    peak = max(values) or 1
    count = len(items)

    # Géométrie : le SVG est étiré à la largeur de sa carte (width:100%). Une
    # largeur intrinsèque trop faible agrandissait donc les libellés jusqu'à
    # les faire se chevaucher. On dimensionne à ~420 px minimum pour que le
    # facteur d'agrandissement reste proche de 1.
    gap = 12
    bar_w = max(24, min(44, max(320 // count - gap, 24)))
    marge = 24
    width = max(count * (bar_w + gap) + 2 * marge, 420)

    # Tailles de police exposées aux gabarits : elles ne sont plus figées
    # dans le HTML, ce qui évite qu'une modification d'un côté désaccorde
    # l'autre.
    label_font = 7.5
    value_font = 9
    label_line_gap = 8
    # Largeur approximative d'un caractère à cette taille (police système).
    largeur_car = label_font * 0.56
    max_car = max(4, int((bar_w + gap - 6) / largeur_car))

    bars = []
    for index, item in enumerate(items):
        value = item.get(value_key, 0)
        bar_h = max(6, round(value / peak * (height - 24))) if value > 0 else 0
        bar_h = bar_h or 2
        x = marge + index * (bar_w + gap)
        label = str(item.get('label', ''))
        # Troncature calculée sur l'espace réellement disponible, et non sur
        # un nombre de caractères arbitraire.
        label_lines = _decouper_libelle(label, max_car)
        # `label_short` reste fourni pour les usages qui veulent une seule
        # chaîne (infobulles, aria) ; l'axe utilise `label_lines`.
        label_short = ' '.join(label_lines)
        bars.append({
            **item,
            'x': x,
            'y': height - bar_h,
            'bar_w': bar_w,
            'bar_h': bar_h,
            'text_x': x + bar_w / 2,
            'value_y': height - bar_h - 4,
            'label_y': height + 13,
            'label_short': label_short,
            'label_lines': label_lines,
            'show_value': value > 0,
            'fill': item.get('color', color),
        })

    return {
        'width': width,
        'height': height + 48,
        'plot_height': height,
        'bars': bars,
        'label_font': label_font,
        'value_font': value_font,
        'label_line_gap': label_line_gap,
    }


def _donut_slice_path(cx, cy, radius, start_angle, arc):
    """Trace une part de camembert ; gère le cas 100 % (arc complet)."""
    if arc >= 2 * math.pi - 1e-9:
        x1 = cx + radius * math.cos(start_angle)
        y1 = cy + radius * math.sin(start_angle)
        mid_angle = start_angle + math.pi
        xm = cx + radius * math.cos(mid_angle)
        ym = cy + radius * math.sin(mid_angle)
        return (
            f'M{cx:.2f} {cy:.2f} L{x1:.2f} {y1:.2f} '
            f'A{radius:.2f} {radius:.2f} 0 1 1 {xm:.2f} {ym:.2f} '
            f'A{radius:.2f} {radius:.2f} 0 1 1 {x1:.2f} {y1:.2f} Z'
        )

    x1 = cx + radius * math.cos(start_angle)
    y1 = cy + radius * math.sin(start_angle)
    end_angle = start_angle + arc
    x2 = cx + radius * math.cos(end_angle)
    y2 = cy + radius * math.sin(end_angle)
    large = 1 if arc > math.pi else 0
    return (
        f'M{cx:.2f} {cy:.2f} L{x1:.2f} {y1:.2f} '
        f'A{radius:.2f} {radius:.2f} 0 {large} 1 {x2:.2f} {y2:.2f} Z'
    )


def build_donut(items, *, size=None, value_key='value'):
    """Camembert / donut SVG avec légende."""
    active = [item for item in items if item.get(value_key, 0)]
    total = sum(item.get(value_key, 0) for item in active)
    if not total:
        return None

    if size is None:
        size = 168 if len(active) > 5 else 196

    radius = size / 2 - 16
    cx = cy = size / 2
    angle = -math.pi / 2
    slices = []

    for item in items:
        value = item.get(value_key, 0)
        if not value:
            continue
        arc = (value / total) * 2 * math.pi
        slices.append({
            **item,
            'path': _donut_slice_path(cx, cy, radius, angle, arc),
            'pct': round(value / total * 100),
        })
        angle += arc

    if not slices:
        return None

    return {
        'size': size,
        'cx': cx,
        'cy': cy,
        'inner_r': radius * 0.55,
        'total': total,
        'slices': slices,
    }


def build_stacked_bars(items, *, value_keys=('presents', 'absents')):
    """Bandes horizontales empilées (présents / absents par période)."""
    if not items:
        return None

    rows = []
    for item in items:
        first_key, second_key = value_keys
        first_val = item.get(first_key, 0)
        second_val = item.get(second_key, 0)
        total = first_val + second_val
        if total:
            first_pct = round(first_val / total * 100, 1)
            second_pct = round(100 - first_pct, 1)
        else:
            first_pct = second_pct = 0.0

        rows.append({
            **item,
            'first_pct': first_pct,
            'second_pct': second_pct,
            'first_pct_width': f'{first_pct:.1f}',
            'second_pct_width': f'{second_pct:.1f}',
        })

    return rows

def _tronquer(texte, max_car):
    """Tronque un fragment à la largeur disponible, avec ellipsis si besoin."""
    if len(texte) <= max_car:
        return texte
    return f'{texte[:max_car - 1]}…'


def _decouper_libelle(label, max_car):
    """Découpe un libellé en au plus deux lignes pour l'axe des abscisses.

    « sept. 2025 » devient ['sept.', '2025'] : sur deux lignes, chaque fragment
    tient dans l'espace entre deux barres, même avec 12 mois. Un libellé d'un
    seul mot reste sur une ligne.
    """
    morceaux = label.split(None, 1)
    if len(morceaux) == 2:
        return [_tronquer(morceaux[0], max_car), _tronquer(morceaux[1], max_car)]
    return [_tronquer(label, max_car)]
