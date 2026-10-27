#!/bin/bash

set -euo pipefail

# ============================================================
# Sauvegarde sécurisée de la base PostgreSQL INJS-LMD
# ============================================================

DB_HOST="127.0.0.1"
DB_PORT="5432"
DB_NAME="injs_lmd_current"
DB_USER="injs_user"

BACKUP_DIR="$HOME/Backups/INJS-LMD/database"
TIMESTAMP="$(date '+%Y-%m-%d_%H-%M-%S')"

BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.dump"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"

echo "============================================================"
echo " SAUVEGARDE INJS-LMD"
echo "============================================================"
echo
echo "Base      : $DB_NAME"
echo "Utilisateur : $DB_USER"
echo "Serveur   : $DB_HOST:$DB_PORT"
echo "Destination : $BACKUP_FILE"
echo

mkdir -p "$BACKUP_DIR"

echo "1/5 Vérification PostgreSQL..."
pg_isready -h "$DB_HOST" -p "$DB_PORT"

echo
echo "2/5 Vérification de la base..."
psql \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  -c "SELECT current_database(), current_user;"

echo
echo "3/5 Création du dump..."
pg_dump \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  -Fc \
  -f "$BACKUP_FILE"

echo
echo "4/5 Vérification du dump..."

if [ ! -s "$BACKUP_FILE" ]; then
    echo "ERREUR : le dump est vide."
    rm -f "$BACKUP_FILE"
    exit 1
fi

pg_restore --list "$BACKUP_FILE" > /dev/null

echo "Dump PostgreSQL valide."
ls -lh "$BACKUP_FILE"

echo
echo "5/5 Calcul SHA-256..."
shasum -a 256 "$BACKUP_FILE" | tee "$CHECKSUM_FILE"

echo
echo "============================================================"
echo " SAUVEGARDE TERMINÉE AVEC SUCCÈS"
echo "============================================================"
echo
echo "Dump :"
echo "$BACKUP_FILE"
echo
echo "SHA-256 :"
echo "$CHECKSUM_FILE"
echo
