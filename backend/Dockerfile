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

# Copier le code backend (contexte = racine du monorepo)
COPY . .

# Créer les répertoires persistants et appliquer les permissions
RUN mkdir -p /app/media /app/staticfiles && \
    chmod +x /app/entrypoint.sh /app/scripts/gunicorn-autoscale.sh && \
    chown -R appuser:appuser /app

# Collecter les fichiers statiques en tant qu'appuser (évite PermissionError au runtime)
USER appuser
RUN SECRET_KEY=build-time-only DEBUG=True \
    python manage.py collectstatic --noinput

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
