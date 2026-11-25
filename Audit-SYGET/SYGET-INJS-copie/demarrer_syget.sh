#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "[SYGET-INJS] Création de l'environnement virtuel Python..."
  python3 -m venv .venv
fi

source .venv/bin/activate
echo "[SYGET-INJS] Vérification / installation des dépendances..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

export DJANGO_USE_SQLITE=1
python manage.py migrate --noinput
echo "================================================================="
echo " SYGET-INJS démarré sur : http://127.0.0.1:8000/"
echo " Identifiants Administrateur : admin / admin"
echo "================================================================="
python manage.py runserver 0.0.0.0:8000
