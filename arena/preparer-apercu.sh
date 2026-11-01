#!/usr/bin/env bash
# =============================================================================
# Remise en état de l'aperçu Arena — IDEMPOTENT, rejouable à chaque réinitialisation.
#
# Le bac à sable ne conserve pas `backend/.venv`, `frontend/node_modules`,
# `backend/.env` ni la base SQLite (`*.sqlite3` ignorée par Git). Chaque nouvelle
# session repart donc sans environnement : ce script rejoue la préparation
# complète, sans jamais écraser un état existant.
#
#   ./arena/preparer-apercu.sh              # tout préparer, sans lancer
#   ./arena/preparer-apercu.sh --avec-demo  # + base de démonstration complète
#
# Ne touche jamais à une base déjà peuplée : la base n'est migrée/renseignée que
# si elle est absente ou vide (aucune table métier).
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/backend/.venv"
FRONT="$ROOT/frontend"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-arena.settings_sandbox}"

log() { printf '\033[1;36m[apercu]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[apercu]\033[0m %s\n' "$*" >&2; exit 1; }

# ── 1. Profil d'aperçu + backend/.env (jamais écrasé s'il existe) ────────────
if [ ! -f "$ROOT/backend/.env" ] || [ ! -f "$ROOT/arena/settings_sandbox.py" ]; then
  log "Profil d'aperçu / .env manquant → bootstrap"
  bash "$ROOT/arena/bootstrap.sh" >/dev/null
fi

# ── 2. Environnement Python ──────────────────────────────────────────────────
if [ ! -x "$VENV/bin/python" ]; then
  log "Création de l'environnement virtuel"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q --upgrade pip
  log "Installation des dépendances Python (peut prendre 1–2 min)"
  "$VENV/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
else
  log "Environnement virtuel déjà présent"
fi

# ── 3. Dépendances frontend ──────────────────────────────────────────────────
if [ ! -d "$FRONT/node_modules" ]; then
  log "Installation des dépendances frontend (npm ci)"
  ( cd "$FRONT" && npm ci --no-audit --no-fund >/dev/null 2>&1 ) \
    || fail "npm ci a échoué (voir frontend/)"
else
  log "node_modules déjà présent"
fi

# ── 4. Base SQLite : migrer, et peupler uniquement si elle est vide ──────────
cd "$ROOT/backend"
BASE="$("$VENV/bin/python" - <<'PY'
import os
from config.settings import DATABASES
print(DATABASES['default'].get('NAME') or '')
PY
)"
log "Base utilisée : ${BASE:-<inconnue>}"

MIGRER=0
if [ ! -f "$BASE" ]; then
  MIGRER=1
else
  # Base présente : on ne migre que si elle n'a jamais été initialisée.
  if ! "$VENV/bin/python" - <<'PY' 2>/dev/null
import django, sys
from django.db import connection
try:
    tables = set(connection.introspection.table_names())
except Exception:
    sys.exit(1)
sys.exit(0 if 'authentication_user' in tables else 1)
PY
  then
    MIGRER=1
  fi
fi

if [ "$MIGRER" = "1" ]; then
  log "Migrations"
  "$VENV/bin/python" manage.py migrate --no-input >/dev/null
else
  log "Base déjà initialisée → pas de migration destructive"
  "$VENV/bin/python" manage.py migrate --no-input >/dev/null
fi

# ── 5. Jeu de démonstration (optionnel, jamais rejoué sur base peuplée) ──────
if [ "${1:-}" = "--avec-demo" ]; then
  log "Jeu de démonstration (chaîne LMD complète + comptes par rôle)"
  "$VENV/bin/python" manage.py seed_injs_complet >/dev/null
  "$VENV/bin/python" manage.py creer_comptes_temoins >/dev/null
  log "Démonstration prête : admin (voir backend/.env) et comptes témoins"
fi

log "Préparation terminée — lancer : ./arena/lancer-api.sh (8000) et ./arena/lancer-front.sh (3000)"
