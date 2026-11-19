"""Fondations GET-INJS v2 : calendrier et index sans données réelles."""
from datetime import date, time
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from edts.models import CampagneGeneration, ExecutionCampagne, ExecutionLigne, PeriodeAcademique, RevisionCalendrier
from edts.moteur.calendrier_v2 import (
    dates_semaine, evaluer_periodes, semaine_academique,
)
from edts.moteur.occupation_v2 import (
    IndexOccupation, OccupationHeriteeNonResolue, indexer_affectations, minute,
)
from scolarite.models import AnneeAcademique


class SemaineAcademiqueTests(SimpleTestCase):
    def setUp(self):
        self.annee = SimpleNamespace(date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30))

    def test_53e_semaine_incomplete_et_jour_de_debut_non_lundi(self):
        self.assertEqual(dates_semaine(self.annee, 1), (date(2026, 10, 1), date(2026, 10, 7)))
        self.assertEqual(dates_semaine(self.annee, 53), (date(2027, 9, 30), date(2027, 9, 30)))
        self.assertEqual(semaine_academique(self.annee, date(2027, 9, 30)), 53)

    def test_bornes_et_semaine_hors_annee_refusees(self):
        with self.assertRaises(ValueError):
            semaine_academique(self.annee, date(2027, 10, 1))
        with self.assertRaises(ValueError):
            dates_semaine(self.annee, 54)
        with self.assertRaises(ValueError):
            dates_semaine(self.annee, 0)


