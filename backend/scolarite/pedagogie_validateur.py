"""Moteur de validation du référentiel pédagogique INJS-LMD (A-5.4).

Module de VALIDATION PUR — aucune écriture en base n'est possible depuis ce module.
Il prépare le contrôle d'un futur import sans l'exécuter.

Règles immuables appliquées :
  - une valeur absente reste ``None`` (jamais 0, jamais une estimation) ;
  - un code n'est jamais généré automatiquement ;
  - une source P3/P4 ne peut pas produire une donnée officielle ;
  - une seule condition critique manquante rend la ligne NON IMPORTABLE.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Référentiels métier immutables (validés en A-4.5 / A-4.6)
# ─────────────────────────────────────────────────────────────────────────────

FILIERES = {
    'EM': 'Éducation et Motricité',
    'APA': 'Activités Physiques Adaptées',
    'ES': 'Entraînement Sportif',
    'MS': 'Management du Sport',
    'AND': 'Andragogie',
    'LOI': 'Loisir',
    'ECJP': 'Entrepreneuriat Jeunesse et Conduite de Projets',
    'GER': 'Gérontologie',
}

NIVEAUX = {'L1', 'L2', 'L3', 'M1', 'M2'}
SEMESTRES = {'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10'}
SEMESTRES_LICENCE = {'S1', 'S2', 'S3', 'S4', 'S5', 'S6'}
SEMESTRES_MASTER = {'S7', 'S8', 'S9', 'S10'}
NIVEAU_PAR_SEMESTRE = {
    'S1': 'L1', 'S2': 'L1', 'S3': 'L2', 'S4': 'L2', 'S5': 'L3', 'S6': 'L3',
    'S7': 'M1', 'S8': 'M1', 'S9': 'M2', 'S10': 'M2',
}

ECTS_SEMESTRE = Decimal('30')
ECTS_NIVEAU = Decimal('60')
ECTS_LICENCE = Decimal('180')
ECTS_MASTER = Decimal('120')
ECTS_CYCLE = Decimal('300')

# ─────────────────────────────────────────────────────────────────────────────
# Codes et statuts
# ─────────────────────────────────────────────────────────────────────────────

CODE_OFFICIEL = 'CODE_OFFICIEL'
CODE_DOCUMENTE_NON_OFFICIEL = 'CODE_DOCUMENTE_NON_OFFICIEL'
CODE_ABSENT = 'CODE_ABSENT'
CODE_INTERDIT = 'CODE_INTERDIT'

#: Codifications explicitement interdites — jamais générées, jamais importées.
CODES_INTERDITS = frozenset({
    'UE-EM-001', 'ECUE-EM-001', 'UE-ES-101', 'ECUE-ES-101',
    'EM-S1-ECUE-01', 'UE-EM-101', 'ECUE-EM-001',
})

#: Motif des codes « documentés » mais non officiels (extraits web, propositions).
MOTIF_CODE_NON_OFFICIEL = re.compile(r'^(?!.*\b8\d{4}\b)[A-Z0-9\-]{2,20}$')

CLASSES_SOURCE = {
    'P1': 'source administrative / officielle primaire',
    'P2': 'source officielle secondaire',
    'P3': 'source documentaire / extraction non opposable',
    'P4': 'source technique / dérivée',
}
#: Préfixes acceptés pour la classe de source (les livrables A-5 nomment
#: « P1_SOURCE_PRIMAIRE_SIGNEE », « P3_EXTRACTION_WEB », etc.).
PREFIXES_SOURCE = ('P1_', 'P2_', 'P3_', 'P4_')
CLASSES_POTENTIELLEMENT_OFFICIELLES = {'P1', 'P2'}


def classe_source(valeur: str) -> str:
    """Ramène une classe de source à son préfixe P1..P4, sinon ''."""
    v = (valeur or '').strip().upper()
    if not v:
        return ''
    if v in CLASSES_SOURCE:
        return v
    for p in PREFIXES_SOURCE:
        if v.startswith(p):
            return p[:-1]
    return ''


STATUTS_DOCUMENTAIRES = (
    'ABSENTE', 'PARTIELLE', 'COMPLETE', 'CONTRADICTOIRE',
    'A_VERIFIER', 'VALIDEE', 'REJETEE',
)
#: Statuts qui interdisent définitivement toute importation.
STATUTS_NON_IMPORTABLES = {'ABSENTE', 'PARTIELLE', 'CONTRADICTOIRE', 'A_VERIFIER', 'REJETEE'}

STATUTS_IMPORT = (
    'NON_IMPORTABLE', 'PRETE_A_VALIDER', 'VALIDEE_POUR_IMPORT',
    'IMPORT_EN_COURS', 'IMPORTEE', 'ERREUR_IMPORT',
)

#: Valeurs sentinelles jamais converties en nombre.
SENTINELLES_ABSENCE = {'NULL', '', 'NON_DOCUMENTE', 'NON_ARBITRABLE', 'N/A', 'NA', '-'}

CRITERES = {
    'A': 'A. Filière reconnue',
    'B': 'B. Niveau reconnu',
    'C': 'C. Semestre reconnu',
    'D': 'D. UE documentée',
    'E': 'E. ECUE documenté',
    'F': 'F. Relation UE → ECUE documentée',
    'G': 'G. CECT documentés',
    'H': 'H. Coefficient documenté',
    'I': 'I. CM documenté',
    'J': 'J. TD documenté',
    'K': 'K. TP documenté',
}



@dataclass
class Anomalie:
    """Anomalie détectée sur une ligne. Bloquante = interdit l'import."""

    niveau: str          # ERREUR_BLOQUANTE | AVERTISSEMENT
    code: str            # identifiant machine, ex. A_K_COEFFICIENT_ABSENT
    critere: str         # lettre A→K, ou 'X' hors grille
    champ: str
    valeur: str
    motif: str
    ligne: int = 0
    filiere: str = ''
    niveau_etude: str = ''
    semestre: str = ''
    ue: str = ''
    ecue: str = ''

    def ligne_csv(self) -> dict:
        return {
            'ligne': self.ligne,
            'niveau': self.niveau,
            'code': self.code,
            'critere': self.critere,
            'filiere': self.filiere,
            'niveau_etude': self.niveau_etude,
            'semestre': self.semestre,
            'ue': self.ue,
            'ecue': self.ecue,
            'champ': self.champ,
            'valeur': self.valeur,
            'motif': self.motif,
        }


