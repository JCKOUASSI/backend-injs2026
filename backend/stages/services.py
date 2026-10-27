"""Services du lot L5 — workflow de convention de stage et évaluation.

La machine à transitions contrôlée garantit qu'aucune étape n'est sautée ;
le refus exige un motif, la validation jury exige les notes de rapport et
soutenance. Toutes les transitions sont journalisées via ``scolarite.journaliser``
(actions STAGE_*).
"""
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from scolarite.models import journaliser

from .models import ConventionStage, EvaluationStage


# Machine à transitions contrôlée (un seul chemin possible, pas de saut)
TRANSITIONS = {
    ConventionStage.Statut.BROUILLON: {ConventionStage.Statut.SOUMISE},
    ConventionStage.Statut.SOUMISE: {
        ConventionStage.Statut.VALIDEE,
        ConventionStage.Statut.REFUSEE,
        ConventionStage.Statut.BROUILLON,  # retour en brouillon possible
    },
    ConventionStage.Statut.VALIDEE: {ConventionStage.Statut.SIGNEE},
    ConventionStage.Statut.REFUSEE: {ConventionStage.Statut.BROUILLON},
    ConventionStage.Statut.SIGNEE: {ConventionStage.Statut.EN_COURS},
    ConventionStage.Statut.EN_COURS: {ConventionStage.Statut.TERMINEE},
    ConventionStage.Statut.TERMINEE: {ConventionStage.Statut.SOUTENUE},
    ConventionStage.Statut.SOUTENUE: {ConventionStage.Statut.VALIDEE_JURY},
    ConventionStage.Statut.VALIDEE_JURY: {ConventionStage.Statut.ARCHIVEE},
    ConventionStage.Statut.ARCHIVEE: set(),  # terminal
}

# États terminaux (pas de sortie)
ETATS_TERMINAUX = {ConventionStage.Statut.ARCHIVEE}

# États verrouillés : aucune modification libre des données de la convention
ETATS_VERROUILLES = {ConventionStage.Statut.VALIDEE_JURY, ConventionStage.Statut.ARCHIVEE}


def transition_autorisee(convention, cible):
    """Retourne True si la transition courante → cible est autorisée."""
    return cible in TRANSITIONS.get(convention.statut, set())


def appliquer_transition(convention, cible, user, motif_refus=''):
    """Applique une transition contrôlée.

    Pré-conditions :
      - Transition autorisée par la machine à états ;
      - Si cible = REFUSEE : motif_refus obligatoire ;
      - Si cible = VALIDEE : valide_par + date_validation_admin automatiquement datés ;
      - Si cible = VALIDEE_JURY : note_rapport + note_soutension doivent être renseignées
        sur la convention (saisies par l'encadrant interne au préalable) ;
      - Si cible = ARCHIVEE : archive_par + date_archivage automatiques.
    Toutes les transitions sont journalisées.
    """
    cible = (cible or '').strip()
    if cible not in ConventionStage.Statut.values:
        raise ValidationError(f"Statut cible inconnu : {cible!r}.")
    cible_enum = ConventionStage.Statut(cible)
    if cible_enum == convention.statut:
        raise ValidationError("Le statut est déjà à cette valeur.")
    if cible_enum in ETATS_TERMINAUX:
        raise ValidationError(f"Statut terminal : aucune transition depuis {cible_enum.value}.")
    if not transition_autorisee(convention, cible_enum):
        raise ValidationError(
            f"Transition interdite : {convention.statut} → {cible_enum}."
        )

    motif = (motif_refus or '').strip()
    if cible_enum == ConventionStage.Statut.REFUSEE and not motif:
        raise ValidationError({'motif_refus': "Le motif de refus est obligatoire."})
    if cible_enum == ConventionStage.Statut.VALIDEE_JURY:
        if convention.note_rapport is None or convention.note_soutenance is None:
            raise ValidationError(
                "Validation jury : note_rapport et note_soutenance doivent être renseignées."
            )

    with transaction.atomic():
        convention.statut = cible_enum
        if cible_enum == ConventionStage.Statut.SOUMISE:
            convention.date_soumission = timezone.now()
        elif cible_enum == ConventionStage.Statut.VALIDEE:
            convention.date_validation_admin = timezone.now()
            convention.valide_par = user
        elif cible_enum == ConventionStage.Statut.REFUSEE:
            convention.motif_refus = motif
        elif cible_enum == ConventionStage.Statut.SIGNEE:
            convention.date_signature = timezone.now()
        elif cible_enum == ConventionStage.Statut.ARCHIVEE:
            convention.archive_par = user
            convention.date_archivage = timezone.now()
        convention.save()
        journaliser(
            'STAGE_TRANSITION',
            objet=convention,
            acteur=user,
            ancienne_valeur=convention.__class__.Statut(convention.statut).value if False else '',
            nouvelle_valeur=cible_enum.value,
            extra={'cible': cible_enum.value},
        )
    return convention


