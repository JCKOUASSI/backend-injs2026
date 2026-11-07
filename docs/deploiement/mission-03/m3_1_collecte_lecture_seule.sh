#!/bin/sh
# =============================================================================
# DEPLOY-INJS-2026 — MISSION 03.1 — COLLECTE D'AUDIT VPS (LECTURE SEULE)
#
# Pourquoi ce script existe : l'audit du 06/11/2026 n'a pas pu être exécuté
# depuis l'environnement de l'agent (accès SSH bloqué au niveau réseau, cf.
# rapport §0). Ce script produit donc SUR LE VPS les relevés manquants des
# sections A à F de la mission, en une seule passe.
#
# GARANTIES DE LECTURE SEULE (vérifiables dans le code, ligne par ligne) :
#   * aucune commande de cycle de vie Docker : ni run, start, stop, restart,
#     rm, pull, push, build, prune, ni compose up/down ;
#   * aucun `docker exec` en écriture : uniquement psql en transaction
#     `default_transaction_read_only=on`, redis-cli en mode lecture,
#     rabbitmqctl en consultation, sqlite3 en `mode=ro` ;
#   * aucun DROP / CREATE / ALTER / TRUNCATE / DELETE / UPDATE / INSERT ;
#   * aucune modification de fichier : le seul fichier écrit est le journal
#     de sortie, choisi par vous via `tee` ;
#   * aucun secret affiché : les variables d'environnement sont listées par
#     NOM, leurs valeurs sont remplacées par <masque>, les jetons et mots de
#     passe ne sont jamais lus.
#
# Usage (sur le VPS, utilisateur ayant accès à docker) :
#   sh m3_1_collecte_lecture_seule.sh 2>&1 | tee m3-1-collecte-$(date -u +%Y%m%dT%H%M%SZ).log
#
# Variables ajustables (défauts issus du diagnostic H1) :
#   PG_CONTAINER=injs-db  NPM=npm-app-1  REDIS=injs-redis  RABBIT=injs-rabbitmq
#   BASES="injs-db injs_lmd_prod_20261026"   DOMAINE=injs.badge-qr-code.pro
#   PGUSER=postgres
# =============================================================================
set -u

PG_CONTAINER="${PG_CONTAINER:-injs-db}"
NPM="${NPM:-npm-app-1}"
REDIS="${REDIS:-injs-redis}"
RABBIT="${RABBIT:-injs-rabbitmq}"
BASES="${BASES:-injs-db injs_lmd_prod_20261026}"
DOMAINE="${DOMAINE:-injs.badge-qr-code.pro}"
PGUSER="${PGUSER:-postgres}"

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
  if sudo -n true 2>/dev/null; then SUDO="sudo -n"; fi
fi

titre() { printf '\n\n========== %s ==========\n' "$1"; }
sous()  { printf '\n--- %s ---\n' "$1"; }
masque() { sed -E 's/(=|: *)([^ ,;]+)/\1<masque>/g'; }

echo "MISSION 03.1 — collecte lecture seule"
echo "horodatage : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "hote       : $(hostname 2>/dev/null)"
echo "operateur  : $(id -un 2>/dev/null) (uid $(id -u))"
echo "AVERTISSEMENT : ce journal ne doit pas etre publie tel quel s'il contient"
echo "des noms de bases ou d'utilisateurs internes ; il ne contient aucun secret."

