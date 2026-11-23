"""Tests A02 — contrat REST de la composition du jury.

Avant correction, `/api/jurys/sessions/{id}/membres/` n'exposait que POST :
la consultation de la composition (écran générique) renvoyait 405. Ces
tests verrouillent le contrat GET/POST sur une seule URL et les permissions.
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from formations.models import RefFormation
from scolarite.models import AnneeAcademique, Maquette, Niveau

from jurys.models import MembreJury, SessionJury

User = get_user_model()


class CompositionJuryRestTest(TestCase):
    """GET = lecture de la composition, POST = ajout, sur la même URL."""

    def setUp(self):
        self.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
        )
        self.ref_formation = RefFormation.objects.create(intitule='Licence Composition')
        self.niveau = Niveau.objects.create(code='LC', libelle='L1 Composition', credits_requis=20)
        self.maquette = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.ref_formation,
            niveau=self.niveau, statut=Maquette.Statut.ACTIVE,
        )
        self.session = SessionJury.objects.create(
            annee_academique=self.annee, ref_formation=self.ref_formation,
            niveau=self.niveau, maquette=self.maquette, libelle='Jury composition',
        )
        self.dfrc = User.objects.create_user(username='comp_dfrc', password='p', role='INJS_ADMIN')
        self.auditeur = User.objects.create_user(username='comp_aud', password='p', role='AUDITEUR')
        self.president = User.objects.create_user(
            username='comp_pres', password='p', role='FORMATEUR',
            first_name='Aya', last_name='Kouassi',
        )
        MembreJury.objects.create(
            session=self.session, user=self.president,
            fonction=MembreJury.Fonction.PRESIDENT, ajoute_par=self.dfrc,
        )
        self.client = APIClient()
        self.url = f'/api/jurys/sessions/{self.session.pk}/membres/'

    def test_get_composition_renvoie_200_et_les_membres(self):
        """A02 : la consultation de la composition est une lecture."""
        self.client.force_authenticate(self.dfrc)
        reponse = self.client.get(self.url)
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(len(reponse.data), 1)
        membre = reponse.data[0]
        self.assertEqual(membre['nom'], 'Aya Kouassi')
        self.assertEqual(membre['nom_affiche'], 'Aya Kouassi')
        self.assertEqual(membre['fonction'], MembreJury.Fonction.PRESIDENT)

    def test_get_composition_anonyme_refuse(self):
        reponse = self.client.get(self.url)
        self.assertIn(reponse.status_code, (401, 403))

    def test_get_composition_role_non_autorise_refuse(self):
        self.client.force_authenticate(self.auditeur)
        reponse = self.client.get(self.url)
        self.assertIn(reponse.status_code, (401, 403))

    def test_get_composition_session_inexistante(self):
        self.client.force_authenticate(self.dfrc)
        reponse = self.client.get('/api/jurys/sessions/999999/membres/')
        self.assertEqual(reponse.status_code, 404)

    def test_post_ajout_valide(self):
        """L'écriture reste disponible sur la même URL."""
        nouveau = User.objects.create_user(username='comp_new', password='p', role='FORMATEUR')
        self.client.force_authenticate(self.dfrc)
        reponse = self.client.post(self.url, {'user_id': nouveau.pk}, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        self.assertEqual(self.session.membres.count(), 2)

    def test_post_ajout_invalide(self):
        self.client.force_authenticate(self.dfrc)
        reponse = self.client.post(self.url, {}, format='json')
        self.assertEqual(reponse.status_code, 400)

    def test_post_ajout_role_non_autorise_refuse(self):
        nouveau = User.objects.create_user(username='comp_new2', password='p', role='FORMATEUR')
        self.client.force_authenticate(self.auditeur)
        reponse = self.client.post(self.url, {'user_id': nouveau.pk}, format='json')
        self.assertIn(reponse.status_code, (401, 403))

    def test_post_ajout_session_verrouillee_refuse(self):
        """Le verrouillage post-clôture reste protégé (règle §7)."""
        nouveau = User.objects.create_user(username='comp_new3', password='p', role='FORMATEUR')
        SessionJury.objects.filter(pk=self.session.pk).update(
            statut=SessionJury.Statut.VERROUILLE,
        )
        self.client.force_authenticate(self.dfrc)
        reponse = self.client.post(self.url, {'user_id': nouveau.pk}, format='json')
        self.assertEqual(reponse.status_code, 400)
