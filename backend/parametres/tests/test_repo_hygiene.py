"""Tests de la garde-fou d'hygiène du dépôt P00-02 (check_repo_hygiene)."""
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from parametres.management.commands.check_repo_hygiene import (
    est_python_runtime,
    find_print_violations,
    find_violations,
    lire_contenus_runtime,
    trouver_appels_print,
)


class FindViolationsTests(TestCase):
    def test_ensemble_propre(self):
        tracked = [
            "backend/formations/models.py",
            "docs/modeles/modele_formations.csv",
            "docs/modeles/modele_seances.csv",
            "backend/test_import_formations_seances.xlsx",  # fixture synthétique
            "frontend/src/App.jsx",
        ]
        self.assertEqual(find_violations(tracked), [])

    def test_detecte_donnees_nominatives(self):
        tracked = [
            "backend/import_participants.csv",
            "backend/import_formateurs.xlsx",
            "backend/LISTE DES FORMATEURS FAB.numbers",
            "backend/importverif/FAB A4 OPHIR.xlsx",
        ]
        violations = find_violations(tracked)
        self.assertEqual(sorted(violations), sorted(tracked))

    def test_detecte_staticfiles_et_secrets(self):
        tracked = [
            "backend/staticfiles/sw.js",
            "backend/staticfiles/img/logo.png",
            "backend/.env",
            "qr_badge_mobile/assets/app.env",
            "backend/db.sqlite3",
        ]
        violations = find_violations(tracked)
        self.assertEqual(sorted(violations), sorted(tracked))

    def test_modele_en_dehors_de_docs_modeles_est_violation(self):
        tracked = ["backend/modele_formations.csv"]
        self.assertEqual(find_violations(tracked), ["backend/modele_formations.csv"])


