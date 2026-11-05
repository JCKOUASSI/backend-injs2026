#!/bin/sh
# =====================================================================
# H2 — CARTOGRAPHIE TECHNIQUE DU VPS (LECTURE SEULE EXCLUSIVE)
#
# Ce script ne modifie rien :
#   - aucune commande docker de cycle de vie (restart/stop/start/rm/pull)
#   - aucun docker exec écrivant : uniquement `psql` en transaction
#     READ ONLY, `grep`, `cat`, `printenv`, `ps`
#   - aucun fichier créé hors du journal de sortie
#   - aucune valeur sensible affichée : les variables d'environnement
#     sont listées par NOM, les valeurs sont remplacées par <masque>
#
# Usage (sur le VPS, en tant qu'utilisateur ayant accès à docker) :
#     sh h2_collecte_lecture_seule.sh
#     sh h2_collecte_lecture_seule.sh 2>&1 | tee h2-collecte-$(date -u +%Y%m%dT%H%M%SZ).log
#
# Variables ajustables :
#     PG_CONTAINER=injs-db
#     BE_ANCIEN=injs-be  BE_CANDIDAT=injs-be-candidate  NPM=npm-app-1
#     BASES_METIER="injs-db injs_lmd_prod_20261026"
# =====================================================================
set -u

PG_CONTAINER="${PG_CONTAINER:-injs-db}"
BE_ANCIEN="${BE_ANCIEN:-injs-be}"
BE_CANDIDAT="${BE_CANDIDAT:-injs-be-candidate}"
NPM="${NPM:-npm-app-1}"
BASES_METIER="${BASES_METIER:-injs-db injs_lmd_prod_20261026}"
REDIS="${REDIS:-injs-redis}"
WORKER="${WORKER:-injs-worker}"
CRON="${CRON:-injs-cron}"
RABBIT="${RABBIT:-injs-rabbitmq}"

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
  if sudo -n true 2>/dev/null; then SUDO="sudo -n"; fi
fi

titre() { printf '\n\n========== %s ==========\n' "$1"; }
sous()  { printf '\n--- %s ---\n' "$1"; }
existe() { docker inspect "$1" >/dev/null 2>&1; }

# --- Masquage systématique des valeurs d'environnement -----------------
env_noms() {
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$1" 2>/dev/null \
    | sed 's/=.*/=<masque>/' | sort
}
non_secret() {
  # Uniquement le NOM de la base, l'hôte et le port : jamais de mot de passe.
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$1" 2>/dev/null \
    | grep -E '^(POSTGRES_DB|POSTGRES_HOST|POSTGRES_PORT|PGDATABASE|DB_NAME|DATABASE_NAME)=' \
    | sed 's/^/    /'
}
resume_conteneur() {
  docker inspect -f '    image      : {{.Config.Image}}
    cree       : {{.Created}}
    demarre    : {{.State.StartedAt}}
    statut     : {{.State.Status}}
    redemarre  : {{.HostConfig.RestartPolicy.Name}}' "$1" 2>/dev/null
}

# --- Accès PostgreSQL en lecture seule stricte -------------------------
# $1 = base ; $2 = SQL. Transaction READ ONLY, annulée en fin de bloc.
pg_run() {
  _db="$1"; shift
  _sql="$1"
  docker exec -i "$PG_CONTAINER" sh -c \
    "psql -X -q -v ON_ERROR_STOP=0 -U \"\$POSTGRES_USER\" -d \"$_db\" -f -" <<EOF
SET default_transaction_read_only = on;
SET statement_timeout = '120s';
BEGIN TRANSACTION READ ONLY;
$_sql
ROLLBACK;
EOF
}

echo "H2 — cartographie lecture seule"
echo "hôte    : $(hostname 2>/dev/null)"
echo "date    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "docker  : $(docker --version 2>/dev/null)"

# =====================================================================
titre "LOT 0 — CONTENEURS PRÉSENTS"
# =====================================================================
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null

