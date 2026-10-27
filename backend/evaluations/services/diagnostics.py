"""C2 — Diagnostics : ce qui empêche un résultat, et sur quelle décision.

Le moteur ne « choisit » rien : il **constate** qu'un élément manque et
rattache ce constat à la décision métier qui devra trancher. Aucun de ces
codes n'a de conséquence académique tant que la décision correspondante
n'est pas validée.

Correspondance (contrat B.1 §17) :
    D1  seuil de validation      D2  absence -> valeur
    D3  composition rattrapage   D5  granularité/poids des composants
    D6  composant obligatoire    D10 gouvernance pédagogique / jury
    D15 éligibilité rattrapage
"""
#: Les sept décisions métier bloquantes, référencées partout ailleurs.
DECISIONS = ('D1', 'D2', 'D3', 'D5', 'D6', 'D10', 'D15')

#: Description d'un point bloquant. ``decision`` désigne la décision
#: métier qui doit trancher ; ``consequence`` ce que le moteur s'interdit
#: de faire en attendant.
BLOQUANTS = {
    'REGLE_ABSENTE': {
        'decision': 'D5',
        'message': "Aucune règle de calcul déclarée pour ce périmètre.",
        'consequence': "Aucune moyenne n'est produite.",
    },
    'COMPOSITION_NON_DECLAREE': {
        'decision': 'D5',
        'message': "La somme et la pondération des composants ne sont pas définies.",
        'consequence': "Les quotients sont exposés, mais pas agrégés.",
    },
    'COMPOSANT_MANQUANT': {
        'decision': 'D6',
        'message': "Un composant obligatoire n'a pas de note.",
        'consequence': "Aucune conséquence académique n'est déduite.",
    },
    'ABSENCE_NON_TRAITEE': {
        'decision': 'D2',
        'message': "Une absence est constatée et sa conversion n'est pas définie.",
        'consequence': "Aucune valeur n'est substituée à l'absence.",
    },
    'SEUIL_NON_DECLARE': {
        'decision': 'D1',
        'message': "Le seuil de validation n'est pas déclaré par une règle.",
        'consequence': "Aucune mention d'acquis/non acquis n'est émise.",
    },
    'RATTRAPAGE_NON_DECLARE': {
        'decision': 'D3',
        'message': "La composition du rattrapage n'est pas déclarée.",
        'consequence': "Aucune session de rattrapage n'est calculée.",
    },
    'GOUVERNANCE_NON_DECLAREE': {
        'decision': 'D10',
        'message': "La gouvernance pédagogique / jury n'est pas déclarée.",
        'consequence': "Aucun résultat calculé n'est transformé en décision.",
    },
    'ELIGIBILITE_NON_DECLAREE': {
        'decision': 'D15',
        'message': "Les conditions d'éligibilité au rattrapage ne sont pas déclarées.",
        'consequence': "Le champ reste non renseigné.",
    },
}


def diagnostic(code, detail=None):
    """Construit un diagnostic sérialisable à partir d'un code connu."""
    base = BLOQUANTS[code]
    return {
        'code': code,
        'decision': base['decision'],
        'message': base['message'],
        'consequence': base['consequence'],
        'detail': detail,
    }


def decisions_concernees(diagnostics):
    """Décisions distinctes visées par une liste de diagnostics."""
    return sorted({d['decision'] for d in diagnostics})