#!/bin/sh
set -e

# Entrypoint backend INJS-LMD — démarrage sous contrôle
# 1. permissions media  2. décision de migration (config.demarrage)
# 3. exécution éventuelle : attente PostgreSQL, migrate, collectstatic, superuser
# 4. gunicorn (workers auto ou fixes)
#
# BLOCAGE B2 (mission 02, 6 novembre 2026) : `manage.py migrate` n'est PLUS
# exécuté implicitement. La décision est rendue par `python3 -m config.demarrage`
# (fonction pure, testée) selon la variable SKIP_DB_SETUP :
#   0  -> aucune migration (défaut sûr, y compris si la variable est absente)
#   10 -> migrations explicites (SKIP_DB_SETUP=false)
#   2  -> valeur invalide -> arrêt du conteneur, aucun comportement implicite.

if [ "$(id -u)" = "0" ]; then
  mkdir -p /app/media/students/qr
  chown -R appuser:appuser /app/media /app/staticfiles
  if ! command -v gosu >/dev/null 2>&1; then
    echo "[injs-be] ERREUR : démarrage en root, mais 'gosu' est introuvable dans l'image." >&2
    echo "[injs-be] L'image s'exécute normalement sous l'utilisateur 'appuser'." >&2
    exit 1
  fi
  exec gosu appuser /app/entrypoint.sh "$@"
fi

mkdir -p /app/media/students/qr

# ── Décision de démarrage (aucune migration implicite) ──────────────────────
set +e
python3 -m config.demarrage
CODE_DEMARRAGE=$?
set -e

case "$CODE_DEMARRAGE" in

  0)
    # Défaut sûr : aucune migration, aucun collectstatic, aucune création de compte.
    if [ "$#" -gt 0 ]; then
      echo "[injs-be] SKIP_DB_SETUP exec: $*"
      exec "$@"
    fi
    echo "[injs-be] SKIP_DB_SETUP sans commande" >&2
    exit 1
    ;;

  10)
    # Demande EXPLICITE et contraire au défaut : on applique les migrations.
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
    ;;

  *)
    echo "[injs-be] arrêt : configuration de démarrage invalide (code $CODE_DEMARRAGE)." >&2
    exit "$CODE_DEMARRAGE"
    ;;

esac

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
