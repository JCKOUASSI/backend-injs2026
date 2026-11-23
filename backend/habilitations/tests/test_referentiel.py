"""U1 — Rôles métier et permissions atomiques (structure du référentiel)."""
from django.db import IntegrityError
from django.test import TestCase

from habilitations.models import PermissionMetier
from habilitations.services.validations import (
    declarer_incompatibilite,
    mettre_a_jour_disponibilite_roles,
)

from .helpers import creer_permission, creer_role


class RoleMetierTests(TestCase):
    def test_role_disponible_sans_module_requis(self):
        role = creer_role('ROLE_GENERIQUE')
        self.assertTrue(role.module_est_installe())
        self.assertTrue(role.rendre_disponibilite())

    def test_role_actif_quand_le_module_requis_existe(self):
        role = creer_role('ROLE_STAGES', module_requis='stages')
        self.assertTrue(role.module_est_installe())

    def test_role_indisponible_quand_le_module_est_absent(self):
        role = creer_role('ROLE_FANTAISIE', module_requis='application_inexistante')
        self.assertFalse(role.module_est_installe())
        disponibilite = role.rendre_disponibilite(enregistrer=True)
        self.assertFalse(disponibilite)
        role.refresh_from_db()
        self.assertFalse(role.disponible)

    def test_mise_a_jour_globale_ne_leve_jamais_d_erreur(self):
        creer_role('ROLE_OK', module_requis='formations', disponible=False)
        creer_role('ROLE_KO', module_requis='n_existe_pas', disponible=True)
        disponibles, indisponibles = mettre_a_jour_disponibilite_roles()
        self.assertIn('ROLE_OK', disponibles)
        self.assertIn('ROLE_KO', indisponibles)

    def test_code_role_unique(self):
        creer_role('DOUBLON')
        with self.assertRaises(IntegrityError):
            creer_role('DOUBLON', libelle='Autre')

    def test_incompatibilite_declaree_dans_les_deux_sens(self):
        notes = creer_role('GEST_NOTES')
        jury = creer_role('RESP_JURY')
        declarer_incompatibilite(notes, jury)
        self.assertIn(jury, notes.incompatible_avec.all())
        self.assertIn(notes, jury.incompatible_avec.all())


class PermissionMetierTests(TestCase):
    def test_le_code_est_derive_de_la_quadruple(self):
        permission = creer_permission(
            code_module='evaluations', ressource='note', action='valider')
        self.assertEqual(permission.code, 'evaluations.note.valider')

    def test_les_treize_actions_sont_proposees(self):
        # U3 : les treize verbes canoniques restent tous proposés (extension
        # additive R2) ; l'annexe A3 ajoute des verbes métier (saisir,
        # signer, verrouiller…), d'où une inclusion plutôt qu'un décompte figé.
        treize_canoniques = {
            'consulter', 'creer', 'modifier', 'soumettre', 'valider',
            'rejeter', 'publier', 'annuler', 'exporter', 'imprimer',
            'archiver', 'supprimer', 'administrer',
        }
        self.assertTrue(treize_canoniques.issubset(set(PermissionMetier.Action.values)))
        self.assertGreaterEqual(len(PermissionMetier.Action.values), 13)

    def test_une_consultation_n_est_pas_journalisee_par_defaut(self):
        permission = creer_permission(action=PermissionMetier.Action.CONSULTER)
        self.assertFalse(permission.journalisee)

    def test_une_modification_est_journalisee_par_defaut(self):
        permission = creer_permission(action=PermissionMetier.Action.MODIFIER)
        self.assertTrue(permission.journalisee)

    def test_code_permission_unique(self):
        creer_permission(code_module='x', ressource='r', action='creer')
        with self.assertRaises(IntegrityError):
            creer_permission(code_module='x', ressource='r', action='creer')

    def test_permission_critique_porte_ses_exigences(self):
        permission = creer_permission(
            code_module='jurys', ressource='pv', action='signer',
            criticite=PermissionMetier.Criticite.CRITIQUE,
            necessite_motif=True, necessite_double_validation=True)
        self.assertEqual(permission.criticite, 'CRITIQUE')
        self.assertTrue(permission.necessite_double_validation)
