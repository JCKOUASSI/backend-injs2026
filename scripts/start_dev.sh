#!/usr/bin/env bash
# =============================================================================
# Démarrage complet de l'environnement de démonstration INJS-LMD (mode local)
#
# Architecture utilisée dans la sandbox (une seule origine, zéro proxy maison) :
#   - « frontend » (port 3000) : build React servi PAR Django (PREVIEW_SPA=1),
#     donc l'application web, l'API et l'admin sont sur la même origine.
#   - « backend »  (port 8000) : Django en mode API uniquement (JSON à la racine).
#   - « cron »     : worker de tâches planifiées (équivalent du service cron Docker).
#
# Le sandbox n'ayant pas Docker/PostgreSQL, la base utilisée est SQLite
# (USE_SQLITE=1 dans backend/.env). Le script est idempotent : il crée
# l'environnement virtuel, installe les dépendances, applique les migrations
# et charge les données de démo seulement si c'est nécessaire.
#
# Usage :
#   ./scripts/start_dev.sh            # démarre frontend(3000) + backend(8000) + cron
#   ./scripts/start_dev.sh frontend   # application web (Django + SPA) sur 3000
#   ./scripts/start_dev.sh backend    # API Django sur 8000
#   ./scripts/start_dev.sh cron       # worker de tâches planifiées
#   FRONTEND_MODE=dev ./scripts/start_dev.sh frontend  # Vite + HMR (dev local réel)
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"

log() { printf '\033[1;36m[start_dev]\033[0m %s\n' "$*"; }

ensure_backend() {
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
  if [ ! -f "$BACKEND/.env" ]; then
    log "Création de backend/.env (SQLite, développement)…"
    cat > "$BACKEND/.env" <<'ENV'
SECRET_KEY=django-insecure-dev-demo-key-1234567890
DEBUG=true
USE_SQLITE=1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,.e2b.app
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
CORS_ALLOWED_ORIGIN_REGEXES=^https://[a-z0-9-]+\.e2b\.app$
# Django CSRF accepte les wildcard hôtes (https://*.domaine), pas les regex.
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://*.e2b.app,http://*.e2b.app
FRONTEND_URL=http://localhost:3000
TRUST_FORWARDED_PROTO=1
USE_X_FORWARDED_HOST=1
DEV_FRAME_ANCESTORS=*
# Iframe d'aperçu (cookies tiers bloqués) : refresh/session/CSRF en SameSite=None
JWT_COOKIE_SAMESITE=None
JWT_COOKIE_SECURE=1
COOKIE_SAMESITE=None
# Démo uniquement : admin Django accessible sans cookie dans l'iframe (inertes en prod)
DEMO_ADMIN_AUTOLOGIN=1
ENV
  fi
  log "Application des migrations…"
  (cd "$BACKEND" && USE_SQLITE=1 "$VENV/bin/python" manage.py migrate --noinput)
  if [ ! -f "$BACKEND/.seed_ok" ]; then
    log "Chargement des données de démonstration (une seule fois)…"
    (cd "$BACKEND" && USE_SQLITE=1 "$VENV/bin/python" seed_data.py) && touch "$BACKEND/.seed_ok"
  fi
}

ensure_frontend() {
  if [ ! -d "$FRONTEND/node_modules" ]; then
    log "Installation des dépendances npm…"
    (cd "$FRONTEND" && npm install --silent)
  fi
  if [ ! -f "$FRONTEND/.env" ]; then
    cat > "$FRONTEND/.env" <<'ENV'
# URLs relatives : l'application et l'API sont servies sur la même origine (Django)
VITE_API_URL=/api
VITE_ADMIN_URL=/admin/
# Aperçu en iframe : refresh aussi en stockage local (les cookies tiers peuvent être bloqués)
VITE_REFRESH_FALLBACK=1
ENV
  fi
}

build_frontend() {
  ensure_frontend
  log "Build de production du frontend (dist/)…"
  (cd "$FRONTEND" && npm run build)
}

start_backend() {
  ensure_backend
  log "Démarrage de l'API Django sur http://0.0.0.0:8000"
  cd "$BACKEND"
  exec "$VENV/bin/python" manage.py runserver 0.0.0.0:8000
}

start_frontend() {
  if [ "${FRONTEND_MODE:-spa}" = "dev" ]; then
    # Développement local réel : Vite (3000) + API Django à lancer à côté (8000)
    ensure_frontend
    log "Mode dev Vite (HMR) sur http://0.0.0.0:3000 (pensez à lancer ./start_dev.sh backend)"
    cd "$FRONTEND"
    exec npm run dev
  fi
  # Mode par défaut : build React servi par Django sur 3000 (app + API + admin).
  build_frontend
  ensure_backend
  log "Démarrage application complète (Django + SPA) sur http://0.0.0.0:3000"
  cd "$BACKEND"
  exec env PREVIEW_SPA=1 "$VENV/bin/python" manage.py runserver 0.0.0.0:3000
}

start_cron() {
  ensure_backend
  log "Démarrage du worker de tâches planifiées (heartbeats / pointages / sessions)"
  cd "$BACKEND"
  while true; do
    "$VENV/bin/python" manage.py process_mobile_heartbeats || true
    "$VENV/bin/python" manage.py auto_close_pointages --skip-heartbeat || true
    "$VENV/bin/python" manage.py auto_sessions || true
    sleep 300
  done
}

case "${1:-all}" in
  backend)  start_backend ;;
  frontend) start_frontend ;;
  cron)     start_cron ;;
  all)
    ensure_backend
    build_frontend
    log "Lancement frontend(3000) + backend(8000) + cron"
    "$0" frontend &
    PID_F=$!
    "$0" backend  &
    PID_B=$!
    "$0" cron     &
    PID_C=$!
    trap 'kill $PID_F $PID_B $PID_C 2>/dev/null || true' INT TERM EXIT
    wait -n
    ;;
  *)
    echo "Usage: $0 [all|frontend|backend|cron]" >&2
    exit 1
    ;;
esac
