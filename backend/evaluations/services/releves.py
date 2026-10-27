"""L1 — Relevé de notes : projection des résultats officiels.

Le relevé n'est **pas** un second moteur de calcul : il lit les résultats
déjà publiés (`ECUEResult`, `UEResult`, `SemesterResult`) et les décisions
officielles du jury (`jurys.DecisionJury`), puis les projette dans une charge
utile versionnée et empreinte SHA-256 (`services.empreinte`).

Invariant D10 : une décision `EXCLUSION` est reproduite **telle quelle**. Le
relevé ne réinterprète jamais une décision, ne recalcule aucune moyenne, ne
réattribue aucun crédit et ne lit aucune table legacy.
"""

from evaluations.services.empreinte import empreinte, json_canonique


def _resultats(inscription, session):
    """Résultats officiels UE/ECUE de l'inscription pour la session."""
    from evaluations.models import ECUEResult, UEResult

    return (
        list(
            UEResult.objects
            .filter(inscription=inscription, session=session)
            .select_related('ue')
            .order_by('ue__code')
        ),
        list(
            ECUEResult.objects
            .filter(inscription_pedagogique__inscription=inscription,
                    session=session)
            .select_related('ecue', 'ecue__ue')
            .order_by('ecue__code')
        ),
    )


def _lignes_ue(ue_result, ecues):
    """Un UE et ses ECUE, valeurs affichables strictes."""
    return {
        'ue_code': ue_result.ue.code,
        'ue_libelle': ue_result.ue.intitule,
        'credits_ue': ue_result.ue.credits,
        'moyenne': (
            format(ue_result.moyenne, 'f') if ue_result.moyenne is not None else None
        ),
        'statut': ue_result.statut,
        'ecues': [
            {
                'ecue_code': e.ecue.code,
                'ecue_libelle': e.ecue.intitule,
                'credits': e.ecue.credits,
                # Une absence ou une note manquante reste `None` : jamais 0.
                'note': format(e.moyenne, 'f') if e.moyenne is not None else None,
                'bareme': format(e.bareme, 'f') if e.bareme is not None else None,
                'statut': e.statut,
                'dispense': e.avec_dispense,
                'imputation_absence': e.imputation_absence,
            }
            for e in ecues
        ],
    }


def contenu_releve(inscription, session):
    """Charge utile canonique du relevé pour une inscription et une session.

    Ne modifie rien : la fonction est pure et lisible. Deux appels sur les
    mêmes données produisent la MÊME empreinte.
    """
    from evaluations.models import SemesterResult
    from jurys.models import DecisionJury

    ues, ecues = _resultats(inscription, session)
    par_ue = {}
    for e in ecues:
        par_ue.setdefault(e.ecue.ue_id, []).append(e)

    semestres = list(
        SemesterResult.objects
        .filter(inscription=inscription, session=session)
        .select_related('semestre', 'semestre__niveau')
        .order_by('semestre__numero')
    )
    # `DecisionJury` est rattachée à une `SessionJury`, pas à la
    # `SessionEvaluation` : on ne filtre donc pas sur `session`. La décision
    # la plus récente de l'inscription est celle qui fait foi.
    decision = DecisionJury.objects.filter(
        inscription=inscription,
    ).order_by('-decide_le').first()

    return {
        'inscription': inscription.pk,
        'session': session.pk,
        'participant': {
            # Convention du projet (`serializers._identite`) : l'identité est
            # lue sur le `DossierEtudiant`, sans dénormalisation.
            'pk': inscription.etudiant.participant_id,
            'matricule': inscription.etudiant.matricule,
            'nom': inscription.etudiant.participant.nom,
            'prenoms': inscription.etudiant.participant.prenom,
            'nom_complet': inscription.etudiant.nom_complet,
        },
        # Champs réellement portés par `InscriptionAdministrative` : aucun
        # nom de champ n'est supposé.
        'niveau': inscription.niveau.code if inscription.niveau_id else None,
        'formation': getattr(inscription.ref_formation, 'code', None),
        'parcours': getattr(inscription.parcours, 'code', None),
        'vague': getattr(inscription.vague, 'code', None),
        'semestres': [
            {
                'semestre': s.semestre.libelle,
                'niveau': s.semestre.niveau.code,
                'statut': s.statut_semestre,
                'credits_attendus': s.credits_attendus,
                'credits_acquis': s.credits_acquis,
            }
            for s in semestres
        ],
        'unites_enseignement': [
            _lignes_ue(u, par_ue.get(u.ue_id, [])) for u in ues
        ],
        # Décision officielle reproduite telle quelle (EXCLUSION incluse).
        'decision': (
            {
                'valeur': decision.decision,
                'libelle': decision.get_decision_display(),
                'credits_acquis': decision.credits_acquis,
                'moyenne_generale': (
                    format(decision.moyenne_generale, 'f')
                    if decision.moyenne_generale is not None else None
                ),
                'mention': decision.mention,
                'decide_le': (
                    decision.decide_le.isoformat() if decision.decide_le else None
                ),
            }
            if decision is not None else None
        ),
    }


def enregistrer_releve(inscription, session, user=None):
    """Génère puis persiste le relevé (version suivante).

    Le contenu canonique est stocké dans `ReleveNotes.fichier` (JSON UTF-8) :
    le modèle existant porte déjà `fichier`, `sha256` et `version`, aucun
    champ supplémentaire — donc aucune migration — n'est nécessaire.

    Une génération ne réécrit JAMAIS un relevé : elle crée la version suivante.
    """
    from django.core.files.base import ContentFile

    from django.db.models import Max

    from evaluations.models import ReleveNotes

    charge = contenu_releve(inscription, session)
    version = (
        ReleveNotes.objects.filter(inscription=inscription, session=session)
        .aggregate(maximum=Max('version'))['maximum'] or 0
    ) + 1
    empreinte_releve = empreinte(charge)
    releve = ReleveNotes(
        inscription=inscription, session=session, version=version,
        sha256=empreinte_releve, genere_par=user,
    )
    releve.fichier.save(
        f'releve_{inscription.pk}_v{version}.json',
        ContentFile(json_canonique(charge).encode('utf-8')),
        save=False,
    )
    releve.save()
    return releve, charge