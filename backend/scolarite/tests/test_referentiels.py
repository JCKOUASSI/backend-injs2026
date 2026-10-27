from datetime import date
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db.utils import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import RefFormation, RefModule
from scolarite.models import (
    AnneeAcademique,
    ECUE,
    Groupe,
    Maquette,
    Niveau,
    Parcours,
    Semestre,
    UE,
)


def make_user(username, role='INJS_ADMIN', **kwargs):
    return User.objects.create_user(username=username, password='pass', role=role, **kwargs)


def make_annee(libelle='2026-2027', courante=False):
    debut = int(libelle.split('-')[0])
    return AnneeAcademique.objects.create(
        libelle=libelle,
        date_debut=date(debut, 10, 1),
        date_fin=date(debut + 1, 9, 30),
        courante=courante,
    )


class AnneeAcademiqueTests(TestCase):

    def test_une_seule_annee_courante(self):
        make_annee('2025-2026', courante=True)
        with self.assertRaises(IntegrityError):
            make_annee('2026-2027', courante=True)

    def test_plusieurs_annees_non_courantes(self):
        make_annee('2025-2026')
        make_annee('2026-2027')
        self.assertEqual(AnneeAcademique.objects.count(), 2)

    def test_date_fin_doit_suivre_date_debut(self):
        annee = AnneeAcademique(
            libelle='2027-2028', date_debut=date(2028, 9, 30), date_fin=date(2027, 10, 1),
        )
        with self.assertRaises(ValidationError):
            annee.clean()

    def test_courante_ou_none(self):
        self.assertIsNone(AnneeAcademique.courante_ou_none())
        annee = make_annee('2026-2027', courante=True)
        self.assertEqual(AnneeAcademique.courante_ou_none(), annee)


class ParcoursEtGroupeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.annee = make_annee('2026-2027', courante=True)
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.autre_formation = RefFormation.objects.create(intitule='MASTER STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.parcours = Parcours.objects.create(
            ref_formation=cls.formation, code='EM', intitule='Éducation et Motricité',
        )

    def test_code_parcours_unique_par_formation_insensible_a_la_casse(self):
        with self.assertRaises(IntegrityError):
            Parcours.objects.create(
                ref_formation=self.formation, code='em', intitule='Doublon',
            )

    def test_meme_code_autorise_sur_une_autre_formation(self):
        parcours = Parcours.objects.create(
            ref_formation=self.autre_formation, code='EM', intitule='Éducation et Motricité',
        )
        self.assertIsNotNone(parcours.pk)

    def test_groupe_refuse_un_parcours_d_une_autre_formation(self):
        groupe = Groupe(
            annee_academique=self.annee,
            ref_formation=self.autre_formation,
            parcours=self.parcours,
            niveau=self.niveau,
            nom='L1-G1',
        )
        with self.assertRaises(ValidationError):
            groupe.clean()

    def test_nom_groupe_unique_par_annee_formation_niveau(self):
        Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, nom='L1-G1',
        )
        with self.assertRaises(IntegrityError):
            Groupe.objects.create(
                annee_academique=self.annee, ref_formation=self.formation,
                niveau=self.niveau, nom='l1-g1',
            )


class MaquetteTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.annee = make_annee('2026-2027', courante=True)
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.semestre = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
        )
        cls.ue = UE.objects.create(
            maquette=cls.maquette, semestre=cls.semestre,
            code='UE11', intitule='Sciences du mouvement', credits=6,
        )
        cls.ref_module = RefModule.objects.create(intitule='ANATOMIE FONCTIONNELLE')
        cls.ecue = ECUE.objects.create(
            ue=cls.ue, code='ECUE111', intitule='Anatomie', credits=3,
            volume_cm=20, volume_td=10, ref_module=cls.ref_module,
        )

    def test_volume_total_ecue(self):
        self.assertEqual(self.ecue.volume_total, 30)

    def test_credits_total_maquette(self):
        UE.objects.create(
            maquette=self.maquette, semestre=self.semestre,
            code='UE12', intitule='Physiologie', credits=4,
        )
        self.assertEqual(self.maquette.credits_total, 10)

    def test_code_ue_unique_dans_la_maquette(self):
        with self.assertRaises(IntegrityError):
            UE.objects.create(
                maquette=self.maquette, semestre=self.semestre,
                code='ue11', intitule='Doublon', credits=2,
            )

    def test_passerelle_vers_ref_module(self):
        self.assertEqual(self.ecue.ref_module, self.ref_module)
        self.assertIn(self.ecue, self.ref_module.ecues.all())

    def test_suppression_ref_module_conserve_ecue(self):
        self.ref_module.delete()
        self.ecue.refresh_from_db()
        self.assertIsNone(self.ecue.ref_module_id)


