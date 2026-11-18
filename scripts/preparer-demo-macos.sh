#!/usr/bin/env bash
# Démo locale macOS : SQLite isolée dans le dépôt, jamais le VPS.
#   bash scripts/preparer-demo-macos.sh --check
#   bash scripts/preparer-demo-macos.sh --apply --confirm-local-demo
# Recrée les données versionnées puis complète 3500 → 5000 profils fictifs.
# Ne restaure PAS les données saisies manuellement dans la session Arena.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
DB="$ROOT/backend/db.sqlite3"
ENV_FILE="$ROOT/backend/.env"
FRONT_ENV="$ROOT/frontend/.env"
MARKER='# INJS_LOCAL_DEMO_ONLY'
APPLY=0
case "${1:---check}" in
  --check) [ "$#" -eq 0 ] || [ "$#" -eq 1 ] || { echo 'Arguments inattendus' >&2; exit 2; } ;;
  --apply) [ "${2:-}" = '--confirm-local-demo' ] && [ "$#" -eq 2 ] || {
      echo 'Confirmation requise : --apply --confirm-local-demo' >&2; exit 2;
    }
    APPLY=1 ;;
  *) echo 'Usage: bash scripts/preparer-demo-macos.sh [--check | --apply --confirm-local-demo]' >&2; exit 2 ;;
esac

[ -f "$ROOT/backend/manage.py" ] && [ -f "$ROOT/arena/remplir-base-locale.py" ] \
  || { echo 'Dépôt incomplet : backend/ et arena/ requis.' >&2; exit 1; }
if [ -e "$ENV_FILE" ] && ! grep -qFx "$MARKER" "$ENV_FILE"; then
  echo "backend/.env existe et n'est pas marqué DEMO LOCALE : refus. N'écrasez pas votre configuration." >&2
  exit 1
fi
if [ -e "$FRONT_ENV" ] && ! grep -qFx "$MARKER" "$FRONT_ENV"; then
  echo "frontend/.env existe et peut pointer vers un autre site : refus. Ne l'écrasez pas." >&2
  exit 1
fi
if [ -e "$DB" ]; then
  echo "Base déjà présente : $DB. Aucune réinitialisation ni seed sur une base existante." >&2
  echo 'Si elle contient des données à conserver, faites une sauvegarde et utilisez un clone neuf.' >&2
  exit 1
fi
if [ "$APPLY" -eq 0 ]; then
  printf 'Cible EXCLUSIVEMENT locale : %s\n' "$DB"
  printf 'Aucune base existante. Le remplissage créera ~5000 profils fictifs, des comptes démo et des référentiels.\n'
  printf 'Aucune copie exacte de la SQLite Arena ni connexion au VPS.\n'
  exit 0
fi

PYTHON=''
for candidat in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidat" >/dev/null 2>&1 && "$candidat" -c \
      'import sys; assert (3, 10) <= sys.version_info[:2] < (3, 14)' 2>/dev/null; then
    PYTHON="$candidat"
    break
  fi
done
[ -n "$PYTHON" ] || { echo 'Python 3.10–3.13 requis (installer Python 3.12 recommandé).' >&2; exit 1; }
command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 \
  || { echo 'Node.js et npm requis pour le frontend (Node 20.19+ recommandé).' >&2; exit 1; }
node -e 'const [major,minor] = process.versions.node.split(".").map(Number); process.exit(major > 22 || (major === 22 && minor >= 12) || (major === 20 && minor >= 19) ? 0 : 1)' \
  || { echo 'Node.js 20.19+ ou 22.12+ requis pour Vite.' >&2; exit 1; }

umask 077
if [ ! -f "$ROOT/backend/.venv/bin/python" ]; then
  "$PYTHON" -m venv "$ROOT/backend/.venv"
fi
VENV="$ROOT/backend/.venv/bin/python"
"$VENV" -m pip install -r "$ROOT/backend/requirements.txt"
if [ ! -f "$ENV_FILE" ]; then
  SECRET="$($VENV -c 'import secrets; print(secrets.token_urlsafe(48))')"
  cat > "$ENV_FILE" <<ENV
$MARKER
DJANGO_DEBUG=1
DJANGO_SECRET_KEY=$SECRET
USE_SQLITE=1
SQLITE_PATH=$DB
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
ENV
  chmod 600 "$ENV_FILE"
fi
if [ ! -f "$FRONT_ENV" ]; then
  cat > "$FRONT_ENV" <<ENV
$MARKER
VITE_API_URL=/api
VITE_BADGE_BASE_URL=http://localhost:3000
ENV
  chmod 600 "$FRONT_ENV"
fi
export DJANGO_SETTINGS_MODULE=config.settings DJANGO_DEBUG=1 USE_SQLITE=1 SQLITE_PATH="$DB"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
# Le script vérifie la cible, crée une sauvegarde si nécessaire et applique
# les migrations + seeds versionnés, dont la cohorte initiale de 3500.
"$VENV" "$ROOT/arena/remplir-base-locale.py" --sqlite --apply --confirm-demo

# Le complément est une opération distincte et refuse tout autre état de base.
# Le mode simulation vérifie 3500 inscriptions, 67 enseignants et 130 groupes.
export DJANGO_SETTINGS_MODULE=arena.settings_sandbox
(cd "$ROOT/backend" && "$VENV" manage.py completer_capture_dashboard_demo --base "$DB")
BACKUP="$ROOT/backups/demo-macos-avant-complement-$(date +%Y%m%d-%H%M%S).sqlite3"
mkdir -p "$ROOT/backups"
"$VENV" - "$DB" "$BACKUP" <<'PY'
import sqlite3, sys
source = sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True)
try:
    destination = sqlite3.connect(sys.argv[2])
    try:
        source.backup(destination)
        assert destination.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        destination.close()
finally:
    source.close()
PY
chmod 600 "$BACKUP"
printf 'Sauvegarde locale vérifiée avant complément : %s\n' "$BACKUP"
(cd "$ROOT/backend" && "$VENV" manage.py completer_capture_dashboard_demo \
  --base "$DB" --appliquer --confirmer DEMO_FICTIVE)

# Compteurs réels, pas d'inférence à partir d'une capture.
"$VENV" - "$DB" <<'PY'
import sqlite3, sys
connection = sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True)
try:
    for table in ('formations_participant', 'scolarite_dossieretudiant', 'formations_formateur'):
        print(f'{table}: {connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]}')
    assert connection.execute('SELECT COUNT(*) FROM formations_participant').fetchone()[0] == 5037
finally:
    connection.close()
PY
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  (cd "$ROOT/frontend" && npm ci)
fi
printf '\nDémo locale prête. Vérifier que les deux adresses restent sur localhost.\n'
printf 'API locale : cd "%s/backend" && "%s" manage.py runserver 127.0.0.1:8000\n' "$ROOT" "$VENV"
printf 'Site local : cd "%s/frontend" && npm run dev -- --host 127.0.0.1\n' "$ROOT"
