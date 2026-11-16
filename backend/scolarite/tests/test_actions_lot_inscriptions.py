"""Actions groupées des inscriptions : mêmes droits, retrait sûr, transaction unique."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from formations.models import Participant
from scolarite import inscription_services
from scolarite.models import DossierEtudiant, InscriptionAdministrative, JournalScolarite

from .test_inscriptions import ConversionFixture, make_user

URL = '/api/scolarite/inscriptions/action-lot/'


class ActionsLotTests(ConversionFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.acteur)
        self.brouillons = []
        for numero in (1, 2):
            participant = Participant.objects.create(
                matricule=f'RETRAIT-LOT-{numero}', nom='Lot', prenom=str(numero),
            )
            dossier = DossierEtudiant.objects.create(participant=participant)
            self.brouillons.append(InscriptionAdministrative.objects.create(
                etudiant=dossier, annee_academique=self.annee,
                ref_formation=self.formation, niveau=self.niveau,
            ))

    def envoyer(self, action, ids):
        return self.client.post(URL, {'action': action, 'ids': ids}, format='json')

    def test_retirer_supprime_isole_et_archive_utilise_sans_cascade(self):
        admission = self.admettre()
        liee = inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur, valider=True,
        )
        ids = [self.brouillons[0].pk, liee.pk]
        res = self.envoyer('retirer', ids)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['resultats'], [
            {'id': ids[0], 'resultat': 'supprime'}, {'id': ids[1], 'resultat': 'archive'},
        ])
        self.assertFalse(InscriptionAdministrative.objects.filter(pk=ids[0]).exists())
        liee.refresh_from_db()
        self.assertTrue(liee.archive)
        self.assertEqual(liee.statut, InscriptionAdministrative.Statut.VALIDEE)
        self.assertEqual(liee.admission_id, admission.pk)
        self.assertTrue(JournalScolarite.objects.filter(
            objet_id=ids[0], action=JournalScolarite.Action.INSCRIPTION_SUPPRIMEE,
        ).exists())

    def test_archiver_explicitement_un_brouillon_isole_et_reactiver(self):
        ids = [b.pk for b in self.brouillons]
        res = self.envoyer('archiver', ids)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual([r['resultat'] for r in res.data['resultats']], ['archive', 'archive'])
        self.assertEqual(InscriptionAdministrative.objects.filter(pk__in=ids, archive=True).count(), 2)
        res = self.envoyer('reactiver', ids)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual([r['resultat'] for r in res.data['resultats']], ['reactive', 'reactive'])
        self.assertEqual(InscriptionAdministrative.objects.filter(pk__in=ids, archive=False).count(), 2)
        self.assertEqual(JournalScolarite.objects.filter(
            objet_id__in=ids, action=JournalScolarite.Action.INSCRIPTION_REACTIVEE,
        ).count(), 2)

    def test_selection_perimee_ou_etat_invalide_ne_change_rien(self):
        ids = [b.pk for b in self.brouillons]
        avant = JournalScolarite.objects.count()
        for action, selection, code in (
            ('retirer', [ids[0], 999999], 409),
            ('retirer', [ids[0], ids[0]], 400),
            ('archiver', [], 400),
            ('reactiver', ids, 409),
            ('inconnu', ids, 400),
            ('retirer', list(range(1, 202)), 400),
        ):
            self.assertEqual(self.envoyer(action, selection).status_code, code)
        self.assertEqual(InscriptionAdministrative.objects.filter(pk__in=ids).count(), 2)
        self.assertEqual(JournalScolarite.objects.count(), avant)
        inscription_services.archiver_inscription(ids[1], acteur=self.acteur)
        avant = JournalScolarite.objects.count()
        self.assertEqual(self.envoyer('retirer', ids).status_code, 409)
        self.assertEqual(InscriptionAdministrative.objects.filter(pk__in=ids).count(), 2)
        self.assertEqual(JournalScolarite.objects.count(), avant)

    def test_echec_apres_premiere_suppression_annule_delete_et_journal(self):
        ids = [b.pk for b in self.brouillons]
        original = inscription_services.supprimer_ou_archiver

        def operation(pk, acteur=None):
            if pk == ids[1]:
                raise inscription_services.InscriptionImpossible('Échec métier simulé')
            return original(pk, acteur=acteur)

        with patch('scolarite.inscription_api.inscription_services.supprimer_ou_archiver', operation):
            res = self.envoyer('retirer', ids)
        self.assertEqual(res.status_code, 409, res.data)
        self.assertEqual(InscriptionAdministrative.objects.filter(pk__in=ids).count(), 2)
        self.assertFalse(JournalScolarite.objects.filter(
            objet_id=ids[0], action=JournalScolarite.Action.INSCRIPTION_SUPPRIMEE,
        ).exists())

    def test_reactivation_mixte_annule_tout(self):
        ids = [b.pk for b in self.brouillons]
        inscription_services.archiver_inscription(ids[0], acteur=self.acteur)
        res = self.envoyer('reactiver', ids)
        self.assertEqual(res.status_code, 409, res.data)
        self.assertTrue(InscriptionAdministrative.objects.get(pk=ids[0]).archive)

    def test_role_lecteur_refuse(self):
        self.client.force_authenticate(make_user('lecteur_actions_lot', role='AUDITEUR'))
        self.assertEqual(self.envoyer('retirer', [self.brouillons[0].pk]).status_code, 403)
        self.assertEqual(InscriptionAdministrative.objects.count(), 2)
