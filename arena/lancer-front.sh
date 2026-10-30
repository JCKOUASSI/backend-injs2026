#!/usr/bin/env bash
# =============================================================================
# Site web (Vite) de l'aperçu — PORT FIGÉ à 3000 (règle projet, cf. tests).
# Le proxy `/api`, `/static` et `/media` renvoie vers l'API Django sur 8000
# (voir vite.config.js). L'admin Django n'est jamais servi par ce port.
#
#   ./arena/lancer-front.sh          # 0.0.0.0:3000
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Port canonique : 3000 (strictPort côté Vite : échec plutôt que 5173).
PORT=3000
export PORT
export VITE_HMR_PROTOCOL="${VITE_HMR_PROTOCOL:-wss}"
export VITE_HMR_CLIENT_PORT="${VITE_HMR_CLIENT_PORT:-443}"

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Dépendances absentes : cd frontend && npm install" >&2
  exit 1
fi

cd "$ROOT/frontend"
exec npm run dev
