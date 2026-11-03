"""Finalisation des maquettes : ventilation des crédits ECUE, validation
en lot (API) et commande ``finaliser_maquettes_injs`` (exemples F05–F08).

Le référentiel officiel publie l'ECTS au niveau UE : les maquettes
importées ont donc leurs ECUE à 0 crédit et sont invalidables. Ces tests
couvrent le déblocage (ventilation à parts égales, sans jamais toucher
une saisie existante) et la création des maquettes d'exemple ACTIVE.
"""
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import RefFormation

from scolarite.models import (
    ECUE, AnneeAcademique, Maquette, MaquetteJournal, Niveau, Semestre, UE,
)


def make_user(username, role):
    return User.objects.create_user(username=username, password='pass', role=role)


class FinalisationBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31',
            courante=True,
        )
        cls.formation = RefFormation.objects.create(
            intitule='ÉDUCATION ET MOTRICITÉ — LICENCE', filiere_code='F01',
            type_diplome='LICENCE',
        )
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.s1 = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='Semestre 1')
        cls.s2 = Semestre.objects.create(niveau=cls.niveau, numero=2, libelle='Semestre 2')
        cls.admin = make_user('admin_maq', 'ADMIN')

    def maquette_importee(self, credits_ue=5, nb_ecue=2, credits_ecue=0):
        """Maquette « importée » : crédits uniquement au niveau UE."""
        maquette = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau,
        )
        ue = UE.objects.create(
            maquette=maquette, semestre=self.s1, code='EM-S1-UE01',
            intitule='Sciences de la vie', credits=credits_ue,
        )
        for rang in range(1, nb_ecue + 1):
            ECUE.objects.create(
                ue=ue, code=f'EM-S1-UE01-EC{rang:02d}',
                intitule=f'Élément {rang}', credits=credits_ecue, ordre=rang,
            )
        return maquette


class RepartirCreditsTests(FinalisationBase):
    def test_ventilation_a_parts_egales_avec_reliquat(self):
        maquette = self.maquette_importee(credits_ue=5, nb_ecue=2)
        self.assertTrue(maquette.verifier_coherence())
        self.assertEqual(maquette.repartir_credits_ecue(), 2)
        credits = list(
            ECUE.objects.filter(ue__maquette=maquette).order_by('ordre')
            .values_list('credits', flat=True)
        )
        self.assertEqual(credits, [3, 2])  # reliquat à la première ECUE
        self.assertEqual(maquette.verifier_coherence(), [])

    def test_ne_touche_jamais_une_saisie_existante(self):
        maquette = self.maquette_importee(credits_ue=6, nb_ecue=1, credits_ecue=4)
        self.assertEqual(maquette.repartir_credits_ecue(), 0)

    def test_maquette_non_brouillon_ignoree(self):
        maquette = self.maquette_importee()
        maquette.repartir_credits_ecue()
        maquette.statut = Maquette.Statut.VALIDEE
        maquette.save(update_fields=['statut'])
        self.assertEqual(maquette.repartir_credits_ecue(), 0)


class ValiderToutesAPITests(FinalisationBase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_valide_les_brouillons_apres_ventilation(self):
        ok = self.maquette_importee()
        ko = Maquette.objects.create(  # UE sans ECUE : échec rapporté
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, version=2,
        )
        UE.objects.create(
            maquette=ko, semestre=self.s2, code='EM-S2-UE01',
            intitule='UE incomplète', credits=3,
        )
        resp = self.client.post('/api/scolarite/maquettes/valider-toutes/', {}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['validees'], [ok.id])
        self.assertEqual([e['id'] for e in resp.data['echecs']], [ko.id])
        ok.refresh_from_db()
        self.assertEqual(ok.statut, 'VALIDEE')
        self.assertEqual(ok.validee_par, self.admin)
        self.assertTrue(
            MaquetteJournal.objects.filter(
                maquette=ok, action=MaquetteJournal.Action.VALIDATION,
            ).exists()
        )
        ko.refresh_from_db()
        self.assertEqual(ko.statut, 'BROUILLON')

    def test_role_non_habilite_refuse(self):
        self.client.force_authenticate(make_user('auditeur_maq', 'AUDITEUR'))
        resp = self.client.post('/api/scolarite/maquettes/valider-toutes/', {}, format='json')
        self.assertEqual(resp.status_code, 403)


class CommandeFinaliserTests(FinalisationBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Filière sans référentiel officiel → maquettes d'exemple attendues.
        cls.formation_andragogie = RefFormation.objects.create(
            intitule='ANDRAGOGIE — LICENCE', filiere_code='F05', type_diplome='LICENCE',
        )
        for ordre, code in [(2, 'L2'), (3, 'L3')]:
            niveau = Niveau.objects.create(code=code, libelle=code, ordre=ordre)
            for numero in (2 * ordre - 1, 2 * ordre):
                Semestre.objects.create(niveau=niveau, numero=numero, libelle=f'S{numero}')

    def test_cree_valide_et_active_toutes_formations(self):
        officielle = self.maquette_importee()
        call_command('finaliser_maquettes_injs', utilisateur='admin_maq', stdout=None)

        officielle.refresh_from_db()
        self.assertEqual(officielle.statut, 'ACTIVE')
        self.assertEqual(officielle.verifier_coherence(), [])

        exemples = Maquette.objects.filter(ref_formation=self.formation_andragogie)
        self.assertEqual(exemples.count(), 3)  # L1, L2, L3
        for maquette in exemples:
            self.assertEqual(maquette.statut, 'ACTIVE')
            self.assertTrue(maquette.libelle.startswith('[Exemple]'))
            self.assertEqual(maquette.verifier_coherence(), [])
            self.assertTrue(maquette.controler_completude()['complet'])

        # Idempotence : un second passage ne crée ni ne casse rien.
        call_command('finaliser_maquettes_injs', utilisateur='admin_maq', stdout=None)
        self.assertEqual(Maquette.objects.count(), 4)

    def test_purger_exemples_ne_touche_pas_les_officielles(self):
        self.maquette_importee()
        call_command('finaliser_maquettes_injs', utilisateur='admin_maq', stdout=None)
        self.assertEqual(Maquette.objects.count(), 4)
        call_command('finaliser_maquettes_injs', purger_exemples=True, stdout=None)
        restes = Maquette.objects.all()
        self.assertEqual(restes.count(), 1)
        self.assertFalse(restes.first().libelle.startswith('[Exemple]'))