def enregistrer_notes_stage(convention, note_rapport, note_soutenance, mention, user):
    """Saisie des notes de rapport et soutenance (avant VALIDEE_JURY)."""
    if note_rapport is None or note_soutenance is None:
        raise ValidationError("note_rapport et note_soutenance sont obligatoires.")
    if convention.statut not in (
        ConventionStage.Statut.TERMINEE,
        ConventionStage.Statut.SOUTENUE,
    ):
        raise ValidationError(
            "Les notes de stage ne peuvent être saisies qu'après TERMINEE (ou SOUTENUE)."
        )
    convention.note_rapport = note_rapport
    convention.note_soutenance = note_soutenance
    if mention:
        convention.mention = mention
    convention.save(update_fields=['note_rapport', 'note_soutenance', 'mention'])
    journaliser(
        'STAGE_NOTES',
        objet=convention,
        acteur=user,
        nouvelle_valeur=f'{note_rapport}/{note_soutenance}',
    )
    return convention
    return convention


def calculer_note_finale(evaluation):
    """Calcule la note finale /20 à partir des critères (moyenne simple).

    Convention de pondération : 5 critères équipondérés /20 chacun.
    """
    notes = [
        float(evaluation.note_aptitude or 0),
        float(evaluation.note_integration or 0),
        float(evaluation.note_autonomie or 0),
        float(evaluation.note_production or 0),
        float(evaluation.note_rapport or 0),
    ]
    if any(n > 20 or n < 0 for n in notes):
        raise ValidationError("Toutes les notes doivent être entre 0 et 20.")
    moyenne = sum(notes) / len(notes)
    return round(moyenne, 2)


def enregistrer_evaluation(
    convention, *, note_aptitude=None, note_integration=None, note_autonomie=None,
    note_production=None, note_rapport=None, appreciation_libre='', user=None,
    valider=False,
):
    """Enregistre (ou met à jour) l'évaluation d'une convention de stage.

    - Si ``valider=True`` : calcule la note finale, détermine la mention et
      applique la transition convention → VALIDEE_JURY (avec recopie des
      notes sur la convention pour traçabilité).
    """
    if convention.statut not in (
        ConventionStage.Statut.TERMINEE,
        ConventionStage.Statut.SOUTENUE,
    ):
        raise ValidationError(
            "L'évaluation n'est possible qu'après TERMINEE ou SOUTENUE."
        )
    evaluation, _created = EvaluationStage.objects.update_or_create(
        convention=convention,
        defaults={
            'note_aptitude': note_aptitude,
            'note_integration': note_integration,
            'note_autonomie': note_autonomie,
            'note_production': note_production,
            'note_rapport': note_rapport,
            'appreciation_libre': appreciation_libre,
            'evalue_par': user,
        },
    )

    if valider:
        note_finale = calculer_note_finale(evaluation)
        evaluation.note_finale = note_finale
        if note_finale >= 16:
            evaluation.mention = EvaluationStage.Mention.TRES_BIEN
        elif note_finale >= 14:
            evaluation.mention = EvaluationStage.Mention.BIEN
        elif note_finale >= 12:
            evaluation.mention = EvaluationStage.Mention.ASSEZ_BIEN
        elif note_finale >= 10:
            evaluation.mention = EvaluationStage.Mention.PASSABLE
        else:
            evaluation.mention = EvaluationStage.Mention.INSUFFISANT
        evaluation.valide_par = user
        evaluation.date_validation = timezone.now()
        evaluation.save()
        convention.note_rapport = note_rapport
        convention.note_soutenance = note_finale
        convention.mention = evaluation.mention
        convention.save(update_fields=['note_rapport', 'note_soutenance', 'mention'])
        appliquer_transition(convention, ConventionStage.Statut.VALIDEE_JURY.value, user)
        journaliser(
            'STAGE_EVALUATION_VALIDEE',
            objet=convention, acteur=user,
            nouvelle_valeur=f'{note_finale} ({evaluation.mention})',
        )
    else:
        journaliser(
            'STAGE_EVALUATION_MODIFIEE',
            objet=convention, acteur=user,
            nouvelle_valeur=appreciation_libre[:200] or 'mise à jour',
        )
    return evaluation

