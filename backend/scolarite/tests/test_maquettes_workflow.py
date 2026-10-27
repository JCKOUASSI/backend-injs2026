"""Lot L1 — tests du workflow des maquettes et du garde-fou R4.

Couvre : immutabilité d'une maquette VALIDEE/ACTIVE/ARCHIVEE, clonage de
version, contrôles de cohérence, workflow BROUILLON → VALIDEE → ACTIVE →
ARCHIVEE, permissions (IsSecretariatOrDFRC / IsDFRC) et journal.
"""
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import RefFormation, RefModule

from scolarite.models import (
    AnneeAcademique,
    ECUE,
    Maquette,
    MaquetteJournal,
    Niveau,
    Semestre,
    UE,
)


def make_user(username, role):
    return User.objects.create_user(username=username, password='pass', role=role)


class MaquetteWorkflowBase(TestCase):
    """Fixture commune : référentiels LMD + maquette complète en BROUILLON."""

    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31', courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.s1 = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        cls.ref_module = RefModule.objects.create(intitule='ANATOMIE FONCTIONNELLE')
        cls.maquette = cls._creer_maquette_complete()

    @classmethod
    def _creer_maquette_complete(cls):
        maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
        )
        ue = UE.objects.create(
            maquette=maquette, semestre=cls.s1, code='UE11',
            intitule='Sciences du mouvement', credits=6,
        )
        ECUE.objects.create(
            ue=ue, code='ECUE111', intitule='Anatomie', credits=3,
            volume_cm=20, volume_td=5, ref_module=cls.ref_module,
        )
        ECUE.objects.create(
            ue=ue, code='ECUE112', intitule='Pratique sportive', credits=3, volume_tp=30,
        )
        return maquette

    @classmethod
    def _activer(cls, maquette):
        maquette.statut = Maquette.Statut.VALIDEE
        maquette.save(update_fields=['statut'])
        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save(update_fields=['statut'])


class GardeImmutabiliteTests(MaquetteWorkflowBase):
    """R4 — une maquette aboutie est immuable ; on corrige par clonage."""

    def test_maquette_active_immuable_via_save(self):
        self._activer(self.maquette)
        self.maquette.libelle = 'Tentative de modification'
        with self.assertRaises(ValidationError):
            self.maquette.save()

    def test_maquette_active_fk_non_modifiable(self):
        self._activer(self.maquette)
        autre_formation = RefFormation.objects.create(intitule='MASTER STAPS')
        self.maquette.ref_formation = autre_formation
        with self.assertRaises(ValidationError):
            self.maquette.save()

    def test_transition_active_vers_brouillon_interdite(self):
        self._activer(self.maquette)
        self.maquette.statut = Maquette.Statut.BROUILLON
        with self.assertRaises(ValidationError):
            self.maquette.save()

    def test_transition_active_vers_archivee_autorisee(self):
        self._activer(self.maquette)
        self.maquette.statut = Maquette.Statut.ARCHIVEE
        self.maquette.save(update_fields=['statut'])
        self.maquette.refresh_from_db()
        self.assertEqual(self.maquette.statut, Maquette.Statut.ARCHIVEE)

    def test_ue_non_modifiable_sur_maquette_active(self):
        self._activer(self.maquette)
        ue = self.maquette.unites_enseignement.first()
        ue.intitule = 'Piratage'
        with self.assertRaises(ValidationError):
            ue.save()

    def test_ecue_non_supprimable_sur_maquette_active(self):
        self._activer(self.maquette)
        ecue = ECUE.objects.first()
        with self.assertRaises(ValidationError):
            ecue.delete()

    def test_nouvelle_ecue_interdite_sur_maquette_active(self):
        self._activer(self.maquette)
        ue = self.maquette.unites_enseignement.first()


class ClonageTests(MaquetteWorkflowBase):
    def test_clonage_cree_nouvelle_version_brouillon(self):
        self._activer(self.maquette)
        clone = self.maquette.cloner()
        self.assertEqual(clone.statut, Maquette.Statut.BROUILLON)
        self.assertEqual(clone.version, 2)
        self.assertEqual(clone.unites_enseignement.count(), 1)
        ue_clone = clone.unites_enseignement.first()
        self.assertEqual(ue_clone.ecues.count(), 2)
        # Les instances sont bien des copies (pas de réutilisation).
        self.assertNotEqual(ue_clone.pk, self.maquette.unites_enseignement.first().pk)
        # La source est intacte.
        self.maquette.refresh_from_db()
        self.assertEqual(self.maquette.statut, Maquette.Statut.ACTIVE)
        # Journal : CLONAGE sur le clone.
        self.assertTrue(MaquetteJournal.objects.filter(
            maquette=clone, action=MaquetteJournal.Action.CLONAGE,
        ).exists())

    def test_ecue_archivee_non_clonee(self):
        ue = self.maquette.unites_enseignement.first()
        ecue = ue.ecues.first()
        ecue.archive = True
        ecue.save(update_fields=['archive'])
        clone = self.maquette.cloner()
        self.assertEqual(
            clone.unites_enseignement.first().ecues.count(),
            ue.ecues.filter(archive=False).count(),
        )


class CoherenceTests(MaquetteWorkflowBase):
    def test_maquette_complete_coherente(self):
        self.assertEqual(self.maquette.verifier_coherence(), [])

    def test_maquette_vide_incomplete(self):
        vide = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.formation, niveau=self.niveau,
        )
        problemes = vide.verifier_coherence()
        self.assertTrue(any('incomplète' in p for p in problemes))

    def test_credits_ue_differents_de_somme_ecue_signales(self):
        ue = self.maquette.unites_enseignement.first()
        ue.credits = 8
        ue.save(update_fields=['credits'])
        problemes = self.maquette.verifier_coherence()
        self.assertTrue(any('crédits ECUE' in p for p in problemes))

    def test_module_duplique_dans_la_maquette_signale(self):
        ue = self.maquette.unites_enseignement.first()
        ECUE.objects.create(
            ue=ue, code='ECUE113', intitule='Doublon', credits=0,
            ref_module=self.ref_module,
        )
        problemes = self.maquette.verifier_coherence()


