FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    GUNICORN_WORKERS=auto \
    GUNICORN_WORKERS_MIN=2 \
    GUNICORN_WORKERS_MAX=10 \
    GUNICORN_AUTOSCALE=true \
    GUNICORN_AUTOSCALE_INTERVAL=30

WORKDIR /app

# Installer les dépendances système nécessaires (Pillow/qrcode + PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash \
        gcc \
        gosu \
        libjpeg-dev \
        zlib1g-dev \
        libpq-dev \
        procps \
    && rm -rf /var/lib/apt/lists/*

# Créer un utilisateur non-root pour la sécurité
RUN useradd --create-home --shell /bin/bash appuser

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copier le code backend (contexte de build = ./backend — voir .dockerignore)
COPY . .

# Créer les répertoires persistants et appliquer les permissions.
# Les scripts de politique de base (B2) doivent être exécutables dans l'image :
# l'entrypoint refuse de démarrer (code 78) si la politique est introuvable.
RUN mkdir -p /app/media /app/staticfiles && \
    chmod +x /app/entrypoint.sh \
             /app/scripts/gunicorn-autoscale.sh \
             /app/scripts/db_setup_policy.sh \
             /app/scripts/migrate_explicit.sh && \
    chown -R appuser:appuser /app

# Garde-fou de construction : la politique de préparation de base fait partie
# du contrat de démarrage. Une image sans ce fichier ne doit pas être publiée.
RUN test -r /app/scripts/db_setup_policy.sh && \
    sh -n /app/entrypoint.sh && \
    sh -n /app/scripts/db_setup_policy.sh && \
    sh -n /app/scripts/migrate_explicit.sh

# Valeur par défaut sûre : aucune préparation de base implicite.
# Une valeur explicite dans l'environnement du conteneur reste prioritaire.
ENV SKIP_DB_SETUP=true

# Collecter les fichiers statiques en tant qu'appuser (évite PermissionError au runtime)
USER appuser
RUN SECRET_KEY=build-time-only DEBUG=True \
    python manage.py collectstatic --noinput

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
