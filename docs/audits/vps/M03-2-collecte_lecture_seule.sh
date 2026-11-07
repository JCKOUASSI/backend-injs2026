#!/bin/sh
# =============================================================================
# MISSION 03.2 — AUDIT TECHNIQUE RÉEL DU VPS — COLLECTE LECTURE SEULE
#
# Ce script produit, en une passe, les preuves des LOT 1 à 6 de la mission.
# Il remplace provisoirement le kit M03.1 (mêmes garanties, numérotation alignée
# sur la mission 03.2).
#
# GARANTIES (vérifiables à la lecture du fichier) :
#   * aucun cycle de vie Docker (run/start/stop/restart/rm/pull/push/build/prune,
#     compose up|down) ;
#   * aucun SQL d'écriture ; psql en `default_transaction_read_only=on` ;
#   * aucune modification de permissions, de rôles ou de configuration ;
#   * aucune restauration, aucune migration ;
#   * secrets jamais affichés : variables listées PAR NOM, valeurs <masque>.
#
# Exécution :
#   sh M03-2-collecte_lecture_seule.sh 2>&1 | tee m032-$(date -u +%Y%m%dT%H%M%SZ).log
#
# Variables : PG_CONTAINER=injs-db  NPM=npm-app-1  REDIS=injs-redis
#             RABBIT=injs-rabbitmq  DOMAINE=injs.badge-qr-code.pro
#             BASES="injs-db injs_lmd_prod_20261026"  PGUSER=postgres
#             CHECKSUM=1  (calcule sha256 des sauvegardes — LECTURE seule, lent)
# =============================================================================
set -u

PG_CONTAINER="${PG_CONTAINER:-injs-db}"
NPM="${NPM:-npm-app-1}"
REDIS="${REDIS:-injs-redis}"
RABBIT="${RABBIT:-injs-rabbitmq}"
DOMAINE="${DOMAINE:-injs.badge-qr-code.pro}"
BASES="${BASES:-injs-db injs_lmd_prod_20261026}"
PGUSER="${PGUSER:-postgres}"
CHECKSUM="${CHECKSUM:-0}"

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
  if sudo -n true 2>/dev/null; then SUDO="sudo -n"; fi
fi

lot()  { printf '\n\n########## LOT %s ##########\n' "$1"; }
sous() { printf '\n--- %s ---\n' "$1"; }

echo "MISSION 03.2 — collecte lecture seule"
echo "horodatage : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "hôte : $(hostname 2>/dev/null)  opérateur : $(id -un 2>/dev/null)"

# =============================================================================
lot "1 — SYSTÈME"
hostnamectl 2>&1 | head -12
cat /etc/os-release 2>&1 | grep -E '^(NAME|VERSION|VERSION_ID|PRETTY_NAME|ID)='
uname -a
echo "nproc : $(nproc 2>/dev/null)"
free -h
df -hT -x tmpfs -x devtmpfs 2>/dev/null || df -h
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT,TYPE 2>&1 | head -25
uptime
sous "1.9 Services en échec (systemctl --failed)"
systemctl --failed --no-pager 2>&1 | head -15
sous "1.10 Pare-feu"
if command -v firewall-cmd >/dev/null 2>&1; then
  $SUDO firewall-cmd --state 2>&1
  $SUDO firewall-cmd --list-all 2>&1
else
  echo "firewalld : absent"; command -v nft >/dev/null 2>&1 && $SUDO nft list ruleset 2>&1 | head -40
fi
sous "1.11 Ports en écoute"
(ss -tulpnH 2>/dev/null || netstat -tulpn 2>/dev/null) | head -60
sous "1.12 Services actifs"
systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null | head -30

# =============================================================================
lot "2 — DOCKER"
docker version --format 'client={{.Client.Version}} serveur={{.Server.Version}}' 2>&1
docker compose version 2>&1 | head -1
sous "2.3 Conteneurs"
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1
sous "2.4 Détail par conteneur (image, état, ports, réseaux, volumes, restart, health)"
for c in $(docker ps -aq 2>/dev/null); do
  docker inspect "$c" --format \
'{{.Name}} | image={{.Config.Image}} | etat={{.State.Status}} | restart={{.HostConfig.RestartPolicy.Name}} | health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}
    ports={{json .HostConfig.PortBindings}}
    reseaux={{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}
    volumes={{range .Mounts}}{{.Type}}:{{.Source}}->{{.Destination}}(rw={{.RW}}) {{end}}' 2>/dev/null
done
sous "2.5 Images"
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}\t{{.Size}}' 2>&1
sous "2.6 Réseaux"
docker network ls 2>&1
sous "2.7 Volumes"
docker volume ls 2>&1
for v in $(docker volume ls -q 2>/dev/null); do
  docker volume inspect "$v" --format '{{.Name}} | {{.Mountpoint}}' 2>/dev/null
done
sous "2.8 Ressources (instantané)"
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}' 2>&1 | head -25
docker system df 2>&1
sous "2.9 Variables d'environnement — NOMS seulement"
for c in $(docker ps -q 2>/dev/null); do
  echo "-- $(docker inspect "$c" --format '{{.Name}}') --"
  docker inspect "$c" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | cut -d= -f1
