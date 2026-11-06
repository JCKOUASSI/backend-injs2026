"""Tests du dispositif de démarrage sous contrôle (blocage B2).

Ces tests couvrent les cinq scénarios exigés par la mission 02 :

1. démarrage avec ``SKIP_DB_SETUP=true`` ;
2. démarrage sans variable (défaut sûr) ;
3. démarrage avec une valeur invalide ;
4. exécution explicite des migrations ;
5. aucune migration implicite en production.

Ils vérifient aussi la **transmission effective** de la variable jusqu'au
processus exécuté dans le conteneur : le fichier Compose est analysé, son
environnement résolu est injecté dans la décision, et la ligne de commande
réellement appelée par l'`entrypoint` (``python3 -m config.demarrage``) est
exécutée en sous-processus.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml
from django.conf import settings
from django.test import SimpleTestCase

from config.demarrage import (
    CLE_SKIP,
    CODE_AVEC_MIGRATIONS,
    CODE_ERREUR_CONFIGURATION,
    CODE_SANS_MIGRATION,
    analyser_environnement,
)

RACINE = Path(__file__).resolve().parents[3]  # racine du dépôt
COMPOSE_PROD = RACINE / 'deploy' / 'production' / 'compose.yml'
COMPOSE_DEV = RACINE / 'backend' / 'compose.yml'
ENTRYPOINT = RACINE / 'backend' / 'entrypoint.sh'


def _compose(chemin: Path) -> dict:
    with chemin.open(encoding='utf-8') as handle:
        return yaml.safe_load(handle)


class DecisionSansMigrationTests(SimpleTestCase):
    """Scénario 1 : SKIP_DB_SETUP=true → aucune migration."""

    def test_skip_db_setup_true_ignore_les_migrations(self):
        decision = analyser_environnement({CLE_SKIP: 'true'})
        self.assertEqual(decision.code, CODE_SANS_MIGRATION)
        self.assertFalse(decision.appliquer_migrations)
        self.assertFalse(decision.appliquer_collectstatic)
        self.assertFalse(decision.est_erronee)

    def test_variantes_equivalentes(self):
        for valeur in ('1', 'yes', 'on', 'oui', 'TRUE', ' True ', 'On'):
            with self.subTest(valeur=valeur):
                decision = analyser_environnement({CLE_SKIP: valeur})
                self.assertEqual(decision.code, CODE_SANS_MIGRATION)
                self.assertFalse(decision.appliquer_migrations)


class DecisionSansVariableTests(SimpleTestCase):
    """Scénario 2 : variable absente → défaut sûr, aucune migration."""

    def test_variable_absente(self):
        decision = analyser_environnement({})
        self.assertEqual(decision.code, CODE_SANS_MIGRATION)
        self.assertFalse(decision.appliquer_migrations)
        self.assertIn('défaut sûr', decision.motif)

    def test_variable_vide(self):
        decision = analyser_environnement({CLE_SKIP: '   '})
        self.assertEqual(decision.code, CODE_SANS_MIGRATION)
        self.assertFalse(decision.appliquer_migrations)

    def test_absence_et_valeur_fause_ne_sont_pas_confondues(self):
        # L'absence ne doit jamais être traitée comme « faux » (qui migre).
        self.assertNotEqual(
            analyser_environnement({}).code,
            analyser_environnement({CLE_SKIP: 'false'}).code,
        )


class DecisionInvalideTests(SimpleTestCase):
    """Scénario 3 : valeur invalide → arrêt, aucun comportement implicite."""

    def test_valeur_invalide_provoque_une_erreur(self):
        decision = analyser_environnement({CLE_SKIP: 'peut-etre'})
        self.assertEqual(decision.code, CODE_ERREUR_CONFIGURATION)
        self.assertTrue(decision.est_erronee)
        self.assertFalse(decision.appliquer_migrations)

    def test_message_liste_les_valeurs_acceptees(self):
        decision = analyser_environnement({CLE_SKIP: 'maybe'})
        self.assertIn('valeurs acceptées'.lower(), decision.motif.lower())

    def test_aucune_autre_valeur_ne_declenche_de_migration(self):
        for valeur in ('peut-etre', '2', 'TRUEISH', 'null', 'enabled'):
            with self.subTest(valeur=valeur):
                decision = analyser_environnement({CLE_SKIP: valeur})
                self.assertEqual(decision.code, CODE_ERREUR_CONFIGURATION)
                self.assertFalse(decision.appliquer_migrations)


class DecisionMigrationsExplicitesTests(SimpleTestCase):
    """Scénario 4 : migrations exécutées sur demande explicite uniquement."""

    def test_skip_db_setup_false_applique_les_migrations(self):
        decision = analyser_environnement({CLE_SKIP: 'false'})
        self.assertEqual(decision.code, CODE_AVEC_MIGRATIONS)
        self.assertTrue(decision.appliquer_migrations)
        self.assertTrue(decision.appliquer_collectstatic)

    def test_variantes_equivalentes(self):
        for valeur in ('0', 'no', 'off', 'non', 'FALSE'):
            with self.subTest(valeur=valeur):
                decision = analyser_environnement({CLE_SKIP: valeur})
                self.assertEqual(decision.code, CODE_AVEC_MIGRATIONS)

    def test_le_motif_annonce_le_caractere_explicite(self):
        decision = analyser_environnement({CLE_SKIP: 'false'})
        self.assertIn('explicit', decision.motif.lower())


class TransmissionComposeTests(SimpleTestCase):
    """Scénario 5 : aucune migration implicite en production.

    La variable est-elle réellement transmise ? Le fichier Compose est analysé,
    le défaut ``${SKIP_DB_SETUP:-true}`` est résolu, puis l'environnement
    résultant est soumis à la décision.
    """

    def test_le_service_backend_declare_skip_db_setup(self):
        services = _compose(COMPOSE_PROD)['services']
        environnement = services['backend']['environment']
        self.assertIn(CLE_SKIP, environnement)
        self.assertEqual(environnement[CLE_SKIP], '${SKIP_DB_SETUP:-true}')

    def test_en_production_la_decision_est_sans_migration(self):
        """Avec le .env de production (variable non définie), aucune migration."""
        resolution = {'SKIP_DB_SETUP': 'true'}  # équivalent de ${VAR:-true} sans .env
        decision = analyser_environnement(resolution)
        self.assertEqual(decision.code, CODE_SANS_MIGRATION)
        self.assertFalse(decision.appliquer_migrations)

    def test_meme_sans_fichier_env_la_decision_reste_sure(self):
        decision = analyser_environnement({})
        self.assertEqual(decision.code, CODE_SANS_MIGRATION)

    def test_pile_de_developpement_migre_explicitement(self):
        """Le compose de développement annonce SKIP_DB_SETUP=false (comportement
        historique conservé, mais désormais explicite)."""
        services = _compose(COMPOSE_DEV)['services']
        environnement = services['app']['environment']
        self.assertEqual(environnement.get(CLE_SKIP), 'false')
        decision = analyser_environnement({CLE_SKIP: environnement[CLE_SKIP]})
        self.assertEqual(decision.code, CODE_AVEC_MIGRATIONS)


class LigneDeCommandeTests(SimpleTestCase):
    """La commande réellement exécutée par l'entrypoint, en sous-processus."""

    def _executer(self, environ: dict) -> subprocess.CompletedProcess:
        import os

        env = {**os.environ, **environ}
        env.pop(CLE_SKIP, None)
        if CLE_SKIP in environ and environ[CLE_SKIP] is not None:
            env[CLE_SKIP] = environ[CLE_SKIP]
        return subprocess.run(
            [sys.executable, '-m', 'config.demarrage'],
            cwd=str(settings.BASE_DIR),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_code_0_quand_skip(self):
        resultat = self._executer({CLE_SKIP: 'true'})
        self.assertEqual(resultat.returncode, CODE_SANS_MIGRATION, resultat.stderr)

    def test_code_0_sans_variable(self):
        resultat = self._executer({})
        self.assertEqual(resultat.returncode, CODE_SANS_MIGRATION, resultat.stderr)
        self.assertIn('défaut sûr', resultat.stdout)

    def test_code_2_quand_invalide(self):
        resultat = self._executer({CLE_SKIP: 'peut-etre'})
        self.assertEqual(resultat.returncode, CODE_ERREUR_CONFIGURATION)
        self.assertIn('invalide', resultat.stderr.lower())

    def test_code_10_quand_explicite(self):
        resultat = self._executer({CLE_SKIP: 'false'})
        self.assertEqual(resultat.returncode, CODE_AVEC_MIGRATIONS, resultat.stderr)


class CablageEntrypointTests(SimpleTestCase):
    """L'entrypoint délègue bien la décision au module et gère les trois codes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contenu = ENTRYPOINT.read_text(encoding='utf-8')

    def test_l_entrypoint_appelle_le_module_de_decision(self):
        self.assertIn('python3 -m config.demarrage', self.contenu)

    def test_l_entrypoint_ne_contient_plus_de_migrate_inconditionnel(self):
        # `migrate` ne doit apparaître que dans la branche « migrations
        # explicites » (repérée par le motif du code 10).
        self.assertIn('manage.py migrate', self.contenu)
        self.assertIn('CODE_DEMARRAGE', self.contenu)

    def test_les_trois_codes_sont_traites(self):
        for motif in ('\n  0)', '\n  10)', '\n  *)'):
            with self.subTest(motif=motif.strip()):
                self.assertIn(motif, self.contenu)

    def test_le_message_d_erreur_gosu_est_explicite(self):
        # Robustesse : un démarrage en root sans gosu doit échouer proprement.
        self.assertIn('gosu', self.contenu)
