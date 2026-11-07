#!/bin/sh
set -e

# Entrypoint backend INJS-LMD.
#
# MISSION 02 / BLOCAGE B2 — la préparation de la base n'est plus implicite.
#
# La décision est déléguée à `scripts/db_setup_policy.sh`, testable sans Django :
#   * SKIP_DB_SETUP absent, vide, true/1/yes/on -> aucune préparation (skip) ;
#   * SKIP_DB_SETUP = false/0/no/off            -> préparation explicite (run) ;
#   * toute autre valeur                        -> arrêt immédiat (code 64).
#
# Conséquence : un conteneur démarré sans SKIP_DB_SETUP ne migre plus la base
# par accident. Les migrations s'exécutent uniquement sur demande explicite,
# via `python manage.py migrate` ou `scripts/migrate_explicit.sh`.
#
# Séquence lorsque la préparation est explicitement demandée (run) :
# 1. permissions media  2. attente PostgreSQL  3. migrate  4. collectstatic
# 5. superuser idempotent  6. commande fournie ou gunicorn (workers auto/fixes)

POLITIQUE_DB="${INJS_DB_SETUP_POLICY:-/app/scripts/db_setup_policy.sh}"
if [ ! -r "$POLITIQUE_DB" ]; then
  echo "[injs-be] Politique de base introuvable : $POLITIQUE_DB" >&2
  exit 78
fi
# shellcheck source=/dev/null
. "$POLITIQUE_DB"

# Politique résolue AVANT toute action : une valeur inutilisable arrête le
# conteneur sans rien exécuter (jamais de repli silencieux vers migrate).
if ! injs_resoudre_politique_db; then
  exit "$INJS_EXIT_POLITIQUE_INVALIDE"
fi

MEDIA_DIR="${INJS_MEDIA_DIR:-/app/media}"
STATIC_DIR="${INJS_STATIC_DIR:-/app/staticfiles}"
SELF="${INJS_ENTRYPOINT_PATH:-/app/entrypoint.sh}"

if [ "$(id -u)" = "0" ] && command -v gosu >/dev/null 2>&1; then
  mkdir -p "$MEDIA_DIR/students/qr"
  chown -R appuser:appuser "$MEDIA_DIR" "$STATIC_DIR"
  exec gosu appuser "$SELF" "$@"
fi

mkdir -p "$MEDIA_DIR/students/qr"

if [ "$INJS_DB_SETUP_MODE" = "skip" ]; then
  if [ "$#" -gt 0 ]; then
    echo "[injs-be] preparation de base ignoree (SKIP_DB_SETUP=${SKIP_DB_SETUP:-absent}) -> exec: $*"
    exec "$@"
  fi
  echo "[injs-be] SKIP_DB_SETUP actif mais aucune commande fournie :" >&2
  echo "[injs-be] fournir une commande explicite (gunicorn ... ou manage.py migrate)." >&2
  exit 1
fi

echo "[injs-be] SKIP_DB_SETUP=${SKIP_DB_SETUP:-absent} -> preparation explicite de la base demandee."

if [ "${USE_POSTGRES:-true}" = "true" ]; then
  echo "[injs-be] waiting for database..."
  python3 - <<'PY'
import os, sys, time
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.db import connection
for attempt in range(60):
    try:
        connection.ensure_connection()
        print('[injs-be] database ready')
        sys.exit(0)
    except Exception as exc:
        print(f'[injs-be] db not ready ({attempt+1}/60): {exc}')
        time.sleep(2)
print('[injs-be] database unavailable', file=sys.stderr)
sys.exit(1)
PY
fi

echo "[injs-be] migrate..."
python manage.py migrate --noinput

echo "[injs-be] collectstatic..."
python manage.py collectstatic --noinput

if [ -n "${DJANGO_SUPERUSER_EMAIL:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  echo "[injs-be] ensure superuser..."
  python3 - <<'PY'
import os, django
from django.contrib.auth import get_user_model
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
User = get_user_model()
email = os.environ['DJANGO_SUPERUSER_EMAIL'].strip().lower()
password = os.environ['DJANGO_SUPERUSER_PASSWORD']
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', email.split('@')[0])
first_name = os.environ.get('DJANGO_SUPERUSER_FIRST_NAME', 'Admin')
last_name = os.environ.get('DJANGO_SUPERUSER_LAST_NAME', 'INJS')
if not User.objects.filter(email=email).exists():
    User.objects.create_superuser(
        username=username, email=email, password=password,
        first_name=first_name, last_name=last_name,
        is_staff=True, is_superuser=True,
    )
    print(f'[injs-be] superuser created: {email}')
else:
    print(f'[injs-be] superuser already exists: {email}')
PY
fi

if [ "$#" -gt 0 ]; then
  echo "[injs-be] exec: $*"
  exec "$@"
fi

WORKERS="${GUNICORN_WORKERS:-auto}"
TIMEOUT="${GUNICORN_TIMEOUT:-120}"
PORT="${PORT:-8000}"

if [ "$WORKERS" = "auto" ]; then
  NP="$(nproc)"
  W="$(( NP * 2 + 1 ))"
  echo "[injs-be] gunicorn workers=auto (CPUs=$NP -> $W workers)"
else
  W="$WORKERS"
  echo "[injs-be] gunicorn workers=$W"
fi

exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers "$W" \
  --timeout "$TIMEOUT" \
  --access-logfile - \
  --error-logfile -
