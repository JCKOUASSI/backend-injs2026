"""Tests du jeu de données d'exemple ``seed_candidatures_demo``.

La commande doit produire un panorama complet et cohérent du module
(12 statuts de candidature, admissions dans tous les états de décision,
concours classé), être idempotente et entièrement réversible via --purger.
"""

import tempfile
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from admissions.models import (
    Admission, CampagneAdmission, Candidat, Candidature, ClassementConcours,
    Epreuve, NoteConcoursHistorique, NoteConcours, PieceCandidature,
)
from authentication.models import User
from formations.models import Participant, RefCategorie, RefFormation
from scolarite.models import (
    AnneeAcademique, DossierEtudiant, InscriptionAdministrative, Niveau,
)

# Les dépôts de pièces écrivent dans un dossier temporaire, jamais dans
# le MEDIA_ROOT du projet (même convention que test_candidatures.py).
media_temporaire = override_settings(
    MEDIA_ROOT=tempfile.mkdtemp(prefix='test-seed-candidatures-'))

FORMATIONS_REQUISES = [
    ('F01', 'LICENCE'), ('F01', 'MASTER'),
    ('F02', 'LICENCE'), ('F02', 'MASTER'),
    ('F03', 'LICENCE'), ('F03', 'MASTER'),
    ('F04', 'LICENCE'), ('F04', 'MASTER'),
    ('F05', 'LICENCE'), ('F05', 'MASTER'), ('F06', 'LICENCE'),
    ('F07', 'LICENCE'), ('F07', 'MASTER'),
    ('F08', 'LICENCE'), ('F08', 'MASTER'),
]