def est_absent(valeur) -> bool:
    """Vrai si la valeur est une absence documentaire — jamais une valeur nulle métier."""
    if valeur is None:
        return True
    return isinstance(valeur, str) and valeur.strip().upper() in SENTINELLES_ABSENCE


def nombre(valeur):
    """Convertit en Decimal. Retourne None si la valeur est une absence.

    Ne convertit JAMAIS une sentinelle d'absence en 0.
    """
    if est_absent(valeur):
        return None
    if isinstance(valeur, Decimal):
        return valeur
    try:
        return Decimal(str(valeur).strip().replace(',', '.'))
    except (InvalidOperation, ValueError, TypeError):
        return None


def sha256_fichier(chemin) -> str:
    h = hashlib.sha256()
    with open(chemin, 'rb') as fh:
        for bloc in iter(lambda: fh.read(65536), b''):
            h.update(bloc)
    return h.hexdigest()


def classer_code(code: str, officiel: bool = False) -> str:
    """Classe un code sans jamais le générer.

    Retourne ``CODE_ABSENT``, ``CODE_INTERDIT``, ``CODE_OFFICIEL`` ou
    ``CODE_DOCUMENTE_NON_OFFICIEL``.
    """
    if est_absent(code):
        return CODE_ABSENT
    c = str(code).strip().upper()
    if c in {x.upper() for x in CODES_INTERDITS}:
        return CODE_INTERDIT
    if officiel:
        return CODE_OFFICIEL
    return CODE_DOCUMENTE_NON_OFFICIEL


