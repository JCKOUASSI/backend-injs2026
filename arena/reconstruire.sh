#!/usr/bin/env bash
# =============================================================================
# Reconstruction COMPLÈTE de l'aperçu après réinitialisation du bac à sable.
#
# Le bac à sable est éphémère : environnement virtuel, node_modules, .env et
# base SQLite peuvent disparaître. Tout ce qui est nécessaire pour repartir est
# versionné dans le dépôt ; ce script enchaîne, de façon idempotente :
#
#   1. environnement Python (venv + requirements.txt)
#   2. profil d'aperçu + backend/.env + frontend/.env (arena/bootstrap.sh)
#   3. schéma (migrate)
#   4. données de démonstration (seed_data.py)
#   5. référentiels officiels INJS (importer_referentiels_injs : écoles,
#      mentions, 8 filières, cycles LMD, modules officiels, lieux, volumes)
#   6. dépendances npm du site
#
# Les données SAISIES dans l'application ne sont pas reproductibles : si une
# sauvegarde existe dans backups/ (voir arena/sauvegarder-donnees.sh), le
# script l'indique ; restaurez-la avec arena/restaurer-donnees.sh.
#
#   ./arena/reconstruire.sh           # tout reconstruire (étapes déjà faites sautées)
#   ./arena/reconstruire.sh --verifier  # ne rien modifier, juste contrôler l'état
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"

log() { printf '\033[1;36m[reconstruire]\033[0m %s\n' "$*"; }

etat() {
  # Affiche l'état de chaque brique ; renvoie 0 si tout est en place.
  local manquant=0
  for entree in \
    "venv:$VENV/bin/python" \
    "backend/.env:$BACKEND/.env" \
    "profil d'aperçu:$ROOT/arena/settings_sandbox.py" \
    "base SQLite:$BACKEND/db.sqlite3" \
    "frontend/.env:$FRONTEND/.env" \
    "node_modules:$FRONTEND/node_modules/.bin/vite"
  do
    nom="${entree%%:*}"; chemin="${entree#*:}"
    if [ -e "$chemin" ]; then echo "  ✓ $nom"; else echo "  ✗ $nom — absent ($chemin)"; manquant=1; fi
  done
  if ls "$ROOT"/backups/apercu-*/donnees.json >/dev/null 2>&1; then
    echo "  ℹ sauvegarde(s) de données présente(s) dans backups/ :"
    ls -1d "$ROOT"/backups/apercu-* | sed 's/^/      /'
    echo "    → restauration des saisies : ./arena/restaurer-donnees.sh <dossier>"
  fi
  return $manquant
}

if [ "${1:-}" = "--verifier" ]; then
  log "État de l'aperçu :"
  etat || true
  exit 0
fi

# ── 1. Backend Python ────────────────────────────────────────────────────────
if [ ! -x "$VENV/bin/python" ]; then
  log "Création de l'environnement virtuel Python…"
  python3 -m venv "$VENV"
fi
if [ ! -f "$VENV/.deps_ok" ] || [ "$BACKEND/requirements.txt" -nt "$VENV/.deps_ok" ]; then
  log "Installation des dépendances Python…"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r "$BACKEND/requirements.txt"
  touch "$VENV/.deps_ok"
fi

# ── 2. Profil d'aperçu et environnements ─────────────────────────────────────
# bootstrap.sh régénère le profil à l'identique et n'écrit backend/.env que
# s'il est absent (jamais d'écrasement sans --write-env explicite).
log "Profil d'aperçu…"
bash "$ROOT/arena/bootstrap.sh" >/dev/null
if [ ! -f "$FRONTEND/.env" ]; then
  cat > "$FRONTEND/.env" <<'ENV'
# Aperçu Arena : URLs relatives (proxy Vite /api -> Django 8000)
VITE_API_URL=/api
# Iframe d'aperçu : refresh aussi en stockage local (cookies tiers parfois bloqués)
VITE_REFRESH_FALLBACK=1
ENV
fi

# ── 3–5. Schéma, démonstration, référentiels officiels ─────────────────────
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-arena.settings_sandbox}"
export USE_SQLITE=1

log "Migrations…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py migrate --noinput)

if [ ! -f "$BACKEND/.seed_ok" ]; then
  log "Données de démonstration…"
  (cd "$BACKEND" && "$VENV/bin/python" seed_data.py) && touch "$BACKEND/.seed_ok"
fi

log "Référentiels officiels INJS (import idempotent)…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py importer_referentiels_injs) \
  && touch "$BACKEND/.referentiels_ok"

# ── 6. Site web ──────────────────────────────────────────────────────────────
if [ ! -d "$FRONTEND/node_modules" ]; then
  log "Installation des dépendances npm…"
  (cd "$FRONTEND" && if [ -f package-lock.json ]; then npm ci --silent; else npm install --silent; fi)
fi

# ── Contrôle final ───────────────────────────────────────────────────────────
log "Contrôle final :"
etat || true
(cd "$BACKEND" && "$VENV/bin/python" manage.py verifier_coherence_referentiels | tail -3)

log "Reconstruction terminée. Lancement :"
echo "  ./arena/lancer-api.sh         # API + admin Django (8000)"
echo "  ./arena/lancer-front-demo.sh  # site web (3000)"
