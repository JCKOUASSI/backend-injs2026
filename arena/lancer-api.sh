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
# Une base SQLite neuve peut laisser /api/ répondre 200 alors que /api/auth/login/
# échoue en 500 (tables absentes). En aperçu seulement, préparer le schéma AVANT
# de rendre le serveur accessible. migrate est idempotent et crée aussi le
# compte de démonstration via le signal post_migrate.
if [ "$DJANGO_SETTINGS_MODULE" = "arena.settings_sandbox" ]; then
  "$VENV/bin/python" manage.py migrate --noinput
fi
exec "$VENV/bin/python" manage.py runserver 0.0.0.0:$PORT
