"""Dimensionnement dynamique GET-INJS2026 — tests fonctionnels et d'échelle.

Vérifie que le nombre d'emplois du temps à produire est **dérivé** des
données réelles (inscriptions VALIDÉE, groupes, maquettes), jamais
imposé ; que la capacité cible est paramétrable ; que les manques
(groupes, maquettes) sont signalés comme anomalies explicites ; et que
le calcul par agrégats tient à l'échelle (1 200 inscrits créés en masse,
comptage exact).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from edts.moteur.dimensionnement import dimensionner
from edts.tests.test_lot2_moteur import FabriqueLMD
from formations.models import Participant
from scolarite.models import (
    DossierEtudiant, InscriptionAdministrative, Maquette, Niveau,
)


class DimensionnementBase(TestCase):
    def setUp(self):
        self.f = FabriqueLMD(self).creer_base(perimetre='INJS', filiere='F01')
        self.formation = self.f.cycle
        self.annee = self.f.annee
        self.f.creer_creneaux(jours=('LUNDI', 'MARDI'), heures=((8, 10), (10, 12)))
        self.f.creer_salle(nom='Salle A', capacite=60)
        maquette, ue, ecue = self.f.creer_maquette()
        ecue.volume_cm = 4
        ecue.volume_td = 2
        ecue.save()
        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save()
        self.groupe = self.f.creer_groupe(nom='L1-G1', capacite=30)

    def inscrire(self, nombre, *, prefixe='ETU', niveau=None,
                 statut=InscriptionAdministrative.Statut.VALIDEE):
        niveau = niveau or self.f.niveau
        participants = [
            Participant(matricule=f'{prefixe}-{i:05d}', nom=f'Nom{i}',
                        prenom=f'Prenom{i}')
            for i in range(nombre)
        ]
        Participant.objects.bulk_create(participants)
        dossiers = [DossierEtudiant(participant=p) for p in participants]
        DossierEtudiant.objects.bulk_create(dossiers)
        InscriptionAdministrative.objects.bulk_create([
            InscriptionAdministrative(
                etudiant=d, annee_academique=self.annee,
                ref_formation=self.formation, niveau=niveau,
                parcours=self.f.parcours, statut=statut,
            )
            for d in dossiers
        ])


class DimensionnementTests(DimensionnementBase):
    def test_groupes_necessaires_derives_des_effectifs(self):
        self.inscrire(130)
        rapport = dimensionner(self.annee.pk, capacite_cible=60)

        self.assertEqual(rapport['effectif_total_a_planifier'], 130)
        promo = rapport['promotions'][0]
        # plafond(130 / 60) = 3 groupes ; 1 existe → déficit 2.
        self.assertEqual(promo['groupes_necessaires'], 3)
        self.assertEqual(promo['groupes_existants'], 1)
        self.assertEqual(promo['deficit_groupes'], 2)
        # Le nombre d'EDT à produire est le nombre de groupes nécessaires.
        self.assertEqual(rapport['totaux']['emplois_du_temps_a_produire'], 3)
        types = {a['type'] for a in rapport['anomalies']}
        self.assertIn('GROUPES_INSUFFISANTS', types)

    def test_capacite_cible_parametrable(self):
        self.inscrire(130)
        rapport = dimensionner(self.annee.pk, capacite_cible=30)
        self.assertEqual(rapport['capacite_cible_par_groupe'], 30)
        self.assertEqual(rapport['promotions'][0]['groupes_necessaires'], 5)

    def test_promotion_sans_groupe_signalee(self):
        niveau_l2, _ = Niveau.objects.get_or_create(
            code='L2', defaults={'libelle': 'Licence 2', 'cycle': 'LICENCE',
                                 'ordre': 2, 'credits_requis': 120},
        )
        self.inscrire(5, prefixe='L2X', niveau=niveau_l2)
        rapport = dimensionner(self.annee.pk)
        types = {a['type'] for a in rapport['anomalies']}
        self.assertIn('PROMOTION_SANS_GROUPE', types)

    def test_seances_derivees_de_la_maquette_active(self):
        self.inscrire(30)
        rapport = dimensionner(self.annee.pk)
        # Maquette : CM 4 h + TD 2 h, séances de 2 h → 3 séances, 6 heures.
        self.assertEqual(rapport['totaux']['seances_a_programmer'], 3)
        self.assertEqual(rapport['totaux']['heures_a_programmer'], 6)

    def test_inscriptions_non_validees_ignorees(self):
        self.inscrire(10, prefixe='VAL')
        self.inscrire(7, prefixe='BRO',
                      statut=InscriptionAdministrative.Statut.BROUILLON)
        rapport = dimensionner(self.annee.pk)
        self.assertEqual(rapport['effectif_total_a_planifier'], 10)

    def test_echelle_par_agregats(self):
        """1 200 inscrits : comptage exact, 20 groupes à 60, sans N+1 métier."""
        self.inscrire(1200, prefixe='MASSE')
        rapport = dimensionner(self.annee.pk, capacite_cible=60)
        self.assertEqual(rapport['effectif_total_a_planifier'], 1200)
        self.assertEqual(rapport['promotions'][0]['groupes_necessaires'], 20)
        self.assertEqual(rapport['totaux']['emplois_du_temps_a_produire'], 20)


class DimensionnementApiTests(DimensionnementBase):
    def setUp(self):
        super().setUp()
        self.inscrire(12)
        self.client = APIClient()
        user = get_user_model().objects.create_user(
            username='lecteur-dim', password='x',
        )
        self.client.force_authenticate(user=user)

    def test_sans_annee_400_explicite(self):
        reponse = self.client.get('/api/edts/lmd/dimensionnement/')
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(reponse.data['motif_echec'], 'ANNEE_ACADEMIQUE_REQUISE')

    def test_rapport_api(self):
        reponse = self.client.get(
            '/api/edts/lmd/dimensionnement/',
            {'annee': self.annee.pk, 'capacite': 10},
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['effectif_total_a_planifier'], 12)
        self.assertEqual(reponse.data['capacite_cible_par_groupe'], 10)
        self.assertEqual(
            reponse.data['promotions'][0]['groupes_necessaires'], 2)

    def test_non_authentifie_refuse(self):
        self.client.force_authenticate(user=None)
        reponse = self.client.get(
            '/api/edts/lmd/dimensionnement/', {'annee': self.annee.pk})
        self.assertIn(reponse.status_code, (401, 403))
