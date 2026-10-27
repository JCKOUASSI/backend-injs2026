"""Tests d'étanchéité des endpoints API React (formations)."""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import (
    Formation,
    Module,
    Participant,
    Formateur,
    Secretariat,
    ModuleParticipant,
    ModuleFormateur,
)


def make_user(username, role='INJS_ADMIN', **kwargs):
    return User.objects.create_user(username=username, password='pass', role=role, **kwargs)


class ParticipantListAPIAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sec_a = Secretariat.objects.create(nom='Sec A')
        cls.sec_b = Secretariat.objects.create(nom='Sec B')
        cls.formation = Formation.objects.create(formation='Cycle accès')
        cls.module_a = Module.objects.create(
            formation=cls.formation, intitule='Mod A', secretariat=cls.sec_a,
        )
        cls.module_b = Module.objects.create(
            formation=cls.formation, intitule='Mod B', secretariat=cls.sec_b,
        )
        cls.participant_a = Participant.objects.create(
            matricule='PA001', nom='Alpha', prenom='Un', secretariat=cls.sec_a,
        )
        cls.participant_b = Participant.objects.create(
            matricule='PB001', nom='Beta', prenom='Deux', secretariat=cls.sec_b,
        )
        ModuleParticipant.objects.create(module=cls.module_a, participant=cls.participant_a)
        ModuleParticipant.objects.create(module=cls.module_b, participant=cls.participant_b)

    def setUp(self):
        self.client = APIClient()

    def test_auditeur_cannot_list_participants(self):
        auditeur = make_user('aud_list', role='AUDITEUR')
        self.client.force_authenticate(auditeur)
        res = self.client.get('/api/formations/participants/list/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_formateur_cannot_list_participants(self):
        formateur = make_user('fmt_list', role='FORMATEUR')
        self.client.force_authenticate(formateur)
        res = self.client.get('/api/formations/participants/list/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_finance_cannot_list_participants(self):
        finance = make_user('fin_list', role='FINANCE')
        self.client.force_authenticate(finance)
        res = self.client.get('/api/formations/participants/list/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_secretariat_sees_only_own_scope(self):
        user = make_user('sec_list', role='SECRETARIAT', secretariat=self.sec_a)
        self.client.force_authenticate(user)
        res = self.client.get('/api/formations/participants/list/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = {p['id'] for p in res.data['results']}
        self.assertIn(self.participant_a.id, ids)
        self.assertNotIn(self.participant_b.id, ids)

    def test_chef_secretariat_sees_only_own_scope(self):
        user = make_user('chef_sec_list', role='CHEF_SECRETARIAT', secretariat=self.sec_a)
        self.client.force_authenticate(user)
        res = self.client.get('/api/formations/participants/list/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = {p['id'] for p in res.data['results']}
        self.assertIn(self.participant_a.id, ids)
        self.assertNotIn(self.participant_b.id, ids)

    def test_encadrant_sees_only_supervised_participants(self):
        enc = make_user('enc_list', role='ENCADRANT')
        self.module_a.superviseur = enc
        self.module_a.save(update_fields=['superviseur'])
        self.client.force_authenticate(enc)
        res = self.client.get('/api/formations/participants/list/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = {p['id'] for p in res.data['results']}
        self.assertIn(self.participant_a.id, ids)
        self.assertNotIn(self.participant_b.id, ids)


class FormationFormateursAPIAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sec_a = Secretariat.objects.create(nom='Sec formateurs A')
        cls.sec_b = Secretariat.objects.create(nom='Sec formateurs B')
        cls.formation_a = Formation.objects.create(formation='Formation A')
        cls.formation_b = Formation.objects.create(formation='Formation B')
        cls.module_a = Module.objects.create(
            formation=cls.formation_a, intitule='M A', secretariat=cls.sec_a,
        )
        cls.module_b = Module.objects.create(
            formation=cls.formation_b, intitule='M B', secretariat=cls.sec_b,
        )
        cls.formateur = Formateur.objects.create(numerobadge='F100', nom='Form', prenom='Un')
        ModuleFormateur.objects.create(module=cls.module_a, formateur=cls.formateur)

    def setUp(self):
        self.client = APIClient()

    def test_secretariat_cannot_list_foreign_formation_formateurs(self):
        user = make_user('sec_fmt', role='SECRETARIAT', secretariat=self.sec_b)
        self.client.force_authenticate(user)
        res = self.client.get(f'/api/formations/{self.formation_a.pk}/formateurs/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_secretariat_can_list_own_formation_formateurs(self):
        user = make_user('sec_fmt_ok', role='SECRETARIAT', secretariat=self.sec_a)
        self.client.force_authenticate(user)
        res = self.client.get(f'/api/formations/{self.formation_a.pk}/formateurs/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['numerobadge'], 'F100')


class ParticipantFicheAdminAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sec_a = Secretariat.objects.create(nom='Sec fiche A')
        cls.sec_b = Secretariat.objects.create(nom='Sec fiche B')
        cls.formation = Formation.objects.create(formation='Cycle fiche')
        cls.module_a = Module.objects.create(
            formation=cls.formation, intitule='MF A', secretariat=cls.sec_a,
        )
        cls.module_b = Module.objects.create(
            formation=cls.formation, intitule='MF B', secretariat=cls.sec_b,
        )
        cls.participant_a = Participant.objects.create(
            matricule='FA001', nom='Fiche', prenom='A', secretariat=cls.sec_a,
        )
        cls.participant_b = Participant.objects.create(
            matricule='FB001', nom='Fiche', prenom='B', secretariat=cls.sec_b,
        )
        ModuleParticipant.objects.create(module=cls.module_a, participant=cls.participant_a)
        ModuleParticipant.objects.create(module=cls.module_b, participant=cls.participant_b)

    def setUp(self):
        self.client = APIClient()

    def test_encadrant_cannot_view_foreign_participant_fiche(self):
        enc = make_user('enc_fiche', role='ENCADRANT')
        self.module_a.superviseur = enc
        self.module_a.save(update_fields=['superviseur'])
        self.client.force_authenticate(enc)
        res = self.client.get(f'/api/participant/{self.participant_b.pk}/fiche-admin/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_encadrant_can_view_supervised_participant_fiche(self):
        enc = make_user('enc_fiche_ok', role='ENCADRANT')
        self.module_a.superviseur = enc
        self.module_a.save(update_fields=['superviseur'])
        self.client.force_authenticate(enc)
        res = self.client.get(f'/api/participant/{self.participant_a.pk}/fiche-admin/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['participant']['id'], self.participant_a.id)

    def test_chef_secretariat_scoped_to_own_secretariat(self):
        chef = make_user('chef_fiche', role='CHEF_SECRETARIAT', secretariat=self.sec_a)
        self.client.force_authenticate(chef)
        res_ok = self.client.get(f'/api/participant/{self.participant_a.pk}/fiche-admin/')
        res_ko = self.client.get(f'/api/participant/{self.participant_b.pk}/fiche-admin/')
        self.assertEqual(res_ok.status_code, status.HTTP_200_OK)
        self.assertEqual(res_ko.status_code, status.HTTP_404_NOT_FOUND)

    def test_finance_can_read_any_participant_fiche(self):
        finance = make_user('fin_fiche', role='FINANCE')
        self.client.force_authenticate(finance)
        res = self.client.get(f'/api/participant/{self.participant_b.pk}/fiche-admin/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)


class ParticipantFormationsAPIAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sec_a = Secretariat.objects.create(nom='Sec PF A')
        cls.sec_b = Secretariat.objects.create(nom='Sec PF B')
        cls.formation = Formation.objects.create(formation='Cycle PF')
        cls.module_a = Module.objects.create(
            formation=cls.formation, intitule='PF A', secretariat=cls.sec_a,
        )
        cls.module_b = Module.objects.create(
            formation=cls.formation, intitule='PF B', secretariat=cls.sec_b,
        )
        cls.participant_a = Participant.objects.create(
            matricule='PFA01', nom='PF', prenom='A', secretariat=cls.sec_a,
        )
        cls.participant_b = Participant.objects.create(
            matricule='PFB01', nom='PF', prenom='B', secretariat=cls.sec_b,
        )
        ModuleParticipant.objects.create(module=cls.module_a, participant=cls.participant_a)
        ModuleParticipant.objects.create(module=cls.module_b, participant=cls.participant_b)

    def setUp(self):
        self.client = APIClient()

    def test_auditeur_cannot_list_participant_formations(self):
        auditeur = make_user('aud_pf', role='AUDITEUR')
        self.client.force_authenticate(auditeur)
        res = self.client.get(f'/api/formations/participants/{self.participant_a.pk}/formations/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_secretariat_cannot_view_foreign_participant_formations(self):
        user = make_user('sec_pf', role='SECRETARIAT', secretariat=self.sec_a)
        self.client.force_authenticate(user)
        res = self.client.get(f'/api/formations/participants/{self.participant_b.pk}/formations/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class ModuleAPIAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sec_a = Secretariat.objects.create(nom='Sec mod A')
        cls.sec_b = Secretariat.objects.create(nom='Sec mod B')
        cls.formation = Formation.objects.create(formation='Cycle mod')
        cls.module_a = Module.objects.create(
            formation=cls.formation, intitule='Mod scope A', secretariat=cls.sec_a,
        )
        cls.module_b = Module.objects.create(
            formation=cls.formation, intitule='Mod scope B', secretariat=cls.sec_b,
        )

    def setUp(self):
        self.client = APIClient()

    def test_encadrant_cannot_access_foreign_module_presences(self):
        enc = make_user('enc_mod', role='ENCADRANT')
        self.module_a.superviseur = enc
        self.module_a.save(update_fields=['superviseur'])
        self.client.force_authenticate(enc)
        res = self.client.get(
            f'/api/formations/{self.formation.pk}/modules/{self.module_b.pk}/presences/',
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_auditeur_cannot_access_module_presences(self):
        auditeur = make_user('aud_mod', role='AUDITEUR')
        self.client.force_authenticate(auditeur)
        res = self.client.get(
            f'/api/formations/{self.formation.pk}/modules/{self.module_a.pk}/presences/',
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class ReferentielAPIAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_auditeur_cannot_access_ref_formations(self):
        auditeur = make_user('aud_ref', role='AUDITEUR')
        self.client.force_authenticate(auditeur)
        res = self.client.get('/api/formations/ref/formations/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_auditeur_cannot_access_referentiels_dropdown(self):
        auditeur = make_user('aud_ref2', role='AUDITEUR')
        self.client.force_authenticate(auditeur)
        res = self.client.get('/api/formations/referentiels/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_cpfae_can_access_ref_formations(self):
        admin = make_user('admin_ref', role='INJS_ADMIN')
        self.client.force_authenticate(admin)
        res = self.client.get('/api/formations/ref/formations/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