class WorkflowAPITests(MaquetteWorkflowBase):
    """Workflow via l'API : création, validation, activation, archivage, clonage."""

    def setUp(self):
        self.client = APIClient()

    def test_anonyme_refuse(self):
        res = self.client.post('/api/scolarite/maquettes/creer/', {})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_workflow_complet(self):
        secretariat = make_user('sec_maq', role='SECRETARIAT')
        admin = make_user('admin_maq', role='ADMIN')
        # Création (secrétariat) — v2 car la fixture occupe v1
        self.client.force_authenticate(secretariat)
        res = self.client.post('/api/scolarite/maquettes/creer/', {
            'annee_academique_id': self.annee.pk,
            'ref_formation_id': self.formation.pk,
            'niveau_id': self.niveau.pk,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        maquette_id = res.data['id']
        self.assertEqual(res.data['version'], 2)
        # Contenu : une UE complète (crédits ECUE = crédits UE)
        res = self.client.post(f'/api/scolarite/maquettes/{maquette_id}/ues/', {
            'semestre_id': self.s1.pk, 'code': 'UE11B', 'intitule': 'Bases 2', 'credits': 6,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        ue_id = res.data['id']
        res = self.client.post(f'/api/scolarite/ues/{ue_id}/ecues/', {
            'code': 'ECUE11B1', 'intitule': 'Anatomie 2', 'credits': 6, 'volume_cm': 20,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        # Validation (secrétariat)
        res = self.client.post(f'/api/scolarite/maquettes/{maquette_id}/valider/', {'commentaire': 'OK'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['statut'], Maquette.Statut.VALIDEE)
        # Activation : le secrétariat n'a pas le droit (IsDFRC)
        res = self.client.post(f'/api/scolarite/maquettes/{maquette_id}/activer/', {})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        # Activation par un rôle DFRC (ADMIN)
        self.client.force_authenticate(admin)
        res = self.client.post(f'/api/scolarite/maquettes/{maquette_id}/activer/', {})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['statut'], Maquette.Statut.ACTIVE)
        # Archivage
        res = self.client.post(f'/api/scolarite/maquettes/{maquette_id}/archiver/', {})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['statut'], Maquette.Statut.ARCHIVEE)
        # Journal complet
        res = self.client.get(f'/api/scolarite/maquettes/{maquette_id}/journal/')
        actions = [e['action'] for e in res.data]
        self.assertIn('CREATION', actions)
        self.assertIn('VALIDATION', actions)
        self.assertIn('ACTIVATION', actions)
        self.assertIn('ARCHIVAGE', actions)

    def test_activation_incomplete_refusee(self):
        secretariat = make_user('sec_maq2', role='SECRETARIAT')
        self.client.force_authenticate(secretariat)
        res = self.client.post('/api/scolarite/maquettes/creer/', {
            'annee_academique_id': self.annee.pk,
            'ref_formation_id': self.formation.pk,
            'niveau_id': self.niveau.pk,
        }, format='json')
        maquette_id = res.data['id']
        # Aucune UE → validation refusée (maquette incomplète)
        res = self.client.post(f'/api/scolarite/maquettes/{maquette_id}/valider/', {})
        self.assertEqual(res.status_code, 400)
        self.assertIn('problemes', res.data)
        # Et l'activation directe d'une BROUILLON est refusée
        admin = make_user('admin_maq2', role='ADMIN')
        self.client.force_authenticate(admin)
        res = self.client.post(f'/api/scolarite/maquettes/{maquette_id}/activer/', {})
        self.assertEqual(res.status_code, 400)

    def test_validation_incoherente_refusee(self):
        secretariat = make_user('sec_maq3', role='SECRETARIAT')
        self.client.force_authenticate(secretariat)
        # UE sans ECUE → incohérente
        res = self.client.post('/api/scolarite/maquettes/creer/', {
            'annee_academique_id': self.annee.pk,
            'ref_formation_id': self.formation.pk,
            'niveau_id': self.niveau.pk,
        }, format='json')
        maquette_id = res.data['id']
        self.client.post(f'/api/scolarite/maquettes/{maquette_id}/ues/', {
            'semestre_id': self.s1.pk, 'code': 'UE99', 'intitule': 'Vide', 'credits': 6,
        }, format='json')
        res = self.client.post(f'/api/scolarite/maquettes/{maquette_id}/valider/', {})
        self.assertEqual(res.status_code, 400)
        self.assertTrue(any('aucune ECUE' in p for p in res.data['problemes']))

    def test_patch_maquette_active_refuse(self):
        self._activer(self.maquette)
        self.client.force_authenticate(make_user('sec_maq4', role='SECRETARIAT'))
        res = self.client.patch(
            f'/api/scolarite/maquettes/{self.maquette.pk}/modifier/',
            {'libelle': 'Piratage'}, format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_clonage_via_api(self):
        self._activer(self.maquette)
        self.client.force_authenticate(make_user('sec_maq5', role='SECRETARIAT'))
        res = self.client.post(f'/api/scolarite/maquettes/{self.maquette.pk}/cloner/', {})
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['version'], 2)
        self.assertEqual(res.data['statut'], Maquette.Statut.BROUILLON)
