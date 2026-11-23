#!/usr/bin/env bash
# =============================================================================
# Site web (Vite) de l'aperçu — bundle de production par défaut, PORT 3000.
# Le proxy `/api`, `/static` et `/media` renvoie vers l'API Django sur 8000
# (voir vite.config.js). L'admin Django n'est jamais servi par ce port.
# Le mode dev reste disponible explicitement avec --dev.
#
#   ./arena/lancer-front.sh          # build + aperçu production sur 0.0.0.0:3000
#   ./arena/lancer-front.sh --dev    # Vite dev/HMR sur 0.0.0.0:3000
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Port canonique : 3000 (strictPort côté Vite : échec plutôt que 5173).
PORT=3000
export PORT
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Dépendances absentes : cd frontend && npm install" >&2
  exit 1
fi

cd "$ROOT/frontend"
if [ "${1:-}" = "--dev" ]; then
  if [ "$#" -ne 1 ]; then
    echo "Usage: ./arena/lancer-front.sh [--dev]" >&2
    exit 2
  fi
  export VITE_HMR_PROTOCOL="${VITE_HMR_PROTOCOL:-wss}"
  export VITE_HMR_CLIENT_PORT="${VITE_HMR_CLIENT_PORT:-443}"
  exec npm run dev -- --host 0.0.0.0 --port "$PORT"
fi
if [ "$#" -ne 0 ]; then
  echo "Usage: ./arena/lancer-front.sh [--dev]" >&2
  exit 2
fi

npm run build
exec npm run preview -- --host 0.0.0.0 --port "$PORT"
