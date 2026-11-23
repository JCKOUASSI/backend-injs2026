"""C2 — Moteur de préparation d'un résultat.

Séparation stricte des responsabilités (mission §13) : ce module fait de
la **collecte** et de la **traçabilité**. Il ne valide pas, ne décide pas,
ne verrouille pas.

Ce que le moteur fait, sans aucune règle inventée :
    * collecte les notes dans un ordre canonique ;
    * expose le quotient valeur/barème de chaque composant (arithmétique,
      pas une règle) ;
    * signale les absences, dispenses et notes manquantes SANS jamais les
      convertir en valeur ;
    * capture un instantané immuable de la règle déclarée ;
    * calcule une empreinte SHA-256 reproductible ;
    * liste les diagnostics rattachés aux décisions métier à valider.

Ce que le moteur ne fait PAS, tant que D1/D2/D3/D5/D6/D10/D15 ne sont pas
validées : produire une moyenne, un statut d'acquis, une éligibilité au
rattrapage ou une décision de jury. Aucune écriture en base n'est faite
ici : la préparation est une projection, pas une persistance.
"""
from decimal import Decimal

from .diagnostics import BLOQUANTS, diagnostic
from .empreinte import empreinte

#: Version du schéma de préparation. Toute évolution incompatible doit
#: changer cette valeur : une empreinte n'est comparable qu'à schéma égal.
PREPARATION_SCHEMA_VERSION = 'c2.preparation.v1'

#: Version de formule. Elle n'est PAS un choix : elle désigne la formule
#: déjà implémentée et validée par le moteur LMD du projet
#: (``scolarite.validation_services``) :
#:     quotient  = note × 20 / barème        (convention D20 du projet)
#:     moyenne   = Σ(quotient × poids) / Σ(poids)   (poids > 0, cf. _ponderee)
#: Un écart de cette version signale un changement de formule.
FORMULE_VERSION = 'LMD.2026.1'

#: Barème de référence du projet (D20 de validation_services).
BAREME_REFERENCE = Decimal('20')

#: Arrondi du projet (convention ``_d`` de validation_services).
ARRONDI = Decimal('0.01')

#: Statuts signifiant « le candidat n'a pas passé ».
STATUTS_ABSENCE = ('ABSENT', 'ABSENT_JUSTIFIE', 'ABSENT_INJUSTIFIE')

#: Décision d'imputation d'absence : jamais prise ici (D2).
IMPUTATION_ABSENCE = 'NON_DECIDEE'


def _composants(evaluation):
    """Composants dans l'ordre canonique (ordre, puis id)."""
    return list(
        evaluation.components.filter(actif=True).order_by('ordre', 'id'),
    )


def _notes_par_composant(participant):
    """Note connue par composant."""
    notes = {}
    for note in participant.notes.select_related('component').order_by('id'):
        notes[note.component_id] = note
    return notes


def _absent(participant):
    """Constat d'absence — jamais converti en valeur."""
    return participant.statut_participation in STATUTS_ABSENCE


def _absences_emargement(participant):
    """Présences d'émargement constatant une absence (informatif)."""
    return [
        presence.statut for presence in participant.presences.all()
        if presence.statut in STATUTS_ABSENCE
    ]


#: Règle D2 (validée pour le lot C2.3) : une absence ACADÉMIQUE rend la
#: composante NON NOTÉE. Elle ne produit jamais de note et jamais de 0 :
#: l'ECUE devient non calculable par la règle D6. La distinction
#: justifié / non justifié est disciplinaire : aucune différence
#: académique. Ce statut est sans rapport avec la présence aux séances,
#: le badgeage, le QR ou la géolocalisation.
REGLE_ABSENCE_ACADEMIQUE = 'COMPOSANTE_NON_NOTEE'

#: Statuts treated comme « composante non notée » : les absences
#: académiques et la dispense (composante non applicable).
STATUTS_COMPOSANTE_NON_NOTEE = STATUTS_ABSENCE + ('DISPENSE',)

#: Règle D3 : le moteur NE RETIENT aucune note automatiquement tant que la
#: règle de substitution (remplace / si supérieure / conserve) n'est pas
#: déclarée par la scolarité. Les deux notes restent consultables.
REGLE_SUBSTITUTION = 'NON_DECLAREE'


def _composante_non_notee(participant):
    """Vrai si la composante doit être considérée comme non notée (D2)."""
    return participant.statut_participation in STATUTS_COMPOSANTE_NON_NOTEE