# =============================================================================
titre "A. SYSTÈME"
sous "A.1 Distribution et noyau"
cat /etc/os-release 2>/dev/null | grep -E '^(NAME|VERSION|VERSION_ID|PRETTY_NAME|ID|ID_LIKE)='
uname -a
sous "A.2 Architecture CPU"
uname -m
grep -c '^processor' /proc/cpuinfo 2>/dev/null | sed 's/^/cœurs logiques : /'
sous "A.3 Mémoire et swap"
free -h 2>/dev/null || free -m
sous "A.4 Disque et partitions"
df -hT -x tmpfs -x devtmpfs 2>/dev/null || df -h
sous "A.5 Charge système"
uptime
cat /proc/loadavg 2>/dev/null
sous "A.6 Ports en écoute (aucune modification)"
(ss -tulpnH 2>/dev/null || netstat -tulpn 2>/dev/null) | sed -E 's/(users:\(\(")([^"]+)/\1\2/' | head -80
sous "A.7 Pare-feu"
if command -v firewall-cmd >/dev/null 2>&1; then
  $SUDO firewall-cmd --state 2>&1
  $SUDO firewall-cmd --list-all 2>&1
else
  echo "firewalld : binaire absent"
fi
if command -v nft >/dev/null 2>&1; then
  echo "-- nftables (règles, lecture) --"
  $SUDO nft list ruleset 2>&1 | head -60
fi
if command -v iptables >/dev/null 2>&1; then
  echo "-- iptables (chaînes INPUT) --"
  $SUDO iptables -S INPUT 2>&1 | head -30
fi
sous "A.8 Services système actifs"
systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null | head -40
systemctl is-enabled docker 2>&1
sous "A.9 Heure et fuseau"
timedatectl 2>/dev/null | head -6

# =============================================================================
titre "B. DOCKER"
if ! command -v docker >/dev/null 2>&1; then
  echo "docker : commande absente — section impossible"
else
  sous "B.1 Versions"
  docker version --format 'Engine client {{.Client.Version}} / serveur {{.Server.Version}}' 2>&1
  docker compose version 2>&1 | head -2
  sous "B.2 Conteneurs (actifs et arrêtés)"
  docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1
  sous "B.3 Politique de redémarrage et état de santé"
  for c in $(docker ps -aq 2>/dev/null); do
    docker inspect "$c" --format '{{.Name}} | restart={{.HostConfig.RestartPolicy.Name}} | health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}} | running={{.State.Running}}' 2>/dev/null
  done
  sous "B.4 Images présentes"
  docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedSince}}\t{{.Size}}' 2>&1
  sous "B.5 Réseaux Docker"
  docker network ls 2>&1
  for n in $(docker network ls -q 2>/dev/null); do
    docker network inspect "$n" --format '{{.Name}} | driver={{.Driver}} | conteneurs={{range .Containers}}{{.Name}} {{end}}' 2>/dev/null
  done
  sous "B.6 Volumes Docker (noms et points de montage)"
  docker volume ls 2>&1
  for v in $(docker volume ls -q 2>/dev/null); do
    docker volume inspect "$v" --format '{{.Name}} | {{.Mountpoint}} | {{.Driver}}' 2>/dev/null
  done
  sous "B.7 Utilisation des ressources (instantané)"
  docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}' 2>&1 | head -25
  sous "B.8 Espace disque Docker"
  docker system df 2>&1
fi

# =============================================================================
titre "C. POSTGRESQL"
sous "C.1 Conteneurs PostgreSQL détectés"
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' 2>/dev/null | grep -i postgres || echo "aucun conteneur dont l'image contient 'postgres'"

psql_ro() {  # $1 = base, $2 = requête — transaction explicitement en lecture seule
  docker exec -i "$PG_CONTAINER" env PGOPTIONS='-c default_transaction_read_only=on' \
    psql -U "$PGUSER" -d "$1" -tAc "$2" 2>&1
}

