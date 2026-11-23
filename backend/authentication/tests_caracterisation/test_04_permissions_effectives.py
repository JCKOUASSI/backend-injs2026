"""U0-CURP — caractérisation des PERMISSIONS Django effectives par rôle.

Les groupes ``ROLE_*`` reçoivent leurs permissions de ``ROLE_POLICY`` via
``ensure_role_groups`` (permissions modèles dérivées des applications et
actions, plus les 10 permissions métier ``authentication.*``).

Ces tests interrogent la pile d'autorisation Django réelle
(``user.has_perm``) : ils échoueront si une unité CURP modifie
silencieusement le périmètre d'un rôle (règle S2).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from authentication.role_groups import ROLE_POLICY, ensure_role_groups

User = get_user_model()

MOT_DE_PASSE = 'Perms#2026x'


class PermissionsEffectivesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()

    def _compte(self, role, numero=1):
        return User.objects.create_user(
            username=f'car-perm-{role.lower()}-{numero}',
            password=MOT_DE_PASSE, role=role,
        )

    # ── Trio administrateur : pouvoirs délégués (finance exceptée) ────────
    def test_admin_autorise_pour_neuf_permissions_metier(self):
        # COMPORTEMENT ACTUEL CARACTÉRISÉ : ROLE_POLICY ADMIN n'accorde PAS
        # ``finance_module`` (l'accès finance du vrai super-admin passe par
        # is_superuser ; les écrans finance sont gouvernés par la constante
        # FINANCE_MODULE_ROLES, pas seulement par cette permission).
        admin = self._compte('ADMIN')
        pour = (
            'access_web', 'operational_web', 'mutate_users', 'global_scope',
            'list_participants', 'manage_questionnaires',
            'manage_notes', 'validate_decisions', 'consult_evaluation',
        )
        for codename in pour:
            with self.subTest(codename=codename):
                self.assertTrue(admin.has_perm(f'authentication.{codename}'))
        self.assertFalse(admin.has_perm('authentication.finance_module'))

    def test_superutilisateur_contourne_les_permissions_par_design_django(self):
        root = User.objects.create_superuser(
            username='car-perm-root', password=MOT_DE_PASSE, role='ADMIN',
        )
        self.assertTrue(root.has_perm('authentication.finance_module'))

    def test_admin_autorise_pour_creer_et_supprimer_un_participant(self):
        admin = self._compte('ADMIN', 2)
        self.assertTrue(admin.has_perm('formations.add_participant'))
        self.assertTrue(admin.has_perm('formations.delete_participant'))

    def test_trio_admin_permissions_identiques(self):
        for role in ('ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'):
            with self.subTest(role=role):
                compte = self._compte(role, 3)
                self.assertTrue(compte.has_perm('authentication.mutate_users'))
                self.assertTrue(compte.has_perm('authentication.global_scope'))
                self.assertTrue(compte.has_perm('formations.add_participant'))

    # ── DIRECTION : lecture globale, pas de mutation de comptes ───────────
    def test_direction_autorise_pour_la_lecture_globale(self):
        direction = self._compte('DIRECTION')
        self.assertTrue(direction.has_perm('authentication.access_web'))
        self.assertTrue(direction.has_perm('authentication.global_scope'))

    def test_direction_accourt_finance_sans_la_permission_django(self):
        # ÉCART DE SOURCE DOUBLE CARACTÉRISÉ : DIRECTION figure dans
        # FINANCE_MODULE_ROLES (les vues finance l'admettent) alors que la
        # permission Django ``authentication.finance_module`` ne lui est PAS
        # accordée par ROLE_POLICY. U2 devra réconcilier ces deux sources.
        from authentication.role_groups import FINANCE_MODULE_ROLES
        direction = self._compte('DIRECTION', 7)
        self.assertIn('DIRECTION', set(FINANCE_MODULE_ROLES))
        self.assertFalse(direction.has_perm('authentication.finance_module'))

    def test_direction_refuse_pour_la_mutation_de_comptes(self):
        direction = self._compte('DIRECTION', 2)
        self.assertFalse(direction.has_perm('authentication.mutate_users'))

    def test_direction_refuse_pour_ajouter_un_participant(self):
        # Policy DIRECTION : actions=(view,) sur CORE_APPS.
        direction = self._compte('DIRECTION', 3)
        self.assertFalse(direction.has_perm('formations.add_participant'))
        self.assertTrue(direction.has_perm('formations.view_participant'))

    # ── Secrétariat : exclusion add_participant, mais delete conservé ─────
    def test_chef_secretariat_refuse_pour_ajouter_un_participant(self):
        chef = self._compte('CHEF_SECRETARIAT')
        self.assertFalse(chef.has_perm('formations.add_participant'))

    def test_chef_secretariat_autorise_pour_supprimer_un_participant(self):
        # État ACTUEL caractérisé (écart à instruire U2) : l'exclusion ne
        # porte que sur add_participant ; delete reste accordé.
        chef = self._compte('CHEF_SECRETARIAT', 2)
        self.assertTrue(chef.has_perm('formations.delete_participant'))

    def test_secretariat_refuse_pour_ajouter_un_participant(self):
        secretariat = self._compte('SECRETARIAT')
        self.assertFalse(secretariat.has_perm('formations.add_participant'))

    def test_secretariat_autorise_pour_supprimer_un_participant(self):
        secretariat = self._compte('SECRETARIAT', 2)
        self.assertTrue(secretariat.has_perm('formations.delete_participant'))

    def test_secretariat_autorise_pour_la_mutation_de_comptes(self):
        for role in ('CHEF_SECRETARIAT', 'SECRETARIAT'):
            with self.subTest(role=role):
                self.assertTrue(self._compte(role, 4).has_perm('authentication.mutate_users'))

    def test_secretariat_n_a_pas_le_perimetre_global(self):
        for role in ('CHEF_SECRETARIAT', 'SECRETARIAT'):
            with self.subTest(role=role):
                self.assertFalse(self._compte(role, 5).has_perm('authentication.global_scope'))

    # ── FINANCE : module finance, pas de web opérationnel ni de participants ─
    def test_finance_autorise_pour_le_module_finance(self):
        finance = self._compte('FINANCE')
        self.assertTrue(finance.has_perm('authentication.finance_module'))
        self.assertTrue(finance.has_perm('authentication.access_web'))

    def test_finance_refuse_pour_le_web_operationnel(self):
        finance = self._compte('FINANCE', 2)
        self.assertFalse(finance.has_perm('authentication.operational_web'))
        self.assertFalse(finance.has_perm('authentication.list_participants'))
        self.assertFalse(finance.has_perm('authentication.global_scope'))
        self.assertFalse(finance.has_perm('authentication.mutate_users'))

    def test_finance_refuse_pour_ecrire_dans_formations(self):
        finance = self._compte('FINANCE', 3)
        self.assertTrue(finance.has_perm('formations.view_participant'))
        self.assertFalse(finance.has_perm('formations.add_participant'))
        self.assertFalse(finance.has_perm('formations.change_participant'))

    # ── ARCHIVE : lecture globale + module finance ────────────────────────
    def test_archive_autorise_pour_la_lecture_globale_et_finance(self):
        archive = self._compte('ARCHIVE')
        self.assertTrue(archive.has_perm('authentication.global_scope'))
        self.assertTrue(archive.has_perm('authentication.finance_module'))
        self.assertFalse(archive.has_perm('formations.add_participant'))

    # ── ENCADRANT / SUPERVISEUR ───────────────────────────────────────────
    def test_encadrant_refuse_pour_la_mutation_de_comptes(self):
        encadrant = self._compte('ENCADRANT')
        self.assertFalse(encadrant.has_perm('authentication.mutate_users'))
        self.assertTrue(encadrant.has_perm('authentication.operational_web'))
        self.assertTrue(encadrant.has_perm('formations.add_participant'))

    def test_superviseur_refuse_pour_la_liste_participants_web(self):
        # Policy SUPERVISEUR : applications = (suiviEvaluation,) uniquement ;
        # pas de list_participants ni d'accès modèles formations.
        superviseur = self._compte('SUPERVISEUR')
        self.assertFalse(superviseur.has_perm('authentication.list_participants'))
        self.assertFalse(superviseur.has_perm('formations.view_participant'))
        self.assertTrue(superviseur.has_perm('authentication.operational_web'))

    # ── Rôles mobile uniquement : aucun droit métier web ──────────────────
    def test_formateur_refuse_pour_tous_les_droits_metier_web(self):
        formateur = self._compte('FORMATEUR')
        self.assertFalse(formateur.has_perm('authentication.access_web'))
        self.assertFalse(formateur.has_perm('authentication.mutate_users'))
        # Lecture applicative conservée pour le mobile.
        self.assertTrue(formateur.has_perm('formations.view_participant'))
        self.assertFalse(formateur.has_perm('formations.add_participant'))

    def test_auditeur_refuse_pour_tous_les_droits_metier_web(self):
        auditeur = self._compte('AUDITEUR')
        self.assertFalse(auditeur.has_perm('authentication.access_web'))
        self.assertFalse(auditeur.has_perm('authentication.mutate_users'))
        self.assertTrue(auditeur.has_perm('formations.view_participant'))

    # ── Cohérence générique ROLE_POLICY ↔ groupe effectif ─────────────────
    def test_les_permissions_custom_de_chaque_role_sont_accordees(self):
        for role, politique in ROLE_POLICY.items():
            compte = self._compte(role, 9)
            for cle in politique.get('custom', ()):
                with self.subTest(role=role, permission=cle):
                    self.assertTrue(compte.has_perm(f'authentication.{cle}'))