class ReferentielAPITests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.annee = make_annee('2026-2027', courante=True)
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        Semestre.objects.create(niveau=cls.niveau, numero=2, libelle='S2')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('admin_lmd'))

    def test_liste_niveaux(self):
        response = self.client.get('/api/scolarite/ref/niveaux/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([n['code'] for n in response.json()], ['L1'])

    def test_liste_formations(self):
        RefFormation.objects.create(intitule='LICENCE STAPS')
        response = self.client.get('/api/scolarite/ref/formations/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(f['intitule'] == 'LICENCE STAPS' for f in response.json()))

    def test_liste_salles(self):
        from formations.models import RefSite, RefSalle
        site = RefSite.objects.create(nom='Site Principal')
        RefSalle.objects.create(site=site, nom='Salle Polyvalente', capacite=40)
        response = self.client.get('/api/scolarite/ref/salles/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(s['nom'] == 'Salle Polyvalente' for s in response.json()))

    def test_filtre_semestres_par_niveau(self):
        response = self.client.get('/api/scolarite/ref/semestres/', {'niveau_id': self.niveau.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_referentiel_inconnu_renvoie_404(self):
        response = self.client.get('/api/scolarite/ref/inexistant/')
        self.assertEqual(response.status_code, 404)

    def test_creation_niveau(self):
        response = self.client.post('/api/scolarite/ref/niveaux/', {
            'code': 'L2', 'libelle': 'Licence 2', 'cycle': 'LICENCE', 'ordre': 2,
            'credits_requis': 60, 'actif': True,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Niveau.objects.filter(code='L2').exists())

    def test_creation_invalide_rejetee(self):
        response = self.client.post('/api/scolarite/ref/niveaux/', {
            'code': 'L1', 'libelle': 'Doublon', 'ordre': 1,
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_annee_courante(self):
        response = self.client.get('/api/scolarite/annee-courante/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['annee']['libelle'], '2026-2027')

    def test_acces_refuse_sans_authentification(self):
        response = APIClient().get('/api/scolarite/ref/niveaux/')
        self.assertEqual(response.status_code, 401)

    def test_lecture_seule_pour_la_direction(self):
        client = APIClient()
        client.force_authenticate(make_user('direction_lmd', role='DIRECTION'))
        self.assertEqual(client.get('/api/scolarite/ref/niveaux/').status_code, 200)
        creation = client.post('/api/scolarite/ref/niveaux/', {
            'code': 'M1', 'libelle': 'Master 1', 'ordre': 4,
        }, format='json')
        self.assertEqual(creation.status_code, 403)

    def test_role_non_habilite_refuse(self):
        client = APIClient()
        client.force_authenticate(make_user('auditeur_lmd', role='AUDITEUR'))
        self.assertEqual(client.get('/api/scolarite/ref/niveaux/').status_code, 403)


class MaquetteAPITests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.annee = make_annee('2026-2027', courante=True)
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.semestre = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        # Lot L1 (R4) : les UE/ECUE sont créées AVANT l'activation — une
        # maquette ACTIVE est immuable.
        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
        )
        ue = UE.objects.create(
            maquette=cls.maquette, semestre=cls.semestre,
            code='UE11', intitule='Sciences du mouvement', credits=6,
        )
        ECUE.objects.create(ue=ue, code='ECUE111', intitule='Anatomie', credits=3, volume_cm=20)
        cls.maquette.statut = Maquette.Statut.ACTIVE
        cls.maquette.save()

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('admin_maquette'))

    def test_liste_maquettes_avec_agregats(self):
        response = self.client.get('/api/scolarite/maquettes/')
        self.assertEqual(response.status_code, 200)
        maquette = response.json()[0]
        self.assertEqual(maquette['nb_ue'], 1)
        self.assertEqual(maquette['total_credits'], 6)

    def test_detail_maquette_expose_ue_et_ecues(self):
        response = self.client.get(f'/api/scolarite/maquettes/{self.maquette.id}/')
        self.assertEqual(response.status_code, 200)
        unites = response.json()['unites_enseignement']
        self.assertEqual(len(unites), 1)
        self.assertEqual(unites[0]['ecues'][0]['code'], 'ECUE111')

    def test_ecues_par_semestre(self):
        response = self.client.get(
            f'/api/scolarite/maquettes/{self.maquette.id}/semestres/{self.semestre.id}/ecues/',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]['ue_code'], 'UE11')

    def test_maquette_introuvable(self):
        response = self.client.get('/api/scolarite/maquettes/99999/')
        self.assertEqual(response.status_code, 404)


class InitReferentielsLMDCommandTests(TestCase):

    def test_creation_et_idempotence(self):
        call_command('init_referentiels_lmd', '--annee', '2026-2027', '--courante', stdout=StringIO())
        self.assertEqual(Niveau.objects.count(), 5)
        self.assertEqual(Semestre.objects.count(), 10)
        self.assertTrue(AnneeAcademique.objects.filter(libelle='2026-2027', courante=True).exists())

        call_command('init_referentiels_lmd', '--annee', '2026-2027', stdout=StringIO())
        self.assertEqual(Niveau.objects.count(), 5)
        self.assertEqual(Semestre.objects.count(), 10)
        self.assertEqual(AnneeAcademique.objects.count(), 1)

    def test_bascule_annee_courante(self):
        call_command('init_referentiels_lmd', '--annee', '2025-2026', '--courante', stdout=StringIO())
        call_command('init_referentiels_lmd', '--annee', '2026-2027', '--courante', stdout=StringIO())
        self.assertEqual(AnneeAcademique.objects.filter(courante=True).count(), 1)
        self.assertEqual(AnneeAcademique.objects.get(courante=True).libelle, '2026-2027')

    def test_parcours_injs_sans_cycle_de_formation(self):
        call_command('init_referentiels_lmd', '--avec-parcours-injs', stdout=StringIO(), stderr=StringIO())
        self.assertEqual(Parcours.objects.count(), 0)

    def test_parcours_injs_avec_cycle_de_formation(self):
        RefFormation.objects.create(intitule='LICENCE STAPS')
        call_command('init_referentiels_lmd', '--avec-parcours-injs', stdout=StringIO())
        self.assertEqual(Parcours.objects.count(), 6)
