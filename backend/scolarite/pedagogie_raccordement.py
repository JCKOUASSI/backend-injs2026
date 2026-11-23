"""Résolution des référentiels métier INJS-LMD et construction du plan d'import (A-6).

Aucune écriture en base. Ce module ne fait que :

* résoudre les formations / niveaux / semestres / maquettes existants ;
* classer la résolution (EXACT_MATCH, NO_MATCH, MULTIPLE_MATCH, CONFLICT) ;
* produire un ``ImportPlan`` — un **verdict de simulation**, jamais une action.

Aucun ``NEW_REFERENCE`` n'est créé automatiquement. Aucun code n'est généré.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from scolarite.pedagogie_validateur import (
    FILIERES,
    NIVEAU_PAR_SEMESTRE,
    STATUTS_DOCUMENTAIRES,
    STATUTS_NON_IMPORTABLES,
    classe_source,
    est_absent,
)

# ─────────────────────────────────────────────────────────────────────────────
# Statuts de résolution
# ─────────────────────────────────────────────────────────────────────────────

EXACT_MATCH = 'EXACT_MATCH'
NO_MATCH = 'NO_MATCH'
MULTIPLE_MATCH = 'MULTIPLE_MATCH'
CONFLICT = 'CONFLICT'
NEW_REFERENCE = 'NEW_REFERENCE'

RESOLUTIONS = (EXACT_MATCH, NO_MATCH, MULTIPLE_MATCH, CONFLICT, NEW_REFERENCE)

# ─────────────────────────────────────────────────────────────────────────────
# Actions du plan
# ─────────────────────────────────────────────────────────────────────────────

CREATE = 'CREATE'
UPDATE = 'UPDATE'
UNCHANGED = 'UNCHANGED'
SKIP = 'SKIP'
REJECT = 'REJECT'

ACTIONS = (CREATE, UPDATE, UNCHANGED, SKIP, REJECT)

#: Une résolution « sans UE certaine » vaut rejet, pas simple absence.
REJECT_LIKE = REJECT

#: Verdict final. `PRETE_A_IMPORTER` est un verdict de SIMULATION : il ne
#:Declenche aucune ecriture et n'autorise aucun import en A-6.
PRETE_A_IMPORTER = 'PRETE_A_IMPORTER'
REJETEE = 'REJETEE'


def normaliser(texte: str) -> str:
    """Normalise un intitulé pour comparaison : casse, accents, ponctuation."""
    if not texte:
        return ''
    s = unicodedata.normalize('NFKD', str(texte))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    s = s.replace('—', ' ').replace('–', ' ').replace('-', ' ')
    return ' '.join(s.split())


#: Sigle métier -> fragments d'intitulé présents dans `RefFormation.intitule`.
FRAGMENTS_FILIERE = {
    'EM': ('EDUCATION ET MOTRICITE', 'ÉDUCATION ET MOTRICITÉ'),
    'APA': ('ACTIVITES PHYSIQUES ADAPTEE', 'ACTIVITÉS PHYSIQUES ADAPTÉES'),
    'ES': ('ENTRAINEMENT SPORTIF', 'ENTRAÎNEMENT SPORTIF'),
    'MS': ('MANAGEMENT DU SPORT',),
    'AND': ('ANDRAGOGIE',),
    'LOI': ('LOISIR',),
    'ECJP': ('ENTREPRENEURIAT JEUNESSE',),
    'GER': ('GERONTOLOGIE', 'GÉRONTOLOGIE'),
}

#: Cycle attendu — les formations STAPS existent en deux lignes (Licence, Master).
CYCLES = {'LICENCE': ('LICENCE', 'L1', 'L2', 'L3'),
          'MASTER': ('MASTER', 'M1', 'M2')}


@dataclass
class Resolution:
    """Résultat d'une résolution de référentiel."""

    objet: str
    cle: str
    resolution: str
    candidats: list = field(default_factory=list)
    retenu: object = None
    motif: str = ''

    @property
    def resolu(self) -> bool:
        return self.resolution == EXACT_MATCH


# ─────────────────────────────────────────────────────────────────────────────
# Résolutions — LECTURE SEULE sur la base
# ─────────────────────────────────────────────────────────────────────────────