if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$PG_CONTAINER"; then
  sous "C.2 Version du serveur"
  psql_ro postgres 'select version();'
  sous "C.3 Bases existantes (taille et encodage)"
  psql_ro postgres "select datname, pg_encoding_to_char(encoding), datcollate from pg_database order by datname;"
  for b in $BASES; do
    echo "-- base $b --"
    psql_ro postgres "select '$b', pg_size_pretty(pg_database_size('$b'));"
    psql_ro "$b" "select count(*) as tables from information_schema.tables where table_schema='public';"
    psql_ro "$b" "select count(*) as lignes_estimees from pg_stat_user_tables;"
    psql_ro "$b" "select extname from pg_extension order by extname;"
  done
  sous "C.4 Rôles et attributs (aucun mot de passe)"
  psql_ro postgres "select rolname, rolsuper, rolcreatedb, rolcanlogin from pg_roles order by rolname;"
  sous "C.5 Connexions en cours"
  psql_ro postgres "select datname, state, count(*) from pg_stat_activity group by 1,2 order by 1,2;"
  psql_ro postgres "select count(*) from pg_stat_activity;"
  sous "C.6 Réglages de persistance (sans secret)"
  psql_ro postgres "select name, setting from pg_settings where name in ('data_directory','archive_mode','archive_command','max_connections','shared_buffers','wal_level') order by name;"
  sous "C.7 Réplication / sauvegarde logique"
  psql_ro postgres "select client_addr, state, sync_state from pg_stat_replication;"
else
  echo "conteneur $PG_CONTAINER non actif : sections C.2 à C.7 non mesurées"
fi
sous "C.8 Volumes et ports du conteneur PostgreSQL"
docker inspect "$PG_CONTAINER" --format '{{range .Mounts}}{{.Type}} {{.Source}} -> {{.Destination}} (rw={{.RW}}){{println}}{{end}}' 2>&1
docker inspect "$PG_CONTAINER" --format '{{json .HostConfig.PortBindings}}' 2>&1

# =============================================================================
titre "D. NGINX PROXY MANAGER"
sous "D.1 Conteneur, ports, réseaux"
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null | grep -iE "nginx|proxy-manager|$NPM" || echo "aucun conteneur de proxy détecté"
docker inspect "$NPM" --format 'ports={{json .HostConfig.PortBindings}}{{println}}networks={{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}{{println}}restart={{.HostConfig.RestartPolicy.Name}}' 2>&1
sous "D.2 Variables d'environnement du proxy (NOMS seulement)"
docker inspect "$NPM" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>&1 | cut -d= -f1
sous "D.3 Proxy hosts déclarés (lecture seule de la base NPM)"
if docker exec "$NPM" sh -c 'command -v sqlite3 >/dev/null 2>&1' 2>/dev/null; then
  docker exec "$NPM" sh -c \
    "sqlite3 'file:/data/database.sqlite?mode=ro' \"select domain_names, forward_host, forward_port, ssl_forced, certificate_id from proxy_host order by id;\"" 2>&1
else
  echo "sqlite3 absent de l'image : relevé des proxy hosts à faire depuis l'interface NPM (onglet Hosts)"
fi
sous "D.4 Certificats SSL visibles"
docker exec "$NPM" sh -c "ls -l /etc/letsencrypt/live 2>/dev/null; ls -l /data/custom_ssl 2>/dev/null" 2>&1
sous "D.5 Test public (aucune modification)"
if command -v curl >/dev/null 2>&1; then
  curl -sS -o /dev/null -D - --max-time 10 "https://$DOMAINE/" 2>&1 | head -20
  echo "-- validité du certificat --"
  echo | timeout 10 openssl s_client -servername "$DOMAINE" -connect "$DOMAINE:443" 2>/dev/null \
    | openssl x509 -noout -subject -issuer -dates 2>/dev/null
fi

# =============================================================================
titre "E. REDIS ET RABBITMQ"
sous "E.1 Conteneurs"
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null | grep -iE "redis|rabbit|amqp" || echo "aucun conteneur redis/rabbitmq détecté"
sous "E.2 Redis — version, persistance, clients"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$REDIS"; then
  docker exec "$REDIS" redis-server --version 2>&1
  docker exec "$REDIS" redis-cli config get appendonly 2>&1
  docker exec "$REDIS" redis-cli config get save 2>&1
  docker exec "$REDIS" redis-cli info clients 2>&1 | head -8
  docker exec "$REDIS" redis-cli dbsize 2>&1