done

# =============================================================================
lot "3 — POSTGRESQL"
sous "3.1 Instances PostgreSQL détectées"
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' 2>/dev/null | grep -i postgres \
  || echo "aucun conteneur dont l'image contient 'postgres'"

psql_ro() {  # transaction explicitement en lecture seule
  docker exec -i "$PG_CONTAINER" env PGOPTIONS='-c default_transaction_read_only=on' \
    psql -U "$PGUSER" -d "$1" -tAc "$2" 2>&1
}

if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$PG_CONTAINER"; then
  sous "3.2 Version"
  psql_ro postgres 'select version();'
  sous "3.3 Bases : nom, taille, encodage"
  psql_ro postgres "select datname, pg_size_pretty(pg_database_size(datname)),
                            pg_encoding_to_char(encoding), datcollate
                     from pg_database where not datistemplate order by datname;"
  sous "3.4 Détail par base métier"
  for b in $BASES; do
    echo "-- $b --"
    psql_ro postgres "select '$b', pg_size_pretty(pg_database_size('$b'));"
    psql_ro "$b" "select count(*) from information_schema.tables where table_schema='public';"
    psql_ro "$b" "select extname from pg_extension order by extname;"
    psql_ro "$b" "select count(*) from pg_stat_user_tables;"
    psql_ro "$b" "select relname, n_live_tup from pg_stat_user_tables order by n_live_tup desc limit 10;"
    psql_ro "$b" "select nspname from pg_namespace where nspname like 'pg_temp%';"
  done
  sous "3.5 Rôles (aucun secret)"
  psql_ro postgres "select rolname, rolsuper, rolcreatedb, rolcanlogin from pg_roles order by rolname;"
  sous "3.6 Propriétaire des bases"
  psql_ro postgres "select datname, pg_get_userbyid(datdba) as proprietaire from pg_database where not datistemplate order by datname;"
  sous "3.7 Connexions"
  psql_ro postgres "select datname, usename, state, count(*) from pg_stat_activity group by 1,2,3 order by 1,2,3;"
  sous "3.8 Persistance et configuration"
  psql_ro postgres "select name, setting from pg_settings where name in
     ('data_directory','wal_level','archive_mode','archive_command','max_connections','shared_buffers','listen_addresses','port') order by name;"
  psql_ro postgres "select client_addr, state, sync_state from pg_stat_replication;"
  sous "3.9 Sauvegardes logiques internes (pg_dump en cours ?)"
  psql_ro postgres "select count(*) from pg_stat_activity where query like '%pg_dump%' and state <> 'idle';"
else
  echo "conteneur $PG_CONTAINER non actif : LOT 3 non mesuré"
fi
sous "3.10 Volume et ports du conteneur PostgreSQL"
docker inspect "$PG_CONTAINER" --format '{{range .Mounts}}{{.Type}} {{.Source}} -> {{.Destination}} (rw={{.RW}}){{println}}{{end}}' 2>&1
docker inspect "$PG_CONTAINER" --format 'ports={{json .HostConfig.PortBindings}}' 2>&1

# =============================================================================
lot "4 — NGINX PROXY MANAGER"
sous "4.1 Conteneur proxy"
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null | grep -iE "nginx|proxy|$NPM" \
  || echo "aucun conteneur de proxy détecté"
sous "4.2 Version, ports, réseaux"
docker exec "$NPM" nginx -v 2>&1 | head -2
docker inspect "$NPM" --format 'ports={{json .HostConfig.PortBindings}}{{println}}reseaux={{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>&1
sous "4.3 Proxy hosts (base NPM en lecture seule)"
if docker exec "$NPM" sh -c 'command -v sqlite3 >/dev/null 2>&1' 2>/dev/null; then
  docker exec "$NPM" sh -c "sqlite3 'file:/data/database.sqlite?mode=ro' \
    \"select domain_names, forward_host, forward_port, ssl_forced, certificate_id from proxy_host order by id;\"" 2>&1
else
  echo "sqlite3 absent de l'image — relever les proxy hosts depuis l'interface NPM"