def resoudre_formation(sigle: str, cycle: str = '') -> Resolution:
    """Résout un sigle de filière vers une (ou plusieurs) RefFormation.

    Les 4 filières STAPS existent en DEUX lignes (Licence + Master) : sans
    précision de cycle, la résolution est volontairement `MULTIPLE_MATCH` et
    bloque. Aucune formation n'est créée.
    """
    from formations.models import RefFormation

    if sigle not in FRAGMENTS_FILIERE:
        return Resolution('formation', sigle, NO_MATCH, [], None,
                          f"Sigle {sigle} hors referentiel metier")

    fragments = {normaliser(f) for f in FRAGMENTS_FILIERE[sigle]}
    candidats = [
        f for f in RefFormation.objects.all()
        if any(frag in normaliser(f.intitule or '') for frag in fragments)
    ]
    candidats.sort(key=lambda f: f.id)

    if not candidats:
        return Resolution('formation', sigle, NO_MATCH, [], None,
                          "Aucune RefFormation correspondante en base")

    if cycle:
        cles = {normaliser(c) for c in CYCLES.get(cycle.upper(), ())}
        # L'intitule DB est du type « ÉDUCATION ET MOTRICITÉ — LICENCE » :
        # le cycle est un SUFFIXE, pas une egalite.
        filt = [f for f in candidats
                if cles & {normaliser(t) for t in normaliser(f.intitule or '').split()}]
        if len(filt) == 1:
            return Resolution('formation', sigle, EXACT_MATCH,
                              [f.id for f in filt], filt[0],
                              f"Correspondance unique : {filt[0].intitule}")
        if len(filt) > 1:
            return Resolution('formation', sigle, MULTIPLE_MATCH,
                              [f.id for f in filt], None,
                              f"Cycle {cycle} ambigu : {[f.id for f in filt]}")
        return Resolution('formation', sigle, CONFLICT,
                          [f.id for f in candidats], None,
                          f"Aucune formation ne porte le suffixe {cycle}")

    if len(candidats) == 1:
        return Resolution('formation', sigle, EXACT_MATCH, [candidats[0].id],
                          candidats[0], f"Correspondance unique : {candidats[0].intitule}")

    return Resolution('formation', sigle, MULTIPLE_MATCH,
                      [f.id for f in candidats], None,
                      f"{len(candidats)} formations pour ce sigle "
                      f"({[f.id for f in candidats]}) : cycle non precise")


def resoudre_niveau(code: str) -> Resolution:
    from scolarite.models import Niveau

    if not code:
        return Resolution('niveau', code, NO_MATCH, [], None, 'Niveau absent')
    niveaux = list(Niveau.objects.filter(code=code))
    if len(niveaux) == 1:
        return Resolution('niveau', code, EXACT_MATCH, [niveaux[0].id], niveaux[0],
                          f"Niveau {code} resolu")
    if len(niveaux) > 1:
        return Resolution('niveau', code, MULTIPLE_MATCH, [n.id for n in niveaux], None,
                          f"{len(niveaux)} niveaux portent le code {code}")
    return Resolution('niveau', code, NO_MATCH, [], None,
                      f"Aucun Niveau avec le code {code}")


def resoudre_semestre(semestre: str, niveau_id=None) -> Resolution:
    from scolarite.models import Semestre

    if est_absent(semestre):
        return Resolution('semestre', str(semestre), NO_MATCH, [], None, 'Semestre absent')
    brut = str(semestre).strip().upper().lstrip('S')
    if not brut.isdigit():
        return Resolution('semestre', str(semestre), NO_MATCH, [], None,
                          f"Semestre illisible : {semestre}")
    qs = Semestre.objects.filter(numero=int(brut))
    if niveau_id:
        qs = qs.filter(niveau_id=niveau_id)
    lst = list(qs)
    if len(lst) == 1:
        return Resolution('semestre', str(semestre), EXACT_MATCH, [lst[0].id], lst[0],
                          f"Semestre S{brut} resolu")
    if len(lst) > 1:
        return Resolution('semestre', str(semestre), MULTIPLE_MATCH,
                          [s.id for s in lst], None, f"{len(lst)} semestres pour S{brut}")
    return Resolution('semestre', str(semestre), NO_MATCH, [], None,
                      f"Aucun Semestre numero {brut}" + (
                          f" pour le niveau {niveau_id}" if niveau_id else ''))


def resoudre_maquette(annee_id, formation_id, niveau_id, parcours_id=None) -> Resolution:
    """Résout une maquette existante. Ne crée JAMAIS de maquette."""
    from scolarite.models import Maquette

    if not all([annee_id, formation_id, niveau_id]):
        return Resolution('maquette', '-', NO_MATCH, [], None,
                          "Annee / formation / niveau requis pour resoudre une maquette")
    qs = Maquette.objects.filter(annee_academique_id=annee_id,
                                 ref_formation_id=formation_id,
                                 niveau_id=niveau_id)
    if parcours_id:
        qs = qs.filter(parcours_id=parcours_id)
    lst = list(qs)
    if not lst:
        return Resolution('maquette', '-', NO_MATCH, [], None,
                          "Aucune maquette existante (NEW_REFERENCE requise : "
                          "ne sera pas creee en A-6)")
    if len(lst) == 1:
        return Resolution('maquette', f"v{lst[0].version}", EXACT_MATCH,
                          [lst[0].id], lst[0], f"Maquette v{lst[0].version} resolue")
    return Resolution('maquette', '-', MULTIPLE_MATCH, [m.id for m in lst], None,
                      f"{len(lst)} maquettes candidates : import bloque")


