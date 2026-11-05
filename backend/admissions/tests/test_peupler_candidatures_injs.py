"""Couverture massive des candidatures : statuts, fiches complètes, parité."""
from django.core.management import call_command
from django.test import TestCase

from admissions.models import Candidat, Candidature, PieceCandidature
from formations.models import RefFormation
from scolarite.models import AnneeAcademique, Niveau, RegimeEtudes


class PeuplerCandidaturesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_referentiels_admission')
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01',
            date_fin='2027-07-31', courante=True,
        )
        for code, libelle, ordre in [
            ('L1', 'Licence 1', 1), ('L2', 'Licence 2', 2), ('L3', 'Licence 3', 3),
            ('M1', 'Master 1', 4), ('M2', 'Master 2', 5),
        ]:
            Niveau.objects.create(code=code, libelle=libelle, ordre=ordre)
        for code in ('INITIAL', 'CONTINU', 'PROFESSIONNEL', 'ALTERNANCE'):
            RegimeEtudes.objects.create(code=code, libelle=code.title(), actif=True)
        RefFormation.objects.create(
            code='EM-L', intitule='ÉDUCATION ET MOTRICITÉ — LICENCE',
            type_diplome='LICENCE', actif=True,
        )
        RefFormation.objects.create(
            code='EM-M', intitule='ÉDUCATION ET MOTRICITÉ — MASTER',
            type_diplome='MASTER', actif=True,
        )

    def test_couverture_statuts_fiche_et_parite(self):
        call_command('peupler_candidatures_injs', '--par-combo', '1')
        # 5 cases (Licence L1-L3 + Master M1-M2) × 12 statuts = 60 dossiers.
        self.assertEqual(Candidature.objects.count(), 60)
        self.assertEqual(Candidat.objects.count(), 60)
        statuts = set(Candidature.objects.values_list('statut', flat=True))
        self.assertEqual(statuts, set(Candidature.Statut.values))
        # Parité exacte hommes/femmes.
        self.assertEqual(Candidat.objects.filter(sexe='F').count(), 30)
        self.assertEqual(Candidat.objects.filter(sexe='M').count(), 30)
        # Année unique : l'année courante.
        self.assertEqual(
            set(Candidature.objects.values_list('annee_academique_id', flat=True)),
            {self.annee.id},
        )
        # Toutes les zones de la fiche sont remplies.
        dossier = Candidature.objects.exclude(statut='BROUILLON').first()
        self.assertTrue(dossier.candidat.nom)
        self.assertTrue(dossier.candidat.date_naissance)
        self.assertTrue(dossier.candidat.email)
        self.assertTrue(dossier.candidat.telephone)
        self.assertIsNotNone(dossier.ref_formation_id)
        self.assertIsNotNone(dossier.niveau_id)
        self.assertIsNotNone(dossier.type_candidature_id)
        self.assertIsNotNone(dossier.voie_acces_id)
        self.assertIsNotNone(dossier.regime_id)
        self.assertTrue(dossier.observations.startswith('[Exemple] Couverture INJS'))
        # Pièces obligatoires initialisées partout, validées pour les admis.
        self.assertTrue(PieceCandidature.objects.filter(obligatoire=True).exists())
        admis = Candidature.objects.filter(statut='ADMIS').first()
        self.assertTrue(admis.dossier_complet)
        self.assertIsNotNone(admis.score)
        self.assertIsNotNone(admis.date_decision)

    def test_idempotent_puis_purge(self):
        call_command('peupler_candidatures_injs', '--par-combo', '1')
        call_command('peupler_candidatures_injs', '--par-combo', '1')
        self.assertEqual(Candidature.objects.count(), 60)
        call_command('peupler_candidatures_injs', '--purger')
        self.assertEqual(Candidature.objects.count(), 0)
        self.assertEqual(Candidat.objects.count(), 0)
