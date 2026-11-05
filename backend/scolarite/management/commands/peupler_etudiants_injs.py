"""Cohorte étudiante de démonstration INJS (année courante, niveau L1).

Sans étudiants ni inscriptions administratives, plusieurs écrans de
suivi (Évaluations académiques, listes de notes…) restent vides alors
que le reste du référentiel (maquettes, ECUE, enseignants affectés) est
peuplé. Cette commande crée, de façon idempotente et déterministe :

- un ``Participant`` par étudiant (matricule ``INJS26-####`` stable) ;
- son ``DossierEtudiant`` (statut « Actif » du référentiel) ;
- une ``InscriptionAdministrative`` VALIDEE pour l'année courante, le
  niveau L1 et chaque formation disposant d'une maquette ACTIVE.

Elle ne génère volontairement AUCUNE inscription pédagogique : cette
étape reste l'action explicite et journalisée du service officiel
``generer_inscriptions_pedagogiques`` (consommée par exemple par
``seed_evaluations_demo``). ``--purger`` retire la cohorte créée ici.
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from formations.models import Participant, RefFormation
from scolarite.models import (
    AnneeAcademique, DossierEtudiant, InscriptionAdministrative, Maquette,
    Niveau, StatutEtudiant,
)

ETUDIANTS_PAR_FORMATION = 25
PREFIXE_MATRICULE = 'INJS26-'

NOMS = [
    'Kouassi', 'Koné', 'Touré', 'Diabaté', 'Coulibaly', 'Traoré', 'Cissé',
    'Fofana', 'Bamba', 'Sangaré', 'Yao', 'N’Guessan', 'Koffi', 'Aya',
    'Brou', 'Gnahoré', 'Zokou', 'Diby', 'Kra', 'Assalé', 'Yoboué', 'Séri',
    'Gbagbo', 'Ouattara', 'Bakayoko', 'Kouadio',
]
PRENOMS_F = [
    'Aya', 'Fatou', 'Mariam', 'Adjoua', 'Akissi', 'Nadia', 'Sarah',
    'Grâce', 'Esther', 'Rebecca', 'Sandrine', 'Larissa', 'Manon', 'Aïcha',
]
PRENOMS_M = [
    'Jean', 'Mohamed', 'Ibrahim', 'Serge', 'Franck', 'Wilfried',
    'Ange', 'Boris', 'Cédric', 'Landry', 'Olivier', 'Sékou', 'Moussa',
    'Junior',
]


def _identite(seq):
    """Identité déterministe d'un rang (stable d'une exécution à l'autre)."""
    nom = NOMS[seq % len(NOMS)]
    if seq % 2 == 0:
        return nom, PRENOMS_F[seq % len(PRENOMS_F)], Participant.Sexe.FEMININ
    return nom, PRENOMS_M[seq % len(PRENOMS_M)], Participant.Sexe.MASCULIN


class Command(BaseCommand):
    help = 'Cohorte étudiante de démonstration (L1, année courante).'

    def add_arguments(self, parser):
        parser.add_argument('--purger', action='store_true')
        parser.add_argument(
            '--par-formation', type=int, default=ETUDIANTS_PAR_FORMATION,
        )

    def handle(self, *args, **options):
        if options['purger']:
            participants = Participant.objects.filter(
                matricule__startswith=PREFIXE_MATRICULE,
            )
            dossiers = DossierEtudiant.objects.filter(
                participant__in=participants,
            )
            inscriptions = InscriptionAdministrative.objects.filter(
                etudiant__in=dossiers,
            )
            supprimes = inscriptions.count()
            inscriptions.delete()
            dossiers.delete()
            participants.delete()
            self.stdout.write(self.style.SUCCESS(
                f'Cohorte purgée : {supprimes} inscriptions retirées.',
            ))
            return

        annee = AnneeAcademique.objects.filter(courante=True).first()
        niveau_l1 = Niveau.objects.filter(code='L1').first()
        if annee is None or niveau_l1 is None:
            raise CommandError('Année courante ou niveau L1 manquant.')
        statut_actif = StatutEtudiant.objects.filter(code='ACTIF').first()

        formations = list(
            RefFormation.objects.filter(
                maquettes__annee_academique=annee, maquettes__niveau=niveau_l1,
                maquettes__statut=Maquette.Statut.ACTIVE,
            ).distinct().order_by('intitule'),
        )
        if not formations:
            raise CommandError('Aucune maquette ACTIVE de L1 pour l’année courante.')

        nb = {'participants': 0, 'inscriptions': 0}
        with transaction.atomic():
            seq = 0
            for formation in formations:
                for _ in range(options['par_formation']):
                    seq += 1
                    matricule = f'{PREFIXE_MATRICULE}{seq:04d}'
                    nom, prenom, sexe = _identite(seq)
                    participant, cree = Participant.objects.update_or_create(
                        matricule=matricule,
                        defaults={
                            'nom': nom.upper(), 'prenom': prenom, 'sexe': sexe,
                            'date_naissance': date(2003 + seq % 5, 1 + seq % 12, 1 + seq % 27),
                            'lieu_naissance': 'Abidjan',
                            'email': (
                                f'{prenom}.{nom}@etu.injs.ci'
                                .lower().replace(' ', '').replace('’', '')
                            ),
                        },
                    )
                    nb['participants'] += int(cree)
                    dossier, _ = DossierEtudiant.objects.get_or_create(
                        participant=participant,
                        defaults={'statut': statut_actif},
                    )
                    _, cree_ins = (
                        InscriptionAdministrative.objects.get_or_create(
                            etudiant=dossier, annee_academique=annee,
                            ref_formation=formation, niveau=niveau_l1,
                            statut=InscriptionAdministrative.Statut.VALIDEE,
                            defaults={
                                'type_inscription': (
                                    InscriptionAdministrative.Type.PREMIERE
                                ),
                            },
                        )
                    )
                    nb['inscriptions'] += int(cree_ins)

        self.stdout.write(self.style.SUCCESS(
            f'Cohorte étudiante : {seq} étudiants sur {len(formations)} '
            f'formations L1 ({annee.libelle}) — {nb["participants"]} '
            f'participants créés, {nb["inscriptions"]} inscriptions '
            'administratives VALIDEE créées.',
        ))
