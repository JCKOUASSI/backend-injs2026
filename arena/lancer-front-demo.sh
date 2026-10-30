#!/usr/bin/env bash
# =============================================================================
# Site web (Vite) de l'aperçu — VARIANTE PRODUCTION, PORT FIGÉ à 3000.
#
# Pourquoi cette variante : le serveur de développement de Vite dépend d'un
# WebSocket (HMR) et transforme les modules à la volée. Derrière certaines
# passerelles d'aperçu (iframe, proxy TLS), ce mode peut produire une page
# blanche sans message. Cette variante sert le bundle de PRODUCTION construit
# par `vite build`, sur le même port et avec le même proxy `/api` — donc le
# même comportement applicatif, sans dépendance à l'HMR.
#
#   ./arena/lancer-front-demo.sh          # construit puis sert 0.0.0.0:3000
#   ./arena/lancer-front-demo.sh --build-seulement
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONT="$ROOT/frontend"

PORT=3000
export PORT

if [ ! -d "$FRONT/node_modules" ]; then
  echo "Dépendances absentes : cd frontend && npm ci" >&2
  exit 1
fi

cd "$FRONT"

echo "Construction du bundle de production…"
npm run build --silent

if [ "${1:-}" = "--build-seulement" ]; then
  exit 0
fi

if [ ! -f "$FRONT/dist/index.html" ]; then
  echo "Bundle absent après construction : $FRONT/dist/index.html" >&2
  exit 1
fi

echo "Service du bundle sur 0.0.0.0:$PORT (vite preview)…"
exec npx vite preview --port "$PORT" --strictPort --host 0.0.0.0
