"""Données d'exemple du module Évaluations (tâche 34).

Garde-fous (notes = données officielles) :
- les notes créées restent en BROUILLON, jamais soumises, validées ou
  verrouillées : elles n'entrent dans aucun résultat officiel ;
- les inscriptions pédagogiques nécessaires sont générées par le
  service OFFICIEL ``generer_inscriptions_pedagogiques`` (action
  explicite et journalisée, conforme à la frontière métier : aucun
  régime automatique n'est activé, le paramètre
  ``INJS_AUTO_INSCRIPTION_PEDAGOGIQUE`` reste False) ;
- participants étiquetés : source MANUEL, motif « [Exemple] … » ;
- sessions [Exemple] jamais verrouillées ; types d'évaluation
  [Exemple] (codes EX-*) : aucun référentiel officiel n'est implicite.
- ``--purger`` retire sessions/évaluations/participants/notes
  d'exemple ; les inscriptions pédagogiques, opération de scolarité
  journalisée, restent acquises.
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from evaluations.models import (
    Evaluation, EvaluationComponent, EvaluationGrade,
    EvaluationParticipant, SessionEvaluation, TypeEvaluation,
)
from formations.models import RefFormation
from scolarite.models import (
    AffectationPedagogique, AnneeAcademique, InscriptionAdministrative,
    InscriptionPedagogique, Maquette, Niveau,
)
from scolarite.pedagogie_services import (
    PedagogieImpossible, generer_inscriptions_pedagogiques,
)

User = get_user_model()
MARQUEUR = '[Exemple]'
ETUDIANTS_PAR_FORMATION = 25
ECUE_PAR_SESSION = 4

TYPES = [
    ('EX-CC', 'Contrôle continu', 'CONTINU'),
    ('EX-TD', 'Devoir de travaux dirigés', 'CONTINU'),
    ('EX-TP', 'Évaluation de travaux pratiques', 'PRATIQUE'),
    ('EX-ET', 'Évaluation terminale', 'TERMINAL'),
]
STATUTS_SESSION = ['OUVERTE', 'PUBLIEE', 'OUVERTE', 'CLOTUREE']


class Command(BaseCommand):
    help = 'Sessions, évaluations et notes brouillons d’exemple.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--purger', action='store_true')

    def handle(self, *args, **options):
        if options['purger']:
            # Evaluation.session est PROTÉGÉ : purge ordonnée explicite.
            sessions = SessionEvaluation.objects.filter(
                libelle__startswith=MARQUEUR,
            )
            evaluations = Evaluation.objects.filter(session__in=sessions)
            EvaluationGrade.objects.filter(
                component__evaluation__in=evaluations,
            ).delete()
            EvaluationParticipant.objects.filter(
                evaluation__in=evaluations,
            ).delete()
            EvaluationComponent.objects.filter(
                evaluation__in=evaluations,
            ).delete()
            evaluations.delete()
            sessions.delete()
            TypeEvaluation.objects.filter(code__startswith='EX-').delete()
            self.stdout.write(self.style.SUCCESS(
                'Purge des évaluations d’exemple terminée (inscriptions '
                'pédagogiques conservées : opération journalisée).'
            ))
            return

        annee = AnneeAcademique.objects.filter(courante=True).first()
        niveau_l1 = Niveau.objects.filter(code='L1').first()
        if annee is None or niveau_l1 is None:
            raise CommandError('Année courante ou niveau L1 manquant.')
        createur = User.objects.filter(is_active=True).order_by('id').first()
        rng = random.Random(20261103)

        # Formations avec maquette ACTIVE en L1 (une session par formation).
        formations = list(
            RefFormation.objects.filter(
                maquettes__annee_academique=annee, maquettes__niveau=niveau_l1,
                maquettes__statut=Maquette.Statut.ACTIVE,
            ).distinct().order_by('intitule')[:8],
        )
        if not formations:
            raise CommandError('Aucune maquette ACTIVE de L1 pour l’année courante.')

        nb = {'sessions': 0, 'evaluations': 0, 'participants': 0, 'notes': 0}
        with transaction.atomic():
            types = {}
            for code, libelle, categorie in TYPES:
                types[code], _ = TypeEvaluation.objects.update_or_create(
                    code=code,
                    defaults={
                        'libelle': f'{MARQUEUR} {libelle}',
                        'categorie': categorie, 'actif': True,
                    },
                )

            for rang, formation in enumerate(formations):
                maquette = Maquette.objects.filter(
                    annee_academique=annee, ref_formation=formation,
                    niveau=niveau_l1, statut=Maquette.Statut.ACTIVE,
                ).order_by('-version').first()
                statut = STATUTS_SESSION[rang % len(STATUTS_SESSION)]
                session, _ = SessionEvaluation.objects.update_or_create(
                    libelle=(
                        f'{MARQUEUR} Session normale S1 — '
                        f'{formation.intitule} ({annee.libelle})'
                    ),
                    defaults={
                        'annee_academique': annee, 'ref_formation': formation,
                        'niveau': niveau_l1, 'semestre': None,
                        'maquette': maquette,
                        'type_session': 'NORMALE', 'statut': statut,
                        'date_debut': date(2026, 12, 7),
                        'date_fin': date(2027, 1, 15),
                        'verrouillee': False, 'creee_par': createur,
                    },
                )
                nb['sessions'] += 1

                # ECUE du premier semestre disposant d'un enseignant affecté.
                affectations = list(
                    AffectationPedagogique.objects.select_related('ecue')
                    .filter(
                        ecue__ue__maquette=maquette,
                        ecue__ue__semestre__numero=1,
                    ).order_by('ecue__code'),
                )
                vues = {}
                for aff in affectations:
                    vues.setdefault(aff.ecue_id, aff)
                affectations = list(vues.values())[:ECUE_PAR_SESSION]

                inscriptions = list(
                    InscriptionAdministrative.objects.filter(
                        annee_academique=annee, ref_formation=formation,
                        niveau=niveau_l1,
                        statut=InscriptionAdministrative.Statut.VALIDEE,
                    ).order_by('id')[:ETUDIANTS_PAR_FORMATION],
                )
                # Génération explicite via le service officiel (journalisée).
                for inscription in inscriptions:
                    try:
                        generer_inscriptions_pedagogiques(
                            inscription, acteur=createur,
                        )
                    except PedagogieImpossible:
                        continue

                statut_eval = 'CLOTUREE' if statut == 'CLOTUREE' else 'PUBLIEE'
                for i, affectation in enumerate(affectations):
                    type_eval = types[TYPES[i % len(TYPES)][0]]
                    evaluation, _ = Evaluation.objects.update_or_create(
                        session=session, ecue=affectation.ecue,
                        type_evaluation=type_eval,
                        defaults={
                            'affectation_pedagogique': affectation,
                            'libelle': (
                                f'{MARQUEUR} {type_eval.libelle.replace(MARQUEUR + " ", "")} '
                                f'— {affectation.ecue.code}'
                            ),
                            'description': (
                                'Évaluation de démonstration : notes '
                                'fictives conservées en brouillon.'
                            ),
                            'bareme': Decimal('20'), 'poids': Decimal('1'),
                            'date_prevue': date(2026, 12, 7) + timedelta(days=i * 7),
                            'statut': statut_eval,
                            'composition_verrouillee': False,
                        },
                    )
                    nb['evaluations'] += 1
                    composant, _ = EvaluationComponent.objects.update_or_create(
                        evaluation=evaluation, code='NOTE',
                        defaults={
                            'libelle': 'Note', 'poids': Decimal('1'),
                            'bareme': Decimal('20'), 'ordre': 1,
                            'obligatoire': True, 'actif': True,
                        },
                    )
                    lignes = InscriptionPedagogique.objects.filter(
                        inscription__in=inscriptions, ecue=affectation.ecue,
                    )
                    for ligne in lignes:
                        participant, _ = (
                            EvaluationParticipant.objects.update_or_create(
                                evaluation=evaluation,
                                inscription_pedagogique=ligne,
                                defaults={
                                    'statut_participation': 'PRESENT',
                                    'source': 'MANUEL',
                                    'motif': (
                                        f'{MARQUEUR} Participant de '
                                        'démonstration.'
                                    ),
                                },
                            )
                        )
                        nb['participants'] += 1
                        _, cree = EvaluationGrade.objects.update_or_create(
                            evaluation_participant=participant,
                            component=composant,
                            defaults={
                                'valeur': Decimal(str(round(rng.uniform(5, 19), 2))),
                                'bareme': Decimal('20'),
                                'statut': 'BROUILLON',
                                'verrouillee': False,
                                'saisie_par': createur,
                            },
                        )
                        nb['notes'] += int(cree)

            if options['dry_run']:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f'Évaluations d’exemple : {nb["sessions"]} sessions, '
            f'{nb["evaluations"]} évaluations, {nb["participants"]} '
            f'participants, {nb["notes"]} notes en BROUILLON '
            '(aucune note validée/verrouillée).',
        ))
