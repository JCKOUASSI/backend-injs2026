"""Tests de la complétion du module Utilisateurs (2026-09) — LOT 1.

Couvre :
* l'organisation institutionnelle additique (Direction → Département →
  Service existant) et les rattachements compte ↔ organisation ;
* le référentiel étendu aux 46 rôles cibles J2 du prompt module
  Utilisateurs : chargement, caractéristiques, permissions dérivées,
  idempotence, absence d'anomalie (0 rôle sans permission, 0 permission
  orpheline).

Aucun comportement existant n'est modifié : les tests de régression des
unités U1–U5 restent la référence.
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import ProtectedError
from rest_framework.test import APITestCase

from administrations.models import Departement, Direction
from habilitations.models import CompteUtilisateur, RoleMetier
from habilitations.referentiel.chargement import (
    charger_referentiel,
    niveaux_du_role,
)
from habilitations.referentiel.catalogue_matrice import NIVEAUX_ROLES_CIBLES
from habilitations.referentiel.catalogue_roles import ROLES

from . import _u5_fixtures as fx

User = get_user_model()

#: Rôles de la section « CIBLES (J2) » du catalogue (ordre >= 360).
ROLES_CIBLES = [ligne for ligne in ROLES if ligne[8] >= 360]


class ReferentielRolesCiblesTests(APITestCase):
    """Le référentiel étendu se charge sans anomalie (portails qualité U3).

    Le catalogue RBAC est un CATALOGUE en lecture seule : il est chargé UNE
    fois par classe dans `setUpTestData` (transaction annulée en fin de
    classe). Le recharger dans chaque test enchaînait cinq chargements
    complets — des milliers d'`update_or_create` — dans UNE SEULE
    transaction : la transaction s'allongeait démesurément et chaque
    rechargement devenait quadrativement plus coûteux (36 minutes mesurées
    pour la seule exécution de test_06, contre 11 s pour le fichier entier
    exécuté seul). Le test d'idempotence est isolé dans sa propre classe
    pour disposer d'une transaction dédiée.
    """

    @classmethod
    def setUpTestData(cls):
        charger_referentiel()

    def test_01_chargement_81_roles_sans_anomalie(self):
        # Le RAPPORT du chargeur est vérifié ici : cet appel est le-sujet
        # du test, il ne peut pas être remplacé par le chargement de classe.
        rapport = charger_referentiel()
        self.assertEqual(rapport.roles, len(ROLES))
        self.assertEqual(len(ROLES), 81)
        self.assertEqual(rapport.roles_sans_permission, [])
        self.assertEqual(rapport.permissions_orphelines, [])
        self.assertEqual(rapport.roles_indisponibles, [])

    def test_02_tous_les_roles_cibles_portent_des_niveaux_j2(self):
        # Garde-fou de données : un rôle cible sans case de matrice serait
        # chargé sans aucune permission (anomalie signalée par le chargeur).
        sans_case = [
            code for code, *_ in ROLES_CIBLES
            if not NIVEAUX_ROLES_CIBLES.get(code)
        ]
        self.assertEqual(sans_case, [])

    def test_03_caracteristiques_des_roles_cibles(self):
        sysadmin = RoleMetier.objects.get(code='SYSADMIN')
        self.assertTrue(sysadmin.sensible)
        self.assertEqual(sysadmin.niveau_defaut, 'N4')
        finance = RoleMetier.objects.get(code='RESPONSABLE_FINANCES')
        self.assertTrue(finance.sensible)
        self.assertEqual(finance.niveau_defaut, 'N4')
        chef = RoleMetier.objects.get(code='CHEF_DEPARTEMENT')
        self.assertEqual(chef.perimetre_defaut, 'DIRECTION')
        vacataire = RoleMetier.objects.get(code='VACATAIRE')
        self.assertEqual(vacataire.perimetre_defaut, 'MODULE_ECUE')
        tuteur = RoleMetier.objects.get(code='TUTEUR_ENTREPRISE')
        self.assertEqual(tuteur.perimetre_defaut, 'PROPRE_COMPTE')
        auditeur = RoleMetier.objects.get(code='AUDITEUR')
        self.assertFalse(auditeur.sensible)
        self.assertEqual(auditeur.niveau_defaut, 'N1')

    def test_04_permissions_cibles_derivees(self):
        sysadmin = RoleMetier.objects.get(code='SYSADMIN')
        support = RoleMetier.objects.get(code='SUPPORT_IT')
        auditeur = RoleMetier.objects.get(code='AUDITEUR')
        sysadmin_codes = set(sysadmin.permissions.values_list('code', flat=True))
        support_codes = set(support.permissions.values_list('code', flat=True))
        auditeur_codes = set(auditeur.permissions.values_list('code', flat=True))
        # Le niveau parametres N4 de SYSADMIN inclut l'administration des
        # paramètres ; le N2 du support ne l'inclut pas.
        self.assertIn('parametres.parametre.administrer', sysadmin_codes)
        self.assertNotIn('parametres.parametre.administrer', support_codes)
        self.assertIn('parametres.parametre.modifier', support_codes)
        # L'auditeur (N1) consulte partout mais ne modifie rien.
        self.assertIn('scolarite.dossier_etudiant.consulter', auditeur_codes)
        self.assertNotIn('scolarite.dossier_etudiant.modifier', auditeur_codes)
        self.assertNotIn('jurys.session_jury.creer', auditeur_codes)

    def test_05_niveaux_du_role_origine_j2(self):
        niveaux, origine = niveaux_du_role('SIGNATAIRE', 'DIPLOMATION')
        self.assertEqual(origine, {'jurys': 'J2', 'diplomation': 'J2',
                                    'evaluations': 'J2',
                                    'referentiels': 'J2'})
        self.assertEqual(niveaux['jurys'], 'N3')
        # Les règles dérivées s'appliquent aussi aux rôles cibles.
        niveaux_auditeur, _ = niveaux_du_role('AUDITEUR', 'ADMINISTRATION_GENERALE')
        self.assertEqual(niveaux_auditeur.get('referentiels'), 'N1')


class IdempotenceRechargementTests(APITestCase):
    """Le rechargement du catalogue est idempotent (classe dédiée).

    Ce contrôle enchaîne DEUX chargements complets et doit donc disposer
    d'une transaction à lui seul : le partager avec les tests de
    consultation l'accumulait aux rechargements precedents et rendait
    l'exécution quadrativement plus lente. Aucun `setUpTestData` ici : la
    transaction ne contient que ce que le test produit.
    """

    def test_06_idempotence_du_rechargement(self):
        premier = charger_referentiel()
        deuxieme = charger_referentiel()
        self.assertEqual(premier.as_dict(), deuxieme.as_dict())
        self.assertEqual(RoleMetier.objects.count(), 81)


class OrganisationTests(APITestCase):
    """Direction → Département → Service (existant) et rattachements compte."""

    @classmethod
    def setUpTestData(cls):
        fx.referentiel_charge()

    def setUp(self):
        self.admin = fx.admin()

    def test_01_hierarchie_et_rattachement_service(self):
        direction = Direction.objects.create(
            code='DG', libelle='Direction générale', ordre=1)
        departement = Departement.objects.create(
            code='DIPLO', libelle='Département diplômation',
            direction=direction, ordre=1)
        from ressources_humaines.models import Service
        service = Service.objects.create(nom='Service diplômation')
        service.departement = departement
        service.save()
        self.assertEqual(direction.departements.count(), 1)
        self.assertEqual(departement.services.count(), 1)
        self.assertEqual(Service.objects.get(pk=service.pk).departement,
                         departement)
        # PROTECT : on ne supprime pas une direction qui porte un département.
        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                direction.delete()

    def test_02_departement_autonome_et_service_non_rattache(self):
        departement = Departement.objects.create(
            code='AUT', libelle='Département autonome')
        self.assertIsNone(departement.direction)
        from ressources_humaines.models import Service
        service = Service.objects.create(nom='Service sans département')
        self.assertIsNone(service.departement)

    def test_03_rattachement_compte_departements_services(self):
        from ressources_humaines.models import Service
        direction = Direction.objects.create(code='SG',
                                             libelle='Secrétariat général')
        departement = Departement.objects.create(
            code='PEDA', libelle='Département pédagogie', direction=direction)
        service = Service.objects.create(nom='Service pédagogie',
                                         departement=departement)
        compte = fx.compte_curp('org1', 'ENSEIGNANT', role_legacy='FORMATEUR',
                                cree_par=self.admin)
        compte.departements.add(departement)
        compte.services.add(service)
        self.assertEqual(compte.departements.count(), 1)
        self.assertEqual(compte.services.count(), 1)
        self.assertIn(compte, departement.comptes.all())
        self.assertIn(compte, service.comptes.all())
        # Detachement sans perte : le compte conserve son identité.
        compte.departements.clear()
        self.assertEqual(departement.comptes.count(), 0)
        self.assertEqual(CompteUtilisateur.objects.get(
            pk=compte.pk).user, User.objects.get(pk=compte.user_id))

    def test_04_compte_existants_vides_par_defaut(self):
        # Le champ additif est vide pour tout compte créé sans rattachement :
        # aucun compte existant n'est modifié.
        compte = fx.compte_curp('org2', 'AGENT_INSCRIPTIONS',
                                role_legacy='SECRETARIAT', cree_par=self.admin)
        self.assertEqual(compte.departements.count(), 0)
        self.assertEqual(compte.services.count(), 0)
