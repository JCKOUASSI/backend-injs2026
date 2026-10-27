#!/bin/sh
set -e

# Entrypoint backend INJS-LMD — mécanisme automatique (monorepo injs-app-ref)
# 1. permissions media  2. attente PostgreSQL  3. migrate  4. collectstatic
# 5. superuser idempotent  6. gunicorn (workers auto ou fixes)

if [ "$(id -u)" = "0" ]; then
  mkdir -p /app/media/students/qr
  chown -R appuser:appuser /app/media /app/staticfiles
  exec gosu appuser /app/entrypoint.sh "$@"
fi

mkdir -p /app/media/students/qr

if [ "${SKIP_DB_SETUP:-}" = "true" ]; then
  if [ "$#" -gt 0 ]; then
    echo "[injs-be] SKIP_DB_SETUP exec: $*"
    exec "$@"
  fi
  echo "[injs-be] SKIP_DB_SETUP sans commande" >&2
  exit 1
fi

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