else
  echo "conteneur $REDIS non actif"
fi
sous "E.3 RabbitMQ — version, files, connexions"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$RABBIT"; then
  docker exec "$RABBIT" rabbitmqctl version 2>&1 | head -3
  docker exec "$RABBIT" rabbitmqctl list_queues name messages consumers 2>&1 | head -20
  docker exec "$RABBIT" rabbitmqctl list_connections 2>&1 | head -10
else
  echo "conteneur $RABBIT non actif"
fi
sous "E.4 Volumes et réseaux de ces services"
for c in "$REDIS" "$RABBIT"; do
  docker inspect "$c" --format "$c : {{range .Mounts}}{{.Source}} -> {{.Destination}} {{end}} | net={{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}} {{end}}" 2>&1
done

# =============================================================================
titre "F. SÉCURITÉ"
sous "F.1 Utilisateurs système (comptes de connexion)"
awk -F: '$3>=1000 && $3<65534 {print $1, $3, $6, $7}' /etc/passwd 2>/dev/null
sous "F.2 Appartenance au groupe docker (accès root de fait)"
getent group docker 2>/dev/null
ls -l /var/run/docker.sock 2>/dev/null
sous "F.3 Permissions des répertoires applicatifs"
for d in /home/almalinux /opt /srv /home/almalinux/backups /home/almalinux/injs-db-backups; do
  [ -e "$d" ] && ls -ld "$d"
done
find /home/almalinux -maxdepth 2 -type d -name '*injs*' -exec ls -ld {} \; 2>/dev/null | head -20
sous "F.4 Secrets exposés dans l'environnement des conteneurs (NOMS seulement)"
for c in $(docker ps -q 2>/dev/null); do
  echo "-- $(docker inspect "$c" --format '{{.Name}}') --"
  docker inspect "$c" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
    | cut -d= -f1 | grep -iE "pass|secret|token|key|dsn|url|credential" || echo "   (aucune variable sensible par le nom)"
done
sous "F.5 Ports publiés sur l'hôte (exposition réseau)"
docker ps --format '{{.Names}}\t{{.Ports}}' 2>/dev/null | grep -E '0\.0\.0\.0|:::' || echo "aucun port publié sur toutes les interfaces"
sous "F.6 TLS"
echo | timeout 10 openssl s_client -servername "$DOMAINE" -connect "$DOMAINE:443" 2>/dev/null | grep -E "Protocol|Cipher|Verify return code" | head -5

# =============================================================================
titre "G. SAUVEGARDES (aucune restauration, aucune modification)"
sous "G.1 Fichiers de sauvegarde détectés"
for d in /home/almalinux /home/almalinux/backups /home/almalinux/injs-db-backups /opt /var/backups; do
  [ -d "$d" ] || continue
  find "$d" -maxdepth 4 -type f \( -name '*.sql' -o -name '*.sql.gz' -o -name '*.dump' -o -name '*.tar.gz' \) \
    -printf '%TY-%Tm-%Td %TH:%TM  %10s o  %p\n' 2>/dev/null
done | sort -r | head -40
sous "G.2 Planification de sauvegarde"
crontab -l 2>/dev/null | grep -viE 'pass|secret|token' || echo "  (aucune crontab utilisateur)"
$SUDO ls -1 /etc/cron.d 2>/dev/null
systemctl list-timers --all --no-pager 2>/dev/null | head -12
sous "G.3 Espace disponible pour les sauvegardes"
df -h /home /var 2>/dev/null

# =============================================================================
titre "SYNTHÈSE"
echo "Collecte terminée le $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Rappel : aucun conteneur démarré ni arrêté, aucune base interrogée en"
echo "écriture, aucun fichier modifié, aucun secret affiché."
