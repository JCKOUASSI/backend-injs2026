"""Lot L3/L7 — tests des charges pédagogiques des enseignants.

Couvre : affectation pédagogique (création, double affectation refusée,
maquette incompatible, conflit de disponibilité), volumétrie (prévue/
affectée/planifiée/réalisée), détections d'anomalies (module sans
enseignant, volume non couvert, surcharge) et API.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Formateur, RefFormation, RefSalle, RefSite

from scolarite.models import (
    AffectationPedagogique,
    AnneeAcademique,
    DossierEtudiant,
    ECUE,
    IndisponibiliteEnseignant,
    Maquette,
    Niveau,
    Semestre,
    UE,
)

from scolarite import charges_services


def make_user(username, role='SECRETARIAT'):
    return User.objects.create_user(username=username, password='pass', role=role)


class ChargesBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31', courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.s1 = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
        )
        # Passage à ACTIVE : la maquette référence doit exister avant.
        cls.ue = UE.objects.create(
            maquette=cls.maquette, semestre=cls.s1, code='UE11',
            intitule='Sciences du mouvement', credits=6,
        )
        cls.ecue = ECUE.objects.create(
            ue=cls.ue, code='ECUE111', intitule='Anatomie', credits=3,
            volume_cm=20, volume_td=10,
        )  # volume_total = 30 h
        cls.maquette.statut = Maquette.Statut.ACTIVE
        cls.maquette.save(update_fields=['statut'])

        cls.site = RefSite.objects.create(nom='Campus INJS')
        cls.salle = RefSalle.objects.create(site=cls.site, nom='Amphi A', capacite=30)
        cls.enseignant = Formateur.objects.create(
            numerobadge='F-0001', nom='Konan', prenom='Jean',
        )
        cls.autre_enseignant = Formateur.objects.create(
            numerobadge='F-0002', nom='Adjoua', prenom='Marie',
        )

    @classmethod
    def _affectation(cls, enseignant=None, ecue=None, statut='PLANIFIEE', volume=30, **kwargs):
        return AffectationPedagogique(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
            semestre=cls.s1, ecue=ecue or cls.ecue, enseignant=enseignant or cls.enseignant,
            type_enseignement='CM', volume_horaire=Decimal(str(volume)), statut=statut,
            **kwargs,
        )


class AffectationTests(ChargesBase):
    def test_affectation_valide(self):
        affectation = self._affectation()
        affectation.full_clean()
        affectation.save()
        self.assertEqual(affectation.statut, 'PLANIFIEE')

    def test_double_affectation_refusee(self):
        AffectationPedagogique.objects.create(
            annee_academique=self.annee, ref_formation=self.formation, niveau=self.niveau,
            semestre=self.s1, ecue=self.ecue, enseignant=self.enseignant,
            type_enseignement='CM', volume_horaire=30, statut='PLANIFIEE',
        )
        doublon = self._affectation(enseignant=self.autre_enseignant)
        with self.assertRaises(ValidationError):
            doublon.full_clean()

    def test_meme_enseignant_peut_reprendre_apres_annulation(self):
        premiere = self._affectation(statut='ANNULEE')
        premiere.full_clean()
        premiere.save()
        remplacement = self._affectation(enseignant=self.autre_enseignant)
        remplacement.full_clean()  # annulée → n'empêche pas la réaffectation


class CoherenceTests(ChargesBase):
    def test_ecue_hors_maquette_active_refusee(self):
        autre_maquette = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.formation, niveau=self.niveau,
            version=2,
        )
        autre_ue = UE.objects.create(
            maquette=autre_maquette, semestre=self.s1, code='UEX', intitule='Hors maquette',
        )
        autre_ecue = ECUE.objects.create(ue=autre_ue, code='ECUEX', intitule='Intruse')
        # La v2 n'est pas ACTIVE → affectation incompatible.
        affectation = self._affectation(ecue=autre_ecue)
        with self.assertRaises(ValidationError):
            affectation.full_clean()

    def test_conflit_disponibilite_refuse(self):
        IndisponibiliteEnseignant.objects.create(
            enseignant=self.enseignant,
            date_debut='2026-11-01', date_fin='2026-12-31', motif='Congé',
        )
        affectation = self._affectation(
            date_debut='2026-12-01', date_fin='2027-01-31',
        )
        with self.assertRaises(ValidationError):
            affectation.full_clean()

    def test_indisponibilites_chevauchantes_refusees(self):
        IndisponibiliteEnseignant.objects.create(
            enseignant=self.enseignant,
            date_debut='2026-11-01', date_fin='2026-12-31', motif='Congé',
        )
        doublon = IndisponibiliteEnseignant(
            enseignant=self.enseignant,
            date_debut='2026-12-15', date_fin='2027-01-15', motif='Chevauchement',
        )
        with self.assertRaises(ValidationError):
            doublon.full_clean()

    def test_indisponibilite_dates_inversees_refusees(self):
        indispo = IndisponibiliteEnseignant(
            enseignant=self.enseignant,
            date_debut='2026-12-31', date_fin='2026-11-01',
        )
        with self.assertRaises(ValidationError):
            indispo.full_clean()


class VolumetrieTests(ChargesBase):
    def test_charge_enseignant_volumetrie(self):
        # Affectée = 30 (planifiée) ; aucune réalisée.
        affectation = self._affectation(statut='PLANIFIEE')
        affectation.full_clean()
        affectation.save()
        resume = charges_services.charge_enseignant(self.enseignant, self.annee)
        self.assertEqual(resume['prevue'], 30.0)       # volume maquette ACTIVE
        self.assertEqual(resume['affectee'], 30.0)
        self.assertEqual(resume['planifiee'], 30.0)
        self.assertEqual(resume['realisee'], 0.0)
        self.assertFalse(resume['surcharge'])

    def test_realisee_calculee(self):
        AffectationPedagogique.objects.create(
            annee_academique=self.annee, ref_formation=self.formation, niveau=self.niveau,
            semestre=self.s1, ecue=self.ecue, enseignant=self.enseignant,
            type_enseignement='CM', volume_horaire=30, statut='REALISEE',
        )
        resume = charges_services.charge_enseignant(self.enseignant, self.annee)
        self.assertEqual(resume['realisee'], 30.0)


class AnomaliesTests(ChargesBase):
    def test_anomalies_module_sans_enseignant_et_volume_non_couvert(self):
        # Maquette ACTIVE mais aucune affectation → module sans enseignant.
        problemes = charges_services.anomalies(self.annee)
        self.assertTrue(any(p['type'] == 'MODULE_SANS_ENSEIGNANT' for p in problemes))
        # Affectation partielle → volume non couvert.
        AffectationPedagogique.objects.create(
            annee_academique=self.annee, ref_formation=self.formation, niveau=self.niveau,
            semestre=self.s1, ecue=self.ecue, enseignant=self.enseignant,
            type_enseignement='CM', volume_horaire=10, statut='PLANIFIEE',
        )
        problemes = charges_services.anomalies(self.annee)
        self.assertTrue(any(p['type'] == 'VOLUME_NON_COUVERT' for p in problemes))
        self.assertFalse(any(p['type'] == 'MODULE_SANS_ENSEIGNANT' for p in problemes))

    def test_anomalie_surcharge(self):
        # Seuil par défaut 192 h : deux affectations de 150 h → surcharge.
        AffectationPedagogique.objects.create(
            annee_academique=self.annee, ref_formation=self.formation, niveau=self.niveau,
            semestre=self.s1, ecue=self.ecue, enseignant=self.enseignant,
            type_enseignement='CM', volume_horaire=150, statut='PLANIFIEE',
        )
        # Une seconde affectation du même enseignant sur un autre type (TD).
        AffectationPedagogique.objects.create(
            annee_academique=self.annee, ref_formation=self.formation, niveau=self.niveau,
            semestre=self.s1, ecue=self.ecue, enseignant=self.enseignant,
            type_enseignement='TD', volume_horaire=150, statut='PLANIFIEE',
        )
        problemes = charges_services.anomalies(self.annee)
        self.assertTrue(any(p['type'] == 'SURCHARGE' for p in problemes))


class ChargesAPITests(ChargesBase):
    def setUp(self):
        self.client = APIClient()

    def test_anonyme_refuse(self):
        res = self.client.get(f'/api/enseignants/charges/{self.enseignant.pk}/',
                              {'annee_id': self.annee.pk})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_charge_via_api(self):
        AffectationPedagogique.objects.create(
            annee_academique=self.annee, ref_formation=self.formation, niveau=self.niveau,
            semestre=self.s1, ecue=self.ecue, enseignant=self.enseignant,
            type_enseignement='CM', volume_horaire=30, statut='PLANIFIEE',
        )
        self.client.force_authenticate(make_user('sec_charges', role='SECRETARIAT'))
        res = self.client.get(f'/api/enseignants/charges/{self.enseignant.pk}/',
                              {'annee_id': self.annee.pk})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['affectee'], 30.0)
        self.assertEqual(res.data['planifiee'], 30.0)

    def test_creation_via_api_et_double_refusee(self):
        self.client.force_authenticate(make_user('sec_charges2', role='SECRETARIAT'))
        payload = {
            'annee_academique_id': self.annee.pk, 'ref_formation_id': self.formation.pk,
            'niveau_id': self.niveau.pk, 'semestre_id': self.s1.pk,
            'ecue_id': self.ecue.pk, 'enseignant_id': self.enseignant.pk,
            'type_enseignement': 'CM', 'volume_horaire': 30,
        }
        res = self.client.post('/api/enseignants/affectations/', payload, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        res = self.client.post('/api/enseignants/affectations/', {
            **payload, 'enseignant_id': self.autre_enseignant.pk,
        }, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('ecue', res.data)

    def test_anomalies_et_occupation_via_api(self):
        self.client.force_authenticate(make_user('sec_charges3', role='SECRETARIAT'))
        res = self.client.get('/api/enseignants/anomalies/', {'annee_id': self.annee.pk})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any(p['type'] == 'MODULE_SANS_ENSEIGNANT' for p in res.data['anomalies']))
        res = self.client.get('/api/enseignants/occupation/', {'annee_id': self.annee.pk})
        self.assertEqual(res.status_code, 200)
