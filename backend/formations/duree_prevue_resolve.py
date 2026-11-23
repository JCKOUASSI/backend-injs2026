"""Résolution de ``Module.duree_prevue_heures`` lorsque la valeur est absente.

Ordre de priorité :
  1. Valeur déjà renseignée manuellement sur le module (> 0, non auto-remplie)
  2. ``RefModule.volume_horaire`` (lien direct ou recherche par intitulé)
  3. Volume EDT « type » : durée la plus fréquente des séances × nombre de séances
     (évite de figer une somme faussée par une séance aberrante)
"""

from collections import Counter
from decimal import Decimal

from .models import RefFormation, RefModule, SessionModule
from .volume_horaire import _session_prevu_minutes, accumulate_sessions_volume


def _normalize_volume_categorie_code(categorie_code=None, module=None):
    """Mappe FAB B, A4… vers le libellé référentiel (A, B…)."""
    from .categorie_referentiel import resolve_categorie_ref

    if categorie_code:
        resolved = resolve_categorie_ref(categorie_code)
        if resolved:
            return resolved
        code = str(categorie_code).strip().upper()
        if len(code) == 1 and code in ('A', 'B', 'C', 'D'):
            return code
    if module is not None:
        inferred = _infer_module_categorie_code(module)
        if inferred:
            return inferred
    return None


def _resolve_ref_formation_for_module(module):
    """Retrouve la RefFormation correspondant au cycle du module opérationnel."""
    if not module or not getattr(module, 'formation_id', None):
        return None
    formation_obj = getattr(module, 'formation', None)
    if not formation_obj:
        return None
    label = (getattr(formation_obj, 'formation', None) or '').strip()
    if not label:
        return None
    return RefFormation.objects.filter(intitule__iexact=label).first()


def _infer_module_categorie_code(module):
    """Déduit la catégorie auditeur (A, B…) depuis le secrétariat ou le grade du module."""
    if module is None:
        return None
    secretariat = getattr(module, 'secretariat', None)
    type_obj = getattr(secretariat, 'type', None) if secretariat else None
    libelle = (getattr(type_obj, 'libelle', None) or '').strip()
    if libelle:
        code = libelle.replace('FAB', '').strip()[:1].upper()
        if code:
            return code
    grade = (getattr(module, 'grade', None) or '').strip()
    if grade:
        return grade[:1].upper()
    return None


def _ref_module_volume_hours(module, categorie_code=None, formation_id=None, formation_intitule=None):
    """Volume horaire référentiel pour un module opérationnel.

    Priorité : volume (formation × catégorie) → volume catégorie seule (legacy)
    → volume global ``RefModule.volume_horaire``.
    """
    ref = RefModule.resolve_for_module(module)
    if ref is None:
        return 0.0

    if formation_id is None and formation_intitule is None:
        ref_formation = _resolve_ref_formation_for_module(module)
        if ref_formation:
            formation_id = ref_formation.id
            formation_intitule = ref_formation.intitule

    cat = _normalize_volume_categorie_code(categorie_code, module)

    if cat and (formation_id or formation_intitule):
        vol = ref.get_volume_horaire_for_formation_categorie(
            formation_id=formation_id,
            formation_intitule=formation_intitule,
            categorie_code=cat,
        )
        if vol is not None and float(vol) > 0:
            return float(vol)

    if cat:
        heures = float(ref.get_volume_horaire_for_categorie(cat) or 0)
        if heures > 0:
            return heures

    heures = float(ref.volume_horaire or 0)
    return heures if heures > 0 else 0.0


def _get_module_participants_categories(module):
    """Retourne un dict {categorie: count} des participants du module."""
    from collections import Counter

    categories = module.module_participants.select_related('participant').values_list(
        'participant__categorie', flat=True
    )
    # Filtrer les valeurs vides
    categories = [c for c in categories if c]
    return dict(Counter(categories))


def _get_majoritaire_categorie(module):
    """Retourne la catégorie majoritaire des participants du module, ou None."""
    cat_counts = _get_module_participants_categories(module)
    if not cat_counts:
        return None
    raw = max(cat_counts, key=cat_counts.get)
    return _normalize_volume_categorie_code(raw, module)


def _ref_module_volume_hours_for_module(module, use_majoritaire=True):
    """Volume horaire du référentiel en tenant compte des catégories des participants.

    Si use_majoritaire=True, utilise la catégorie majoritaire des participants.
    Sinon, utilise le volume global.
    """
    if use_majoritaire:
        cat_majoritaire = _get_majoritaire_categorie(module)
        if cat_majoritaire:
            return _ref_module_volume_hours(module, cat_majoritaire)
    return _ref_module_volume_hours(module)


def _session_durations_hours(module):
    sessions = SessionModule.objects.filter(module=module).only(
        'heure_debut_prevue', 'heure_fin_prevue', 'date_journee',
        'demarree_le', 'terminee_le',
    )
    durations = []
    for session in sessions:
        minutes = _session_prevu_minutes(session)
        if minutes > 0:
            durations.append(round(minutes / 60, 2))
    return durations


