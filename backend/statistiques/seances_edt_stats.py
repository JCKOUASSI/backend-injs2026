"""Statistiques des séances LMD planifiées par l'EDT (canal ``seance_edt``).

Pourquoi ce module existe
-------------------------
Le socle décisionnel historique (``statistiques/effectifs.py`` et
``point_journalier.py``) raisonne en **``Module``** : une séance y est un
``SessionModule``, rattaché à un module, donc à une ``Formation`` **instance**.

Les présences LMD, elles, sont enregistrées sur le canal EDT : le ``Pointage``
porte ``seance_edt = AffectationCreneau`` et ``session = None``. Or
``AffectationCreneau`` est rattachée à une ``RefFormation`` (entrée de
catalogue) et à un ``Groupe`` — **pas** à un ``Module``.

Il n'existe donc **aucun lien déterministe** entre une séance EDT et un
``Module`` : rattacher une présence EDT à un module demanderait de répartir
une séance de catalogue sur N modules, ce qui reviendrait à inventer une règle
d'attribution et à fausser silencieusement les taux. Ce module évite donc cet
écueil : il calcule l'assiduité **dans le monde EDT**, à la granularité
(formation, groupe) qui est la sienne, sans rien imposer au socle legacy.

Règles appliquées (alignées sur le canal legacy, voir ``effectifs.py``)
------------------------------------------------------------------------
- **Séance comptabilisable** : séance déjà tenue (date atteinte) **ou** portant
  au moins une présence valide.
- **Attendus** : membres actifs du groupe de la séance
  (``presences.seances_edt_services.membres_groupe``).
- **Présent** : pointage valide (``q_pointage_present``) — entrée sans sortie,
  ou sortie avec durée > 0, hors ``ABSENT_NON_BADGE``.
- **Absent** : attendu sans présence valide sur les séances de la période.
- **Taux** : présents / attendus, arrondi à 4 décimales (convention maison).

Aucune écriture : ce module est exclusivement en lecture.
"""
from collections import defaultdict
from datetime import date, timedelta

from django.utils import timezone

from formations.models import RefFormation
from presences import seances_edt_services as service
from presences.models import Pointage

from .effectifs import q_pointage_present

__all__ = [
    'seances_comptabilisables',
    'presentes_par_seance',
    'stats_seance',
    'stats_periode',
    'taux_presence',
]


def _periode_occurrence(affectation, date_debut, date_fin):
    """Occurrences (dates réelles de séance) comprises dans la période.

    Une ``AffectationCreneau`` couvre des semaines académiques : on balaie les
    jours de la période et on ne retient que ceux où la séance a effectivement
    lieu (``est_seance_du_jour``).
    """
    aujourdhui = timezone.localdate()
    if date_debut is None and date_fin is None:
        return [aujourdhui]
    debut = date_debut or aujourdhui - timedelta(days=365)
    fin = date_fin or aujourdhui
    if fin < debut:
        debut, fin = fin, debut
    # Garde-fou : on ne balaie pas plus de 5 ans (bornes erronées).
    if (fin - debut).days > 1826:
        debut = fin - timedelta(days=1826)
    occurrences = []
    courant = debut
    while courant <= fin:
        if service.est_seance_du_jour(affectation, courant):
            occurrences.append(courant)
        courant += timedelta(days=1)
    return occurrences


def seances_comptabilisables(
    formation_id=None,
    groupe_id=None,
    date_debut=None,
    date_fin=None,
    *,
    seulement_terminees=True,
):
    """``[(AffectationCreneau, jour, jour)]`` — séances EDT comptabilisables.

    ``seulement_terminees=True`` applique la règle legacy : la séance doit être
    passée, ou porter au moins une présence valide (saisie anticipée).
    """
    from edts.models import AffectationCreneau

    qs = AffectationCreneau.objects.filter(
        actif=True,
        emploi_du_temps__statut__in=('VALIDE', 'PUBLIE'),
    ).select_related('creneau_template', 'emploi_du_temps', 'formation', 'groupe')

    if formation_id is not None:
        qs = qs.filter(formation_id=formation_id)
    if groupe_id is not None:
        qs = qs.filter(groupe_id=groupe_id)

    resultat = []
    for affectation in qs:
        for jour in _periode_occurrence(affectation, date_debut, date_fin):
            if not seulement_terminees or jour <= timezone.localdate():
                resultat.append((affectation, jour, jour))
            elif Pointage.objects.filter(seance_edt=affectation, date_journee=jour) \
                    .filter(q_pointage_present()).exists():
                resultat.append((affectation, jour, jour))
    return resultat


