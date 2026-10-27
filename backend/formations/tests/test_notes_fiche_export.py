"""Impression des fiches de notes : par module (classe) et par auditeur."""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from ..models import (
    ModuleParticipant,
    NoteModule,
    NoteModuleColonne,
    NoteModuleSynthese,
)
from .test_core import make_formation, make_module, make_participant, make_user


class NotesFicheExportTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_fiche_notes', role='INJS_ADMIN')
        self.client.force_authenticate(self.admin)

        self.f = make_formation('Cycle fiche notes')
        self.m = make_module(self.f, intitule='Droit administratif', grade='A4', groupe='GROUPE 1')
        self.p = make_participant(matricule='M-FICHE-1', nom='Kone', prenom='Awa')
        ModuleParticipant.objects.create(module=self.m, participant=self.p)

        self.colonne = NoteModuleColonne.objects.create(
            module=self.m, libelle='Examen final', ordre=0, note_max=20,
        )
        NoteModule.objects.create(colonne=self.colonne, participant=self.p, note=15)
        NoteModuleSynthese.objects.create(
            module=self.m, participant=self.p, mention='BIEN', observations='Bon niveau.',
        )

    def _module_url(self, module=None):
        module = module or self.m
        return f'/api/formations/{self.f.pk}/modules/{module.pk}/notes/fiche/pdf/'

    def _auditeur_url(self, participant=None):
        participant = participant or self.p
        return f'/api/formations/{self.f.pk}/modules/{self.m.pk}/notes/fiche/{participant.pk}/pdf/'

    def _assert_pdf(self, res):
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'application/pdf')
        self.assertTrue(res['Content-Disposition'].startswith('attachment;'))
        self.assertTrue(res.content.startswith(b'%PDF'))

    # ── Fiche module ──

    def test_fiche_module_pdf(self):
        res = self.client.get(self._module_url())
        self._assert_pdf(res)
        self.assertIn('fiche_notes_droit_administratif', res['Content-Disposition'])

    def test_fiche_module_pdf_sans_auditeur(self):
        vide = make_module(self.f, intitule='Module vide', grade='A3')
        res = self.client.get(self._module_url(vide))
        self._assert_pdf(res)

    def test_fiche_module_pdf_plusieurs_colonnes(self):
        for index in range(1, 7):
            colonne = NoteModuleColonne.objects.create(
                module=self.m, libelle=f'Devoir {index}', ordre=index, note_max=10,
            )
            NoteModule.objects.create(colonne=colonne, participant=self.p, note=8)
        res = self.client.get(self._module_url())
        self._assert_pdf(res)

    def test_fiche_module_pdf_sur_module_archive(self):
        self.m.archived = True
        self.m.save(update_fields=['archived'])
        res = self.client.get(self._module_url())
        self._assert_pdf(res)

    # ── Fiche auditeur ──

    def test_fiche_auditeur_pdf(self):
        res = self.client.get(self._auditeur_url())
        self._assert_pdf(res)
        self.assertIn('kone_awa', res['Content-Disposition'])

    def test_fiche_auditeur_pdf_sur_module_archive(self):
        self.m.archived = True
        self.m.save(update_fields=['archived'])
        res = self.client.get(self._auditeur_url())
        self._assert_pdf(res)

    def test_fiche_auditeur_non_inscrit_renvoie_404(self):
        autre = make_participant(matricule='M-FICHE-2', nom='Traore', prenom='Ali')
        res = self.client.get(self._auditeur_url(autre))
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # ── Accès ──

    def test_fiche_lecture_autorisee_pour_archiviste(self):
        self.client.force_authenticate(make_user('archiviste_fiche', role='ARCHIVE'))
        self._assert_pdf(self.client.get(self._module_url()))
        self._assert_pdf(self.client.get(self._auditeur_url()))

    def test_fiche_refusee_pour_finance(self):
        self.client.force_authenticate(make_user('finance_fiche', role='FINANCE'))
        res = self.client.get(self._module_url())
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_fiche_refusee_pour_auditeur(self):
        self.client.force_authenticate(make_user('auditeur_fiche', role='AUDITEUR'))
        res = self.client.get(self._module_url())
        self.assertIn(
            res.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )

    def test_fiche_refusee_hors_secretariat(self):
        autre_secretariat = make_user('sec_autre_fiche', role='SECRETARIAT')
        self.client.force_authenticate(autre_secretariat)
        res = self.client.get(self._module_url())
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_fiche_refusee_sans_authentification(self):
        self.client.force_authenticate(None)
        res = self.client.get(self._module_url())
        self.assertIn(
            res.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    # ── Régression : notes consultables après archivage ──

    def test_notes_list_api_accessible_sur_module_archive(self):
        self.m.archived = True
        self.m.save(update_fields=['archived'])
        res = self.client.get(f'/api/formations/{self.f.pk}/modules/{self.m.pk}/notes/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual([r['participant_id'] for r in res.data['rows']], [self.p.pk])