@dataclass
class LigneValidee:
    """Résultat de la validation d'une ligne du référentiel."""

    index: int
    filiere: str = ''
    niveau: str = ''
    semestre: str = ''
    ue: str = ''
    ecue: str = ''
    code_ue: str = ''
    code_ecue: str = ''
    cect: object = None
    coefficient: object = None
    cm: object = None
    td: object = None
    tp: object = None
    source_id: str = ''
    source_type: str = ''
    statut_documentaire: str = ''
    criteres: dict = field(default_factory=dict)
    anomalies: list = field(default_factory=list)

    @property
    def importable(self) -> bool:
        return all(self.criteres.values()) and not any(
            a.niveau == 'ERREUR_BLOQUANTE' for a in self.anomalies
        )

    @property
    def statut_import(self) -> str:
        if self.importable:
            return 'PRETE_A_VALIDER'
        return 'NON_IMPORTABLE'

    @property
    def criteres_manquants(self) -> str:
        return ','.join(k for k in CRITERES if not self.criteres.get(k))

    def apercu(self) -> dict:
        return {
            'ligne': self.index,
            'filiere': self.filiere,
            'niveau': self.niveau,
            'semestre': self.semestre,
            'ue': self.ue or '—',
            'ecue': self.ecue or '—',
            'code_ue': self.code_ue or '—',
            'code_ecue': self.code_ecue or '—',
            'cect': str(self.cect) if self.cect is not None else 'NULL',
            'coefficient': str(self.coefficient) if self.coefficient is not None else 'NULL',
            'cm': str(self.cm) if self.cm is not None else 'NULL',
            'td': str(self.td) if self.td is not None else 'NULL',
            'tp': str(self.tp) if self.tp is not None else 'NULL',
            'source': self.source_id,
            'statut': self.statut_documentaire,
            'importable': 'OUI' if self.importable else 'NON',
            'criteres_manquants': self.criteres_manquants or '—',
        }


#: Alias de colonnes acceptés en entrée — le format canonique est prioritaire,
#: les alias couvrent les variantes staging A-5.3 sans jamais inventer de valeur.
ALIAS_COLONNES = {
    'ue': 'ue', 'intitule_ue': 'ue',
    'ecue': 'ecue', 'intitule_ecue': 'ecue',
    'code_ue': 'code_ue',
    'code_ecue': 'code_ecue',
    'cect': 'cect', 'credits': 'cect',
    'coefficient': 'coefficient',
    'cm': 'cm', 'volume_cm': 'cm',
    'td': 'td', 'volume_td': 'td',
    'tp': 'tp', 'volume_tp': 'tp',
    'filiere': 'filiere',
    'niveau': 'niveau',
    'semestre': 'semestre',
    'source_id': 'source_id',
    'source_type': 'source_type',
    'statut_documentaire': 'statut_documentaire',
    'statut': 'statut_documentaire',
}


def normaliser_ligne(brut: dict) -> dict:
    """Ramène une ligne vers le format canonique, sans jamais créer de valeur."""
    out = {}
    for cle, valeur in brut.items():
        if cle is None:
            continue
        canon = ALIAS_COLONNES.get(cle.strip().lower())
        if canon and canon not in out:
            out[canon] = valeur
    return out