def _regle_lmd(maquette):
    """Règle de validation **déclarée par la scolarité** (D1, D5, D6).

    Seuil, compensation et crédits sont LUS dans
    ``scolarite.RegleValidationLMD`` via la fonction existante ``regle_pour`` :
    le moteur C2 n'invente aucun seuil et n'applique aucun repli. Sans règle
    déclarée, il reste muet (diagnostic ``REGLE_ABSENTE``).
    """
    from scolarite.validation_services import regle_pour

    return regle_pour(maquette)


def _instantane_lmd(regle_lmd):
    """Photographie de la règle LMD effectivement appliquée."""
    if regle_lmd is None:
        return None
    return {
        'regle_id': regle_lmd.pk,
        'ref_formation': regle_lmd.ref_formation_id,
        'niveau': regle_lmd.niveau_id,
        'seuil_admission': float(regle_lmd.seuil_admission),
        'seuil_elim': (
            float(regle_lmd.seuil_elim)
            if regle_lmd.seuil_elim is not None else None
        ),
        'compensation': regle_lmd.compensation,
        'credits_semestre': int(regle_lmd.credits_semestre),
        'capitalisation': bool(regle_lmd.capitalisation_activee),
    }


def _moyenne_ponderee(lignes):
    """Moyenne pondérée du projet : Σ(v×p)/Σ(p), poids strictement > 0.

    Aucune valeur de repli : sans paire exploitable, la fonction renvoie
    ``None`` — une absence ou une note manquante ne vaut jamais 0.
    """
    paires = [
        (Decimal(str(ligne['valeur'])), Decimal(ligne['poids']))
        for ligne in lignes
        if ligne['valeur'] is not None and Decimal(ligne['poids']) > 0
    ]
    if not paires:
        return None
    total_poids = sum((p for _, p in paires), Decimal('0'))
    if total_poids <= 0:
        return None
    moyenne = sum((v * p for v, p in paires), Decimal('0')) / total_poids
    return moyenne.quantize(ARRONDI)


def _iso(valeur):
    """Date en ISO 8601, qu'elle vienne du modèle ou d'une saisie brute."""
    if valeur is None:
        return None
    isoformat = getattr(valeur, 'isoformat', None)
    return isoformat() if callable(isoformat) else str(valeur)


def _instantane(regle_version):
    """Copie immuable de la règle : une modification ultérieure ne doit
    pas réécrire le passé d'une préparation déjà affichée."""
    if regle_version is None:
        return None
    return {
        'regle_id': regle_version.regle_id,
        'code': regle_version.regle.code,
        'categorie': regle_version.regle.categorie,
        'version': regle_version.version,
        'date_effet': _iso(regle_version.date_effet),
        'date_fin': _iso(regle_version.date_fin),
        'parametres': dict(regle_version.parametres or {}),
    }