fi
sous "4.4 Certificats (noms et dates seulement, aucune clé)"
docker exec "$NPM" sh -c "for f in /etc/letsencrypt/live/*/cert.pem; do
  [ -f \"\$f\" ] && openssl x509 -in \"\$f\" -noout -subject -issuer -dates; done" 2>&1
docker exec "$NPM" sh -c "ls -1 /data/custom_ssl 2>/dev/null" 2>&1
sous "4.5 Vérification publique"
if command -v curl >/dev/null 2>&1; then
  curl -sS -o /dev/null -D - --max-time 12 "https://$DOMAINE/" 2>&1 | head -15
  echo | timeout 12 openssl s_client -servername "$DOMAINE" -connect "$DOMAINE:443" 2>/dev/null \
    | openssl x509 -noout -subject -issuer -dates 2>/dev/null
  echo "-- routage API --"
  curl -sS -o /dev/null -w 'GET /api/health/ -> %{http_code}\n' --max-time 12 "https://$DOMAINE/api/health/" 2>&1
fi

# =============================================================================
lot "5 — REDIS ET RABBITMQ"
sous "5.1 Conteneurs présents"
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null | grep -iE "redis|rabbit|amqp" \
  || echo "aucun conteneur redis/rabbitmq"
sous "5.2 Redis : version, persistance, clients, clés"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$REDIS"; then
  docker exec "$REDIS" redis-server --version 2>&1
  docker exec "$REDIS" redis-cli config get appendonly 2>&1
  docker exec "$REDIS" redis-cli config get save 2>&1
  docker exec "$REDIS" redis-cli config get maxmemory-policy 2>&1
  docker exec "$REDIS" redis-cli info clients 2>&1 | head -6
  docker exec "$REDIS" redis-cli info keyspace 2>&1 | head -8
else
  echo "conteneur $REDIS non actif"
fi
sous "5.3 RabbitMQ : version, files, connexions"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$RABBIT"; then
  docker exec "$RABBIT" rabbitmqctl version 2>&1 | head -2
  docker exec "$RABBIT" rabbitmqctl list_queues name messages consumers 2>&1 | head -15
  docker exec "$RABBIT" rabbitmqctl list_connections 2>&1 | head -8
else
  echo "conteneur $RABBIT non actif"
fi
sous "5.4 Volumes et réseaux"
for c in "$REDIS" "$RABBIT"; do
  docker inspect "$c" --format "$c : {{range .Mounts}}{{.Source}}->{{.Destination}} {{end}}| net={{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}} {{end}}" 2>&1
done
sous "5.5 Qui utilise REDIS_URL côté applications (noms de variables seulement)"
for c in $(docker ps -q 2>/dev/null); do
  if docker inspect "$c" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep -q '^REDIS_URL='; then
    echo "  $(docker inspect "$c" --format '{{.Name}}') : REDIS_URL défini"
  fi
  if docker inspect "$c" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep -qE '^(RABBITMQ|AMQP|CELERY)'; then
    echo "  $(docker inspect "$c" --format '{{.Name}}') : variable AMQP/Celery définie"
  fi
done

# =============================================================================
lot "6 — SAUVEGARDES"
sous "6.1 Inventaire (emplacement, date, taille, type)"
TROUVES=$(mktemp)
for d in /home/almalinux /home/almalinux/backups /home/almalinux/injs-db-backups \
         /home/almalinux/injs-predeploy-* /opt /var/backups /srv; do
  [ -d "$d" ] || continue
  find "$d" -maxdepth 4 -type f \( -name '*.sql' -o -name '*.sql.gz' -o -name '*.dump' \
       -o -name '*.tar.gz' -o -name '*.tgz' \) \
    -printf '%TY-%Tm-%Td %TH:%TM  %10s  %p\n' 2>/dev/null >> "$TROUVES"
done
sort -r "$TROUVES" | head -40
sous "6.2 Nature des fichiers (en-tête seul, aucune restauration)"
while read -r _date _heure _taille chemin; do
  [ -f "$chemin" ] || continue
  entete=$(head -c 200 "$chemin" 2>/dev/null | tr -d '\000')
  case "$entete" in
    PGDMP*)              type="archive custom pg_dump" ;;
    *"PostgreSQL database dump"*) type="dump texte SQL" ;;
    *"CREATE TABLE"*)    type="dump texte SQL (sans en-tête)" ;;
    *)                   type="indéterminé" ;;
  esac
  echo "  $chemin -> $type"
done < "$(sort -r "$TROUVES" | head -20)"
sous "6.3 Sommaire des archives custom (pg_restore --list, SANS restauration)"
while read -r _d _h _t chemin; do
  case "$chemin" in
    *.dump)
      echo "  -- $chemin --"
      cat "$chemin" | docker exec -i "$PG_CONTAINER" pg_restore --list 2>&1 | grep -cE 'TABLE DATA' \
        | sed 's/^/     objets TABLE DATA : /'
      ;;
  esac
done < "$(sort -r "$TROUVES" | head -20)"
sous "6.4 Empreintes sha256 (LECTURE seule)"
if [ "$CHECKSUM" = "1" ]; then
  while read -r _d _h _t chemin; do
    [ -f "$chemin" ] && sha256sum "$chemin" 2>/dev/null
  done < "$(sort -r "$TROUVES" | head -10)"
else
  echo "  (CHECKSUM=1 pour activer — lecture intégrale, lent sur gros fichiers)"
fi
sous "6.5 Planification"
crontab -l 2>/dev/null | grep -viE 'pass|secret|token' || echo "  (aucune crontab utilisateur)"
$SUDO ls -1 /etc/cron.d 2>/dev/null
systemctl list-timers --all --no-pager 2>/dev/null | head -10
sous "6.6 Espace disponible"
df -h /home /var 2>/dev/null
rm -f "$TROUVES"

# =============================================================================
printf '\n\n########## FIN DE COLLECTE ##########\n'
echo "terminé le $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Aucun conteneur démarré/arrêté, aucune écriture SQL, aucune restauration,"
echo "aucune permission modifiée, aucun secret affiché."
