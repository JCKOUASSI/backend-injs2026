#!/bin/sh
# =============================================================================
# INJS-LMD — Politique de préparation de la base au démarrage du conteneur.
#
# MISSION 02 / BLOCAGE B2.
#
# Problème corrigé : l'ancien entrypoint testait `[ "$SKIP_DB_SETUP" = "true" ]`.
# Toute AUTRE valeur — variable absente, faute de frappe, `TRUE`, `1`, `yes` —
# faisait tomber dans la branche `else` qui exécutait `manage.py migrate`.
# La valeur par défaut du système était donc « migrer », c'est-à-dire le
# comportement le plus dangereux possible pour une base de production.
#
# Politique appliquée désormais :
#
#   SKIP_DB_SETUP absent, vide, true, 1, yes, on   -> skip  (AUCUNE migration)
#   SKIP_DB_SETUP = false, 0, no, off              -> run   (migrations explicites)
#   toute autre valeur                             -> invalide, code 64, arrêt
#
# Deux garanties :
#   1. l'absence de variable ne provoque jamais de migration ;
#   2. une valeur non reconnue n'est jamais interprétée : elle arrête le
#      conteneur au lieu de choisir un comportement par défaut silencieux.
#
# Ce fichier est sourcé par `entrypoint.sh` et par les tests automatisés
# (`backend/docker_tests/db_setup_policy_test.sh`). Il ne dépend d'aucun
# interpréteur Python : il est testable sans Django ni base de données.
# =============================================================================

#: Code retour utilisé lorsqu'une valeur de SKIP_DB_SETUP est inutilisable.
INJS_EXIT_POLITIQUE_INVALIDE=64

# injs_resoudre_politique_db
#   Lit SKIP_DB_SETUP et exporte INJS_DB_SETUP_MODE = "skip" | "run".
#   Retourne 0 si la politique est déterminée, 64 sinon (mode "invalide").
injs_resoudre_politique_db() {
    _brut=${SKIP_DB_SETUP-}
    # Normalisation : casse indifférente, espaces et tabulations retirés.
    _norme=$(printf '%s' "$_brut" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')

    case "$_norme" in
        ''|true|1|yes|on)
            INJS_DB_SETUP_MODE=skip
            ;;
        false|0|no|off)
            INJS_DB_SETUP_MODE=run
            ;;
        *)
            INJS_DB_SETUP_MODE=invalide
            printf '[injs-be] SKIP_DB_SETUP="%s" : valeur inutilisable.\n' "$_brut" >&2
            printf '[injs-be] Valeurs acceptees : true|false (ou 1|0, yes|no, on|off).\n' >&2
            printf '[injs-be] Refus de demarrer plutot que de choisir un comportement implicite.\n' >&2
            export INJS_DB_SETUP_MODE
            return "$INJS_EXIT_POLITIQUE_INVALIDE"
            ;;
    esac

    export INJS_DB_SETUP_MODE
    return 0
}