@media_temporaire
class SeedCandidaturesDemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='admin', password='pass', role='INJS_ADMIN')
        AnneeAcademique.objects.create(
            libelle='2025-2026', date_debut=date(2025, 10, 1),
            date_fin=date(2026, 9, 30), courante=False)
        AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1),
            date_fin=date(2027, 9, 30), courante=True)
        for ordre, code in enumerate(['L1', 'L2', 'L3', 'M1', 'M2'], start=1):
            Niveau.objects.create(code=code, libelle=code, ordre=ordre)
        for filiere, diplome in FORMATIONS_REQUISES:
            RefFormation.objects.create(
                intitule=f'{filiere} — {diplome}',
                filiere_code=filiere, type_diplome=diplome)

    def _seed(self, **options):
        call_command('seed_candidatures_demo', stdout=StringIO(), **options)

    def test_panorama_complet_du_module(self):
        self._seed()

        candidatures = list(Candidature.objects.all())
        self.assertEqual(len(candidatures), 36)
        # Les 12 statuts du workflow sont représentés.
        self.assertEqual(
            {c.statut for c in candidatures},
            set(Candidature.Statut.values),
        )
        # Indicateurs tels que les calcule l'écran Candidatures.
        en_cours = {'SOUMISE', 'EN_ATTENTE_DE_VERIFICATION',
                    'PIECES_INCOMPLETES', 'EN_ETUDE'}
        self.assertEqual(sum(1 for c in candidatures if c.taux_completude == 100), 27)
        self.assertEqual(sum(1 for c in candidatures if c.statut in en_cours), 10)
        self.assertEqual(
            sum(1 for c in candidatures
                if c.statut in ('ADMIS', 'ADMIS_SOUS_RESERVE')), 9)

        # Pièces : des fichiers réels, des refus motivés, une pièce expirée.
        self.assertTrue(
            PieceCandidature.objects.filter(statut='VALIDEE')
            .exclude(fichier='').exists())
        self.assertTrue(
            PieceCandidature.objects.filter(statut='REFUSEE')
            .exclude(commentaire='').exists())
        self.assertTrue(
            PieceCandidature.objects.filter(statut='EXPIREE').exists())

        # Admissions : les 5 décisions sont présentes, dont une annulée
        # (désistement) et une expirée (délai d'inscription dépassé).
        self.assertEqual(Admission.objects.count(), 19)
        self.assertEqual(
            set(Admission.objects.values_list('decision', flat=True)),
            {'ADMIS', 'ADMIS_SOUS_RESERVE', 'EN_ATTENTE', 'REFUSEE', 'ANNULEE'},
        )
        self.assertTrue(any(
            a.est_expiree for a in Admission.objects.filter(decision='ADMIS')))
        # Profils administratifs renseignés (catégorie/grade d'exemple).
        self.assertTrue(Admission.objects.filter(
            categorie__isnull=False, grade__isnull=False).exists())
        # Deux admis sont déjà inscrits : dossier étudiant + matricule.
        inscrites = InscriptionAdministrative.objects.filter(
            admission__isnull=False).exclude(statut__in=('ANNULEE', 'REJETEE'))
        self.assertEqual(inscrites.count(), 2)
        self.assertTrue(all(
            i.etudiant.matricule.startswith('INJS') for i in inscrites))
        # Les décisions prononcées alignent le statut de la candidature
        # et portent une référence + une date limite d'inscription.
        admissions_admis = Admission.objects.filter(
            decision='ADMIS', candidature__statut='ADMIS')
        self.assertEqual(admissions_admis.count(), 7)
        for admission in admissions_admis:
            self.assertTrue(admission.reference_decision)
            self.assertIsNotNone(admission.date_limite_inscription)

        # Campagnes : les 7 états du cycle de vie sont représentés.
        campagnes = CampagneAdmission.objects.all()
        self.assertEqual(campagnes.count(), 7)
        self.assertEqual(
            set(campagnes.values_list('statut', flat=True)),
            set(CampagneAdmission.Statut.values),
        )
        ouverte = campagnes.get(statut='OUVERTE')
        self.assertEqual(ouverte.candidatures.count(), 6)

        # Concours : classement calculé, non publié, trié par score.
        classement = list(
            ClassementConcours.objects.filter(campagne=ouverte).order_by('rang'))
        self.assertEqual(len(classement), 6)
        self.assertTrue(all(not ligne.publie for ligne in classement))
        scores = [ligne.score_total for ligne in classement]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(classement[0].liste, 'ADMISSIBLE')
        self.assertEqual(classement[-1].liste, 'NON_ADMIS')

        # Les 4 types d’épreuves notées sont présents sur la campagne
        # ouverte ; la pratique est en saisie partielle (3 notes) et une
        # correction de note est historisée.
        self.assertEqual(
            set(ouverte.epreuves.values_list('type', flat=True)),
            {'ECRIT', 'PHYSIQUE', 'ORAL', 'PRATIQUE'},
        )
        pratique = ouverte.epreuves.get(type='PRATIQUE')
        self.assertEqual(NoteConcours.objects.filter(epreuve=pratique).count(), 3)
        self.assertTrue(NoteConcoursHistorique.objects.filter(
            note__epreuve__campagne=ouverte).exists())

        # Cohorte précédente : classement PUBLIÉ, campagne clôturée,
        # rangs alignés sur les listes (quota admissibles = 3).
        historique = campagnes.get(statut='CLOTUREE')
        self.assertEqual(historique.candidatures.count(), 6)
        classement_publie = list(ClassementConcours.objects.filter(
            campagne=historique).order_by('rang'))
        self.assertEqual(len(classement_publie), 6)
        self.assertTrue(all(ligne.publie for ligne in classement_publie))
        self.assertEqual(
            [ligne.liste for ligne in classement_publie],
            ['ADMISSIBLE', 'ADMISSIBLE', 'ADMISSIBLE',
             'LISTE_ATTENTE', 'LISTE_ATTENTE', 'NON_ADMIS'],
        )
        self.assertTrue(all(
            epreuve.verrouillee for epreuve in historique.epreuves.all()))

    def test_idempotence(self):
        self._seed()
        instantane = (
            Candidat.objects.count(), Candidature.objects.count(),
            PieceCandidature.objects.count(), Admission.objects.count(),
            CampagneAdmission.objects.count(),
            ClassementConcours.objects.count(),
        )
        self._seed()
        self.assertEqual(instantane, (
            Candidat.objects.count(), Candidature.objects.count(),
            PieceCandidature.objects.count(), Admission.objects.count(),
            CampagneAdmission.objects.count(),
            ClassementConcours.objects.count(),
        ))

    def test_purge_retire_toutes_les_donnees_exemple(self):
        self._seed()
        self.assertEqual(Candidature.objects.count(), 36)

        self._seed(purger=True)
        self.assertEqual(Candidat.objects.count(), 0)
        self.assertEqual(Candidature.objects.count(), 0)
        self.assertEqual(Admission.objects.count(), 0)
        self.assertEqual(CampagneAdmission.objects.count(), 0)
        self.assertEqual(PieceCandidature.objects.count(), 0)
        # La chaîne d'inscription des admis convertis est aussi retirée,
        # ainsi que les catégories/grades d'exemple.
        self.assertEqual(InscriptionAdministrative.objects.count(), 0)
        self.assertEqual(DossierEtudiant.objects.count(), 0)
        self.assertEqual(Participant.objects.count(), 0)
        self.assertEqual(RefCategorie.objects.count(), 0)
