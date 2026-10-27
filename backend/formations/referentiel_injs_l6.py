
"""L6 — Référentiel officiel INJS-LMD : qualification des cycles de formation.

Source métier unique et traçable : ``docs/audits/A-4.5-DOSSIER-VALIDATION-
METIER-INJS-LMD-2026-09-27.md`` §2 (table « Nomenclature des 8 filières »,
sources O7 / PDF / O2 / O6 / O9).

Ce module ne crée aucun modèle : il s'appuie exclusively sur
``formations.RefFormation`` (§4 L6). Il fournit :

* ``FILIERES_INJS``          — les 8 filières validées (valeurs attestées) ;
* ``CORPUS_INJS``            — les intitulés de cycles rattachés à ces filières ;
* ``formations_injs()``      — queryset ``RefFormation`` strictement INJS ;
* ``signaler_ecarts()``      — contrôle d'intégrité (8 filières).

Aucune valeur n'est inventée : seules les données attestées par la source
métier sont écrites. Les données étrangères ne sont ni renommées, ni
réutilisées, ni mappées (§1, §8 L6) — eux sont seulement *exclus* du périmètre
fonctionnel INJS (§9), jamais supprimés.
"""

from django.db.models import Q

from formations.models import RefFormation

# ── Source métier : A-4.5 §2 ─────────────────────────────────────────────────
# (code filière, sigle, libellé, école, domaine, diplômes attestés)
# Les sigles F05-F08 ne proviennent que de O7 : le module les porte comme
# traçabilité, sans en déduire de code officiel ni de parcours.
FILIERES_INJS = [
    ('F01', 'EM',   'Éducation et Motricité', 'ENSEPS', 'STAPS', ('LICENCE', 'MASTER')),
    ('F02', 'APA',  'Activités Physiques Adaptées', 'ENSEPS', 'STAPS', ('LICENCE', 'MASTER')),
    ('F03', 'ES',   'Entraînement Sportif', 'ENSEPS', 'STAPS', ('LICENCE', 'MASTER')),
    ('F04', 'MS',   'Management du Sport', 'ENSEPS', 'STAPS', ('LICENCE', 'MASTER')),
    ('F05', 'AND',  'Andragogie', 'ENSEP', '', ('LICENCE',)),
    ('F06', 'LOI',  'Loisir', 'ENSEP', '', ('LICENCE',)),
    ('F07', 'ECJP', 'Entrepreneuriat Jeunesse et Conduite de Projets', 'ENSEP', '', ('LICENCE',)),
    ('F08', 'GER',  'Gérontologie', 'ENSEP', '', ('LICENCE',)),
]

SOURCE_A45 = 'A-4.5 §2 (O7/PDF/O2/O6/O9)'

# Intitulés de cycles rattachés à chaque filière. Seules les combinaisons
# diplôme × filière attestées par la source figurent ici : ES/MS/APA/EM sont
# documentés « Licence + Master » (A-4.5 §3, D8), les quatre filières ENSEP
# (F05-F08) ne sont pas documentées avec un découpage licence/master (§2).
CORPUS_INJS = {
    'ÉDUCATION ET MOTRICITÉ — LICENCE':       'F01',
    'ÉDUCATION ET MOTRICITÉ — MASTER':        'F01',
    'ACTIVITÉS PHYSIQUES ADAPTÉES — LICENCE': 'F02',
    'ACTIVITÉS PHYSIQUES ADAPTÉES — MASTER':  'F02',
    'ENTRAÎNEMENT SPORTIF — LICENCE':         'F03',
    'ENTRAÎNEMENT SPORTIF — MASTER':          'F03',
    'MANAGEMENT DU SPORT — LICENCE':          'F04',
    'MANAGEMENT DU SPORT — MASTER':           'F04',
    'ANDRAGOGIE':                             'F05',
    'LOISIR':                                 'F06',
    'ENTREPRENEURIAT JEUNESSE ET CONDUITE DE PROJETS': 'F07',
    'GÉRONTOLOGIE':                           'F08',
}