class CalendrierConservateurTests(TestCase):
    def setUp(self):
        self.annee = AnneeAcademique.objects.create(
            libelle='2098-2099', date_debut=date(2098, 10, 1), date_fin=date(2099, 9, 30),
            fiabilite='A_RENSEIGNER',
        )
        self.revision = RevisionCalendrier.objects.create(annee_academique=self.annee, numero=1)
        self.groupe = SimpleNamespace(pk=999, annee_academique_id=self.annee.pk,
                                      ref_formation_id=88, niveau_id=77)
        self.jour = date(2098, 10, 5)

    def periode(self, type_, **kwargs):
        p = PeriodeAcademique.objects.create(
            annee_academique=self.annee, revision=self.revision, type=type_,
            date_debut=self.jour, date_fin=self.jour,
            statut_validation=kwargs.pop('statut_validation', 'VALIDEE'),
            fiabilite=kwargs.pop('fiabilite', 'OFFICIEL'),
            source_document=kwargs.pop('source_document', 'Référence fictive pour test'),
            **kwargs,
        )
        return p

    def decision(self, nature='COURS', supplement=()):
        lignes = list(PeriodeAcademique.objects.select_related('revision').all())
        return evaluer_periodes(self.annee, self.groupe, self.jour, nature,
                                [*lignes, *supplement], revision_numero=1)

    def test_absence_de_calendrier_interdit_la_persistance(self):
        self.assertEqual(self.decision().code, 'AUCUNE_PERIODE_VALIDEE')

    def test_cours_valide_puis_fermeture_globale_prime(self):
        self.periode('COURS')
        self.assertTrue(self.decision().autorise)
        self.periode('FERIE')
        self.assertEqual(self.decision().code, 'JOUR_FERME')

    def test_periode_non_confirmee_bloque_meme_avec_cours_valide(self):
        self.periode('COURS')
        self.periode('FERIE', statut_validation='A_CONFIRMER', fiabilite='A_RENSEIGNER',
                     source_document='')
        self.assertEqual(self.decision().code, 'CALENDRIER_NON_VALIDE')

    def test_vacances_ciblees_ne_bloquent_pas_un_autre_groupe(self):
        self.periode('COURS')
        # Objets non persistés : un groupe fictif ne doit pas créer de FK en DB.
        def fermeture(groupe_id):
            return SimpleNamespace(type='VACANCES', portee='GROUPE', groupe_id=groupe_id,
                formation_id=None, niveau_id=None, actif=True,
                annee_academique_id=self.annee.pk, revision=self.revision,
                date_debut=self.jour, date_fin=self.jour,
                statut_validation='VALIDEE', fiabilite='OFFICIEL',
                source_document='Référence fictive pour test')
        self.assertTrue(self.decision(supplement=[fermeture(998)]).autorise)
        self.assertEqual(self.decision(supplement=[fermeture(999)]).code, 'VACANCES')

    def test_meme_portee_contradictoire_requiert_revue(self):
        self.periode('COURS')
        self.periode('VACANCES')
        self.assertEqual(self.decision().code, 'CALENDRIER_AMBIGU')

    def test_examens_ne_permettent_pas_un_cours_ordinaire(self):
        self.periode('EXAMENS')
        self.assertEqual(self.decision().code, 'PERIODE_EXAMENS')
        self.assertTrue(self.decision('EVALUATION').autorise)

    def test_source_et_perimetre_sont_valides_dans_le_modele(self):
        periode = PeriodeAcademique(annee_academique=self.annee, revision=self.revision,
                                    type='COURS', portee='GLOBAL', formation_id=77,
                                    date_debut=self.jour, date_fin=self.jour,
                                    statut_validation='VALIDEE', fiabilite='OFFICIEL')
        with self.assertRaises(ValidationError):
            periode.full_clean()
        periode.formation_id = None
        with self.assertRaises(ValidationError):
            periode.full_clean()  # source absente même si « OFFICIEL » est déclaré
        periode.source_document = 'Référence fictive pour test'
        periode.full_clean()

    def test_contraintes_sql_de_portee_et_dates(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.periode('COURS', portee='GROUPE')  # groupe obligatoire
        with self.assertRaises(IntegrityError), transaction.atomic():
            PeriodeAcademique.objects.create(
                annee_academique=self.annee, revision=self.revision, type='COURS',
                date_debut=date(2099, 1, 2), date_fin=date(2099, 1, 1),
            )

    def test_checkpoint_unique_par_execution_et_cle(self):
        campagne = CampagneGeneration.objects.create(
            annee_academique=self.annee, libelle='Campagne fictive non lancée',
        )
        execution = ExecutionCampagne.objects.create(campagne=campagne, numero=1)
        ExecutionLigne.objects.create(execution=execution, cle_travail='k' * 64,
                                      type_seance='CM', statut='A_REVOIR',
                                      code_contrainte='VOLUME_NON_CONFIRME')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExecutionLigne.objects.create(execution=execution, cle_travail='k' * 64,
                                          type_seance='CM', statut='PLACEE')
        self.assertEqual(ExecutionLigne.objects.count(), 1)


class OccupationDateeTests(SimpleTestCase):
    def setUp(self):
        self.index = IndexOccupation()
        self.jour = date(2098, 10, 5)

    def test_meme_jour_conflits_par_groupe_formateur_salle(self):
        self.assertEqual(self.index.ajouter(self.jour, 480, 600, groupe_id=1,
                                            formateur_id=4, salle_id=8), [])
        self.assertEqual(self.index.conflits(self.jour, 599, 601, groupe_id=1,
                                             formateur_id=4, salle_id=8),
                         ['GROUPE', 'FORMATEUR', 'SALLE'])
        self.assertEqual(self.index.nombre_ressources_dates, 3)
        self.assertEqual(self.index.ajouter(self.jour, 599, 601, groupe_id=2, salle_id=8),
                         ['SALLE'])
        self.assertEqual(self.index.nombre_ressources_dates, 3)  # aucun ajout partiel

    def test_adjacence_et_jours_distincts(self):
        self.index.ajouter(self.jour, 480, 600, groupe_id=1)
        self.assertEqual(self.index.ajouter(self.jour, 600, 660, groupe_id=1), [])
        self.assertEqual(self.index.ajouter(date(2098, 10, 6), 480, 600, groupe_id=1), [])

    def test_refus_des_plages_heritees_et_de_l_arrondi(self):
        with self.assertRaises(OccupationHeriteeNonResolue):
            indexer_affectations([SimpleNamespace(actif=True, date_seance=None)])
        with self.assertRaises(ValueError):
            minute(time(8, 0, 1))
        with self.assertRaises(ValueError):
            self.index.ajouter(self.jour, 600, 600, groupe_id=1)