def preparer(participant, regle_version=None):
    """Prépare (sans l'exécuter) le calcul d'un résultat ECUE.

    :param participant: ``EvaluationParticipant`` visé.
    :param regle_version: ``RegleCalculVersion`` déclarée par la scolarité ;
        à défaut, la version figée sur la session est reprise. Si aucune
        n'existe, le moteur reste muet et le signale.
    :return: dict sérialisable (projet de résultat, sans moyenne).
    """
    evaluation = participant.evaluation
    session = evaluation.session
    regle = regle_version or session.regle_version
    composants = _composants(evaluation)
    notes = _notes_par_composant(participant)
    absences_emargement = _absences_emargement(participant)

    lignes = []
    manquants = []
    # D2 : une absence académique (ou une dispense) rend TOUTE composante
    # non notée. Aucune note existante n'est alors retenue : elle reste
    # historisée, mais n'entre pas dans le calcul (jamais convertie en 0).
    non_notee = _composante_non_notee(participant)
    for composant in composants:
        note = None if non_notee else notes.get(composant.pk)
        valeur = note.valeur if note is not None else None
        bareme = composant.bareme
        quotient = None
        if valeur is not None and bareme:
            # Arithmétique seule : le rapport n'est pas une règle métier.
            quotient = float(
                (Decimal(valeur) / Decimal(bareme)).quantize(Decimal('0.000001')),
            )
        if valeur is None and composant.obligatoire:
            manquants.append(composant.code)
        lignes.append({
            'composant_id': composant.pk,
            'code': composant.code,
            'libelle': composant.libelle,
            'poids': str(composant.poids),
            'bareme': str(bareme),
            'obligatoire': composant.obligatoire,
            'valeur': None if valeur is None else float(valeur),
            'quotient': quotient,
            'note_id': note.pk if note is not None else None,
            'statut_note': note.statut if note is not None else 'ABSENTE',
            'absent': _absent(participant) or bool(absences_emargement),
        })

    # D2 : la règle étant appliquée, AUCUNE imputation n'est réalisée.
    # L'absence produit une composante non notée (puis D6), jamais un 0.
    imputation_absence = False
    snapshot = _instantane(regle)
    regle_lmd = _regle_lmd(session.maquette)
    instantane_lmd = _instantane_lmd(regle_lmd)

    # ── Composition (D5) ───────────────────────────────────────────────
    # Les poids sont une DONNÉE (composants). Le blocage ne subsiste que
    # si aucun poids exploitable n'est déclaré : on n'invente ni 50/50 ni
    # aucune pondération par défaut.
    poids_declares = any(
        Decimal(ligne['poids']) > 0 for ligne in lignes
    )

    diagnostics = []
    if regle_lmd is None:
        diagnostics.append(diagnostic('REGLE_ABSENTE'))
    if not poids_declares:
        diagnostics.append(diagnostic('COMPOSITION_NON_DECLAREE'))
    if manquants:
        diagnostics.append(diagnostic('COMPOSANT_MANQUANT', {'composants': manquants}))

    # ── Agrégation (D1/D5/D6) ─────────────────────────────────────────
    # La moyenne n'est produite que si TOUT est établi : règle déclarée,
    # poids déclarés, aucun composant obligatoire manquant, aucune absence
    # à imputer. Elle reste une projection : rien n'est persisté (D10).
    moyenne = None
    if not diagnostics:
        # Les valeurs sont ramenées sur l'échelle /20 (convention D20).
        echelle = [
            dict(ligne, valeur=(
                Decimal(str(ligne['valeur'])) * BAREME_REFERENCE / Decimal(ligne['bareme'])
            ))
            for ligne in lignes if ligne['valeur'] is not None
        ]
        moyenne = _moyenne_ponderee(echelle)

    # ── Instantanés de règle ──────────────────────────────────────────
    # Les DEUX règles sont conservées : la règle générique du socle
    # (RegleCalculVersion, paramétrage fin) et la règle LMD institutionnelle
    # (RegleValidationLMD : seuil, compensation, crédits). L'empreinte les
    # couvre toutes les deux : changer le seuil change l'empreinte.
    charge = {
        'schema_version': PREPARATION_SCHEMA_VERSION,
        'formule_version': FORMULE_VERSION,
        'evaluation_id': evaluation.pk,
        'session_id': session.pk,
        'participant_id': participant.pk,
        'regle_snapshot': snapshot,
        'regle_lmd': instantane_lmd,
        'composants': lignes,
        'complet': not manquants,
        'imputation_absence': imputation_absence,
        'imputation_absence_decision': IMPUTATION_ABSENCE,
    }

    return {
        'schema_version': PREPARATION_SCHEMA_VERSION,
        'formule_version': FORMULE_VERSION,
        'evaluation_id': evaluation.pk,
        'session_id': session.pk,
        'participant_id': participant.pk,
        'statut_participation': participant.statut_participation,
        'regle_snapshot': snapshot,
        'regle_lmd': instantane_lmd,
        'composants': lignes,
        'complet': not manquants,
        'avec_dispense': participant.statut_participation == 'DISPENSE',
        'imputation_absence': imputation_absence,
        'imputation_absence_decision': IMPUTATION_ABSENCE,
        'regle_absence': REGLE_ABSENCE_ACADEMIQUE,
        'composante_non_notee': non_notee,
        # La moyenne n'existe que si toutes les règles établies sont
        # réunies ; sinon None — jamais 0 par défaut.
        'moyenne': None if moyenne is None else float(moyenne),
        'calculable': moyenne is not None and not diagnostics,
        'diagnostics': diagnostics,
        'empreinte': empreinte(charge),
    }


