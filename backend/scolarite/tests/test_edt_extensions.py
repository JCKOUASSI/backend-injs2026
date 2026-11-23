"""Lot L10 — tests des extensions du contrat EDT (v1.1).

Non-régression : les ressources v1.0 (groupes, enseignements, etudiants)
continuent de répondre. Nouveautés : indisponibilités, créneaux,
affectations, occupation d'espace (lecture seule).
"""
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from admissions.models import CampagneAdmission, Epreuve
from authentication.models import User
from formations.models import Formateur, RefFormation, RefSalle, RefSite
from scolarite.models import AnneeAcademique, IndisponibiliteEnseignant, Maquette, Niveau, Semestre


def make_user(username, role='SECRETARIAT'):
    return User.objects.create_user(username=username, password='pass', role=role)


class EdtExtensionBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31', courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.site = RefSite.objects.create(nom='Campus INJS')
        cls.salle = RefSalle.objects.create(site=cls.site, nom='Amphi A', capacite=30)
        cls.campagne = CampagneAdmission.objects.create(
            libelle='Entrée L1 2026', annee_academique=cls.annee,
            ref_formation=cls.formation, statut=CampagneAdmission.Statut.OUVERTE,
        )
        cls.epreuve = Epreuve.objects.create(
            campagne=cls.campagne, type=Epreuve.Type.ECRIT,
            intitule='Écrit d’admissibilité', date='2026-09-15',
            heure_debut='08:00', duree_minutes=120, salle=cls.salle,
        )
        cls.formateur = Formateur.objects.create(numerobadge='F-0100', nom='Konan', prenom='Jean')
        cls.indispo = IndisponibiliteEnseignant.objects.create(
            enseignant=cls.formateur, date_debut='2026-11-01',
            date_fin='2026-12-15', motif='Congé annuel',
        )


class EdtNonRegressionTests(EdtExtensionBase):
    """Les ressources v1.0 continuent de répondre (contrat inchangé)."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('staff_edt', role='SECRETARIAT'))

    def test_version_contrat_1_1(self):
        res = self.client.get('/api/scolarite/edt/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['version'], '1.1')

    def test_ressources_v1_0_intactes(self):
        for slug in ('groupes', 'enseignements', 'etudiants'):
            res = self.client.get(f'/api/scolarite/edt/{slug}/')
            self.assertEqual(res.status_code, 200, f'{slug} -> {res.status_code}')
            self.assertIn('resultats', res.data)

    def test_csv_export_toujours_disponible(self):
        res = self.client.get('/api/scolarite/edt/groupes/', {'export': 'csv'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('text/csv', res['Content-Type'])


class EdtExtensionTests(EdtExtensionBase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('staff_edt2', role='SECRETARIAT'))

    def test_indisponibilites_exposees(self):
        res = self.client.get('/api/scolarite/edt/indisponibilites/')
        self.assertEqual(res.status_code, 200)
        resultats = res.data['resultats']
        self.assertEqual(len(resultats), 1)
        self.assertEqual(resultats[0]['badge'], 'F-0100')
        self.assertEqual(resultats[0]['motif'], 'Congé annuel')

    def test_indisponibilites_filtre_par_enseignant(self):
        res = self.client.get('/api/scolarite/edt/indisponibilites/',
                              {'enseignant_id': self.formateur.pk + 999})
        self.assertEqual(len(res.data['resultats']), 0)

    def test_creneaux_sans_filtre(self):
        res = self.client.get('/api/scolarite/edt/creneaux/',
                              {'date_min': '2000-01-01', 'date_max': '2100-01-01'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('resultats', res.data)

    def test_affectations_lectures_seules(self):
        res = self.client.get('/api/scolarite/edt/affectations/',
                              {'annee_academique_id': self.annee.pk})
        self.assertEqual(res.status_code, 200)
        # Contrat en lecture : aucune écriture possible (aucun endpoint POST).
        res_post = self.client.post('/api/scolarite/edt/affectations/', {})
        self.assertEqual(res_post.status_code, 405)


class EspacesDisponibiliteTests(EdtExtensionBase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('staff_esp', role='SECRETARIAT'))

    def test_type_espace_sur_salle(self):
        from referentiels.models import RefTypeEspaceSportif
        type_gym = RefTypeEspaceSportif.objects.create(
            code='GYMNASE', libelle='Gymnase',
        )
        salle = RefSalle.objects.create(
            site=self.site, nom='Gymnase principal', type_espace=type_gym,
        )
        self.assertEqual(salle.type_espace, type_gym)

    def test_occupation_salle_expose_les_epreuves(self):
        res = self.client.get(f'/api/scolarite/edt/espaces/{self.salle.pk}/occupation/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['salle']['nom'], 'Amphi A')
        self.assertEqual(len(res.data['occupations']), 1)
        self.assertEqual(res.data['occupations'][0]['source'], 'CONCOURS')

    def test_occupation_salle_inconnue(self):
        res = self.client.get('/api/scolarite/edt/espaces/99999/occupation/')
        self.assertEqual(res.status_code, 404)