def resoudre_ue(maquette_id, code, intitule) -> Resolution:
    """Résout une UE par code officiel, sinon identifiant métier, sinon intitulé EXACT.

    Jamais de fuzzy matching. Jamais de génération de code.
    """
    from scolarite.models import UE

    if maquette_id is None:
        return Resolution('ue', str(code or intitule or ''), NO_MATCH, [], None,
                          "Maquette non resolue : UE non rattachable")
    qs = UE.objects.filter(maquette_id=maquette_id)
    if not est_absent(code):
        exact = list(qs.filter(code__iexact=str(code).strip()))
        if len(exact) == 1:
            return Resolution('ue', str(code), EXACT_MATCH, [exact[0].id], exact[0],
                              f"Code officiel {code} trouve")
        if len(exact) > 1:
            return Resolution('ue', str(code), MULTIPLE_MATCH,
                              [u.id for u in exact], None, f"Code {code} en double")
    if not est_absent(intitule):
        par_intitule = list(qs.filter(intitule__iexact=str(intitule).strip()))
        if len(par_intitule) == 1:
            return Resolution('ue', str(code or ''), EXACT_MATCH,
                              [par_intitule[0].id], par_intitule[0],
                              "Correspondance par intitule exact")
        if len(par_intitule) > 1:
            return Resolution('ue', str(code or ''), MULTIPLE_MATCH,
                              [u.id for u in par_intitule], None,
                              f"{len(par_intitule)} UE portent cet intitule")
    return Resolution('ue', str(code or intitule or ''), NO_MATCH, [], None,
                      "Aucune UE existante (NEW_REFERENCE requise : non creee en A-6)")


def resoudre_ecue(ue_obj, code, intitule) -> Resolution:
    """Résout un ECUE sous une UE explicitement identifiée.

    Un ECUE sans UE certaine est `REJECT` : jamais de recherche par nom seul.
    """
    from scolarite.models import ECUE

    if ue_obj is None or getattr(ue_obj, 'id', None) is None:
        return Resolution('ecue', str(code or intitule or ''), REJECT_LIKE, [], None,
                          "ECUE sans UE certaine : rejet systematique")
    qs = ECUE.objects.filter(ue_id=ue_obj.id)
    if not est_absent(code):
        exact = list(qs.filter(code__iexact=str(code).strip()))
        if len(exact) == 1:
            return Resolution('ecue', str(code), EXACT_MATCH, [exact[0].id], exact[0],
                              f"Code ECUE {code} trouve")
        if len(exact) > 1:
            return Resolution('ecue', str(code), MULTIPLE_MATCH, [e.id for e in exact],
                              None, f"Code ECUE {code} en double")
    if not est_absent(intitule):
        par = list(qs.filter(intitule__iexact=str(intitule).strip()))
        if len(par) == 1:
            return Resolution('ecue', str(code or ''), EXACT_MATCH, [par[0].id], par[0],
                              "Correspondance par intitule exact")
        if len(par) > 1:
            return Resolution('ecue', str(code or ''), MULTIPLE_MATCH, [e.id for e in par],
                              None, f"{len(par)} ECUE portent cet intitule")
    return Resolution('ecue', str(code or intitule or ''), NO_MATCH, [], None,
                      "Aucun ECUE existant (NEW_REFERENCE requise : non creee en A-6)")


# ─────────────────────────────────────────────────────────────────────────────
# Construction du plan — SIMULATION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ActionPlan:
    """Une ligne du plan d'import — verdict, jamais exécution."""

    objet: str
    source_id: str
    identifiant: str
    libelle: str
    action: str
    statut: str
    motif: str
    filiere: str = ''
    niveau: str = ''
    semestre: str = ''
    source_hash: str = ''
    ligne: int = 0
    resolutions: list = field(default_factory=list)


