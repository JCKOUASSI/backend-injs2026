"""Tests U3 — référentiel des 35 rôles et matrice de permissions INJS.

Couvre les livrables L1 à L6 : catalogue A1/A2/A3/A6, chargement idempotent,
dérivation niveau → permissions atomiques, activation conditionnelle des
modules, séparation des tâches, permissions critiques et cohérence globale
(aucune permission orpheline, aucun rôle vide). La base de test est déjà
peuplée par la migration de données ``0005``.
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from habilitations.models import PermissionMetier, RoleMetier
from habilitations.referentiel.catalogue_modules import (
    MODULES,
    NIVEAU_VERBE,
    PERMISSIONS_CRITIQUES,
)
from habilitations.referentiel.chargement import (
    charger_referentiel,
    correspondance_legacy,
    deplier_permissions,
    desactiver_referentiel,
    module_installe,
    niveaux_du_role,
)
from habilitations.referentiel.catalogue_roles import ROLES
from habilitations.referentiel.catalogue_matrice import (
    CORRESPONDANCE_LEGACY,
    INCOMPATIBILITES,
    NIVEAUX,
    NIVEAUX_EXTRA_PROVISOIRES,
)


# ---------------------------------------------------------------------------
# Le catalogue de données lui-même
# ---------------------------------------------------------------------------
class CatalogueDonneesTests(TestCase):
    def test_01_les_35_lignes_A1_sont_chargees(self):
        # 35 lignes A1 + 46 rôles cibles J2 du prompt module Utilisateurs
        # (section « CIBLES (J2) », ordre >= 360) = 81 lignes au total.
        a1 = [l for l in ROLES if l[8] < 360]
        cibles = [l for l in ROLES if l[8] >= 360]
        self.assertEqual(len(a1), 35)
        self.assertEqual(len(cibles), 46)
        self.assertEqual(len(ROLES), 81)

    def test_02_32_roles_internes_et_3_destinataires(self):
        codes = [l[0] for l in ROLES]
        self.assertIn('ETUDIANT', codes)
        self.assertIn('CANDIDAT', codes)
        self.assertIn('CONSULTATION', codes)
        self.assertEqual(
            len([l for l in ROLES if l[2] == 'DESTINATAIRES']), 3
        )

    def test_03_les_roles_sensibles(self):
        # Les 11 rôles sensibles de l'annexe A1 sont préservés ; 11 rôles
        # cibles J2 y sont ajoutés (signature, finances, paie, SI).
        sensibles = sorted(l[0] for l in ROLES if l[6])
        self.assertEqual(sensibles, sorted([
            # A1 (11)
            'ADMIN_SYSTEME', 'DIRECTION_GENERALE', 'DIRECTION_ETUDES',
            'RESPONSABLE_CONCOURS', 'RESPONSABLE_JURY',
            'RESPONSABLE_GRADUATION', 'RESPONSABLE_DIPLOMATION',
            'GESTIONNAIRE_FINANCES_ETUD', 'VALIDATEUR_FINANCIER',
            'GESTIONNAIRE_VACATIONS', 'GESTIONNAIRE_RH',
            # Cibles J2 (11)
            'SIGNATAIRE', 'VALIDATEUR_DIPLOMES', 'BOURSE_MANAGER',
            'RESPONSABLE_FINANCES', 'CONTROLEUR_FINANCIER', 'PAIE_MANAGER',
            'SYSADMIN', 'NETWORK_ADMIN', 'DB_ADMIN', 'SECURITY_ADMIN',
            'API_MANAGER',
        ]))

    def test_04_codes_uniques_et_attributs_complets(self):
        codes = [l[0] for l in ROLES]
        self.assertEqual(len(codes), len(set(codes)))
        for ligne in ROLES:
            self.assertTrue(ligne[0].isupper())
            self.assertIn(ligne[3], ('N0', 'N1', 'N2', 'N3', 'N4'))
            self.assertTrue(ligne[1] and ligne[9])

    def test_05_canaux_mobiles_imposes(self):
        par_code = {l[0]: l for l in ROLES}
        self.assertEqual(par_code['ENSEIGNANT'][7], 'MOBILE')
        self.assertEqual(par_code['ETUDIANT'][7], 'MOBILE')
        self.assertEqual(par_code['CANDIDAT'][7], '')

    def test_06_perimetres_defaut_cles(self):
        par_code = {l[0]: l for l in ROLES}
        self.assertEqual(par_code['ETUDIANT'][4], 'PROPRE_COMPTE')
        self.assertEqual(par_code['ADMIN_SYSTEME'][4], 'INJS_ENTIER')
        self.assertEqual(par_code['ENSEIGNANT'][4], 'MODULE_ECUE')
        self.assertEqual(par_code['SCOLARITE'][4], 'SECRETARIAT')

    def test_07_vingt_modules_A3(self):
        self.assertEqual(len(MODULES), 20)

    def test_08_chargement_joker_en_13_verbes(self):
        codes = [p['code'] for p in deplier_permissions()]
        for verbe in (
            'consulter', 'creer', 'modifier', 'soumettre', 'valider',
            'rejeter', 'publier', 'annuler', 'exporter', 'imprimer',
            'archiver', 'supprimer', 'administrer',
        ):
            self.assertIn(f'administration.compte.{verbe}', codes)

    def test_09_verbes_metier_A3_presents_dans_le_catalogue(self):
        actions = {p['action'] for p in deplier_permissions()}
        for verbe in (
            'saisir', 'verrouiller', 'signer', 'generer', 'editer',
            'revoquer', 'deposer', 'instruire', 'decider', 'ouvrir',
            'cloturer', 'forcer', 'certifier', 'deplacer', 'remplacer',
            'resoudre', 'calculer', 'configurer',
        ):
            self.assertIn(verbe, actions)

    def test_10_tous_les_codes_sont_qualifies(self):
        for permission in deplier_permissions():
            self.assertEqual(len(permission['code'].split('.')), 3)

    def test_11_niveaux_verbes_coherents(self):
        self.assertEqual(NIVEAU_VERBE['consulter'], 0)
        self.assertEqual(NIVEAU_VERBE['creer'], 2)
        self.assertEqual(NIVEAU_VERBE['valider'], 3)
        self.assertEqual(NIVEAU_VERBE['supprimer'], 4)
        self.assertEqual(NIVEAU_VERBE['verrouiller'], 3)

    def test_12_permissions_critiques_repertoriees(self):
        self.assertIn('jurys.pv.signer', PERMISSIONS_CRITIQUES)
        self.assertIn('evaluations.note.verrouiller', PERMISSIONS_CRITIQUES)
        self.assertIn('diplomation.diplome.revoquer', PERMISSIONS_CRITIQUES)
        self.assertIn('presences.emargement.forcer', PERMISSIONS_CRITIQUES)
        self.assertIn('exports.export_sensible.generer', PERMISSIONS_CRITIQUES)

    def test_13_cinq_couples_incompatibilite(self):
        self.assertEqual(len(INCOMPATIBILITES), 5)
        codes = {tuple(sorted(c)) for c in INCOMPATIBILITES}
        self.assertIn(
            tuple(sorted(('GESTIONNAIRE_NOTES', 'RESPONSABLE_JURY'))), codes
        )

    def test_14_correspondance_legacy_A6_complete(self):
        self.assertEqual(len(CORRESPONDANCE_LEGACY), 12)
        codes_roles = {l[0] for l in ROLES}
        for cibles in CORRESPONDANCE_LEGACY.values():
            self.assertTrue(cibles)
            for cible in cibles:
                self.assertIn(cible, codes_roles)

    def test_15_niveaux_A2_administration_systeme(self):
        self.assertEqual(
            set(NIVEAUX['ADMIN_SYSTEME'].values()), {'N4'}
        )
        self.assertEqual(len(NIVEAUX['ADMIN_SYSTEME']), 15)

    def test_16_consultation_est_sans_action(self):
        # Aucune case N2+ : le rôle de consultation ne peut que lire.
        for niveau in NIVEAUX['CONSULTATION'].values():
            self.assertIn(niveau, ('N0', 'N1'))

    def test_17_references_de_donnees_toutes_resolubles(self):
        from habilitations.referentiel.catalogue_modules import (
            MODULES as CAT_MODULES,
            PERMISSIONS_AVEC_MOTIF as AVEC_MOTIF,
            PERMISSIONS_CRITIQUES as CRITIQUES,
            PERMISSIONS_USAGERS as USAGERS,
            RESSOURCES,
        )
        codes = {p['code'] for p in deplier_permissions()}
        # Les permissions critiques, à motif et d'auto-démarche existent.
        for code in CRITIQUES | AVEC_MOTIF:
            self.assertIn(code, codes)
        for code in (c for tuples in USAGERS.values() for c in tuples):
            self.assertIn(code, codes)
        # Tous les modules décrits sont déclarés et réciproquement.
        self.assertEqual(set(RESSOURCES), set(CAT_MODULES))
        # Tous les codes de rôles cités par la matrice, les incompatibilités
        # et la table A6 correspondent à un rôle A1 chargé.
        codes_roles = {ligne[0] for ligne in ROLES}
        for source in (NIVEAUX, NIVEAUX_EXTRA_PROVISOIRES):
            for code_role in source:
                self.assertIn(code_role, codes_roles)
        for pair in INCOMPATIBILITES:
            for code_role in pair:
                self.assertIn(code_role, codes_roles)
        for cibles in CORRESPONDANCE_LEGACY.values():
            for code_role in cibles:
                self.assertIn(code_role, codes_roles)


# ---------------------------------------------------------------------------
# Le chargement en base
# ---------------------------------------------------------------------------
class ChargementBaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # La migration 0005 a déjà tout chargé ; on s'assure que les chiffres
        # attendus sont bien là dans une base de test migrée.
        cls.rapport = charger_referentiel()

    def test_20_81_roles_et_permissions_en_base(self):
        self.assertEqual(RoleMetier.objects.count(), 81)
        self.assertEqual(self.rapport.roles, 81)
        self.assertGreater(PermissionMetier.objects.count(), 900)

    def test_21_aucune_permission_orpheline(self):
        self.assertEqual(self.rapport.permissions_orphelines, [])

    def test_22_aucun_role_vide(self):
        self.assertEqual(self.rapport.roles_sans_permission, [])
        for role in RoleMetier.objects.all():
            self.assertGreater(role.permissions.count(), 0)

    def test_23_idempotence(self):
        avant = RoleMetier.objects.count(), PermissionMetier.objects.count()
        rapport2 = charger_referentiel()
        apres = RoleMetier.objects.count(), PermissionMetier.objects.count()
        self.assertEqual(avant, apres)
        self.assertEqual(rapport2.permissions_orphelines, [])

    def test_24_dry_run_necrit_rien(self):
        avant_p = PermissionMetier.objects.count()
        rapport = charger_referentiel(dry_run=True)
        self.assertEqual(PermissionMetier.objects.count(), avant_p)
        self.assertEqual(rapport.permissions, avant_p)

    def test_25_desactivation_non_destructive(self):
        desactiver_referentiel()
        self.assertEqual(RoleMetier.objects.filter(actif=True).count(), 0)
        self.assertEqual(PermissionMetier.objects.filter(actif=True).count(), 0)
        # Les lignes ne sont pas supprimées.
        self.assertEqual(RoleMetier.objects.count(), 81)


# ---------------------------------------------------------------------------
# Dérivation niveau → permissions : accord et refus par rôle
# ---------------------------------------------------------------------------
class MatriceAccordRefusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        charger_referentiel()

    def _codes(self, code_role):
        role = RoleMetier.objects.get(code=code_role)
        return set(role.permissions.values_list('code', flat=True))

    def test_30_admin_systeme_a_tout_le_catalogue(self):
        codes = self._codes('ADMIN_SYSTEME')
        self.assertEqual(len(codes), PermissionMetier.objects.count())

    def test_31_gestionnaire_notes_saisit_mais_ne_valide_pas(self):
        codes = self._codes('GESTIONNAIRE_NOTES')
        self.assertIn('evaluations.note.saisir', codes)
        self.assertNotIn('evaluations.note.valider', codes)
        self.assertNotIn('evaluations.note.verrouiller', codes)

    def test_32_responsable_jury_signe_les_pv(self):
        codes = self._codes('RESPONSABLE_JURY')
        self.assertIn('jurys.pv.signer', codes)
        self.assertIn('jurys.resultat.publier', codes)

    def test_33_gestionnaire_notes_ne_signe_pas_les_pv(self):
        codes = self._codes('GESTIONNAIRE_NOTES')
        self.assertNotIn('jurys.pv.signer', codes)

    def test_34_responsable_ue_ecue_verrouille_les_notes(self):
        codes = self._codes('RESPONSABLE_UE_ECUE')
        self.assertIn('evaluations.note.verrouiller', codes)

    def test_35_enseignant_ne_verrouille_pas(self):
        codes = self._codes('ENSEIGNANT')
        self.assertIn('evaluations.note.saisir', codes)
        self.assertNotIn('evaluations.note.verrouiller', codes)
        self.assertNotIn('evaluations.note.valider', codes)

    def test_36_finances_separation_saisie_validation(self):
        # Le niveau N2 (saisie) ne peut pas valider ; le N3 (validation)
        # obtient bien l'acte de validation. La séparation des tâches entre
        # les DEUX titulaires est garantie par l'incompatibilité de cumul J5
        # (test 51), conformément à la dérivation « verbe de niveau ≤ N ».
        saisie = self._codes('GESTIONNAIRE_FINANCES_ETUD')
        validation = self._codes('VALIDATEUR_FINANCIER')
        self.assertIn('finances_etud.paiement.saisir', saisie)
        self.assertNotIn('finances_etud.paiement.valider', saisie)
        self.assertIn('finances_etud.paiement.valider', validation)
        self.assertIn('finances_etud.remboursement.valider', validation)
        self.assertNotIn('finances_etud.remboursement.valider', saisie)

    def test_37_direction_generale_ne_supprime_pas_la_scolarite(self):
        codes = self._codes('DIRECTION_GENERALE')
        self.assertNotIn('scolarite.dossier_etudiant.supprimer', codes)
        self.assertIn('diplomation.diplome.valider', codes)

    def test_38_candidat_depose_son_propre_dossier_et_voit_rien_dautre(self):
        codes = self._codes('CANDIDAT')
        self.assertIn('candidatures.candidature.creer', codes)
        self.assertIn('candidatures.candidature.soumettre', codes)
        self.assertNotIn('candidatures.candidature.valider', codes)
        self.assertFalse(any(c.startswith('scolarite.') for c in codes))

    def test_39_etudiant_actes_limites_et_lecture_finance(self):
        codes = self._codes('ETUDIANT')
        self.assertIn('presences.justificatif.deposer', codes)
        self.assertNotIn('presences.emargement.forcer', codes)
        # A2 donne à l'étudiant une lecture N1 de ses frais : aucune écriture,
        # et aucun accès à la rémunération des formateurs.
        self.assertFalse(any(c.startswith('finances_form.') for c in codes))
        for code in codes:
            if code.startswith('finances_etud.'):
                verbe = code.split('.')[-1]
                self.assertLess(NIVEAU_VERBE[verbe], 2, code)

    def test_40_agent_inscriptions_lecture_finance_sans_ecriture(self):
        codes = self._codes('AGENT_INSCRIPTIONS')
        self.assertIn('scolarite.inscription_administrative.creer', codes)
        # N1 finances (statut de paiement à l'inscription) : aucune écriture.
        for code in codes:
            if code.startswith('finances_etud.'):
                verbe = code.split('.')[-1]
                self.assertLess(NIVEAU_VERBE[verbe], 2, code)

    def test_41_consultation_ne_peut_que_consulter(self):
        codes = self._codes('CONSULTATION')
        verbes = {c.split('.')[-1] for c in codes}
        self.assertIn('consulter', verbes)
        for interdit in ('creer', 'modifier', 'supprimer', 'valider', 'signer'):
            self.assertNotIn(interdit, verbes)

    def test_42_archiviste_lit_tout_mais_ne_modifie_rien(self):
        codes = self._codes('ARCHIVISTE')
        self.assertIn('scolarite.dossier_etudiant.consulter', codes)
        verbes = {c.split('.')[-1] for c in codes}
        self.assertNotIn('supprimer', verbes)
        self.assertNotIn('modifier', verbes)

    def test_43_export_sensible_reserve_au_niveau_4(self):
        admin = self._codes('ADMIN_SYSTEME')
        scolarite = self._codes('SCOLARITE')
        self.assertIn('exports.export_sensible.generer', admin)
        self.assertNotIn('exports.export_sensible.generer', scolarite)
        # Un rôle avec statistiques N1 garde les exports courants.
        self.assertIn('exports.export.generer', scolarite)

    def test_44_scolarite_n2_n3_selon_les_modules(self):
        codes = self._codes('SCOLARITE')
        # N3 en scolarité → valider ; N2 en pédagogie → saisir sans valider.
        self.assertIn('scolarite.dossier_etudiant.valider', codes)
        self.assertIn('pedagogie.ue.creer', codes)
        self.assertNotIn('pedagogie.ue.valider', codes)

    def test_45_diplome_revoquer_reserve(self):
        diplo = self._codes('RESPONSABLE_DIPLOMATION')
        self.assertIn('diplomation.diplome.revoquer', diplo)
        self.assertNotIn(
            'diplomation.diplome.revoquer',
            self._codes('RESPONSABLE_GRADUATION'),
        )


# ---------------------------------------------------------------------------
# Règles transversales, activation conditionnelle et A6
# ---------------------------------------------------------------------------
class ReglesTransversalesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        charger_referentiel()

    def test_50_incompatibilites_bilaterales_en_base(self):
        notes = RoleMetier.objects.get(code='GESTIONNAIRE_NOTES')
        jury = RoleMetier.objects.get(code='RESPONSABLE_JURY')
        self.assertIn(jury, notes.incompatible_avec.all())
        self.assertIn(notes, jury.incompatible_avec.all())

    def test_51_les_cinq_couples_sont_bilateraux(self):
        for code_a, code_b in INCOMPATIBILITES:
            a = RoleMetier.objects.get(code=code_a)
            b = RoleMetier.objects.get(code=code_b)
            self.assertIn(b, a.incompatible_avec.all())
            self.assertIn(a, b.incompatible_avec.all())

    def test_52_permissions_critiques_honorees_en_base(self):
        for code in PERMISSIONS_CRITIQUES:
            permission = PermissionMetier.objects.get(code=code)
            self.assertEqual(permission.criticite, 'CRITIQUE', code)
            self.assertTrue(permission.necessite_double_validation, code)
            self.assertTrue(permission.necessite_motif, code)
            self.assertTrue(permission.journalisee, code)

    def test_53_consulter_nest_pas_journalise(self):
        permission = PermissionMetier.objects.get(
            code='scolarite.dossier_etudiant.consulter'
        )
        self.assertFalse(permission.journalisee)

    def test_54_module_present_donne_disponible(self):
        self.assertTrue(module_installe('scolarite'))
        self.assertTrue(module_installe(''))
        self.assertFalse(module_installe('module_inexistant_xyz'))

    def test_55_role_indisponible_si_module_absent(self):
        from unittest import mock
        # On simule une installation dont l'application « admissions » est
        # absente : les rôles candidatures deviennent indisponibles, sans
        # erreur et sans empêcher le chargement des autres rôles.
        def detection(app_label):
            return app_label != 'admissions'

        with mock.patch(
            'habilitations.referentiel.chargement.module_installe',
            side_effect=detection,
        ):
            rapport = charger_referentiel()
        self.assertIn('AGENT_CANDIDATURE', rapport.roles_indisponibles)
        self.assertNotIn('AGENT_INSCRIPTIONS', rapport.roles_indisponibles)

    def test_56_correspondance_legacy_chargee(self):
        table = correspondance_legacy()
        self.assertEqual(table['ADMIN'], ['ADMIN_SYSTEME'])
        self.assertEqual(table['DIRECTION'], ['DIRECTION_GENERALE'])
        self.assertIn('ENSEIGNANT', table['FORMATEUR'])
        self.assertEqual(table['AUDITEUR'], ['ETUDIANT'])

    def test_57_les_douze_roles_legacy_existent_toujours(self):
        from authentication.models import User
        valeurs = set(User.Role.values)
        for code in CORRESPONDANCE_LEGACY:
            self.assertIn(code, valeurs)

    def test_58_commande_chargement_avec_dry_run(self):
        sortie = StringIO()
        call_command('charger_referentiel_injs', '--dry-run', stdout=sortie)
        self.assertIn('[simulation]', sortie.getvalue())
        self.assertIn('81 rôles', sortie.getvalue())

    def test_59_commande_chargement_reel(self):
        sortie = StringIO()
        call_command('charger_referentiel_injs', stdout=sortie)
        self.assertIn('Cohérence', sortie.getvalue())

    def test_60_generation_document_matrice(self):
        from habilitations.management.commands.generer_matrice_habilitations import (
            generer_contenu,
        )
        contenu = generer_contenu()
        self.assertIn('PROVISOIRE', contenu)
        self.assertIn('ADMIN_SYSTEME', contenu)
        self.assertIn('ETUDIANT', contenu)
        self.assertIn('Incompatibilités', contenu)
        for module in NIVEAUX['ADMIN_SYSTEME']:
            self.assertIn(module, contenu)

    def test_61_aucun_role_ne_recouvre_un_module_hors_droits(self):
        # L'enseignant n'a aucun droit finances, RH, patrimoine, administration.
        codes = set(
            RoleMetier.objects.get(code='ENSEIGNANT')
            .permissions.values_list('code', flat=True)
        )
        for module in ('administration', 'finances_etud', 'finances_form',
                       'rh', 'patrimoine', 'parametres'):
            self.assertFalse(
                any(c.startswith(module + '.') for c in codes), module
            )

    def test_62_aucune_permission_en_double(self):
        codes = list(PermissionMetier.objects.values_list('code', flat=True))
        self.assertEqual(len(codes), len(set(codes)))

    def test_63_module_requis_renseigne_sur_les_roles_conditionnels(self):
        role = RoleMetier.objects.get(code='GESTIONNAIRE_STAGES')
        self.assertEqual(role.module_requis, 'stages')
        interne = RoleMetier.objects.get(code='ADMIN_SYSTEME')
        self.assertEqual(interne.module_requis, '')

    def test_64_un_accord_et_un_refus_pour_chacun_des_81_roles(self):
        # ACCORD : chaque rôle détient au moins une permission d'un module que
        # sa matrice (A2 ou cases J2) lui ouvre. REFUS : la permission
        # d'administration des paramètres (verbe N4) n'est détenue que par les
        # rôles N4 du module parametres — ADMIN_SYSTEME (A2) et SYSADMIN (J2).
        roles = list(RoleMetier.objects.prefetch_related('permissions'))
        self.assertEqual(len(roles), 81)
        n4_parametres = {'ADMIN_SYSTEME', 'SYSADMIN'}
        for role in roles:
            codes = set(role.permissions.values_list('code', flat=True))
            self.assertTrue(codes, f'{role.code} sans permission')
            niveaux, _ = niveaux_du_role(role.code, role.domaine)
            ouvert = any(
                any(c.split('.')[0] == module for c in codes)
                for module in niveaux
            )
            self.assertTrue(ouvert, f'{role.code} aucune permission de ses cases')
            if role.code not in n4_parametres:
                self.assertNotIn(
                    'parametres.parametre.administrer', codes, role.code
                )
        detenants = sorted(
            role.code for role in roles
            if role.permissions.filter(
                code='parametres.parametre.administrer'
            ).exists()
        )
        self.assertEqual(detenants, sorted(n4_parametres))


# ---------------------------------------------------------------------------
# La migration de données elle-même (son peuplement est neutralisé pendant la
# constitution de la base de test pour préserver les tests U1/U2 ; on la prouve
# ici en l'appelant explicitement).
# ---------------------------------------------------------------------------
class MigrationChargementTests(TestCase):
    def _module_migration(self):
        import importlib.util
        from pathlib import Path
        chemin = (
            Path(__file__).resolve().parents[1] / 'migrations'
            / '0005_charger_referentiel_injs.py'
        )
        spec = importlib.util.spec_from_file_location('migration_u3_0005', chemin)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_70_migration_peuple_idempotemment_puis_desactive_sans_supprimer(self):
        import os
        from unittest import mock
        migration = self._module_migration()
        # En contexte de test, la base démarre sans référentiel (R5) : la
        # migration est neutralisée ; on la force explicitement pour la prouver.
        self.assertEqual(RoleMetier.objects.count(), 0)
        self.assertEqual(PermissionMetier.objects.count(), 0)

        with mock.patch.dict(os.environ, {'CURP_FORCER_REFERENTIEL': '1'}):
            migration.charger(None, None)
            self.assertEqual(RoleMetier.objects.count(), 81)
            self.assertEqual(
                PermissionMetier.objects.count(), len(deplier_permissions())
            )
            self.assertTrue(RoleMetier.objects.get(code='ADMIN_SYSTEME').actif)

            # Repasser la migration ne crée aucun doublon.
            migration.charger(None, None)
            self.assertEqual(RoleMetier.objects.count(), 81)
            self.assertEqual(
                PermissionMetier.objects.count(), len(deplier_permissions())
            )

            # Le retour arrière désactive sans supprimer.
            migration.decharger(None, None)

        self.assertEqual(RoleMetier.objects.filter(actif=True).count(), 0)
        self.assertEqual(PermissionMetier.objects.filter(actif=True).count(), 0)
        self.assertEqual(RoleMetier.objects.count(), 81)
        self.assertEqual(
            PermissionMetier.objects.count(), len(deplier_permissions())
        )
