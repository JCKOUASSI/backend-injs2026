#!/usr/bin/env bash
# Tests sans VPS/Docker du mode de transfert local et de la synchronisation
# des tags exportés (docker compose préfère l'environnement à --env-file).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# Charger les vraies fonctions sans exécuter main (dernière ligne du script).
sed '$d' "$ROOT/deploy/production/deploy.sh" > "$TMP/fonctions.sh"
# shellcheck source=/dev/null
source "$TMP/fonctions.sh"
LOG_ACTIF=0
LOG_DIR="$TMP/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/test.log"
ENV_FILE="$TMP/.env"
OLD="$(printf 'a%.0s' {1..40})"
NEW="$(printf 'b%.0s' {1..40})"
printf 'INJS_BACKEND_TAG=%s\nINJS_FRONTEND_TAG=%s\n' "$OLD" "$OLD" > "$ENV_FILE"
PUBLIC_PORT=8080

# Ne jamais contacter un daemon Docker : inspection et compose simulés.
docker() {
  if [ "$1" = image ] && [ "$2" = inspect ]; then
    case "$*" in
      *nginx:1.27-alpine*|*"$NEW"*) ;;
      *) return 1 ;;
    esac
    case "$*" in
      *'{{.Os}}/{{.Architecture}}'*) echo "${PLATFORM:-linux/amd64}" ;;
      *'{{.Id}}'*) echo 'sha256:test' ;;
    esac
    return 0
  fi
  return 1
}
compose() {
  printf '%s|%s|%s\n' "$1" "$INJS_BACKEND_TAG" "$INJS_FRONTEND_TAG" >> "$TMP/compose-calls"
  if [ "$1" = run ] && [ "${*: -2}" = 'migrate --plan' ]; then
    echo '  No planned migration operations.'
  fi
}
charger_env() {
  set -a
  # shellcheck source=/dev/null
  . "$ENV_FILE"
  set +a
}
cmd_sauvegarde() { :; }
analyser_plan() { :; }
verifier_coherence_migrations() { :; }
identifier_postgres() { :; }
obtenir_comptages() { :; }
comparer_comptages() { :; }
curl() { :; }

# Manquant ou mauvaise architecture : échec fermé avant toute migration.
if (docker() { return 1; }; verifier_images_locales "$NEW" "$NEW") >/dev/null 2>&1; then
  echo 'Image manquante acceptée' >&2; exit 1
fi
PLATFORM=linux/arm64
if (verifier_images_locales "$NEW" "$NEW") >/dev/null 2>&1; then
  echo 'Image ARM acceptée sur VPS amd64' >&2; exit 1
fi
PLATFORM=linux/amd64
DEPLOY_IMAGES_LOCALES=oui
export DEPLOY_IMAGES_LOCALES
cmd_deployer --tag "$NEW" >/dev/null
# Toutes les opérations compose (run/up/ps) doivent viser le NOUVEAU tag.
[ -s "$TMP/compose-calls" ]
if grep -vF "|$NEW|$NEW" "$TMP/compose-calls"; then
  echo 'Ancien tag transmis à Compose' >&2; exit 1
fi
[ "$(grep -c '^INJS_BACKEND_TAG=' "$ENV_FILE")" -eq 1 ]
grep -q "^INJS_BACKEND_TAG=$NEW$" "$ENV_FILE"
grep -q "^INJS_FRONTEND_TAG=$NEW$" "$ENV_FILE"
# Le mode local ne tente aucun pull ; une valeur invalide échoue fermée.
if grep -q '^pull|' "$TMP/compose-calls"; then
  echo 'Pull inattendu en mode local' >&2; exit 1
fi
if (DEPLOY_IMAGES_LOCALES=inconnue; preparer_images) >/dev/null 2>&1; then
  echo 'Mode inconnu accepté' >&2; exit 1
fi
# Après un premier déploiement, la sauvegarde .env contient l'ancien tag.
# S'il manque localement, le rollback doit échouer AVANT compose down.
if (cmd_rollback) >/dev/null 2>&1; then
  echo 'Rollback avec ancienne image manquante accepté' >&2; exit 1
fi
if grep -q '^down|' "$TMP/compose-calls"; then
  echo 'Rollback a arrêté la stack avant vérification des images' >&2; exit 1
fi
echo 'Mode local : images vérifiées, pas de pull, tags synchronisés, rollback fermé.'