@dataclass
class ImportPlan:
    """Plan d'import SIMULÉ. Aucune action n'est exécutée, quelle qu'elle soit."""

    source: str = ''
    source_hash: str = ''
    lignes: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    resolutions: list = field(default_factory=list)
    annee_id: object = None
    nb_create: int = 0
    nb_update: int = 0
    nb_unchanged: int = 0
    nb_skip: int = 0
    nb_reject: int = 0

    @property
    def pretes(self) -> list:
        return [a for a in self.actions if a.statut == PRETE_A_IMPORTER]

    def ajouter(self, action: ActionPlan):
        self.actions.append(action)
        setattr(self, f'nb_{action.action.lower()}',
                getattr(self, f'nb_{action.action.lower()}') + 1)
        return action

    def ajouter_resolution(self, r: Resolution):
        self.resolutions.append(r)
        return r

    def resume(self) -> dict:
        return {
            'source': self.source,
            'source_hash': self.source_hash,
            'lignes': len(self.lignes),
            'CREATE': self.nb_create,
            'UPDATE': self.nb_update,
            'UNCHANGED': self.nb_unchanged,
            'SKIP': self.nb_skip,
            'REJECT': self.nb_reject,
            'PRETE_A_IMPORTER': len(self.pretes),
        }


def construire_plan(lignes_validees, source: str, source_hash: str,
                    annee=None) -> ImportPlan:
    """Construit le plan de SIMULATION. N'exécute AUCUNE écriture.

    Pour chaque ligne validée : formation → niveau → semestre → maquette →
    UE → ECUE, puis verdict.
    """
    plan = ImportPlan(source=source, source_hash=source_hash,
                      lignes=list(lignes_validees))
    plan.annee_id = getattr(annee, 'id', None)

    for lv in lignes_validees:
        base = dict(
            source_id=lv.source_id,
            identifiant=lv.code_ue or lv.code_ecue or '—',
            libelle=lv.ue or lv.ecue or '—',
            filiere=lv.filiere, niveau=lv.niveau, semestre=lv.semestre,
            source_hash=source_hash, ligne=lv.index,
        )

        cycle = 'MASTER' if NIVEAU_PAR_SEMESTRE.get(lv.semestre) in ('M1', 'M2') else 'LICENCE'
        r_form = plan.ajouter_resolution(resoudre_formation(lv.filiere, cycle))
        r_niv = plan.ajouter_resolution(resoudre_niveau(lv.niveau))
        r_sem = plan.ajouter_resolution(resoudre_semestre(
            lv.semestre, r_niv.retenu.id if r_niv.retenu else None))
        r_maq = plan.ajouter_resolution(resoudre_maquette(
            plan.annee_id,
            r_form.retenu.id if r_form.retenu else None,
            r_niv.retenu.id if r_niv.retenu else None))
        r_ue = plan.ajouter_resolution(resoudre_ue(
            r_maq.retenu.id if r_maq.retenu else None, lv.code_ue, lv.ue))
        r_ecue = plan.ajouter_resolution(resoudre_ecue(r_ue.retenu, lv.code_ecue, lv.ecue))

        resolutions = [r_form, r_niv, r_sem, r_maq, r_ue, r_ecue]
        base['resolutions'] = resolutions

        if lv.statut_documentaire in STATUTS_NON_IMPORTABLES:
            plan.ajouter(ActionPlan(
                objet='cellule', action=REJECT, statut=REJETEE,
                motif=f"Statut documentaire {lv.statut_documentaire} : jamais importable",
                **base))
            continue

        if not lv.importable:
            plan.ajouter(ActionPlan(
                objet='cellule', action=REJECT, statut=REJETEE,
                motif=f"criteres A->K non satisfaits : {lv.criteres_manquants}", **base))
            continue

        if r_ecue.resolution == REJECT_LIKE:
            # Rejet explicite : un ECUE ne peut jamais être rattaché sans UE certaine.
            # Le motif remonte la cause racine (pas de maquette) pour rester diagnostic.
            cause = r_maq.motif if r_maq.resolution != EXACT_MATCH else r_ue.motif
            plan.ajouter(ActionPlan(
                objet='cellule', action=REJECT, statut=REJETEE,
                motif=f"ECUE sans UE certaine : rejet systematique — cause : {cause}",
                **base))
            continue

        non_exactes = [r for r in resolutions if r.resolution != EXACT_MATCH]
        if non_exactes:
            detail = ' | '.join(f"{r.objet}:{r.resolution}" for r in non_exactes)
            plan.ajouter(ActionPlan(
                objet='cellule', action=REJECT, statut=REJETEE,
                motif=f"Resolution incomplete — {detail}", **base))
            continue

        if r_ue.resolu and r_ecue.resolu:
            action, motif = UNCHANGED, "UE et ECUE deja existants"
        elif r_ue.resolu or r_maq.resolu:
            action, motif = UPDATE, "UE existant, ECUE a creer"
        else:
            action, motif = CREATE, "Maquette, UE et ECUE a creer"
        plan.ajouter(ActionPlan(
            objet='cellule', action=action, statut=PRETE_A_IMPORTER,
            motif=motif + " (SIMULATION — aucune ecriture)", **base))

    return plan
