"""Le retrait d'une inscription ne détruit jamais un dossier ou son historique."""
from rest_framework.test import APIClient
from django.test import TestCase

from formations.models import Participant
from scolarite import inscription_services
from scolarite.models import (
    DossierEtudiant, EvenementScolarite, InscriptionAdministrative, JournalScolarite,
)

from .test_inscriptions import ConversionFixture, make_user

BASE = '/api/scolarite/inscriptions/'


class RetraitInscriptionsTests(ConversionFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.acteur)
        participant = Participant.objects.create(matricule='ISOL-001', nom='Test', prenom='Isolé')
        dossier = DossierEtudiant.objects.create(participant=participant)
        self.brouillon = InscriptionAdministrative.objects.create(
            etudiant=dossier, annee_academique=self.annee,
            ref_formation=self.formation, niveau=self.niveau,
        )

    def test_brouillon_isole_supprime_sans_effacer_etudiant_et_avec_audit(self):
        pk = self.brouillon.pk
        dossier_pk = self.brouillon.etudiant_id
        res = self.client.delete(f'{BASE}{pk}/')
        self.assertEqual(res.status_code, 204, res.data)
        self.assertFalse(InscriptionAdministrative.objects.filter(pk=pk).exists())
        self.assertTrue(DossierEtudiant.objects.filter(pk=dossier_pk).exists())
        self.assertTrue(JournalScolarite.objects.filter(
            objet_type='InscriptionAdministrative', objet_id=pk,
            action=JournalScolarite.Action.INSCRIPTION_SUPPRIMEE,
        ).exists())

    def test_lien_cascade_ou_set_null_protege_et_archive(self):
        evenement = EvenementScolarite.objects.create(
            etudiant=self.brouillon.etudiant, inscription=self.brouillon,
            type_evenement=EvenementScolarite.Type.PASSAGE,
        )
        res = self.client.delete(f'{BASE}{self.brouillon.pk}/')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data['archive'])
        self.brouillon.refresh_from_db()
        self.assertEqual(self.brouillon.statut, InscriptionAdministrative.Statut.BROUILLON)
        self.assertTrue(self.brouillon.archive)
        self.assertIsNotNone(self.brouillon.archive_le)
        self.assertTrue(EvenementScolarite.objects.filter(
            pk=evenement.pk, inscription=self.brouillon,
        ).exists())
        self.assertEqual(self.client.get(BASE).data, [])
        self.assertEqual(len(self.client.get(BASE, {'archive': '1'}).data), 1)
        self.assertEqual(self.client.get(f'{BASE}{self.brouillon.pk}/').status_code, 200)
        self.assertEqual(self.client.patch(f'{BASE}{self.brouillon.pk}/', {
            'observations': 'Interdit',
        }).status_code, 409)
        self.assertEqual(self.client.post(f'{BASE}{self.brouillon.pk}/transition/', {
            'statut': 'EN_ATTENTE',
        }).status_code, 409)
        res = self.client.post(f'{BASE}{self.brouillon.pk}/reactiver/')
        self.assertEqual(res.status_code, 200, res.data)
        self.brouillon.refresh_from_db()
        self.assertFalse(self.brouillon.archive)
        self.assertIsNone(self.brouillon.archive_le)
        self.assertTrue(JournalScolarite.objects.filter(
            objet_id=self.brouillon.pk, action=JournalScolarite.Action.INSCRIPTION_REACTIVEE,
        ).exists())

    def test_inscription_validee_conserve_statut_et_admission(self):
        admission = self.admettre()
        validee = inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur, valider=True,
        )
        date_validation = validee.date_validation
        res = self.client.delete(f'{BASE}{validee.pk}/')
        self.assertEqual(res.status_code, 200, res.data)
        validee.refresh_from_db()
        self.assertTrue(validee.archive)
        self.assertEqual(validee.statut, InscriptionAdministrative.Statut.VALIDEE)
        self.assertEqual(validee.admission_id, admission.pk)
        self.assertEqual(validee.date_validation, date_validation)
        self.assertTrue(JournalScolarite.objects.filter(
            objet_id=validee.pk, action=JournalScolarite.Action.INSCRIPTION_ARCHIVEE,
        ).exists())
        # Les bilans historiques ne perdent pas une validation archivée.
        self.assertEqual(self.client.get(BASE + 'stats/').data['inscrits'], 1)

    def test_operations_pedagogiques_et_groupes_refusees_sur_archive(self):
        from scolarite.groupes_services import AffectationImpossible, affecter_groupe
        from scolarite.pedagogie_services import PedagogieImpossible, generer_inscriptions_pedagogiques
        from scolarite.passerelle_services import PasserelleImpossible, synchroniser

        admission = self.admettre()
        inscription = inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur, valider=True,
        )
        inscription_services.supprimer_ou_archiver(inscription.pk, acteur=self.acteur)
        inscription.refresh_from_db()
        with self.assertRaises(PedagogieImpossible):
            generer_inscriptions_pedagogiques(inscription)
        with self.assertRaises(AffectationImpossible):
            affecter_groupe(inscription, None)
        with self.assertRaises(PasserelleImpossible):
            synchroniser(inscription, None)

    def test_inscription_issue_admission_brouillon_est_archivee(self):
        admission = self.admettre()
        brouillon = inscription_services.convertir_admission_en_inscription(admission, acteur=self.acteur)
        res = self.client.delete(f'{BASE}{brouillon.pk}/')
        self.assertEqual(res.status_code, 200, res.data)
        brouillon.refresh_from_db()
        self.assertTrue(brouillon.archive)
        self.assertEqual(brouillon.admission_id, admission.pk)

    def test_retrait_et_reactivation_reserves_aux_roles_autorises(self):
        self.client.force_authenticate(make_user('auditeur_retrait', role='AUDITEUR'))
        self.assertEqual(self.client.delete(f'{BASE}{self.brouillon.pk}/').status_code, 403)
        self.assertEqual(self.client.post(f'{BASE}{self.brouillon.pk}/reactiver/').status_code, 403)
        self.assertTrue(InscriptionAdministrative.objects.filter(pk=self.brouillon.pk).exists())
