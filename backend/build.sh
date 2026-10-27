#!/usr/bin/env bash
# Script de build / déploiement (collectstatic + migrations + seeds optionnels).
set -o errexit

pip install -r requirements.txt

# Cache fichier Django en prod (FileBasedCache, throttling multi-workers).
mkdir -p "${CACHE_DIR:-$PWD/cache}"

python manage.py collectstatic --no-input
python manage.py migrate

# Charger les données de démo si la base est vide
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from authentication.models import User
if not User.objects.exists():
    print('Base vide — chargement des données de démo...')
    exec(open('seed_data.py').read())
else:
    print('Données existantes — seed ignoré.')
"

# Créer / mettre à jour les comptes mobile (opt-in — ne pas exécuter en prod par défaut)
if [ "${SEED_MOBILE_USERS:-}" = "1" ]; then
  python scripts/seed_mobile_users.py
else
  echo "Seed mobile ignoré (SEED_MOBILE_USERS≠1)."
fi