def valider_ligne(brut: dict, index: int) -> LigneValidee:
    """Applique la grille A→K à une ligne. Une condition manquante = NON IMPORTABLE."""
    brut = normaliser_ligne(brut)
    lv = LigneValidee(index=index)

    lv.filiere = (brut.get('filiere') or '').strip()
    lv.niveau = (brut.get('niveau') or '').strip()
    lv.semestre = (brut.get('semestre') or '').strip()
    lv.ue = (brut.get('ue') or '').strip()
    lv.ecue = (brut.get('ecue') or '').strip()
    lv.code_ue = (brut.get('code_ue') or '').strip()
    lv.code_ecue = (brut.get('code_ecue') or '').strip()
    lv.source_id = (brut.get('source_id') or '').strip()
    lv.source_type = (brut.get('source_type') or '').strip()
    lv.statut_documentaire = (brut.get('statut_documentaire') or '').strip().upper()

    lv.cect = nombre(brut.get('cect'))
    lv.coefficient = nombre(brut.get('coefficient'))
    lv.cm = nombre(brut.get('cm'))
    lv.td = nombre(brut.get('td'))
    lv.tp = nombre(brut.get('tp'))

    A = lv.anomalies.append

    # A — filière
    lv.criteres['A'] = lv.filiere in FILIERES
    if not lv.criteres['A']:
        A(Anomalie('ERREUR_BLOQUANTE', 'A_FILIERE_INCONNUE', 'A', 'filiere', lv.filiere,
                   f"Filliere hors referentiel parmi {sorted(FILIERES)}",
                   index, lv.filiere, lv.niveau, lv.semestre, lv.ue, lv.ecue))

    # B — niveau
    lv.criteres['B'] = lv.niveau in NIVEAUX
    if not lv.criteres['B']:
        A(Anomalie('ERREUR_BLOQUANTE', 'B_NIVEAU_INCONNU', 'B', 'niveau', lv.niveau,
                   f"Niveau hors referentiel parmi {sorted(NIVEAUX)}",
                   index, lv.filiere, lv.niveau, lv.semestre, lv.ue, lv.ecue))

    # C — semestre
    lv.criteres['C'] = lv.semestre in SEMESTRES
    if not lv.criteres['C']:
        A(Anomalie('ERREUR_BLOQUANTE', 'C_SEMESTRE_INCONNU', 'C', 'semestre', lv.semestre,
                   f"Semestre hors referentiel parmi {sorted(SEMESTRES)}",
                   index, lv.filiere, lv.niveau, lv.semestre, lv.ue, lv.ecue))
    elif lv.niveau and NIVEAU_PAR_SEMESTRE.get(lv.semestre) != lv.niveau:
        A(Anomalie('ERREUR_BLOQUANTE', 'C_SEMESTRE_NIVEAU_INCOHERENT', 'C', 'semestre',
                   lv.semestre,
                   f"{lv.semestre} appartient a {NIVEAU_PAR_SEMESTRE[lv.semestre]}, "
                   f"pas a {lv.niveau}",
                   index, lv.filiere, lv.niveau, lv.semestre, lv.ue, lv.ecue))
        lv.criteres['C'] = False

    # D — UE documentée
    lv.criteres['D'] = not est_absent(lv.ue)
    if not lv.criteres['D']:
        A(Anomalie('ERREUR_BLOQUANTE', 'D_UE_ABSENTE', 'D', 'ue', lv.ue or 'NULL',
                   "UE non documentee", index, lv.filiere, lv.niveau, lv.semestre,
                   lv.ue, lv.ecue))

    # E — ECUE documenté
    lv.criteres['E'] = not est_absent(lv.ecue)
    if not lv.criteres['E']:
        A(Anomalie('ERREUR_BLOQUANTE', 'E_ECUE_ABSENT', 'E', 'ecue', lv.ecue or 'NULL',
                   "ECUE non documente", index, lv.filiere, lv.niveau, lv.semestre,
                   lv.ue, lv.ecue))

    # F — relation UE → ECUE
    lv.criteres['F'] = lv.criteres['D'] and lv.criteres['E']
    if not lv.criteres['F'] and lv.criteres['D'] and lv.criteres['E']:
        pass
    elif not lv.criteres['F']:
        A(Anomalie('ERREUR_BLOQUANTE', 'F_RELATION_UE_ECUE_ABSENTE', 'F', 'ue->ecue', '',
                   "Relation UE -> ECUE non documentee", index, lv.filiere, lv.niveau,
                   lv.semestre, lv.ue, lv.ecue))

    # G — CECT
    lv.criteres['G'] = lv.cect is not None
    if not lv.criteres['G']:
        A(Anomalie('ERREUR_BLOQUANTE', 'G_CECT_ABSENT', 'G', 'cect',
                   str(brut.get('cect') or 'NULL'),
                   "CECT non documente — jamais complete par calcul", index, lv.filiere,
                   lv.niveau, lv.semestre, lv.ue, lv.ecue))
    elif lv.cect < 0:
        A(Anomalie('ERREUR_BLOQUANTE', 'G_CECT_NEGATIF', 'G', 'cect', str(lv.cect),
                   "CECT negatif", index, lv.filiere, lv.niveau, lv.semestre, lv.ue, lv.ecue))
        lv.criteres['G'] = False

    # Codes — contrôle séparé, jamais généré
    classe_code_ue = classer_code(lv.code_ue, officiel=(lv.source_type == 'P1'))
    classe_code_ecue = classer_code(lv.code_ecue, officiel=(lv.source_type == 'P1'))
    for champ, val, classe in (('code_ue', lv.code_ue, classe_code_ue),
                               ('code_ecue', lv.code_ecue, classe_code_ecue)):
        if classe == CODE_INTERDIT:
            A(Anomalie('ERREUR_BLOQUANTE', f'X_CODE_INTERDIT_{champ.upper()}', 'X', champ, val,
                       "Code artificiel explicitement interdit", index, lv.filiere,
                       lv.niveau, lv.semestre, lv.ue, lv.ecue))
        elif classe == CODE_ABSENT:
            # Aucun code ne doit être généré : l'absence est bloquante
            # (clé d'idempotence UE et ECUE).
            A(Anomalie('ERREUR_BLOQUANTE', f'X_{champ.upper()}_ABSENT', 'X', champ,
                       str(brut.get(champ) or 'NULL'),
                       "Aucun code officiel — aucun code ne sera genere", index,
                       lv.filiere, lv.niveau, lv.semestre, lv.ue, lv.ecue))

    # H — coefficient
    lv.criteres['H'] = lv.coefficient is not None
    if not lv.criteres['H']:
        A(Anomalie('ERREUR_BLOQUANTE', 'H_COEFFICIENT_ABSENT', 'H', 'coefficient',
                   str(brut.get('coefficient') or 'NULL'),
                   "Coefficient non documente — jamais 0, jamais estime", index, lv.filiere,
                   lv.niveau, lv.semestre, lv.ue, lv.ecue))
    elif lv.coefficient <= 0:
        A(Anomalie('ERREUR_BLOQUANTE', 'H_COEFFICIENT_NON_POSITIF', 'H', 'coefficient',
                   str(lv.coefficient), "Coefficient strictement positif attendu", index,
                   lv.filiere, lv.niveau, lv.semestre, lv.ue, lv.ecue))
        lv.criteres['H'] = False

    # I / J / K — volumes
    for critere, champ, attr in (('I', 'cm', 'cm'), ('J', 'td', 'td'), ('K', 'tp', 'tp')):
        val = getattr(lv, attr)
        lv.criteres[critere] = val is not None
        if val is None:
            A(Anomalie('ERREUR_BLOQUANTE', f'{critere}_VOLUME_ABSENT', critere, champ,
                       str(brut.get(champ) or 'NULL'),
                       f"{champ.upper()} non documente — jamais deduit", index, lv.filiere,
                       lv.niveau, lv.semestre, lv.ue, lv.ecue))
        elif val < 0:
            A(Anomalie('ERREUR_BLOQUANTE', f'{critere}_VOLUME_NEGATIF', critere, champ,
                       str(val), f"{champ.upper()} negatif", index, lv.filiere, lv.niveau,
                       lv.semestre, lv.ue, lv.ecue))
            lv.criteres[critere] = False

    # Statut documentaire
    if lv.statut_documentaire in STATUTS_NON_IMPORTABLES:
        A(Anomalie('ERREUR_BLOQUANTE', 'X_STATUT_NON_IMPORTABLE', 'X', 'statut_documentaire',
                   lv.statut_documentaire,
                   f"Le statut {lv.statut_documentaire} interdit l'import", index, lv.filiere,
                   lv.niveau, lv.semestre, lv.ue, lv.ecue))

    # Classe de source : P3/P4 ne peuvent pas produire de donnee officielle
    src = classe_source(lv.source_type)
    if not lv.source_type or est_absent(lv.source_type):
        # Aucune source identifiee : bloquant, le referentiel n'est pas opposable.
        A(Anomalie('ERREUR_BLOQUANTE', 'X_SOURCE_ABSENTE', 'X', 'source_type',
                   str(brut.get('source_type') or 'NULL'),
                   "Aucune source identifiee : la ligne n'est pas opposable", index,
                   lv.filiere, lv.niveau, lv.semestre, lv.ue, lv.ecue))
    elif not src:
        A(Anomalie('ERREUR_BLOQUANTE', 'X_SOURCE_INCONNUE', 'X', 'source_type',
                   lv.source_type,
                   f"Classe de source hors referentiel {sorted(CLASSES_SOURCE)}", index,
                   lv.filiere, lv.niveau, lv.semestre, lv.ue, lv.ecue))
    elif src in {'P3', 'P4'}:
        A(Anomalie('ERREUR_BLOQUANTE', 'X_SOURCE_NON_OPPOSABLE', 'X', 'source_type',
                   lv.source_type,
                   f"Une source {src} ne peut pas devenir une donnee officielle", index,
                   lv.filiere, lv.niveau, lv.semestre, lv.ue, lv.ecue))

    return lv