# =====================================================================
titre "LOT 1 — POSTGRESQL : $PG_CONTAINER"
# =====================================================================
if existe "$PG_CONTAINER"; then
  sous "1.1 Fiche du conteneur"
  resume_conteneur "$PG_CONTAINER"
  docker inspect -f '    réseaux    : {{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}
    ports      : {{range $p,$c := .NetworkSettings.Ports}}{{$p}} {{end}}' "$PG_CONTAINER" 2>/dev/null
  sous "1.2 Volumes montés (données persistantes)"
  docker inspect -f '{{range .Mounts}}    {{.Type}}  {{.Source}} -> {{.Destination}} (rw={{.RW}}){{println}}{{end}}' "$PG_CONTAINER" 2>/dev/null
  sous "1.3 Variables d'environnement — NOMS UNIQUEMENT"
  env_noms "$PG_CONTAINER"
  sous "1.4 Nom de la base par défaut (non secret)"
  non_secret "$PG_CONTAINER"

  sous "1.5 Bases disponibles, taille, accès"
  pg_run postgres "SELECT datname AS base,
       pg_size_pretty(pg_database_size(datname)) AS taille,
       datallowconn AS connexions_autorisees
FROM pg_database
WHERE datistemplate = false
ORDER BY pg_database_size(datname) DESC;"

  sous "1.6 Utilisateurs PostgreSQL (aucun mot de passe)"
  pg_run postgres "SELECT rolname AS utilisateur, rolsuper AS superutilisateur, rolcanlogin AS peut_se_connecter
FROM pg_roles WHERE rolname NOT LIKE 'pg\_%' ORDER BY rolname;"

  sous "1.7 Emplacement physique des données"
  pg_run postgres "SHOW data_directory;"

  sous "1.8 Profil de chaque base (schémas, tables, tables non vides)"
  for base in $BASES_METIER; do
    printf '\n>>> base : %s\n' "$base"
    # reltuples = -1 signifie « jamais analysée » : ce n'est pas « vide ».
    pg_run "$base" "SELECT n.nspname AS schema,
       count(*) AS tables,
       count(*) FILTER (WHERE c.reltuples > 0) AS non_vides_estimees,
       count(*) FILTER (WHERE c.reltuples = 0) AS vides_estimees,
       count(*) FILTER (WHERE c.reltuples < 0) AS volume_inconnu
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p')
  AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
GROUP BY 1 ORDER BY 1;"
    pg_run "$base" "SELECT pg_size_pretty(pg_database_size(current_database())) AS taille_base,
       (SELECT count(*) FROM information_schema.tables WHERE table_schema='public') AS tables_publiques,
       (SELECT count(*) FROM pg_namespace WHERE nspname NOT LIKE 'pg\_%' AND nspname <> 'information_schema') AS schemas;"
  done
else
  echo "IMPOSSIBLE : conteneur $PG_CONTAINER introuvable"
fi

# =====================================================================
titre "LOT 2 — BACKENDS : $BE_ANCIEN / $BE_CANDIDAT"
# =====================================================================
i=0
for c in "$BE_ANCIEN" "$BE_CANDIDAT"; do
  i=$((i+1))
  sous "2.$i Conteneur $c"
  if existe "$c"; then
    resume_conteneur "$c"
    docker inspect -f '    réseaux+alias: {{range $k,$v := .NetworkSettings.Networks}}{{$k}}[{{range $v.Aliases}}{{.}} {{end}}] {{end}}
    ports expo : {{range $p,$v := .NetworkSettings.Ports}}{{$p}}->{{range $v}}{{.HostPort}} {{end}}{{end}}' "$c" 2>/dev/null
    docker inspect -f '{{range .Mounts}}    volume: {{.Type}} {{.Source}} -> {{.Destination}} (rw={{.RW}}){{println}}{{end}}' "$c" 2>/dev/null
    printf '    variables (noms) :\n'
    env_noms "$c" | sed 's/^/      /'
    printf '    connexion PostgreSQL (base/hôte/port, sans secret) :\n'
    non_secret "$c"
  else
    echo "IMPOSSIBLE : conteneur $c introuvable"
  fi