class CheckRepoHygieneCommandTests(TestCase):
    def _run(self, tracked):
        out, err = StringIO(), StringIO()
        with mock.patch(
            "parametres.management.commands.check_repo_hygiene.list_tracked_files",
            return_value=tracked,
        ):
            call_command("check_repo_hygiene", stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_commande_verte_si_propre(self):
        out, _ = self._run(["backend/formations/models.py", "docs/modeles/modele_seances.csv"])
        self.assertIn("CONFORME", out)

    def test_commande_echoue_si_violation(self):
        with self.assertRaises(SystemExit) as ctx:
            self._run(["backend/import_participants.csv"])
        self.assertEqual(ctx.exception.code, 1)


# ---------------------------------------------------------------------------
# P00-05 — zéro print() dans le runtime Django
# ---------------------------------------------------------------------------


class PerimetreRuntimeTests(TestCase):
    def test_code_applicatif_et_commandes_fontent_partie_du_runtime(self):
        self.assertTrue(est_python_runtime("backend/formations/views.py"))
        self.assertTrue(est_python_runtime("backend/config/settings.py"))
        self.assertTrue(est_python_runtime("backend/admin_mixins.py"))
        self.assertTrue(
            est_python_runtime(
                "backend/scolarite/management/commands/smoke_test_injs.py"
            )
        )

    def _hors_runtime(self, chemin):
        self.assertFalse(est_python_runtime(chemin), chemin)

    def test_tests_migrations_et_scripts_sont_exclus(self):
        self._hors_runtime("backend/formations/tests/test_vue.py")
        self._hors_runtime("backend/formations/migrations/0001_initial.py")
        self._hors_runtime("backend/scripts/seed_mobile_users.py")
        self._hors_runtime("backend/seed_data.py")
        self._hors_runtime("backend/count_seances.py")
        self._hors_runtime("backend/manage.py.bak")
        self._hors_runtime("frontend/src/main.jsx")
        self._hors_runtime("backend/formations/module_test.py")


class TrouverAppelsPrintTests(TestCase):
    def test_appels_print_detectes_avec_lignes(self):
        source = (
            "import logging\n"
            "logger = logging.getLogger(__name__)\n"
            "def vue(request):\n"
            "    print('debug', request)\n"
            "    if True:\n"
            "        print('autre')\n"
            "    return None\n"
        )
        self.assertEqual(trouver_appels_print(source), [4, 6])

    def test_commentaires_docstrings_et_faux_positifs_ignores(self):
        source = (
            "# print('commente')\n"
            '"""docstring print(\'x\')"""\n'
            "def _stop_time_fingerprint(events):\n"
            "    return fingerprint(events)\n"
            "texte = 'print(\"dans une chaine\")'\n"
            "logger.info('tout va bien')\n"
        )
        self.assertEqual(trouver_appels_print(source), [])

    def test_print_redefini_module_n_est_pas_builtin(self):
        source = (
            "def print(*args, **kwargs):\n"
            "    logger.info(args)\n"
            "print('appel a la fonction locale')\n"
        )
        self.assertEqual(trouver_appels_print(source), [])
        source_alias = (
            "from journalisation import ecrire as print\n"
            "print('alias importe')\n"
        )
        self.assertEqual(trouver_appels_print(source_alias), [])
        source_assign = "print = lambda *a: None\nprint('redéfini par assignation')\n"
        self.assertEqual(trouver_appels_print(source_assign), [])

    def test_print_parametre_ou_fonction_imbriquee_ignore(self):
        source = (
            "def executer(print, valeurs):\n"
            "    for valeur in valeurs:\n"
            "        print(valeur)\n"
            "\n"
            "def wrapper():\n"
            "    def print(msg):\n"
            "        return msg\n"
            "    print('nested')\n"
        )
        self.assertEqual(trouver_appels_print(source), [])

    def test_print_dans_fonction_imbriquee_sans_redefinition_detecte(self):
        source = (
            "def vue(request):\n"
            "    def interne():\n"
            "        print('builtin depuis une imbrication')\n"
            "    return interne\n"
        )
        self.assertEqual(trouver_appels_print(source), [3])

    def test_self_stdout_write_ignoré(self):
        source = "class Command(BaseCommand):\n    def handle(self):\n        self.stdout.write('ok')\n"
        self.assertEqual(trouver_appels_print(source), [])

    def test_source_syntaxiquement_invalide_ne_fait_pas_echouer(self):
        self.assertEqual(trouver_appels_print("ceci n'est pas du python :::"), [])


class FindPrintViolationsTests(TestCase):
    def test_runtime_avec_print_denonce(self):
        contenus = {
            "backend/formations/views.py": "def v(request):\n    print('x')\n",
            "backend/formations/tests/test_v.py": "print('test')\n",
            "backend/scripts/generate_test_data.py": "print('script')\n",
            "backend/seed_data.py": "print('seed')\n",
            "backend/formations/migrations/0001_initial.py": "print('migration')\n",
        }
        violations = find_print_violations(contenus)
        self.assertEqual(len(violations), 1)
        self.assertIn("backend/formations/views.py:2", violations[0])
        self.assertIn("logging", violations[0])

    def test_ensemble_propre(self):
        contenus = {
            "backend/formations/views.py": "logger.info('ok')\n",
            "backend/scolarite/management/commands/x.py": (
                "class Command:\n    def handle(self):\n        self.stdout.write('ok')\n"
            ),
        }
        self.assertEqual(find_print_violations(contenus), [])


class CommandePrintTests(TestCase):
    def _run_avec(self, tracked, contenus=None):
        out, err = StringIO(), StringIO()
        with mock.patch(
            "parametres.management.commands.check_repo_hygiene.list_tracked_files",
            return_value=tracked,
        ), mock.patch(
            "parametres.management.commands.check_repo_hygiene.lire_contenus_runtime",
            return_value=contenus or {},
        ):
            call_command("check_repo_hygiene", stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_commande_echoue_sur_print_runtime(self):
        with self.assertRaises(SystemExit) as ctx:
            self._run_avec(
                ["backend/formations/views.py"],
                {"backend/formations/views.py": "def v():\n    print('x')\n"},
            )
        self.assertEqual(ctx.exception.code, 1)

    def test_commande_verte_avec_contenus_propres(self):
        out, _ = self._run_avec(
            ["backend/formations/views.py"],
            {"backend/formations/views.py": "logger.info('ok')\n"},
        )
        self.assertIn("CONFORME", out)
        self.assertIn("aucun print() runtime", out)


class RuntimeReelTests(TestCase):
    def test_le_code_runtime_versionne_ne_contient_aucun_print(self):
        """Garde-fou vivant : le dépôt réel doit passer (P00-05)."""
        from parametres.management.commands.check_repo_hygiene import list_tracked_files

        contenus = lire_contenus_runtime(list_tracked_files())
        self.assertEqual(
            find_print_violations(contenus),
            [],
            "Du code runtime utilise encore print() — voir P00-05.",
        )