def controler_ECTS(lignes: list) -> list:
    """Contrôle des totaux ECTS. Ne corrige JAMAIS — signale uniquement."""
    anomalies = []
    totaux = {}
    for lv in lignes:
        if lv.cect is None or not lv.criteres.get('C'):
            continue
        cle = (lv.filiere, lv.semestre)
        totaux[cle] = totaux.get(cle, Decimal('0')) + lv.cect

    for (filiere, semestre), total in sorted(totaux.items()):
        if total != ECTS_SEMESTRE:
            anomalies.append(Anomalie(
                'ERREUR_BLOQUANTE', 'G_ECTS_SEMESTRE', 'G', 'SUM(cect)', str(total),
                f"Semestre {filiere}/{semestre} : somme {total} CECT au lieu de "
                f"{ECTS_SEMESTRE}. Aucune correction automatique.",
                0, filiere, NIVEAU_PAR_SEMESTRE.get(semestre, ''), semestre))

    niveaux = {}
    for (filiere, semestre), total in totaux.items():
        niv = NIVEAU_PAR_SEMESTRE.get(semestre)
        if niv:
            niveaux.setdefault((filiere, niv), Decimal('0'))
            niveaux[(filiere, niv)] += total
    for (filiere, niv), total in sorted(niveaux.items()):
        # un niveau n'est controle que si TOUS ses semestres sont documentes
        sem_attendus = [s for s, n in NIVEAU_PAR_SEMESTRE.items() if n == niv]
        if all((filiere, s) in totaux for s in sem_attendus):
            if total != ECTS_NIVEAU:
                anomalies.append(Anomalie(
                    'ERREUR_BLOQUANTE', 'G_ECTS_NIVEAU', 'G', 'SUM(cect niveau)',
                    str(total),
                    f"Niveau {filiere}/{niv} : somme {total} au lieu de {ECTS_NIVEAU}",
                    0, filiere, niv, ','.join(sem_attendus)))

    for filiere in sorted({f for f, _ in totaux}):
        for libelle, attendus, cible in (
            ('LICENCE', sorted(SEMESTRES_LICENCE, key=lambda s: int(s[1:])), ECTS_LICENCE),
            ('MASTER', sorted(SEMESTRES_MASTER, key=lambda s: int(s[1:])), ECTS_MASTER),
        ):
            if all((filiere, s) in totaux for s in attendus):
                somme = sum((totaux[(filiere, s)] for s in attendus), Decimal('0'))
                if somme != cible:
                    anomalies.append(Anomalie(
                        'ERREUR_BLOQUANTE', f'G_ECTS_{libelle}', 'G', f'SUM({libelle})',
                        str(somme),
                        f"{libelle} {filiere} : somme {somme} au lieu de {cible}",
                        0, filiere, libelle, ','.join(attendus)))
    return anomalies


