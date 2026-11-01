"""Non-régression des performances : pas de requête par ligne sur les listes.

Deux listes déclenchaient une requête supplémentaire **par élément** :

* ``GET /api/finances-etudiantes/echeanciers/`` — comptage des lignes et statut
  global lus deux fois par échéancier ;
* ``GET /api/graduation/diplomes/`` — nombre de rééditions compté par diplôme.

Les tests ci-dessous bornent le nombre de requêtes : il doit rester constant
quand le nombre de lignes augmente (3 puis 6 éléments ⇒ même coût).
"""
from datetime import date
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Participant, RefFormation
from finances_etudiantes.models import Echeancier, LigneEcheancier
from graduation.models import Diplome
from scolarite.models import AnneeAcademique, DossierEtudiant, Niveau


class ListesSansRequeteParLigneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
            courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.agent = User.objects.create_user(
            username='perf_admin', password='pass', role='ADMIN', is_staff=True,
        )

    def _client(self):
        client = APIClient()
        client.force_authenticate(self.agent)
        return client

    def _creer_echeanciers(self, nombre, decalage=0):
        for i in range(nombre):
            i += decalage
            participant = Participant.objects.create(
                nom=f'Nom{i}', prenom=f'Prenom{i}', sexe='F', matricule=f'INJS26-{8000 + i}',
            )
            dossier = DossierEtudiant.objects.create(participant=participant)
            echeancier = Echeancier.objects.create(etudiant=dossier, annee_academique=self.annee)
            for nature in ('DOSSIER', 'INSCRIPTION', 'SCOLARITE'):
                ligne = LigneEcheancier.objects.create(
                    echeancier=echeancier, nature=nature, montant=Decimal('1000'),
                    date_echeance=date(2026, 12, 1), statut='PAYE',
                )
                echeancier.lignes.add(ligne)

    def _creer_diplomes(self, nombre, decalage=0):
        for i in range(nombre):
            i += decalage
            participant = Participant.objects.create(
                nom=f'Dip{i}', prenom=f'Nom{i}', sexe='M', matricule=f'INJS26-{9000 + i}',
            )
            dossier = DossierEtudiant.objects.create(participant=participant)
            Diplome.objects.create(
                etudiant=dossier, annee_academique=self.annee,
                ref_formation=self.formation, niveau=self.niveau,
            )

    def _compter_requetes(self, url):
        client = self._client()
        with CaptureQueriesContext(connection) as contexte:
            reponse = client.get(url)
        return reponse, len(contexte.captured_queries)

    def test_echeanciers_cout_constant(self):
        self._creer_echeanciers(3)
        reponse, cout_3 = self._compter_requetes('/api/finances-etudiantes/echeanciers/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(len(reponse.data['results']), 3)

        self._creer_echeanciers(3, decalage=3)  # 6 au total
        reponse, cout_6 = self._compter_requetes('/api/finances-etudiantes/echeanciers/')
        self.assertEqual(len(reponse.data['results']), 6)
        self.assertEqual(cout_3, cout_6, 'le coût doit rester constant (pas de N+1)')
        self.assertLessEqual(cout_6, 4)

    def test_diplomes_cout_constant(self):
        self._creer_diplomes(3)
        reponse, cout_3 = self._compter_requetes('/api/graduation/diplomes/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(len(reponse.data['results']), 3)

        self._creer_diplomes(3, decalage=3)  # 6 au total
        reponse, cout_6 = self._compter_requetes('/api/graduation/diplomes/')
        self.assertEqual(len(reponse.data['results']), 6)
        self.assertEqual(cout_3, cout_6, 'le coût doit rester constant (pas de N+1)')
        self.assertLessEqual(cout_6, 3)