def presentes_par_seance(seances):
    """``{(seance_edt_id, jour): {participant_id}}`` — présences valides."""
    resultat = defaultdict(set)
    if not seances:
        return resultat
    cles = {(a.pk, jour) for a, jour, _f in seances}
    ids = {a.pk for a, _j, _f in seances}
    for sid, jour in cles:
        for pid in (Pointage.objects
                    .filter(seance_edt_id=sid, date_journee=jour)
                    .filter(q_pointage_present())
                    .values_list('participant_id', flat=True)):
            if pid and sid in ids:
                resultat[(sid, jour)].add(pid)
    return resultat


def stats_seance(affectation, jour, presents):
    """Statistiques d'une séance EDT : attendus / présents / absents / taux."""
    attendus = {p.pk: p for p in service.membres_groupe(affectation)}
    presents_ids = set(presents or ()) & set(attendus)
    effectif = len(attendus)
    presents = len(presents_ids)
    absents = effectif - presents
    return {
        'seance_edt_id': affectation.pk,
        'groupe_id': affectation.groupe_id,
        'formation_id': affectation.formation_id,
        'date_journee': jour,
        'intitule': affectation.intitule or str(affectation.creneau_template),
        'salle': affectation.salle_nom,
        'effectif': effectif,
        'presents': presents,
        'absents': absents,
        'taux_presence': round(presents / effectif, 4) if effectif else 0.0,
        'taux_absence': round(absents / effectif, 4) if effectif else 0.0,
        'attendus_ids': set(attendus),
        'presents_ids': presents_ids,
    }


def stats_periode(
    formation_id=None,
    groupe_id=None,
    date_debut=None,
    date_fin=None,
    *,
    seulement_terminees=True,
):
    """Synthèse d'assiduité LMD sur une période : par séance, puis agrégat.

    L'effectif retenu est l'effectif **union** sur toutes les séances de la
    période : sommer les effectifs séance par séance compterait un étudiant
    présent toute la journée autant de fois qu'il a de séances.
    """
    seances = seances_comptabilisables(
        formation_id=formation_id,
        groupe_id=groupe_id,
        date_debut=date_debut,
        date_fin=date_fin,
        seulement_terminees=seulement_terminees,
    )
    if not seances:
        return {
            'seances': [], 'nb_seances': 0, 'effectif': 0, 'presents': 0, 'absents': 0,
            'taux_presence': 0.0, 'taux_absence': 0.0, 'par_formation': [],
        }

    presents_map = presentes_par_seance(seances)
    lignes = []
    attendus_union = set()
    presents_union = set()
    for affectation, jour, _fin in seances:
        stats = stats_seance(affectation, jour, presents_map.get((affectation.pk, jour)))
        attendus_union |= stats.pop('attendus_ids')
        presents_union |= stats.pop('presents_ids')
        lignes.append(stats)

    presents_union &= attendus_union
    effectif = len(attendus_union)
    presents = len(presents_union)
    absents = effectif - presents

    par_formation = defaultdict(lambda: {'seances': 0, 'presentations': 0, 'attendus': set()})
    for affectation, jour, _fin in seances:
        par_formation[affectation.formation_id]['attendus'] |= {
            p.pk for p in service.membres_groupe(affectation)
        }
    for ligne in lignes:
        donnees = par_formation[ligne['formation_id']]
        donnees['seances'] += 1
        donnees['presentations'] += ligne['presents']

    synthese = []
    for fid, donnees in par_formation.items():
        eff = len(donnees['attendus'])
        pres = donnees['presentations']
        ref = RefFormation.objects.filter(pk=fid).first() if fid else None
        synthese.append({
            'formation_id': fid,
            'formation_intitule': getattr(ref, 'intitule', '') or '—',
            'nb_seances': donnees['seances'],
            'effectif': eff,
            'presentations': pres,
            'taux_presence': round(pres / eff, 4) if eff else 0.0,
        })
    synthese.sort(key=lambda d: d['formation_intitule'])

    return {
        'seances': lignes,
        'nb_seances': len(lignes),
        'effectif': effectif,
        'presents': presents,
        'absents': absents,
        'taux_presence': round(presents / effectif, 4) if effectif else 0.0,
        'taux_absence': round(absents / effectif, 4) if effectif else 0.0,
        'par_formation': synthese,
    }


def taux_presence(seance_edt_id, jour):
    """Taux de présence d'une séance précise (0.0 si séance inconnue)."""
    from edts.models import AffectationCreneau

    affectation = AffectationCreneau.objects.filter(pk=seance_edt_id).first()
    if affectation is None:
        return 0.0
    presents = presentes_par_seance([(affectation, jour, jour)]).get((seance_edt_id, jour), set())
    return stats_seance(affectation, jour, presents)['taux_presence']
