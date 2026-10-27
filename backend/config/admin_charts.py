"""Génération de données SVG pour les graphiques de l'accueil admin."""

import math


def build_histogram(items, *, height=150, color='#0b478a', value_key='value'):
    """Histogramme vertical (barres) — retourne dimensions et barres SVG."""
    if not items:
        return None

    values = [item.get(value_key, 0) for item in items]
    peak = max(values) or 1
    count = len(items)
    bar_w = max(22, min(48, max(280 // count - 10, 22)))
    width = max(count * (bar_w + 10) + 40, 280)

    bars = []
    for index, item in enumerate(items):
        value = item.get(value_key, 0)
        bar_h = max(6, round(value / peak * (height - 24))) if value > 0 else 0
        bar_h = bar_h or 2
        x = 20 + index * (bar_w + 10)
        label = str(item.get('label', ''))
        bars.append({
            **item,
            'x': x,
            'y': height - bar_h,
            'bar_w': bar_w,
            'bar_h': bar_h,
            'text_x': x + bar_w / 2,
            'value_y': height - bar_h - 4,
            'label_y': height + 14,
            'label_short': f'{label[:9]}…' if len(label) > 10 else label,
            'show_value': value > 0,
            'fill': item.get('color', color),
        })

    return {
        'width': width,
        'height': height + 52,
        'plot_height': height,
        'bars': bars,
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
