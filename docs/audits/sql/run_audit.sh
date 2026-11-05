#!/bin/sh
# =====================================================================
# AUDIT COMPARATIF INJS — EXÉCUTION DE LA COLLECTE EN LECTURE SEULE
#
# Ce script ne fait QUE lire : les deux scripts SQL ouvrent une
# transaction « READ ONLY » et la terminent par ROLLBACK. Aucune
# écriture n'est possible, même par erreur.
#
# Il ne contient AUCUN secret : l'authentification repose sur ~/.pgpass
# ou sur l'utilisateur applicatif du conteneur PostgreSQL.
#
# Usage (sur le VPS, ou sur le Mac si psql est installé) :
#   sh run_audit.sh                 # utilise psql local
#   MODE=docker PG_CONTAINER=injs-postgres sh run_audit.sh
#
# Variables :
#   MODE            host (défaut) | docker
#   PG_CONTAINER    nom du conteneur PostgreSQL (MODE=docker)
#   PGUSER          utilisateur PostgreSQL (défaut : postgres)
#   PGHOST          hôte (défaut : 127.0.0.1 ; inutile en MODE=docker)
#   BASES           liste des bases à profiler
#                   (défaut : "injs-db injs_lmd_prod_20261026")
#   SORTIE          dossier de sortie (défaut : ./collecte)
# =====================================================================
set -eu

MODE="${MODE:-host}"
PG_CONTAINER="${PG_CONTAINER:-injs-postgres}"
PGUSER="${PGUSER:-postgres}"
PGHOST="${PGHOST:-127.0.0.1}"
BASES="${BASES:-injs-db injs_lmd_prod_20261026}"
SORTIE="${SORTIE:-./collecte}"
HORODATAGE=$(date -u +%Y%m%dT%H%M%SZ)
ICI=$(cd "$(dirname "$0")" && pwd)

mkdir -p "$SORTIE"

psql_exec() {
  # $1 = base, $2 = fichier SQL
  if [ "$MODE" = "docker" ]; then
    docker exec -i -u postgres "$PG_CONTAINER" \
      psql -X -q -U "$PGUSER" -d "$1" -f - < "$2"
  else
    psql -X -q -h "$PGHOST" -U "$PGUSER" -d "$1" -f "$2"
  fi
}

for base in $BASES; do
  echo "── Base : $base"
  for script in 00_profil_schema.sql 10_anomalies.sql; do
    fichier="$ICI/$script"
    [ -f "$fichier" ] || { echo "   ! script absent : $fichier" >&2; continue; }
    sortie="$SORTIE/${base}__${script%.sql}__${HORODATAGE}.txt"
    if psql_exec "$base" "$fichier" > "$sortie" 2>&1; then
      echo "   ok  $script → $sortie ($(wc -l < "$sortie") lignes)"
    else
      echo "   ECHEC $script → $sortie (voir le fichier ; les autres contrôles continuent)" >&2
    fi
  done
done

echo
echo "Collecte terminée dans : $SORTIE"
echo "Aucune écriture effectuée : chaque script se conclut par ROLLBACK en transaction READ ONLY."
