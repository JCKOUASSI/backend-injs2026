"""Moteur de validation LMD par crédits ECTS (lot L3 — Prompt 13).

Cœur de calcul **pur et déterministe** : mêmes entrées ⇒ même résultat.
Il ne connaît ni les jurys ni l'affichage ; l'app ``jurys`` persiste les
propositions qu'il produit et les écrans consomment des API de lecture.
Aucune règle de calcul n'est dupliquée côté React/Flutter.

Chaîne utilisée :
  NoteModule (VALIDEE + verrouillée, lot L1)
    → module opérationnel (ModuleParticipant / Module.ref_module)
    → ECUE (ECUE.ref_module) → UE (pondération par coefficient)
    → Semestre (compensation paramétrable, crédits / semestre)
    → Niveau (Niveau.credits_requis, capitalisation).

Règles par défaut (règle 10/20, compensation semestre) si aucune
``RegleValidationLMD`` active ne correspond à la formation/niveau.
"""
from decimal import Decimal

from .models import (
    ECUE,
    InscriptionPedagogique,
    Maquette,
    RegleValidationLMD,
)

D20 = Decimal('20')


def _d(value):
    """Decimal arrondi à 2 décimales (convention arrondis du projet)."""
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal('0.01'))


def regle_pour(maquette):
    """Règle applicable : niveau spécifique, sinon défaut formation, sinon défauts."""
    regle = RegleValidationLMD.objects.filter(
        ref_formation=maquette.ref_formation,
        niveau=maquette.niveau, actif=True,
    ).first()
    if regle is None:
        regle = RegleValidationLMD.objects.filter(
            ref_formation=maquette.ref_formation, niveau__isnull=True, actif=True,
        ).first()
    return regle


class _Regle:
    """Vues de paramétrage effectives (règle configurée ou défauts standards)."""

    def __init__(self, regle=None):
        self.seuil = float(regle.seuil_admission) if regle else 10.0
        self.compensation = regle.compensation if regle else RegleValidationLMD.Compensation.SEMESTRE
        self.seuil_elim = float(regle.seuil_elim) if (regle and regle.seuil_elim is not None) else None
        self.credits_semestre = int(regle.credits_semestre) if regle else 30
        self.capitalisation = regle.capitalisation_activee if regle else True


def _moyenne_ecue(ecue, participant, module_participant=None):
    """Moyenne /20 d'une ECUE pour un étudiant, notes verrouillées uniquement.

    Le module opérationnel est identifié par l'inscription pédagogique
    (``module_participant``) puis, à défaut, par la passerelle ref_module.
    Retourne ``(moyenne | None, complet)``.
    """
    from formations.models import Module, NoteModule

    modules_ids = []
    if module_participant is not None:
        modules_ids.append(module_participant.module_id)
    elif ecue.ref_module_id:
        modules_ids = list(
            Module.objects.filter(
                ref_module_id=ecue.ref_module_id,
                module_participants__participant=participant,
            ).values_list('id', flat=True)
        )

    valeurs = NoteModule.objects.filter(
        colonne__module_id__in=modules_ids,
        participant=participant,
        note__isnull=False,
        verrouillee=True,
    ).select_related('colonne')

    if not valeurs.exists():
        return None, False

    # Moyenne par module (colonnes normalisées /20), puis moyenne des modules.
    par_module = {}
    for v in valeurs:
        note_max = float(v.colonne.note_max or D20)
        if note_max <= 0:
            note_max = 20.0
        par_module.setdefault(v.colonne.module_id, []).append(
            float(v.note) * 20.0 / note_max
        )

    moyennes_modules = [
        sum(vals) / len(vals) for vals in par_module.values() if vals
    ]
    if not moyennes_modules:
        return None, False
    return _d(sum(moyennes_modules) / len(moyennes_modules)), True


def _ponderee(paires):
    """Moyenne pondérée [(valeur, poids)] → float | None."""
    notees = [(float(v), float(w)) for v, w in paires if v is not None and float(w) > 0]
    if not notees:
        return None
    total_poids = sum(w for _, w in notees)
    return sum(v * w for v, w in notees) / total_poids


