"""Données d'exemple du module Diplômation (tâche 34).

Idempotent. Règles de prudence (diplômes = documents à valeur
probante) :
- les diplômes créés restent en BROUILLON ou EN ATTENTE DE VALIDATION :
  jamais VALIDATED, donc le portail public de vérification ne peut pas
  les présenter comme authentiques ;
- numéros uniques déterministes (uuid5 d'un namespace « exemple ») :
  reconnaissance et purge précises ;
- rattachement aux décisions de jury d'exemple lorsqu'elles existent
  (même génération de données), aucun PDF fabriqué ;
- gabarits de documents [Exemple] sans fichier ; registre annuel
  ouvert (non clôturé) de l'année courante.

``--purger`` retire diplômes d'exemple, gabarits et le registre s'il ne
contient plus que des exemples.
"""
import uuid

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from graduation.models import Diplome, ModeleDocument, RegistreDiplomes
from jurys.models import DecisionJury
from scolarite.models import AnneeAcademique, InscriptionAdministrative

User = get_user_model()
NS_EXEMPLE = uuid.UUID('20261103-2026-4110-8000-4459504c4f4d')
MARQUEUR = '[Exemple]'
CAP = 60


def numero(etudiant_id, formation_id, niveau_id):
    return uuid.uuid5(
        NS_EXEMPLE, f'diplome-exemple-{etudiant_id}-{formation_id}-{niveau_id}',
    )


GABARITS = [
    ('DIPLOME', 'Gabarit diplôme licence et master'),
    ('ATTESTATION', 'Gabarit attestation de réussite'),
    ('CERTIFICAT', 'Gabarit certificat de scolarité'),
    ('RELEVE_NOTES', 'Gabarit relevé de notes semestriel'),
]


class Command(BaseCommand):
    help = 'Diplômes et gabarits d’exemple (jamais validés).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--purger', action='store_true')

    def handle(self, *args, **options):
        if options['purger']:
            self._purger()
            return
        annee = AnneeAcademique.objects.filter(courante=True).first()
        if annee is None:
            raise CommandError('Aucune année académique courante.')
        createur = User.objects.filter(is_active=True).order_by('id').first()

        inscriptions = list(
            InscriptionAdministrative.objects.filter(
                annee_academique=annee,
                statut=InscriptionAdministrative.Statut.VALIDEE,
                niveau__code__in=('L3', 'M2'),
            ).order_by('ref_formation__intitule', 'id'),
        )
        decisions = {}
        for decision in DecisionJury.objects.select_related('inscription').filter(
            inscription_id__in=[i.id for i in inscriptions],
        ):
            if decision.decision in ('ADMIS', 'ADMIS_RESERVES'):
                decisions[decision.inscription_id] = decision

        # Priorité aux étudiants ayant une décision d'exemple, puis
        # échantillon régulier des autres fin-de-cycle.
        avec = [i for i in inscriptions if i.id in decisions]
        sans = [i for i in inscriptions if i.id not in decisions]
        pas = max(1, len(sans) // max(1, CAP - len(avec)))
        choisis = avec + sans[::pas]
        choisis = choisis[:CAP]

        with transaction.atomic():
            registre, _ = RegistreDiplomes.objects.get_or_create(
                annee_academique=annee,
            )
            livres = []
            for rang, inscription in enumerate(choisis):
                decision = decisions.get(inscription.id)
                diplome, _ = Diplome.objects.update_or_create(
                    numero_unique=numero(
                        inscription.etudiant_id,
                        inscription.ref_formation_id,
                        inscription.niveau_id,
                    ),
                    defaults={
                        'etudiant': inscription.etudiant,
                        'annee_academique': annee,
                        'ref_formation': inscription.ref_formation,
                        'parcours': None,
                        'niveau': inscription.niveau,
                        'session_jury': decision.session if decision else None,
                        'decision_jury': decision,
                        'mention': decision.mention if decision else '',
                        'credits_acquis': (
                            decision.credits_acquis if decision else 0
                        ),
                        'statut': (
                            Diplome.Statut.VALIDATION_PENDING
                            if rang % 2 == 0 else Diplome.Statut.BROUILLON
                        ),
                        'cree_par': createur,
                    },
                )
                livres.append(diplome)
            registre.diplomes.add(*livres)

            for type_doc, libelle in GABARITS:
                ModeleDocument.objects.update_or_create(
                    type=type_doc, formation=None,
                    libelle=f'{MARQUEUR} {libelle}',
                    defaults={'actif': True, 'modifie_par': createur},
                )

            if options['dry_run']:
                transaction.set_rollback(True)

        compte = Diplome.objects.filter(
            numero_unique__in=[
                numero(i.etudiant_id, i.ref_formation_id, i.niveau_id)
                for i in choisis
            ],
        ).count()
        self.stdout.write(self.style.SUCCESS(
            f'Diplômation d’exemple : {compte} diplômes non validés '
            f'(fin de cycle), '
            f'{ModeleDocument.objects.filter(libelle__startswith=MARQUEUR).count()} gabarits, '
            f'registre {annee.libelle} ouvert.',
        ))

    def _purger(self):
        ids = [
            numero(ia.etudiant_id, ia.ref_formation_id, ia.niveau_id)
            for ia in InscriptionAdministrative.objects.filter(
                niveau__code__in=('L3', 'M2'),
            )
        ]
        with transaction.atomic():
            Diplome.objects.filter(
                numero_unique__in=ids,
                statut__in=(
                    Diplome.Statut.BROUILLON,
                    Diplome.Statut.VALIDATION_PENDING,
                ),
            ).delete()
            ModeleDocument.objects.filter(
                libelle__startswith=MARQUEUR,
            ).delete()
            for registre in RegistreDiplomes.objects.all():
                if registre.diplomes.count() == 0 and not registre.cloture:
                    registre.delete()
        self.stdout.write(self.style.SUCCESS(
            'Purge diplômation d’exemple terminée.'
        ))
