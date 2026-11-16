"""Validation groupée : même workflow qu'une inscription, transaction unique."""
from django.test import TestCase
from rest_framework.test import APIClient

from formations.models import Participant
from scolarite.models import DossierEtudiant, InscriptionAdministrative, JournalScolarite

from .test_inscriptions import ConversionFixture, make_user

URL = '/api/scolarite/inscriptions/valider-lot/'


class ValidationLotTests(ConversionFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.acteur)
        self.inscriptions = []
        for n in (1, 2):
            participant = Participant.objects.create(
                matricule=f'LOT-26-{n}', nom=f'Étudiant {n}', prenom='Lot',
            )
            dossier = DossierEtudiant.objects.create(participant=participant)
            self.inscriptions.append(InscriptionAdministrative.objects.create(
                etudiant=dossier, annee_academique=self.annee,
                ref_formation=self.formation, niveau=self.niveau,
            ))

    def test_valide_deux_brouillons_avec_dates_et_journal(self):
        ids = [i.pk for i in self.inscriptions]
        reponse = self.client.post(URL, {'ids': ids}, format='json')
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(reponse.data, {'validees': 2, 'ids': ids})
        for inscription in self.inscriptions:
            inscription.refresh_from_db()
            self.assertEqual(inscription.statut, InscriptionAdministrative.Statut.VALIDEE)
            self.assertIsNotNone(inscription.date_validation)
            self.assertEqual(inscription.valide_par, self.acteur)
        self.assertEqual(JournalScolarite.objects.filter(
            action=JournalScolarite.Action.INSCRIPTION_TRANSITION,
        ).count(), 6)

    def test_une_ligne_deja_validee_annule_tout_le_lot(self):
        premiere, seconde = self.inscriptions
        for statut in ('EN_ATTENTE', 'A_VALIDER', 'VALIDEE'):
            from scolarite import inscription_services
            inscription_services.appliquer_transition(seconde, statut, acteur=self.acteur)
        avant = JournalScolarite.objects.count()
        res = self.client.post(URL, {'ids': [premiere.pk, seconde.pk]}, format='json')
        self.assertEqual(res.status_code, 409, res.data)
        premiere.refresh_from_db()
        self.assertEqual(premiere.statut, InscriptionAdministrative.Statut.BROUILLON)
        self.assertEqual(JournalScolarite.objects.count(), avant)

    def test_annee_cloturee_annule_transitions_et_journal(self):
        from datetime import date
        from scolarite.models import AnneeAcademique
        fermee = AnneeAcademique.objects.create(
            libelle='2027-2028', date_debut=date(2027, 10, 1),
            date_fin=date(2028, 9, 30), cloturee=True,
        )
        self.inscriptions[1].annee_academique = fermee
        self.inscriptions[1].save(update_fields=['annee_academique'])
        # La première peut être validée ; la deuxième échoue APRES ses
        # premières transitions. Le rollback doit annuler les deux dossiers.
        ids = [i.pk for i in self.inscriptions]
        res = self.client.post(URL, {'ids': ids}, format='json')
        self.assertEqual(res.status_code, 409, res.data)
        for inscription in self.inscriptions:
            inscription.refresh_from_db()
            self.assertEqual(inscription.statut, InscriptionAdministrative.Statut.BROUILLON)
        self.assertFalse(JournalScolarite.objects.filter(
            action=JournalScolarite.Action.INSCRIPTION_TRANSITION,
        ).exists())

    def test_selection_perimee_doublon_et_limite(self):
        present = self.inscriptions[0].pk
        for ids, code in (([present, 999999], 409), ([present, present], 400),
                          ([], 400), (list(range(1, 202)), 400)):
            res = self.client.post(URL, {'ids': ids}, format='json')
            self.assertEqual(res.status_code, code, res.data)
        self.inscriptions[0].refresh_from_db()
        self.assertEqual(self.inscriptions[0].statut, InscriptionAdministrative.Statut.BROUILLON)

    def test_lecteur_ne_peut_pas_valider(self):
        self.client.force_authenticate(make_user('lecteur_lot', role='AUDITEUR'))
        res = self.client.post(URL, {'ids': [self.inscriptions[0].pk]}, format='json')
        self.assertEqual(res.status_code, 403)