def calculer_validation_etudiant(inscription, maquette, regle=None,
                                 credits_capitalises=0):
    """Calcule la validation complète d'un étudiant sur une maquette versionnée.

    ``inscription``  : InscriptionAdministrative (étudiant / année / niveau).
    ``maquette``     : version de maquette applicable (VALIDEE/ACTIVE).
    ``regle``        : RegleValidationLMD optionnelle (défauts sinon).
    ``credits_capitalises`` : crédits déjà acquis (sessions antérieures).

    Retourne un dictionnaire **pur** (sérialisable, reproductible) :
    semestres → UE → ECUE, moyennes, crédits acquis, décision proposée.
    """
    if regle is None:
        regle = regle_pour(maquette)
    r = _Regle(regle)
    # ``inscription.etudiant`` est un DossierEtudiant (OneToOne Participant) :
    # les notes sont portées par le Participant opérationnel.
    participant = inscription.etudiant.participant

    # Inscriptions pédagogiques actives de l'étudiant (hors abandon/dispense).
    ips = {
        ip.ecue_id: ip
        for ip in InscriptionPedagogique.objects.filter(
            inscription=inscription,
            statut__in=(
                InscriptionPedagogique.Statut.PREVUE,
                InscriptionPedagogique.Statut.VALIDEE,
            ),
        ).select_related('ecue', 'module_participant')
    }

    semestres_ids = (
        maquette.unites_enseignement.order_by('semestre__numero')
        .values_list('semestre_id', flat=True).distinct()
    )

    resultats_semestres = []
    credits_total_acquis = 0
    toutes_ecues_completes = True
    total_credits_attendus = 0

    for sem_id in semestres_ids:
        ues = maquette.unites_enseignement.filter(semestre_id=sem_id).order_by('ordre', 'code')
        resultats_ues = []
        credits_sem_acquis = 0
        credits_sem_presents = 0

        for ue in ues:
            ecues_resultat = []
            paires = []
            for ecue in ue.ecues.filter(archive=False).order_by('ordre', 'code'):
                ip = ips.get(ecue.id)
                if ip is None:
                    # ECUE non suivie par l'étudiant (option non choisie) :
                    # exclue du calcul et de l'exigence de complétude.
                    continue
                moyenne, complet = _moyenne_ecue(
                    ecue, participant, ip.module_participant,
                )
                if moyenne is None:
                    toutes_ecues_completes = False
                ecues_resultat.append({
                    'ecue_id': ecue.id,
                    'code': ecue.code,
                    'intitule': ecue.intitule,
                    'credits': ecue.credits,
                    'coefficient': float(ecue.coefficient),
                    'moyenne': float(moyenne) if moyenne is not None else None,
                    'complete': moyenne is not None,
                })
                if moyenne is not None:
                    paires.append((moyenne, ecue.coefficient))

            moyenne_ue = _ponderee(paires)
            credits_ue = int(ue.credits or 0)
            credits_sem_presents += credits_ue
            total_credits_attendus += credits_ue

            acquise = moyenne_ue is not None and moyenne_ue >= r.seuil
            par_compensation = False
            if moyenne_ue is None:
                acquise = False

            resultats_ues.append({
                'ue_id': ue.id,
                'code': ue.code,
                'intitule': ue.intitule,
                'credits': credits_ue,
                'moyenne': _d(moyenne_ue) if moyenne_ue is not None else None,
                'acquise': acquise,
                'par_compensation': par_compensation,
                'ecues': ecues_resultat,
            })

        # Moyenne pondérée du semestre (UE notées, pondérées par crédits).
        moyenne_sem = _ponderee([
            (ue_r['moyenne'], ue_r['credits']) for ue_r in resultats_ues
        ])

        # Compensation semestrielle : moyenne semestre >= seuil → UE acquises
        # (sauf moyenne UE sous le seuil éliminatoire paramétré).
        compense = False
        if (r.compensation == RegleValidationLMD.Compensation.SEMESTRE
                and moyenne_sem is not None and moyenne_sem >= r.seuil):
            for ue_r in resultats_ues:
                if not ue_r['acquise'] and ue_r['moyenne'] is not None:
                    if r.seuil_elim is not None and float(ue_r['moyenne']) < r.seuil_elim:
                        continue
                    ue_r['acquise'] = True
                    ue_r['par_compensation'] = True
                    compense = True

        credits_sem_acquis = sum(ue_r['credits'] for ue_r in resultats_ues if ue_r['acquise'])
        credits_total_acquis += credits_sem_acquis

        resultats_semestres.append({
            'semestre_id': sem_id,
            'moyenne': _d(moyenne_sem) if moyenne_sem is not None else None,
            'credits_attendus': credits_sem_presents,
            'credits_acquis': credits_sem_acquis,
            'compense': compense,
            'ues': resultats_ues,
        })

    credits_total_acquis += int(credits_capitalises or 0)

    # ── Décision officielle ──────────────────────────────────────────
    # EXCLUSION : au moins une UE est sous le seuil éliminatoire
    # paramétré (`RegleValidationLMD.seuil_elim`). Ce seuil existait déjà
    # dans le référentiel LMD ; on ne crée aucune règle nouvelle, on donne
    # enfin à l'élimination sa traduction décisionnelle officielle.
    # EXCLUSION n'est jamais ramené à AJOURNE.
    ue_eliminee = any(
        r.seuil_elim is not None
        and ue_r['moyenne'] is not None
        and float(ue_r['moyenne']) < r.seuil_elim
        for sem in resultats_semestres
        for ue_r in sem['ues']
    )

    if ue_eliminee:
        decision = 'EXCLUSION'
    elif credits_total_acquis >= maquette.niveau.credits_requis \
            and toutes_ecues_completes:
        decision = 'ADMIS'
    else:
        decision = 'AJOURNE'

    return {
        'participant_id': participant.id,
        'inscription_id': inscription.id,
        'maquette_id': maquette.id,
        'credits_requis': maquette.niveau.credits_requis,
        'credits_capitalises': int(credits_capitalises or 0),
        'credits_acquis': credits_total_acquis,
        'decision_proposee': decision,
        'complet': toutes_ecues_completes,
        'semestres': resultats_semestres,
    }