# Lignes RefFormation historiques hors des 8 filières validées (A-4.5 §2).
# Elles sont classées LEGACY : elles restent en base (données historiques) mais
# sont exclues du référentiel fonctionnel INJS. Aucune suppression (§9).
CORPUS_LEGACY = [
    'PROFESSORAT DE LYCÉE — EPS',
    'PROFESSORAT DE LYCÉE — SPORT',
    'PROFESSORAT DE COLLÈGE — EPS',
    'MAÎTRE(SSE) D’ÉDUCATION PHYSIQUE ET SPORTIVE',
]

# Marqueurs de rejet : toute ligne dont l'intitulé en porte un est refusée du
# périmètre INJS, quelle que soit sa qualification en base (§10).
MARQUEURS_ETRANGERS = (
    'ADMINISTRATION DE BASE',
    'ADMINISTRATION COMPLÉMENTAIRE',
    'FINANCES PUBLIQUES',
)


def est_intitule_etranger(intitule):
    """Vrai si l'intitulé porte un marqueur de corpus non-INJS."""
    return any(m in (intitule or '').upper() for m in MARQUEURS_ETRANGERS)


def formations_injs(actif_only=False):
    """Queryset des seuls cycles relevant du référentiel officiel INJS.

    Deux conditions cumulatives : qualification ``INJS`` en base **et**
    absence de marqueur de corpus étranger dans l'intitulé. Le second filtre
    est une défense en profondeur : il garantit qu'une ligne mal qualifiée ne
    peut pas fuiter dans l'API INJS.
    """
    qs = RefFormation.objects.filter(perimetre=RefFormation.Perimetre.INJS)
    qs = qs.exclude(
        Q(intitule__icontains='ADMINISTRATION DE BASE')
        | Q(intitule__icontains='ADMINISTRATION COMPLÉMENTAIRE')
        | Q(intitule__icontains='FINANCES PUBLIQUES')
        | Q(intitule__icontains='DEBUG FORM')
        | Q(intitule__icontains='DEBUG')
    )
    return qs.filter(actif=True) if actif_only else qs


def formations_legacy():
    """Queryset des cycles explicitement hors périmètre INJS."""
    return RefFormation.objects.filter(perimetre=RefFormation.Perimetre.LEGACY)


def filieres_injs():
    """Dict ``{code_filiere: queryset des cycles}`` pour les 8 filières."""
    qs = formations_injs()
    return {
        code: qs.filter(filiere_code=code)
        for code, _sigle, _libelle, _ecole, _dom, _diplomes in FILIERES_INJS
    }


def signaler_ecarts():
    """Contrôle d'intégrité du référentiel (§19 L6).

    Retourne un dict de rapport — ne lève pas, pour que l'appelant puisse
    journaliser l'écart sans interrompre une requête de lecture.
    """
    par_filiere = filieres_injs()
    manquantes = [c for c, qs in par_filiere.items() if not qs.exists()]
    intruses = formations_injs().filter(
        Q(intitule__icontains='ADMINISTRATION DE BASE')
        | Q(intitule__icontains='ADMINISTRATION COMPLÉMENTAIRE')
        | Q(intitule__icontains='FINANCES PUBLIQUES')
        | Q(intitule__icontains='DEBUG FORM')
        | Q(intitule__icontains='DEBUG')
    )
    return {
        'nb_filieres_attendues': len(FILIERES_INJS),
        'nb_filieres_chargees': len(FILIERES_INJS) - len(manquantes),
        'filieres_manquantes': manquantes,
        'nb_cycles_injs': formations_injs().count(),
        'cycles_etrangers_inclus': list(intruses.values_list('intitule', flat=True)),
        'nb_cycles_legacy': formations_legacy().count(),
    }
