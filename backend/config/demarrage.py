"""Décision de démarrage du conteneur backend — migrations sous contrôle.

Pourquoi ce module
------------------
L'audit pré-déploiement du 6 novembre 2026 a relevé le blocage **B2** : la
variable ``SKIP_DB_SETUP`` était documentée dans
``deploy/production/.env.example`` mais **jamais transmise au conteneur**
(aucune entrée correspondante dans le bloc ``environment:`` du service, aucun
``env_file``). L'`entrypoint` appliquait donc ``manage.py migrate``
**implicitement** au démarrage de la production, sans validation humaine.

Ce module déplace la décision dans du code **testable** :

* la décision est une fonction **pure** de l'environnement (aucun effet de bord,
  aucune dépendance à Django) ;
* l'`entrypoint` se contente d'exécuter la décision rendue ;
* les cinq scénarios exigés par la mission sont couverts par des tests
  automatisés (voir ``config/tests/test_demarrage.py``).

Contrat
-------
Codes de sortie de la ligne de commande (``python3 -m config.demarrage``) :

* ``0``  — **sans migration** : démarrage direct, aucune migration implicite ;
* ``10`` — **avec migrations** : demande explicite (``SKIP_DB_SETUP=false``) ;
* ``2``  — **erreur de configuration** : valeur invalide → le conteneur
  s'arrête au lieu de choisir un comportement dangereux.

Règles appliquées à ``SKIP_DB_SETUP`` (comparaison insensible à la casse,
espaces ignorés) :

===============================  ==========  ==========================================
Valeur                           Code        Comportement
===============================  ==========  ==========================================
``true``, ``1``, ``yes``, ``on``    0        Aucune migration (démarrage sûr)
absente ou vide                     0        Aucune migration — **défaut sûr**, avertissement
``false``, ``0``, ``no``, ``off``   10       Migrations + collectstatic explicites
toute autre valeur                  2        Arrêt immédiat (erreur de configuration)
===============================  ==========  ==========================================

Le principe directeur est le **défaut sûr** : oublier la variable ne peut
jamais déclencher une migration. Appliquer des migrations suppose une demande
explicite et contraire (``SKIP_DB_SETUP=false``), ou l'exécution d'une commande
séparée (voir la procédure documentée dans
``docs/deploiement/mission-02/DEPLOY_INJS_MISSION_02_DOCKER.md``).

Ce module n'importe rien de Django : il peut être exécuté avant tout
chargement des réglages, y compris si ``SECRET_KEY`` est absente.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# ── Vocabulaire accepté ──────────────────────────────────────────────────────
VALEURS_VRAIES = frozenset({'1', 'true', 'yes', 'on', 'oui'})
VALEURS_FAUSSES = frozenset({'0', 'false', 'no', 'off', 'non'})

# ── Codes de sortie ──────────────────────────────────────────────────────────
CODE_SANS_MIGRATION = 0
CODE_AVEC_MIGRATIONS = 10
CODE_ERREUR_CONFIGURATION = 2

CLE_SKIP = 'SKIP_DB_SETUP'


@dataclass(frozen=True)
class Decision:
    """Résultat de l'analyse de l'environnement de démarrage."""

    code: int
    appliquer_migrations: bool
    appliquer_collectstatic: bool
    motif: str
    valeur_brute: str | None

    @property
    def est_erronee(self) -> bool:
        return self.code == CODE_ERREUR_CONFIGURATION


def _normaliser(valeur: str | None) -> str:
    return (valeur or '').strip().lower()


def analyser_environnement(environ: dict | None = None) -> Decision:
    """Décide, **sans aucun effet de bord**, si le démarrage migre la base.

    Fonction pure : elle ne lit que le dictionnaire fourni (ou ``os.environ``
    par défaut), n'écrit rien et ne touche à aucune base de données.
    """
    env = os.environ if environ is None else environ
    brut = env.get(CLE_SKIP)
    valeur = _normaliser(brut)

    if brut is None or valeur == '':
        return Decision(
            code=CODE_SANS_MIGRATION,
            appliquer_migrations=False,
            appliquer_collectstatic=False,
            motif=(
                f'{CLE_SKIP} est absente : défaut sûr appliqué — aucune migration '
                'implicite au démarrage. Définir SKIP_DB_SETUP=true pour rendre '
                'l’intention explicite, ou SKIP_DB_SETUP=false pour autoriser les '
                'migrations au démarrage.'
            ),
            valeur_brute=brut,
        )

    if valeur in VALEURS_VRAIES:
        return Decision(
            code=CODE_SANS_MIGRATION,
            appliquer_migrations=False,
            appliquer_collectstatic=False,
            motif=f'{CLE_SKIP}={brut!r} : aucune migration, aucun collectstatic au démarrage.',
            valeur_brute=brut,
        )

    if valeur in VALEURS_FAUSSES:
        return Decision(
            code=CODE_AVEC_MIGRATIONS,
            appliquer_migrations=True,
            appliquer_collectstatic=True,
            motif=(
                f'{CLE_SKIP}={brut!r} : migrations et collectstatic EXPLICITES au démarrage '
                '(demande contraire au défaut sûr).'
            ),
            valeur_brute=brut,
        )

    return Decision(
        code=CODE_ERREUR_CONFIGURATION,
        appliquer_migrations=False,
        appliquer_collectstatic=False,
        motif=(
            f'{CLE_SKIP}={brut!r} est une valeur invalide. Valeurs acceptées : '
            f'{sorted(VALEURS_VRAIES)} (ignorer les migrations) ou '
            f'{sorted(VALEURS_FAUSSES)} (les appliquer explicitement). '
            'Arrêt du conteneur : aucun comportement implicite n’est appliqué.'
        ),
        valeur_brute=brut,
    )


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée de la ligne de commande (``python3 -m config.demarrage``)."""
    decision = analyser_environnement()
    flux = sys.stderr if decision.est_erronee else sys.stdout
    prefixe = '[injs-be] ERREUR ' if decision.est_erronee else '[injs-be] '
    print(prefixe + decision.motif, file=flux, flush=True)
    if argv and '--verbose' in argv:
        print(
            f'[injs-be] code={decision.code} '
            f'migrations={decision.appliquer_migrations} '
            f'collectstatic={decision.appliquer_collectstatic}',
            file=flux,
            flush=True,
        )
    return decision.code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