done

sous "2.9 Comparaison des bases visées par les deux backends"
db_de() { docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$1" 2>/dev/null | sed -n 's/^POSTGRES_DB=//p' | head -1; }
A_DB=$(db_de "$BE_ANCIEN" 2>/dev/null || true)
C_DB=$(db_de "$BE_CANDIDAT" 2>/dev/null || true)
if [ -z "${A_DB:-}" ] && [ -z "${C_DB:-}" ]; then
  echo "INDÉTERMINÉ : aucune variable POSTGRES_DB lisible (les conteneurs existent-ils ?)"
elif [ "${A_DB:-}" = "${C_DB:-}" ]; then
  echo "MÊME BASE : '$A_DB' pour $BE_ANCIEN et $BE_CANDIDAT"
else
  echo "BASES DIFFÉRENTES : $BE_ANCIEN='${A_DB:-?}' / $BE_CANDIDAT='${C_DB:-?}'"
fi

sous "2.10 Autres services utilisant une base (Redis, worker, cron, rabbitmq)"
for c in "$REDIS" "$WORKER" "$CRON" "$RABBIT"; do
  if existe "$c"; then
    printf '  %s :\n' "$c"
    non_secret "$c" | sed 's/^/  /'
  else
    printf '  %s : absent\n' "$c"
  fi
done

# =====================================================================
titre "LOT 3 — ROUTAGE PUBLIC (Nginx Proxy Manager : $NPM)"
# =====================================================================
if existe "$NPM"; then
  resume_conteneur "$NPM"
  sous "3.1 Réseaux Docker et adresses (pour résoudre les cibles proxy_pass)"
  for net in $(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$NPM" 2>/dev/null); do
    printf '\n  réseau %s :\n' "$net"
    docker network inspect "$net" -f '{{range .Containers}}    {{.Name}}  {{.IPv4Address}}{{println}}{{end}}' 2>/dev/null
  done

  sous "3.2 Proxy hosts : domaines et destinations internes"
  docker exec "$NPM" sh -c \
    'for f in /data/nginx/proxy_host/*.conf; do
       [ -f "$f" ] || continue
       echo "  --- $f"
       grep -E "^\s*(server_name|proxy_pass|set \$server|server_name_in_redirect)" "$f" \
         | sed "s/^/    /"
     done' 2>/dev/null || echo "  IMPOSSIBLE : lecture de /data/nginx/proxy_host refusée"

  sous "3.3 Redirections (fichiers redirection_host) — domaines et cibles"
  docker exec "$NPM" sh -c \
    'for f in /data/nginx/redirection_host/*.conf; do
       [ -f "$f" ] || continue
       echo "  --- $f"; grep -E "server_name|return|rewrite" "$f" | sed "s/^/    /"
     done' 2>/dev/null || echo "  aucun fichier de redirection lisible"

  sous "3.4 Cible du domaine injs.badge-qr-code.pro"
  docker exec "$NPM" sh -c \
    'grep -rl "injs.badge-qr-code.pro" /data/nginx/ 2>/dev/null | while read -r f; do
       echo "  fichier : $f"
       grep -E "server_name|proxy_pass" "$f" | sed "s/^/    /"
     done' 2>/dev/null || echo "  domaine non trouvé dans /data/nginx"
else
  echo "IMPOSSIBLE : conteneur $NPM introuvable"
fi

# =====================================================================
titre "LOT 4 — VOLUMES ET SAUVEGARDES"
# =====================================================================
sous "4.1 Volumes Docker (nom, point de montage, taille si connue)"
docker volume ls -q 2>/dev/null | while read -r v; do
  printf '  %-45s %s\n' "$v" "$(docker volume inspect -f '{{.Mountpoint}}' "$v" 2>/dev/null)"
done
sous "4.2 Espace disque Docker"
docker system df -v 2>/dev/null | head -40

sous "4.3 Recherche de dumps et archives (aucune modification)"
for d in /home /opt /srv /data /mnt /media /var/backups /root; do
  [ -d "$d" ] || continue
  $SUDO find "$d" -xdev -maxdepth 6 -type f \
    \( -name '*.sql' -o -name '*.sql.gz' -o -name '*.dump' -o -name '*.backup' \
       -o -name '*.tar.gz' -o -name '*.tgz' \) \
    -printf '  %TY-%Tm-%Td %TH:%TM  %10s o  %p\n' 2>/dev/null
done | sort -k1,2

sous "4.4 Sauvegardes autour du 2026-10-26"
for d in /home /opt /srv /data /mnt /media /var/backups /root; do
  [ -d "$d" ] || continue
  $SUDO find "$d" -xdev -maxdepth 6 -type f -newermt '2026-10-20' ! -newermt '2026-11-06' \
    \( -name '*.sql*' -o -name '*.dump' -o -name '*.gz' -o -name '*.tar*' \) \
    -printf '  %TY-%Tm-%Td %TH:%TM  %10s o  %p\n' 2>/dev/null
done | sort

sous "4.5 Planification de sauvegarde visible (crontab, timers)"
$SUDO crontab -l 2>/dev/null | grep -iE 'dump|backup|pg_dump|sauvegarde' || echo "  aucune entrée crontab lisible"
for f in /etc/cron.d/* /etc/crontab; do
  [ -f "$f" ] && $SUDO grep -HiE 'pg_dump|backup|sauvegarde' "$f" 2>/dev/null
done

# =====================================================================
titre "LOT 5 — RECHERCHE DU PACK D'AUDIT"
# =====================================================================
for motif in '20_empreinte_modules.sql' '19_empreinte_modules.sql' 'run_audit.sh' 'consolider.py'; do
  printf '\n  fichiers nommés %s :\n' "$motif"
  for d in /home /opt /srv /root /data; do
    [ -d "$d" ] || continue
    $SUDO find "$d" -xdev -maxdepth 7 -type f -name "$motif" \
      -printf '    %TY-%Tm-%Td  %p\n' 2>/dev/null
  done
done
printf '\n  répertoires docs/audits/sql :\n'
for d in /home /opt /srv /root /data; do
  [ -d "$d" ] || continue
  $SUDO find "$d" -xdev -maxdepth 7 -type d -path '*docs/audits/sql' 2>/dev/null | sed 's/^/    /'
done

# =====================================================================
titre "SYNTHÈSE H2 (bloc destiné au rapport)"
# =====================================================================
echo "SYNTHESE_H2_BEGIN"
echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "pg_image=$(docker inspect -f '{{.Config.Image}}' "$PG_CONTAINER" 2>/dev/null || echo INDETERMINE)"
echo "pg_data_dir_mount=$(docker inspect -f '{{range .Mounts}}{{.Source}}->{{.Destination}} {{end}}' "$PG_CONTAINER" 2>/dev/null || echo INDETERMINE)"
echo "backend_ancien=$BE_ANCIEN image=$(docker inspect -f '{{.Config.Image}}' "$BE_ANCIEN" 2>/dev/null || echo INDETERMINE) base=${A_DB:-INDETERMINE}"
echo "backend_candidat=$BE_CANDIDAT image=$(docker inspect -f '{{.Config.Image}}' "$BE_CANDIDAT" 2>/dev/null || echo INDETERMINE) base=${C_DB:-INDETERMINE}"
echo "meme_base=$([ "${A_DB:-x}" = "${C_DB:-y}" ] && echo OUI || echo NON)"
echo "npm=$NPM"
echo "SYNTHESE_H2_END"
echo
echo "AUCUNE DONNÉE MODIFIÉE — AUCUNE BASCULE EFFECTUÉE — AUDIT EN LECTURE SEULE"