def controler_doublons(lignes: list) -> list:
    """Détecte les doublons fonctionnels. Ne supprime jamais de ligne."""
    anomalies = []
    vus_ue, vus_ecue = {}, {}
    for lv in lignes:
        if not est_absent(lv.code_ue):
            cle = (lv.filiere, lv.semestre, lv.code_ue.strip().upper())
            if cle in vus_ue:
                anomalies.append(Anomalie(
                    'ERREUR_BLOQUANTE', 'X_DOUBLON_UE', 'X', 'code_ue', lv.code_ue,
                    f"UE deja presente ligne {vus_ue[cle]} (cle fonctionnelle "
                    f"filiere+niveau+semestre+code_ue)", lv.index, lv.filiere, lv.niveau,
                    lv.semestre, lv.ue, lv.ecue))
            else:
                vus_ue[cle] = lv.index
        if not est_absent(lv.code_ecue) and not est_absent(lv.code_ue):
            cle = (lv.code_ue.strip().upper(), lv.code_ecue.strip().upper())
            if cle in vus_ecue:
                anomalies.append(Anomalie(
                    'ERREUR_BLOQUANTE', 'X_DOUBLON_ECUE', 'X', 'code_ecue', lv.code_ecue,
                    f"ECUE deja presente ligne {vus_ecue[cle]} (cle fonctionnelle "
                    f"ue+code_ecue)", lv.index, lv.filiere, lv.niveau, lv.semestre,
                    lv.ue, lv.ecue))
            else:
                vus_ecue[cle] = lv.index
    return anomalies


def valider_fichier(chemin, delimiter: str = ';') -> dict:
    """Valide un fichier entier. AUCUNE écriture base de données."""
    chemin = Path(chemin)
    lignes, index = [], 0
    with open(chemin, encoding='utf-8-sig', newline='') as fh:
        for brut in csv.DictReader(fh, delimiter=delimiter):
            index += 1
            lignes.append(valider_ligne(brut, index))
    anomalies = controler_ECTS(lignes) + controler_doublons(lignes)
    return {
        'fichier': str(chemin),
        'sha256': sha256_fichier(chemin),
        'lignes': lignes,
        'anomalies': anomalies,
    }