def module_edt_raw_hours(module):
    """Somme brute des créneaux planifiés (peut inclure des écarts ponctuels)."""
    sessions = SessionModule.objects.filter(module=module).only(
        'heure_debut_prevue', 'heure_fin_prevue', 'date_journee',
        'demarree_le', 'terminee_le',
    )
    prevu_min = accumulate_sessions_volume(sessions)['prevu_min']
    return round(prevu_min / 60, 2) if prevu_min > 0 else 0.0


def _typical_session_duration_hours(durations_hours):
    if not durations_hours:
        return 0.0
    counts = Counter(durations_hours)
    top_count = counts.most_common(1)[0][1]
    modes = [duration for duration, count in counts.items() if count == top_count]
    if len(modes) == 1:
        return modes[0]
    sorted_d = sorted(durations_hours)
    mid = len(sorted_d) // 2
    if len(sorted_d) % 2:
        return sorted_d[mid]
    return round((sorted_d[mid - 1] + sorted_d[mid]) / 2, 2)


def module_edt_typical_hours(module):
    """
    Volume contractuel estimé depuis l'EDT : durée type × nombre de séances.

    Ex. six séances de 5 h et une à 6 h → 6 × 5 h = 30 h (et non 31 h).
    """
    durations = _session_durations_hours(module)
    if not durations:
        return 0.0
    typical = _typical_session_duration_hours(durations)
    return round(typical * len(durations), 2)


def module_edt_planned_hours(module):
    """Alias conservé : volume type EDT (pas la somme brute)."""
    return module_edt_typical_hours(module)


def resolve_module_volume_contractuel_heures(module, *, categorie_code=None, participant=None):
    """
    Volume contractuel pour assiduité / notes / fiche auditeur.

    Ordre : référentiel (catégorie auditeur ou majoritaire) → référentiel global
    → fiche module. N'utilise pas l'EDT planifié.
    """
    if categorie_code is None and participant is not None:
        categorie_code = (getattr(participant, 'categorie', None) or '').strip() or None
    if categorie_code is None:
        categorie_code = _get_majoritaire_categorie(module)
    else:
        categorie_code = _normalize_volume_categorie_code(categorie_code, module)

    if categorie_code:
        ref_cat = _ref_module_volume_hours(module, categorie_code)
        if ref_cat > 0:
            return ref_cat, 'ref_module_categorie'

    ref_h = _ref_module_volume_hours(module)
    if ref_h > 0:
        return ref_h, 'ref_module'

    fiche_h = float(module.duree_prevue_heures or 0)
    if fiche_h > 0:
        return fiche_h, 'module'

    return 0.0, None


def resolve_module_duree_prevue_heures(module, *, include_current=True, categorie_code=None):
    """
    Retourne ``(heures, source)`` avec source parmi
    ``ref_module``, ``module``, ``sessions_edt`` ou ``None``.

    Le référentiel ``RefModule.volume_horaire`` est prioritaire sur la fiche
    module (souvent remplie à tort par la somme brute de l'EDT à l'import).

    Si categorie_code est fourni, utilise le volume horaire spécifique à cette catégorie.
    Sinon, utilise la catégorie majoritaire des participants du module.
    """
    # Déterminer la catégorie à utiliser
    if not categorie_code:
        categorie_code = _get_majoritaire_categorie(module)

    ref_h = _ref_module_volume_hours(module, categorie_code)
    if ref_h > 0:
        return ref_h, 'ref_module'

    if include_current:
        current = float(module.duree_prevue_heures or 0)
        if current > 0:
            return current, 'module'

    edt_h = module_edt_typical_hours(module)
    if edt_h > 0:
        return edt_h, 'sessions_edt'

    return 0.0, None


def _should_overwrite_duree(current, raw_edt, canonical, ref_h):
    if canonical <= 0:
        return False
    if current <= 0:
        return True
    if ref_h > 0 and abs(current - ref_h) >= 0.01:
        return True
    # Corrige une fiche calée sur une somme EDT trop élevée (ex. 31 h ou 35 h au lieu de 30 h).
    if (
        raw_edt > 0
        and abs(current - raw_edt) < 0.01
        and canonical < raw_edt - 0.01
    ):
        return True
    return False


def ensure_module_duree_prevue(module, *, save=True, categorie_code=None):
    """
    Renseigne ou corrige ``duree_prevue_heures`` sur le module.

    Retourne ``(heures_effectives, source_utilisee)`` ;
    ``source_utilisee`` vaut ``None`` si la valeur en base est déjà correcte.

    Si categorie_code est fourni, utilise le volume horaire spécifique à cette catégorie.
    Sinon, utilise la catégorie majoritaire des participants.
    """
    current = float(module.duree_prevue_heures or 0)
    raw_edt = module_edt_raw_hours(module)

    # Déterminer la catégorie à utiliser
    if not categorie_code:
        categorie_code = _get_majoritaire_categorie(module)

    ref_h = _ref_module_volume_hours(module, categorie_code)
    canonical, source = resolve_module_duree_prevue_heures(module, include_current=False, categorie_code=categorie_code)

    if ref_h > 0:
        canonical, source = ref_h, 'ref_module'

    if not _should_overwrite_duree(current, raw_edt, canonical, ref_h):
        return current if current > 0 else 0.0, None

    if save and module.pk:
        module.duree_prevue_heures = Decimal(str(round(canonical, 2)))
        module.save(update_fields=['duree_prevue_heures'])

    return canonical, source
