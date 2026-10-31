"""CRUD des UE et ECUE avec cycle de vie Brouillon → Activé → Désactivé.

Ces tests fixent le comportement attendu par l'écran « UE / ECUE » : on crée,
on consulte, on modifie et on supprime une unité ou un élément — mais jamais
n'importe comment. Les règles défendues ici sont celles qui protègent les
données pédagogiques :

1. **on ne modifie qu'un brouillon** — un élément activé est publié ; le
   réécrire en place effacerait la trace de ce qui a été publié ;
2. **on ne supprime qu'un brouillon**, jamais en cascade silencieuse (une UE
   qui porte des ECUE refuse sa suppression et dit combien) ;
3. **les transitions de statut sont une matrice explicite**, pas un champ
   libre : `ACTIVE → BROUILLON` est refusé, `ACTIVE → DESACTIVEE` accepté ;
4. **une ECUE ne s'active pas sous une UE en brouillon** ;
5. **désactiver une UE retire ses ECUE actives**, et le dit ;
6. **une maquette validée/active/archivée gèle tout**, quel que soit le statut.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import RefFormation

from scolarite.models import (
    AnneeAcademique,
    ECUE,
    Maquette,
    Niveau,
    Semestre,
    UE,
)


def make_user(username, role='SECRETARIAT'):
    return User.objects.create_user(username=username, password='pass', role=role)


class UEECUEBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31',
            courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.s1 = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('sec_ue', 'SECRETARIAT'))

    def _creer_ue(self, code='UE11', credits=6):
        res = self.client.post(
            f'/api/scolarite/maquettes/{self.maquette.id}/ues/',
            {'semestre_id': self.s1.id, 'code': code, 'intitule': 'Sciences du mouvement',
             'credits': credits},
            format='json',
        )
        self.assertEqual(res.status_code, 201, res.data)
        return res.data['id']

    def _creer_ecue(self, ue_id, code='ECUE111', credits=6):
        res = self.client.post(
            f'/api/scolarite/ues/{ue_id}/ecues/',
            {'code': code, 'intitule': 'Anatomie', 'credits': credits, 'volume_cm': 20},
            format='json',
        )
        self.assertEqual(res.status_code, 201, res.data)
        return res.data['id']

    def _statut_ue(self, ue_id, statut):
        return self.client.post(f'/api/scolarite/ues/{ue_id}/statut/',
                                {'statut': statut}, format='json')

    def _statut_ecue(self, ecue_id, statut):
        return self.client.post(f'/api/scolarite/ecues/{ecue_id}/statut/',
                                {'statut': statut}, format='json')


class CreationEtLectureTests(UEECUEBase):
    def test_creation_ue_renvoie_l_objet_complet_en_brouillon(self):
        ue_id = self._creer_ue()
        ue = UE.objects.get(pk=ue_id)
        self.assertEqual(ue.statut, UE.Statut.BROUILLON)
        # Le POST renvoie l'objet sérialisé : l'écran n'a pas besoin d'un
        # second appel pour afficher la ligne qu'il vient de créer.
        res = self.client.post(
            f'/api/scolarite/maquettes/{self.maquette.id}/ues/',
            {'semestre_id': self.s1.id, 'code': 'UE12', 'intitule': 'Physiologie',
             'credits': 3},
            format='json',
        )
        self.assertEqual(res.data['statut'], 'BROUILLON')
        self.assertEqual(res.data['code'], 'UE12')
        self.assertIn('semestre', res.data)
        self.assertIn('ecues', res.data)

    def test_creation_ecue_en_brouillon_et_listee_sous_l_ue(self):
        ue_id = self._creer_ue()
        self._creer_ecue(ue_id)
        res = self.client.get(f'/api/scolarite/maquettes/{self.maquette.id}/ues/')
        self.assertEqual(res.status_code, 200)
        ligne = res.data[0]
        self.assertEqual(ligne['statut'], 'BROUILLON')
        self.assertEqual(ligne['ecues'][0]['statut'], 'BROUILLON')
        self.assertEqual(ligne['ecues'][0]['code'], 'ECUE111')

    def test_creation_refusee_sans_code(self):
        res = self.client.post(
            f'/api/scolarite/maquettes/{self.maquette.id}/ues/',
            {'semestre_id': self.s1.id}, format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_code_ue_unique_dans_la_maquette(self):
        self._creer_ue('UE11')
        res = self.client.post(
            f'/api/scolarite/maquettes/{self.maquette.id}/ues/',
            {'semestre_id': self.s1.id, 'code': 'ue11', 'intitule': 'Doublon'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_creation_ecue_sous_une_ue_inconnue(self):
        res = self.client.post('/api/scolarite/ues/999999/ecues/',
                               {'code': 'X'}, format='json')
        self.assertEqual(res.status_code, 404)


class CycleDeVieUETests(UEECUEBase):
    def test_brouillon_modifiable_puis_actif_non_modifiable(self):
        ue_id = self._creer_ue()
        res = self.client.patch(f'/api/scolarite/ues/{ue_id}/',
                                {'intitule': 'Sciences du mouvement (révisé)'},
                                format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['intitule'], 'Sciences du mouvement (révisé)')

        res = self._statut_ue(ue_id, 'ACTIVE')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['statut'], 'ACTIVE')

        res = self.client.patch(f'/api/scolarite/ues/{ue_id}/',
                                {'intitule': 'Piratage'}, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertIn('brouillon', res.data['error'].lower())
        UE.objects.get(pk=ue_id)
        self.assertEqual(UE.objects.get(pk=ue_id).intitule, 'Sciences du mouvement (révisé)')

    def test_activation_puis_desactivation_puis_retour_brouillon(self):
        ue_id = self._creer_ue()
        self.assertEqual(self._statut_ue(ue_id, 'ACTIVE').status_code, 200)
        self.assertEqual(self._statut_ue(ue_id, 'DESACTIVEE').status_code, 200)
        res = self._statut_ue(ue_id, 'BROUILLON')
        self.assertEqual(res.status_code, 200)
        # De retour en brouillon : la modification redevient possible.
        res = self.client.patch(f'/api/scolarite/ues/{ue_id}/',
                                {'credits': 4}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['credits'], 4)

    def test_transition_active_vers_brouillon_refusee(self):
        ue_id = self._creer_ue()
        self._statut_ue(ue_id, 'ACTIVE')
        res = self._statut_ue(ue_id, 'BROUILLON')
        self.assertEqual(res.status_code, 409)
        self.assertIn('transitions_autorisees', res.data)

    def test_statut_inconnu_refuse(self):
        ue_id = self._creer_ue()
        res = self._statut_ue(ue_id, 'PUBLIE')
        self.assertEqual(res.status_code, 400)
        self.assertIn('statuts_possibles', res.data)

    def test_statut_inchange_refuse(self):
        ue_id = self._creer_ue()
        res = self._statut_ue(ue_id, 'BROUILLON')
        self.assertEqual(res.status_code, 400)


class CycleDeVieECUETests(UEECUEBase):
    def test_ecue_ne_s_active_pas_sous_une_ue_brouillon(self):
        ue_id = self._creer_ue()
        ecue_id = self._creer_ecue(ue_id)
        res = self._statut_ecue(ecue_id, 'ACTIVE')
        self.assertEqual(res.status_code, 409)
        self.assertIn('activez d\'abord l\'UE', res.data['error'])
        self.assertEqual(ECUE.objects.get(pk=ecue_id).statut, ECUE.Statut.BROUILLON)

    def test_ecue_active_quand_l_ue_l_est(self):
        ue_id = self._creer_ue()
        ecue_id = self._creer_ecue(ue_id)
        self._statut_ue(ue_id, 'ACTIVE')
        res = self._statut_ecue(ecue_id, 'ACTIVE')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['statut'], 'ACTIVE')

    def test_desactiver_une_ue_desactive_ses_ecue_actives(self):
        ue_id = self._creer_ue()
        ecue_a = self._creer_ecue(ue_id, 'ECUE111')
        ecue_b = self._creer_ecue(ue_id, 'ECUE112')
        self._statut_ue(ue_id, 'ACTIVE')
        self._statut_ecue(ecue_a, 'ACTIVE')
        self._statut_ecue(ecue_b, 'ACTIVE')

        res = self._statut_ue(ue_id, 'DESACTIVEE')
        self.assertEqual(res.status_code, 200, res.data)
        # La cascade est une décision, pas un effet de bord muet : elle est
        # annoncée dans la réponse et les deux ECUE sont bien désactivées.
        self.assertEqual(sorted(res.data['ecues_desactivees']), ['ECUE111', 'ECUE112'])
        self.assertEqual(
            ECUE.objects.filter(statut=ECUE.Statut.DESACTIVEE).count(), 2,
        )


class SuppressionTests(UEECUEBase):
    def test_suppression_ecue_brouillon(self):
        ue_id = self._creer_ue()
        ecue_id = self._creer_ecue(ue_id)
        res = self.client.delete(f'/api/scolarite/ecues/{ecue_id}/')
        self.assertEqual(res.status_code, 204)
        self.assertFalse(ECUE.objects.filter(pk=ecue_id).exists())

    def test_suppression_ecue_active_refusee(self):
        ue_id = self._creer_ue()
        ecue_id = self._creer_ecue(ue_id)
        self._statut_ue(ue_id, 'ACTIVE')
        self._statut_ecue(ecue_id, 'ACTIVE')
        res = self.client.delete(f'/api/scolarite/ecues/{ecue_id}/')
        self.assertEqual(res.status_code, 400)
        self.assertTrue(ECUE.objects.filter(pk=ecue_id).exists())

    def test_suppression_ue_avec_ecue_refusee_sans_cascade(self):
        ue_id = self._creer_ue()
        self._creer_ecue(ue_id, 'ECUE111')
        self._creer_ecue(ue_id, 'ECUE112')
        res = self.client.delete(f'/api/scolarite/ues/{ue_id}/')
        self.assertEqual(res.status_code, 400)
        self.assertIn('2 ECUE', str(res.data['error']))
        self.assertTrue(UE.objects.filter(pk=ue_id).exists())
        self.assertEqual(ECUE.objects.filter(ue_id=ue_id).count(), 2)

    def test_suppression_ue_sans_ecue_brouillon(self):
        ue_id = self._creer_ue()
        res = self.client.delete(f'/api/scolarite/ues/{ue_id}/')
        self.assertEqual(res.status_code, 204)
        self.assertFalse(UE.objects.filter(pk=ue_id).exists())

    def test_suppression_ue_active_refusee(self):
        ue_id = self._creer_ue()
        self._statut_ue(ue_id, 'ACTIVE')
        res = self.client.delete(f'/api/scolarite/ues/{ue_id}/')
        self.assertEqual(res.status_code, 400)
        self.assertIn('brouillon', str(res.data['error']).lower())
        self.assertTrue(UE.objects.filter(pk=ue_id).exists())


class MaquetteVerrouilleeTests(UEECUEBase):
    def _verrouiller(self):
        self.maquette.statut = Maquette.Statut.VALIDEE
        self.maquette.save(update_fields=['statut'])

    def test_aucune_ecriture_quand_la_maquette_est_validee(self):
        ue_id = self._creer_ue()
        ecue_id = self._creer_ecue(ue_id)
        self._verrouiller()

        self.assertEqual(
            self.client.patch(f'/api/scolarite/ues/{ue_id}/',
                              {'intitule': 'X'}, format='json').status_code, 400,
        )
        self.assertEqual(self._statut_ue(ue_id, 'ACTIVE').status_code, 400)
        self.assertEqual(self._statut_ecue(ecue_id, 'ACTIVE').status_code, 400)
        self.assertEqual(self.client.delete(f'/api/scolarite/ecues/{ecue_id}/').status_code, 400)
        self.assertEqual(self.client.delete(f'/api/scolarite/ues/{ue_id}/').status_code, 400)
        self.assertEqual(
            self.client.post(
                f'/api/scolarite/maquettes/{self.maquette.id}/ues/',
                {'semestre_id': self.s1.id, 'code': 'UE99', 'intitule': 'Tardive'},
                format='json',
            ).status_code, 400,
        )


class PermissionsTests(UEECUEBase):
    def test_anonyme_refuse(self):
        ue_id = self._creer_ue()
        client = APIClient()
        self.assertEqual(
            client.post(f'/api/scolarite/ues/{ue_id}/statut/', {'statut': 'ACTIVE'},
                        format='json').status_code, 401,
        )
        self.assertEqual(client.get(f'/api/scolarite/maquettes/{self.maquette.id}/ues/').status_code, 401)

    def test_secretariat_peut_lister_les_maquettes_qu_il_administre(self):
        """Un secrétariat autorisé à créer des UE doit pouvoir choisir la maquette.

        Sans cette lecture, l'écran UE/ECUE restait vide pour lui alors que ses
        droits d'écriture sont réels : un écran mort derrière une permission
        plus étroite que le contenu qu'il pilote.
        """
        self.assertEqual(self.client.get('/api/scolarite/maquettes/').status_code, 200)
        self.assertEqual(
            self.client.get(f'/api/scolarite/maquettes/{self.maquette.id}/').status_code, 200,
        )

    def test_role_non_habilite_refuse(self):
        ue_id = self._creer_ue()
        client = APIClient()
        client.force_authenticate(make_user('auditeur_crud', 'AUDITEUR'))
        self.assertEqual(client.get(f'/api/scolarite/maquettes/{self.maquette.id}/ues/').status_code, 403)
        # La liste des maquettes reste fermée à un rôle sans droit sur le contenu.
        self.assertEqual(client.get('/api/scolarite/maquettes/').status_code, 403)
        self.assertEqual(
            client.post(f'/api/scolarite/ues/{ue_id}/statut/', {'statut': 'ACTIVE'},
                        format='json').status_code, 403,
        )