#: Les blocages connus, exposés pour l'API et la documentation.
BLOCAGES_CONNUS = tuple(sorted(BLOQUANTS))
def eligibilite_rattrapage(participant, preparation):
    """D15 — Éligibilité technique au rattrapage (calcul, jamais décision).

    Éligible SI ET SEULEMENT SI :
      1. la session est NORMALE (l'éligibilité se juge sur la session
         d'origine, pas sur une session de rattrapage) ;
      2. un résultat est calculé (moyenne disponible) ;
      3. ce résultat est strictement inférieur au seuil LMD déclaré (D1) ;
      4. aucune donnée manquante : absence académique ou composante
         obligatoire non notée.

    Toute condition non satisfaite, et toute donnée manquante, rend
    l'étudiant NON éligible : une absence d'information n'est jamais
    interprétée comme une condition remplie.

    Cette fonction ne modifie pas ``eligible_rattrapage`` : elle calcule.
    Elle n'énonce aucune décision de jury (D10).
    """
    motifs = []
    session = participant.evaluation.session
    if session.type_session != 'NORMALE':
        motifs.append('SESSION_NON_NORMALE')
    moyenne = preparation.get('moyenne')
    if moyenne is None:
        motifs.append('DONNEE_MANQUANTE')
    seuil = (preparation.get('regle_lmd') or {}).get('seuil_admission')
    if seuil is None:
        motifs.append('REGLE_ABSENTE')
    if moyenne is not None and seuil is not None and moyenne >= seuil:
        motifs.append('MOYENNE_SUP_OU_EQUALE_AU_SEUIL')
    return {
        'eligible': not motifs,
        'motifs': motifs,
        'seuil': seuil,
        'moyenne': moyenne,
        'participant_id': participant.pk,
        'regle': 'LMD.SOUS_SEUIL_ET_SANS_DONNEE_MANQUANTE',
    }


#: Valeurs AUTORISÉES pour la règle de substitution du rattrapage (D3).
#: La valeur par défaut reste ``NON_DECLAREE`` : aucune de ces règles n'est
#: activée tant que la scolarité n'a pas explicitement déclaré une version
#: de la famille ``RATTRAPAGE`` dans ``RegleCalculVersion.parametres``.
REGLES_SUBSTITUTION = (
    'NON_DECLAREE',
    'REMPLACEMENT_SYSTEMATIQUE',
    'MEILLEURE_NOTE',
    'CONSERVATION_SEPAREE',
)

#: Code de la famille de règle portant la substitution (cf. RegleCalcul).
FAMILLE_SUBSTITUTION = 'RATTRAPAGE'

#: Paramètre JSON qui porte la valeur déclarée.
PARAMETRE_SUBSTITUTION = 'substitution'


def regle_substitution(regle_version=None):
    """Règle de substitution **déclarée par la scolarité** (D3).

    Le service ne décide rien : il ne fait que lire la valeur déclarée dans
    ``RegleCalculVersion.parametres['substitution']`` de la famille
    ``RATTRAPAGE``. Toute valeur absente, inactive ou hors nomenclature
    ramène à ``NON_DECLAREE`` — donc à l'absence de substitution.

    Aucune valeur n'est déduite : ni ``MEILLEURE_NOTE`` ni
    ``REMPLACEMENT_SYSTEMATIQUE`` ne sont des valeurs de repli.
    """
    if regle_version is None:
        return REGLE_SUBSTITUTION
    # La famille doit être active : une règle retirée ne s'applique pas.
    if not getattr(regle_version.regle, 'actif', False):
        return REGLE_SUBSTITUTION
    valeur = (regle_version.parametres or {}).get(PARAMETRE_SUBSTITUTION)
    if valeur in REGLES_SUBSTITUTION and valeur != REGLE_SUBSTITUTION:
        return valeur
    return REGLE_SUBSTITUTION


def comparer_rattrapage(
    preparation_origine, preparation_rattrapage, regle_version=None,
):
    """D3 — Rapproche des deux sessions SANS rien écraser.

    L'historique est append-only : la note d'origine et la note de
    rattrapage sont toutes deux restituées. La note retenue n'est calculée
    que si la scolarité a DÉCLARÉ une règle autorisée ; sinon elle reste
    ``None`` (aucune substitution implicite, aucune moyenne des deux).

        note_initiale   ─┐
                         ├── REGLE_SUBSTITUTION ──> note_retenue
        note_rattrapage ─┘
    """
    regle = regle_substitution(regle_version)
    initiale = preparation_origine.get('moyenne')
    rattrapage = preparation_rattrapage.get('moyenne')

    retenue = None
    if regle == 'REMPLACEMENT_SYSTEMATIQUE':
        retenue = rattrapage
    elif regle == 'MEILLEURE_NOTE':
        notes = [n for n in (initiale, rattrapage) if n is not None]
        # Un 0 reste une note : seule l'absence est écartée.
        retenue = max(notes) if notes else None
    elif regle == 'CONSERVATION_SEPAREE':
        retenue = None

    return {
        'note_initiale': initiale,
        'note_rattrapage': rattrapage,
        'note_retenue': retenue,
        'regle_substitution': regle,
        'regle_declaree': regle_version.pk if regle_version else None,
        'empreinte_initiale': preparation_origine.get('empreinte'),
        'empreinte_rattrapage': preparation_rattrapage.get('empreinte'),
    }