"""L2 — Moteur de passage de niveau (projection des résultats officiels).

Ce service ne calcule **aucune moyenne** et **n'invente aucun crédit** : il
agrège les `SemesterResult` déjà produits par le moteur Évaluations et les
décisions officielles du jury, puis applique les seules règles présentes en
base :

* `Semestre.niveau` porte le rattachement S1/S2 → L1, S3/S4 → L2, S5/S6 → L3,
  S7/S8 → M1, S9/S10 → M2 (corpus LMD : 30 ECTS/semestre, 60 ECTS/niveau) ;
* `Niveau.credits_requis` porte le barème à atteindre pour le niveau.

Séparation des responsabilités (D10) :

* ce service calcule une **éligibilité technique** et une **proposition** ;
* la **décision officielle reste au jury** (`jurys.DecisionJury`) ;
* une décision `EXCLUSION` du jury ne peut jamais être contredite par une
  proposition de passage : elle est remontée telle quelle.

Règles non spécifiées, donc NON implémentées :

* compensation entre UE d'un même semestre : le modèle porte `compense`,
  mais aucune règle de compensation n'est spécifiée — le service lit le champ,
  il ne le calcule pas ;
* conditions de redoublement / réorientation : non spécifiées, donc absentes ;
* cumul inter-cursus ou équivalences : non spécifiées, donc absentes.
"""

#: Décisions du jury qui interdisent tout passage automatique.
DECISIONS_BLOQUANTES = ('EXCLUSION',)

#: Statut de semestre exposé par `SemesterResult.statut_semestre`.
STATUT_VALIDE = 'VALIDE'


def _resultats_niveau(inscription, session, niveau):
    """`SemesterResult` du niveau pour une inscription et une session."""
    from evaluations.models import SemesterResult

    return (
        SemesterResult.objects
        .filter(inscription=inscription, session=session, semestre__niveau=niveau)
        .select_related('semestre')
        .order_by('semestre__numero')
    )


def _niveau_suivant(inscription, session):
    """Niveau suivant du plus élevé semestre validé (sinon `None`)."""
    from evaluations.models import SemesterResult
    from scolarite.models import Niveau

    valide = (
        SemesterResult.objects
        .filter(inscription=inscription, session=session,
                statut_semestre=STATUT_VALIDE)
        .select_related('semestre__niveau')
        .order_by('-semestre__niveau__ordre')
        .first()
    )
    if valide is None:
        return None
    return Niveau.objects.filter(
        ordre__gt=valide.semestre.niveau.ordre, actif=True,
    ).order_by('ordre').first()


