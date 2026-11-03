#!/usr/bin/env bash
# =============================================================================
# API Django de l'aperçu — PORT FIGÉ à 8000 (règle projet, cf. tests).
# Profil : arena.settings_sandbox (cookies CHIPS + auto-connexion démo).
#
#   ./arena/lancer-api.sh            # 0.0.0.0:8000
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/backend/.venv"

# Port canonique : 8000 (le 3000 est réservé au frontend).
PORT=8000

if [ ! -x "$VENV/bin/python" ]; then
  echo "Environnement virtuel absent : python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt" >&2
  exit 1
fi

# `arena` doit être importable (profil de réglages) → racine du dépôt dans le path.
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-arena.settings_sandbox}"

cd "$ROOT/backend"
exec "$VENV/bin/python" manage.py runserver 0.0.0.0:$PORT
