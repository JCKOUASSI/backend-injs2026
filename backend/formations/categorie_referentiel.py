"""
Résolution des catégories auditeur vers le référentiel RefCategorie.

Toute valeur brute (A, FAB A, FABA…) est normalisée puis mappée sur le libellé
canonique d'une RefCategorie active.
"""
import re

from django.db.models import Q

from .models import RefCategorie

_LETTRE_SUFFIXE = frozenset('ABCD')
_PREFIXES_FAMILLE = ('FAB', 'FAC', 'FAR')


def normalize_categorie_raw(raw):
    """Normalise une saisie brute (casse, espaces, variantes collées)."""
    c = (raw or '').strip().upper()
    if not c:
        return ''
    # Uniquement FAB/FAC/FAR + lettre (FABA → FAB A). Ne pas casser SFC, SST, SAC…
    m = re.fullmatch(r'(FAB|FAC|FAR)\s*([A-D])', c)
    if m:
        return f'{m.group(1)} {m.group(2)}'
    return c


class _RefCategorieIndex:
    """Index en mémoire des RefCategorie actives."""

    def __init__(self):
        self.by_upper = {}
        self.libelles = []
        for libelle in RefCategorie.objects.filter(actif=True).values_list('libelle', flat=True):
            canon = (libelle or '').strip()
            if not canon:
                continue
            self.libelles.append(canon)
            self.by_upper[canon.upper()] = canon

    def resolve(self, raw):
        norm = normalize_categorie_raw(raw)
        if not norm:
            return None

        hit = self.by_upper.get(norm)
        if hit:
            return hit

        m = re.fullmatch(r'([A-Z]{2,4})\s+([A-D])', norm)
        if m:
            letter = m.group(2)
            if letter in self.by_upper:
                return self.by_upper[letter]

        if len(norm) == 1 and norm in _LETTRE_SUFFIXE and norm in self.by_upper:
            return self.by_upper[norm]

        return None

    def raw_variants_for_libelle(self, libelle):
        """Variantes brutes pouvant correspondre à un libellé référentiel."""
        canon = (libelle or '').strip()
        if not canon:
            return set()

        variants = {canon}
        upper = canon.upper()
        variants.add(upper)

        if len(upper) == 1 and upper in _LETTRE_SUFFIXE:
            for prefix in _PREFIXES_FAMILLE:
                variants.add(f'{prefix} {upper}')
                variants.add(f'{prefix}{upper}')

        return {v for v in variants if v}

    def q_participant_categorie(self, libelle):
        """Filtre ORM ModuleParticipant / participant sur une catégorie référentielle."""
        if not libelle or libelle == '—':
            return Q()

        variants = self.raw_variants_for_libelle(libelle)
        q = Q()
        for variant in variants:
            q |= Q(participant__categorie__iexact=variant)
        return q


_ref_index = None


def get_ref_categorie_index():
    global _ref_index
    if _ref_index is None:
        _ref_index = _RefCategorieIndex()
    return _ref_index


def reset_ref_categorie_index():
    """Réinitialise le cache (tests)."""
    global _ref_index
    _ref_index = None


def resolve_categorie_ref(raw):
    """Retourne le libellé RefCategorie canonique ou None."""
    return get_ref_categorie_index().resolve(raw)


def resolve_categorie_participant(raw_categorie='', grade=''):
    """Mappe une saisie auditeur (éventuellement déduite du grade) vers RefCategorie."""
    raw = (raw_categorie or '').strip()
    if not raw and grade:
        first_letter = grade.strip()[:1].upper()
        if first_letter in _LETTRE_SUFFIXE:
            raw = first_letter
    if not raw:
        return ''
    return resolve_categorie_ref(raw) or ''


def libelles_ref_actifs():
    """Libellés actifs du référentiel, triés."""
    idx = get_ref_categorie_index()
    return sorted(idx.libelles, key=lambda c: (len(c), c))


def categories_from_raw_values(raw_values):
    """Déduplique et trie les libellés référentiels issus de valeurs brutes."""
    seen = set()
    out = []
    for raw in raw_values:
        resolved = resolve_categorie_ref(raw)
        if resolved and resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return sorted(out, key=lambda c: (len(c), c))


def q_participant_categorie_ref(libelle):
    return get_ref_categorie_index().q_participant_categorie(libelle)


def q_module_participant_categorie_ref(libelle):
    """Filtre ORM Module sur une catégorie référentielle (via inscriptions)."""
    if not libelle or libelle == '—':
        return Q()

    variants = get_ref_categorie_index().raw_variants_for_libelle(libelle)
    q = Q()
    for variant in variants:
        q |= Q(module_participants__participant__categorie__iexact=variant)
    return q