def passage_niveau(inscription, session, niveau_cible=None):
    """Calcule l'éligibilité technique au passage pour un niveau cible.

    :param inscription: `scolarite.InscriptionAdministrative` concerné.
    :param session: `SessionEvaluation` de référence.
    :param niveau_cible: `scolarite.Niveau` visé ; à défaut, le niveau suivant
        celui du semestre le plus élevé déjà validé.
    :returns: dict d'éligibilité et de proposition, **sans** décision de jury.

    Le résultat est `INDETERMINABLE` tant qu'un semestre du niveau n'a pas de
    résultat : une donnée manquante ne vaut jamais validation (D6/D2).
    """
    from jurys.models import DecisionJury

    if niveau_cible is None:
        niveau_cible = _niveau_suivant(inscription, session)
        if niveau_cible is None:
            return _sortie(
                eligibilite='INDETERMINABLE',
                code='NIVEAU_CIBLE_INCONNU',
                justification=(
                    'Aucun semestre validé ne permet de déterminer un niveau cible.'
                ),
            )

    resultats = list(_resultats_niveau(inscription, session, niveau_cible))
    if not resultats:
        return _sortie(
            niveau=niveau_cible, eligibilite='INDETERMINABLE',
            code='AUCUN_RESULTAT',
            justification=(
                'Aucun résultat de semestre disponible pour ce niveau : '
                'le passage ne peut pas être conclu.'
            ),
        )

    if any(r.statut_semestre == 'EN_ATTENTE' for r in resultats):
        return _sortie(
            niveau=niveau_cible, eligibilite='INDETERMINABLE',
            code='RESULTAT_EN_ATTENTE',
            justification=(
                'Au moins un semestre du niveau est encore en attente : '
                'une donnée manquante ne vaut jamais validation.'
            ),
            resultats=resultats,
        )

    credits_acquis = sum(r.credits_acquis for r in resultats)
    credits_requis = niveau_cible.credits_requis or 0
    non_validates = [r for r in resultats if r.statut_semestre != STATUT_VALIDE]
    # `DecisionJury` est rattachée à une `SessionJury` : on ne filtre donc pas
    # sur la `SessionEvaluation`. La décision la plus récente fait foi.
    decision = DecisionJury.objects.filter(
        inscription=inscription,
    ).order_by('-decide_le').first()

    # Le jury reste maître : une décision bloquante n'est jamais contredite.
    if decision is not None and decision.decision in DECISIONS_BLOQUANTES:
        return _sortie(
            niveau=niveau_cible, eligibilite='BLOQUE',
            code='DECISION_JURY_BLOQUANTE',
            justification=(
                f'Décision officielle du jury : {decision.get_decision_display()} '
                '— aucun passage automatique ne peut être proposé.'
            ),
            resultats=resultats, credits_acquis=credits_acquis,
            credits_requis=credits_requis, decision=decision,
        )

    if non_validates:
        return _sortie(
            niveau=niveau_cible, eligibilite='NON_ELIGIBLE',
            code='SEMESTRE_NON_VALIDE',
            justification=(
                "Un semestre du niveau n'est pas validé : "
                'la validation du niveau n\'est pas acquise.'
            ),
            resultats=resultats, credits_acquis=credits_acquis,
            credits_requis=credits_requis, decision=decision,
        )

    if credits_acquis < credits_requis:
        return _sortie(
            niveau=niveau_cible, eligibilite='NON_ELIGIBLE',
            code='CREDITS_INSUFFISANTS',
            justification=(
                f'{credits_acquis} ECTS acquis pour {credits_requis} requis '
                f'sur le niveau {niveau_cible.code}.'
            ),
            resultats=resultats, credits_acquis=credits_acquis,
            credits_requis=credits_requis, decision=decision,
        )

    return _sortie(
        niveau=niveau_cible, eligibilite='ELIGIBLE',
        code='PASSAGE_ELIGIBLE',
        justification=(
            f'Niveau {niveau_cible.code} complet : '
            f'{credits_acquis}/{credits_requis} ECTS, tous les semestres validés.'
        ),
        resultats=resultats, credits_acquis=credits_acquis,
        credits_requis=credits_requis, decision=decision,
    )


def _sortie(niveau=None, eligibilite='INDETERMINABLE', code='NON_DETERMINE',
            justification='', resultats=None, credits_acquis=None,
            credits_requis=None, decision=None):
    """Charge utile stable du moteur de passage (jamais de décision de jury)."""
    from evaluations.services.empreinte import empreinte

    semestre_details = [
        {
            'semestre': r.semestre.libelle,
            'numero': r.semestre.numero,
            'statut': r.statut_semestre,
            'credits_attendus': r.credits_attendus,
            'credits_acquis': r.credits_acquis,
        }
        for r in (resultats or [])
    ]
    charge = {
        'niveau_cible': niveau.code if niveau is not None else None,
        'eligibilite': eligibilite,
        'code': code,
        'credits_acquis': credits_acquis,
        'credits_requis': credits_requis,
        'semestres': semestre_details,
        'justification': justification,
    }
    return {
        **charge,
        # Décision officielle du jury : lue, jamais produite par ce service.
        'decision_jury': (
            {
                'valeur': decision.decision,
                'libelle': decision.get_decision_display(),
                'decide_le': (
                    decision.decide_le.isoformat() if decision.decide_le else None
                ),
            }
            if decision is not None else None
        ),
        'empreinte': empreinte(charge),
    }