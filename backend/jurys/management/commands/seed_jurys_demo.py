"""Données d'exemple du module Jurys (tâche 34).

Idempotent, étiqueté « [Exemple] » (libellé de session) :
- 16 sessions de jury (une par formation, niveaux en rotation) rattachées
  aux maquettes ACTIVE réelles de l'année courante, statuts couvrant tout
  le cycle Préparation → Publié ;
- compositions (président, secrétaire, membres) choisies parmi les
  comptes actifs existants ;
- décisions de démonstration pour les sessions avancées uniquement
  (décision_manuelle avec justification explicite : aucune note réelle,
  aucune exclusion). Les propositions du moteur ECTS ne sont pas
  fabriquées : elles restent le produit du calcul officiel.

``--purger`` supprime les sessions d'exemple et leurs rattachements
(cascade membres/décisions), sans toucher aux inscriptions.
"""
import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from formations.models import RefFormation
from jurys.models import DecisionJury, MembreJury, SessionJury
from scolarite.models import (
    AnneeAcademique, InscriptionAdministrative, Maquette, Niveau, Semestre,
)

User = get_user_model()
MARQUEUR = '[Exemple]'

STATUTS = [
    'PUBLIE', 'VERROUILLE', 'VALIDE', 'PV_GENERE', 'DECISION', 'DECISION',
    'DELIBERATION', 'DELIBERATION', 'CALCUL', 'CALCUL', 'CONTROLE',
    'CONTROLE', 'PREPARATION', 'PREPARATION', 'PREPARATION', 'PUBLIE',
]
AVEC_DECISIONS = {'DECISION', 'PV_GENERE', 'VALIDE', 'VERROUILLE', 'PUBLIE'}
NIVEAUX_ROTATION = ['L3', 'M2', 'L2', 'M1', 'L1']


def _mention(moyenne):
    if moyenne >= Decimal('16'):
        return 'Très bien'
    if moyenne >= Decimal('14'):
        return 'Bien'
    if moyenne >= Decimal('12'):
        return 'Assez bien'
    if moyenne >= Decimal('10'):
        return 'Passable'
    return ''


class Command(BaseCommand):
    help = 'Sessions et décisions de jury d’exemple [Exemple].'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--purger', action='store_true')

    def handle(self, *args, **options):
        if options['purger']:
            SessionJury.objects.filter(
                libelle__startswith=MARQUEUR,
            ).delete()
            self.stdout.write(self.style.SUCCESS(
                'Purge des jurys d’exemple terminée.'
            ))
            return

        annee = AnneeAcademique.objects.filter(courante=True).first()
        if annee is None:
            raise CommandError('Aucune année académique courante.')
        acteurs = list(
            User.objects.filter(is_active=True).order_by('id')[:12],
        )
        if len(acteurs) < 3:
            raise CommandError('Comptes actifs insuffisants pour composer les jurys.')
        createur = acteurs[0]

        niveaux = {n.code: n for n in Niveau.objects.all()}
        rng = random.Random(20261103)
        nb_sessions = nb_membres = nb_decisions = 0

        with transaction.atomic():
            formations = list(
                RefFormation.objects.order_by('intitule'),
            )
            for rang, formation in enumerate(formations[:16]):
                code_niveau = NIVEAUX_ROTATION[rang % len(NIVEAUX_ROTATION)]
                niveau = niveaux.get(code_niveau)
                maquette = Maquette.objects.filter(
                    ref_formation=formation, annee_academique=annee,
                    niveau=niveau, statut=Maquette.Statut.ACTIVE,
                ).first() or Maquette.objects.filter(
                    ref_formation=formation, annee_academique=annee,
                    statut=Maquette.Statut.ACTIVE,
                ).order_by('niveau__ordre').first()
                if maquette is None:
                    continue
                niveau = maquette.niveau
                semestre = Semestre.objects.filter(
                    niveau=niveau,
                ).order_by('numero').first()
                statut = STATUTS[rang % len(STATUTS)]
                libelle = (
                    f'{MARQUEUR} Session normale — {formation.intitule} '
                    f'{niveau.code} ({annee.libelle})'
                )
                session, _ = SessionJury.objects.update_or_create(
                    libelle=libelle,
                    defaults={
                        'annee_academique': annee,
                        'ref_formation': formation, 'parcours': None,
                        'niveau': niveau, 'semestre': semestre,
                        'maquette': maquette,
                        'type_session': SessionJury.TypeSession.NORMALE,
                        'statut': statut, 'creee_par': createur,
                    },
                )
                nb_sessions += 1
                fonctions = ['PRESIDENT', 'SECRETAIRE', 'MEMBRE']
                for i, fonction in enumerate(fonctions):
                    utilisateur = acteurs[(rang * 3 + i) % len(acteurs)]
                    _, cree = MembreJury.objects.update_or_create(
                        session=session, user=utilisateur,
                        defaults={
                            'fonction': fonction, 'ajoute_par': createur,
                        },
                    )
                    nb_membres += int(cree)

                if statut in AVEC_DECISIONS:
                    inscriptions = list(
                        InscriptionAdministrative.objects.select_related(
                            'etudiant__participant',
                        ).filter(
                            annee_academique=annee, ref_formation=formation,
                            niveau=niveau,
                            statut=InscriptionAdministrative.Statut.VALIDEE,
                        ).order_by('id')[:12],
                    )
                    for inscription in inscriptions:
                        participant = inscription.etudiant.participant
                        moyenne = Decimal(
                            str(round(rng.uniform(8.5, 17.5), 2)),
                        )
                        if moyenne >= Decimal('11'):
                            decision, credits = 'ADMIS', 30
                        elif moyenne >= Decimal('10'):
                            decision, credits = 'ADMIS_RESERVES', 24
                        else:
                            decision, credits = 'AJOURNE', 12
                        _, cree = DecisionJury.objects.update_or_create(
                            session=session, inscription=inscription,
                            defaults={
                                'participant': participant,
                                'decision': decision,
                                'credits_acquis': credits,
                                'moyenne_generale': moyenne,
                                'mention': (
                                    _mention(moyenne)
                                    if decision != 'AJOURNE' else ''
                                ),
                                'decision_manuelle': True,
                                'justification': (
                                    f'{MARQUEUR} Décision de démonstration, '
                                    'saisie manuellement sans notes réelles.'
                                ),
                                'decide_par': createur,
                            },
                        )
                        nb_decisions += int(cree)
            if options['dry_run']:
                transaction.set_rollback(True)

        mode = 'seraient créées' if options['dry_run'] else 'prêtes'
        self.stdout.write(self.style.SUCCESS(
            f'Jurys d’exemple ({mode}) : '
            f'{SessionJury.objects.filter(libelle__startswith=MARQUEUR).count()} sessions, '
            f'{MembreJury.objects.filter(session__libelle__startswith=MARQUEUR).count()} membres, '
            f'{DecisionJury.objects.filter(session__libelle__startswith=MARQUEUR).count()} décisions.',
        ))
