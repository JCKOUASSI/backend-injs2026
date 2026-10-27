"""U1 — Personne : matricules, identités liées et détection de doublons."""
from datetime import date

from django.db import IntegrityError
from django.test import TestCase

from formations.models import Formateur, Participant
from habilitations.models import Personne
from habilitations.services.identite import (
    generer_matricule_personne,
    identifier_doublons,
)
from ressources_humaines.models import Agent

from .helpers import creer_personne


class MatriculePersonneTests(TestCase):
    def test_premier_matricule_suit_le_format_personne(self):
        matricule = generer_matricule_personne()
        self.assertRegex(matricule, r'^PERS-\d{4}-\d{5}$')
        self.assertTrue(matricule.endswith('-00001'))

    def test_les_matricules_sont_incrementes(self):
        premier = creer_personne(nom='A').matricule
        deuxieme = creer_personne(nom='B').matricule
        self.assertTrue(deuxieme.endswith('-00002'))
        self.assertNotEqual(premier, deuxieme)

    def test_matricule_unique_refuse_les_doublons_en_base(self):
        creer_personne(matricule='PERS-2026-00999', nom='A')
        with self.assertRaises(IntegrityError):
            Personne.objects.create(matricule='PERS-2026-00999', nom='B')


class IdentitesLieesTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(
            matricule='AG-HAB-1', nom='Kouassi', prenom='Yao')
        self.formateur = Formateur.objects.create(
            numerobadge='F-HAB-1', nom='Kouassi', prenom='Yao')
        self.participant = Participant.objects.create(
            matricule='P-HAB-1', nom='Kouassi', prenom='Yao')

    def test_une_personne_peut_lier_agent_et_formateur_simultanement(self):
        personne = creer_personne(
            nom='Kouassi', prenoms='Yao',
            agent_rh=self.agent, formateur=self.formateur,
            participant=self.participant,
        )
        self.assertEqual(personne.agent_rh, self.agent)
        self.assertEqual(personne.formateur, self.formateur)
        self.assertEqual(self.agent.personne_habilitation, personne)

    def test_une_identite_source_ne_se_lie_qu_a_une_seule_personne(self):
        creer_personne(nom='A', agent_rh=self.agent)
        with self.assertRaises(IntegrityError):
            creer_personne(nom='B', agent_rh=self.agent)


class DoublonsPersonneTests(TestCase):
    def test_detecte_un_doublon_par_nom_et_date_naissance(self):
        creer_personne(nom='Diallo', prenoms='Awa',
                       date_naissance=date(1990, 5, 1))
        creer_personne(nom='Diallo', prenoms='Awa',
                       date_naissance=date(1990, 5, 1))
        groupes = identifier_doublons()
        criteres = {g['critere'] for g in groupes}
        self.assertIn('NOM_DATE_NAISSANCE', criteres)

    def test_detecte_un_doublon_par_telephone(self):
        creer_personne(nom='A', telephone='0701020304')
        creer_personne(nom='B', telephone2='0701020304')
        groupes = identifier_doublons()
        self.assertTrue(
            any(g['critere'].startswith('TELEPHONE:') for g in groupes))

    def test_detecte_un_doublon_par_courriel(self):
        creer_personne(nom='A', email_institutionnel='x@injs.local')
        creer_personne(nom='B', email_personnel='x@injs.local')
        groupes = identifier_doublons()
        self.assertTrue(
            any(g['critere'].startswith('EMAIL:') for g in groupes))

    def test_pas_de_faux_doublon_pour_deux_personnes_distinctes(self):
        creer_personne(nom='Traoré', prenoms='Ibou',
                       date_naissance=date(1988, 1, 1), telephone='0700000001')
        creer_personne(nom='Bamba', prenoms='Mariam',
                       date_naissance=date(1992, 9, 9), telephone='0700000002')
        self.assertEqual(identifier_doublons(), [])

    def test_la_detection_ne_modifie_aucune_donnee(self):
        creer_personne(nom='Diallo', prenoms='A',
                       date_naissance=date(1990, 5, 1))
        creer_personne(nom='Diallo', prenoms='A',
                       date_naissance=date(1990, 5, 1))
        avant = list(Personne.objects.values_list('pk', flat=True))
        identifier_doublons()
        apres = list(Personne.objects.values_list('pk', flat=True))
        self.assertEqual(avant, apres)

    def test_les_criteres_sont_desactivables(self):
        creer_personne(nom='Diallo', prenoms='A',
                       date_naissance=date(1990, 5, 1), telephone='0711111111')
        creer_personne(nom='Diallo', prenoms='A',
                       date_naissance=date(1990, 5, 1), telephone='0711111111')
        self.assertEqual(
            identifier_doublons(activer_nom_ddn=False, activer_telephone=False,
                                activer_email=False),
            [],
        )
