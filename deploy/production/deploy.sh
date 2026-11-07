#!/usr/bin/env bash
# ============================================================================
# INJS-LMD — Déploiement contrôlé sur le VPS (voir RUNBOOK.md)
#
# Usage :
#   ./deploy.sh inventaire                     État des lieux, lecture seule
#   ./deploy.sh sauvegarde                     Dump PostgreSQL vérifié
#   ./deploy.sh plan                           migrate --plan + analyse des risques
#   ./deploy.sh deployer --tag <SHA>           Sauvegarde → plan → migrations
#                                              → démarrage (port de validation)
#                                              → contrôles de santé et comptages
#   ./deploy.sh rollback                       Arrête la NOUVELLE stack (sans -v)
#   ./deploy.sh analyser-plan <fichier>        Analyse un plan de migrations
#
# Garanties :
#   * aucune commande destructive n'existe dans ce script (DROP, flush,
#     suppression de volumes, down -v) : un garde-fou le vérifie à chaque run ;
#   * les migrations ne partent jamais toutes seules : l'entrypoint est
#     neutralisé par SKIP_DB_SETUP=true (compose) et `migrate` n'est lancé
#     qu'après la porte de contrôle `plan` ;
#   * le tag d'image est explicite et immuable : `stable` et `latest`
#     sont refusés ;
#   * l'ancienne stack et la base PostgreSQL ne sont jamais touchées ;
#   * la bascule Nginx Proxy Manager reste MANUELLE (hors de ce script).
#
# Variables (deploy/production/.env, jamais commité) : POSTGRES_DB,
# POSTGRES_USER, INJS_PUBLIC_PORT (défaut 8080), INJS_BACKEND_TAG,
# INJS_FRONTEND_TAG. Surcharge possible : PG_CONTAINER (défaut injs-db),
# BACKUP_DIR (défaut /opt/injs/backups).
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/compose.yml"
ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/.env}"
PG_CONTAINER="${PG_CONTAINER:-injs-db}"
BACKUP_DIR="${BACKUP_DIR:-/opt/injs/backups}"
LOG_DIR="$SCRIPT_DIR/logs"
HORODATAGE="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/deploy-$HORODATAGE.log"
# Le mode inventaire est intégralement en lecture seule : il ne crée ni
# répertoire ni fichier journal — ses sorties vont uniquement sur stdout.
LOG_ACTIF=1

log() {
  if [ "$LOG_ACTIF" = "1" ]; then
    printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG_FILE"
  else
    printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"
  fi
}
die()  { log "ERREUR FATALE : $*"; exit 1; }

init_journal() {
  mkdir -p "$LOG_DIR"
}

# ── Garde-fou : ce script ne doit contenir aucune opération destructive ────
# Les motifs sont assemblés dynamiquement pour ne pas se déclencher eux-mêmes.
garde_securite() {
  local interdit_down="down -""v"
  local interdit_down_long="down --""volumes"
  local interdit_drop="DROP ""DATABASE"
  local interdit_flush="manage.py ""flush"
  local interdit_volume="volume ""rm"
  local interdit_prune="system ""prune"
  local interdit_vprune="volume ""prune"
  local interdit_iprune="image ""prune"
  local motifs=("$interdit_down" "$interdit_down_long" "$interdit_drop" \
                "$interdit_flush" "$interdit_volume" "$interdit_prune" \
                "$interdit_vprune" "$interdit_iprune")
  local f cible contenu
  # Le script lui-même ET les fichiers compose sont contrôlés (y
  # compris un éventuel fichier override présent à côté du compose,
  # même si compose() force -f sur le fichier principal). L'analyse
  # est faite sur un texte NORMALISÉ (tabulations converties, espaces
  # multiples écrasés) pour ne pas être contournée par l'espacement.
  # LIMITE ASSUMÉE : une analyse statique textuelle ne détecte pas une
  # commande assemblée dynamiquement (variables, interpolation) ; ce
  # garde-fou est une défense en profondeur contre les erreurs, pas
  # une garantie absolue (voir RUNBOOK.md §10).
  for cible in "${BASH_SOURCE[0]}" "$COMPOSE_FILE" \
               "$SCRIPT_DIR/compose.override.yml" "$SCRIPT_DIR/compose.override.yaml"; do
    [ -f "$cible" ] || continue
    contenu="$(grep -v '^[[:space:]]*#' "$cible" | tr '\t' ' ' | tr -s ' ')"
    for f in "${motifs[@]}"; do
      if printf '%s' "$contenu" | grep -Fq "$f"; then
        die "Garde-fou : motif destructif détecté dans $cible ($f). Arrêt."
      fi
    done
  done
}

compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

charger_env() {
  [ -f "$ENV_FILE" ] || die "Fichier d'environnement introuvable : $ENV_FILE (copier .env.example et le renseigner hors Git)."
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  : "${POSTGRES_DB:?POSTGRES_DB manquant dans $ENV_FILE}"
  : "${POSTGRES_USER:?POSTGRES_USER manquant dans $ENV_FILE}"
  verifier_secrets
  PUBLIC_PORT="${INJS_PUBLIC_PORT:-8080}"
}

# Rejette les secrets absents ou manifestement provisoires AVANT toute
# opération. Les messages ne nomment que la variable — jamais sa valeur.
# Lit une variable depuis un fichier .env SANS l'exécuter (grep/sed),
# en retirant guillemets englobants et espaces extrêmes. Utilisé pour
# valider un fichier de configuration (ex. .env.bak-* d'un rollback)
# avant de le charger réellement.
lire_var_env() {
  local fichier="$1" nom="$2" v reste
  v="$(grep -E "^${nom}=" "$fichier" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
  v="${v#"${v%%[![:space:]]*}"}"
  # Même sémantique qu'un « . fichier » lu par bash : valeur entre guillemets
  # englobants extraite telle quelle (un # intérieur y est une donnée),
  # commentaire en ligne d'une valeur nue retiré. Sans ce retrait, un
  # .env.bak-* issu de .env.example (« INJS_BACKEND_TAG=<sha>  # requis :
  # ex. … ») ferait échouer valider_tag et BLOQUERAIT un rollback alors que
  # la valeur réellement restaurée (cp du .env.bak-*) est correcte.
  case "$v" in
    \"*) reste="${v#\"}"; v="${reste%%\"*}" ;;
    \'*) reste="${v#\'}"; v="${reste%%\'*}" ;;
    '#'*) v="" ;;
    *) v="${v%%[[:space:]]#*}"
       v="${v%"${v##*[![:space:]]}"}" ;;
  esac
  printf '%s' "$v"
}

# Valide UNE valeur de secret : rejette l'absence, le vide, la valeur
# constituée uniquement d'espaces et les placeholders connus,
# INDÉPENDAMMENT DE LA CASSE. Les caractères spéciaux légitimes sont
# acceptés : seules des valeurs d'exemple exactes sont rejetées. Une
# valeur faible mais non listée n'est pas détectable automatiquement —
# elle relève de la revue humaine. La valeur n'est JAMAIS affichée.
valider_secret_valeur() {
  local nom="$1" valeur="${2:-}"
  local normalisee minuscules
  normalisee="$(printf '%s' "$valeur" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  case "$normalisee" in
    \"*\") normalisee="${normalisee#\"}"; normalisee="${normalisee%\"}" ;;
    \'*\') normalisee="${normalisee#\'}"; normalisee="${normalisee%\'}" ;;
  esac
  normalisee="$(printf '%s' "$normalisee" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  if [ -z "$normalisee" ]; then
    die "Secret $nom absent, vide ou constitué uniquement d'espaces : opération refusée."
  fi
  minuscules="$(printf '%s' "$normalisee" | tr '[:upper:]' '[:lower:]')"
  case "$minuscules" in
    change-me|changez-moi|changeme|mot-de-passe|password|secret|exemple|a-renseigner|django-insecure*)
      die "Secret $nom encore à sa valeur d'exemple provisoire : opération refusée (renseigner une vraie valeur, hors Git)." ;;
  esac
}

# Rejette les secrets absents ou manifestement provisoires AVANT toute
# opération, via le même validateur unitaire que le pré-contrôle de
# rollback (D3). Les messages ne nomment que la variable.
verifier_secrets() {
  local var
  for var in POSTGRES_PASSWORD DJANGO_SECRET_KEY; do
    valider_secret_valeur "$var" "${!var:-}"
  done
}

valider_tag() {
  local tag="${1:-}"
  [ -n "$tag" ] || die "Tag d'image explicite requis (--tag <SHA complet ou version>)."
  case "$tag" in
    stable|latest)
      die "Tag interdit en production : « $tag » est un pointeur mutable. Utiliser le SHA Git complet publié par le workflow." ;;
  esac
  if ! printf '%s' "$tag" | grep -Eq '^[0-9a-f]{40}$|^v?[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.-]+)?$'; then
    die "Format de tag non reconnu : « $tag » (attendu : SHA Git complet ou version sémantique)."
  fi
}

# ── Identification explicite de PostgreSQL (jamais de paramètres aveugles) ──
identifier_postgres() {
  docker inspect "$PG_CONTAINER" >/dev/null 2>&1 \
    || die "Conteneur PostgreSQL « $PG_CONTAINER » introuvable (docker ps). Rien n'a été touché."
  docker exec "$PG_CONTAINER" pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null \
    || die "PostgreSQL ne répond pas pour $POSTGRES_USER/$POSTGRES_DB dans $PG_CONTAINER."
  PG_VERSION="$(docker exec "$PG_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc 'SHOW server_version;')"
  log "PostgreSQL identifié : conteneur=$PG_CONTAINER base=$POSTGRES_DB utilisateur=$POSTGRES_USER version=$PG_VERSION"
}

# Les cinq compteurs de référence, dans l'ordre du SQL ci-dessous.
# Cette liste est la référence obligatoire : obtenir_comptages refuse
# toute sortie à laquelle il manque un compteur, qui en duplique un ou
# qui en contient un inconnu.
COMPTEURS_ATTENDUS=(utilisateurs etudiants inscriptions formations emplois_du_temps)

# Comptages de référence, tolérants aux tables absentes (anciennes versions).
# -i est indispensable : sans lui, le SQL transmis par heredoc n'atteint
# jamais psql et le résultat est vide. ON_ERROR_STOP=1 : la première
# erreur SQL fait échouer psql au lieu de produire une sortie partielle
# silencieuse.
# PORTÉE EXACTE (D8) : les cinq compteurs sont calculés par UNE SEULE
# instruction SQL (sous-requêtes scalaires reliées par UNION ALL) —
# ils partagent donc le même instantané d'instruction PostgreSQL et
# sont cohérents ENTRE EUX. Ils ne partagent PAS l'instantané interne
# du dump pg_dump (pris à son propre démarrage, juste après) : la
# garantie d'intégrité de la sauvegarde vient de pg_dump et du SHA-256,
# pas de l'égalité des comptages (voir RUNBOOK.md §3).
comptages() {
  docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At <<'SQL'
SELECT 'utilisateurs=' || CASE WHEN to_regclass('authentication_user') IS NOT NULL
  THEN (SELECT count(*) FROM authentication_user)::text ELSE 'table absente' END
UNION ALL
SELECT 'etudiants=' || CASE WHEN to_regclass('scolarite_dossieretudiant') IS NOT NULL
  THEN (SELECT count(*) FROM scolarite_dossieretudiant)::text ELSE 'table absente' END
UNION ALL
SELECT 'inscriptions=' || CASE WHEN to_regclass('scolarite_inscriptionadministrative') IS NOT NULL
  THEN (SELECT count(*) FROM scolarite_inscriptionadministrative)::text ELSE 'table absente' END
UNION ALL
SELECT 'formations=' || CASE WHEN to_regclass('formations_refformation') IS NOT NULL
  THEN (SELECT count(*) FROM formations_refformation)::text ELSE 'table absente' END
UNION ALL
SELECT 'emplois_du_temps=' || CASE WHEN to_regclass('edts_emploidutemps') IS NOT NULL
  THEN (SELECT count(*) FROM edts_emploidutemps)::text ELSE 'table absente' END;
SQL
}

# Obtient les comptages et les VALIDE STRICTEMENT avant de les
# considérer comme une preuve :
#   * le code de retour de psql doit être un succès (ON_ERROR_STOP) ;
#   * la sortie ne doit pas être vide ;
#   * chacune des cinq clés de COMPTEURS_ATTENDUS doit être présente
#     exactement une fois, sans clé inconnue ni doublon ;
#   * chaque valeur doit être un entier (ou « table absente », état
#     déclaré d'une ancienne version, comparé tel quel avant/après).
# Tout écart interrompt immédiatement la chaîne : une comparaison de
# résultats incomplets ne doit jamais valoir réussite.
obtenir_comptages() {
  local destination="$1"
  local sortie ligne cle valeur
  sortie="$(comptages)" || die "Comptages PostgreSQL impossibles à obtenir (échec psql, voir le journal)."
  [ -n "$sortie" ] || die "Comptages PostgreSQL VIDES : arrêt — aucune preuve de conservation ne peut en être tirée."
  local -A vus=()
  while IFS= read -r ligne; do
    if ! printf '%s' "$ligne" | grep -Eq '^[a-z_]+=([0-9]+|table absente)$'; then
      die "Comptage inexploitable : « $ligne » (entier ou « table absente » attendu). Arrêt."
    fi
    cle="${ligne%%=*}"
    valeur="${ligne#*=}"
    case " ${COMPTEURS_ATTENDUS[*]} " in
      *" $cle "*) ;;
      *) die "Compteur inattendu : « $cle ». Arrêt." ;;
    esac
    [ -z "${vus[$cle]:-}" ] || die "Compteur dupliqué : « $cle ». Arrêt."
    vus[$cle]="$valeur"
  done <<< "$sortie"
  for cle in "${COMPTEURS_ATTENDUS[@]}"; do
    [ -n "${vus[$cle]:-}" ] || die "Compteur manquant : « $cle » — sortie SQL incomplète, arrêt (aucune preuve partielle acceptée)."
  done
  printf '%s\n' "$sortie" | tee "$destination"
  log "Comptages valides (5/5 compteurs) enregistrés dans $destination"
}

# Compare deux relevés de comptages (avant / après) avec une sémantique
# honnête (D8) : l'ancienne application continue de servir pendant le
# déploiement, donc une HAUSSE peut refléter l'activité métier normale
# (avertissement fort, revue avant bascule) ; une BAISSE d'un compteur
# est en revanche un signal de perte possible et BLOQUE. Limite
# assumée : une suppression et une insertion simultanées peuvent se
# compenser et rester invisibles à cette comparaison — elle complète
# le dump vérifié, elle ne le remplace pas.
comparer_comptages() {
  local fichier_avant="$1" fichier_apres="$2"
  local -A avant=() apres=()
  local ligne cle
  while IFS= read -r ligne; do
    case "$ligne" in *=*) avant["${ligne%%=*}"]="${ligne#*=}" ;; esac
  done < <(grep -E '^[a-z_]+=' "$fichier_avant" || true)
  while IFS= read -r ligne; do
    case "$ligne" in *=*) apres["${ligne%%=*}"]="${ligne#*=}" ;; esac
  done < <(grep -E '^[a-z_]+=' "$fichier_apres" || true)
  local -a baisses=() hausses=()
  for cle in "${COMPTEURS_ATTENDUS[@]}"; do
    [ -n "${avant[$cle]:-}" ] && [ -n "${apres[$cle]:-}" ] \
      || die "Comparaison impossible : compteur « $cle » absent d'un des relevés. Arrêt."
    if [ "${avant[$cle]}" = "table absente" ] || [ "${apres[$cle]}" = "table absente" ]; then
      [ "${avant[$cle]}" = "${apres[$cle]}" ] \
        || die "Bascule d'état de table pour « $cle » (${avant[$cle]} → ${apres[$cle]}) : arrêt, analyse requise."
      continue
    fi
    if [ "${apres[$cle]}" -lt "${avant[$cle]}" ]; then
      baisses+=("$cle : ${avant[$cle]} → ${apres[$cle]}")
    elif [ "${apres[$cle]}" -gt "${avant[$cle]}" ]; then
      hausses+=("$cle : ${avant[$cle]} → ${apres[$cle]}")
    fi
  done
  if [ "${#baisses[@]}" -gt 0 ]; then
    printf '%s\n' "${baisses[@]}" | sed 's/^/  BAISSE : /'
    die "Baisse de comptages détectée (perte possible) : NE PAS basculer le proxy ; analyser avant toute décision (rollback applicatif possible, aucune restauration de base à ce stade)."
  fi
  if [ "${#hausses[@]}" -gt 0 ]; then
    printf '%s\n' "${hausses[@]}" | sed 's/^/  HAUSSE : /'
    log "ATTENTION : hausses de comptages pendant le déploiement — vraisemblablement l'activité métier de l'ancienne application encore en service. Vérifier métier par métier AVANT de basculer le proxy."
    return 0
  fi
  log "Comptages identiques avant/après déploiement."
}

cmd_inventaire() {
  log "=== INVENTAIRE (lecture seule) ==="
  # Référence métier unique de l'inventaire (le workflow, lui, ne fait
  # que la connexion SSH et la consultation préalable au transfert :
  # voir RUNBOOK.md §10). Si le .env serveur existe, ses paramètres
  # PostgreSQL sont utilisés ; la lecture du fichier ne modifie rien.
  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
    log "Configuration serveur lue depuis $ENV_FILE (lecture seule)."
  fi
  docker --version; docker compose version
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
  docker volume ls
  docker network ls
  df -h / /opt 2>/dev/null || df -h
  free -h
  if docker inspect "$PG_CONTAINER" >/dev/null 2>&1; then
    docker exec "$PG_CONTAINER" psql -U "${POSTGRES_USER:-injs}" -d "${POSTGRES_DB:-injs}" -Atc 'SHOW server_version;' \
      | sed 's/^/PostgreSQL : /' || log "PostgreSQL : version illisible (vérifier POSTGRES_USER/POSTGRES_DB)."
  else
    log "Conteneur PostgreSQL « $PG_CONTAINER » absent des conteneurs actifs."
  fi
  log "Inventaire terminé — aucune modification effectuée."
}

cmd_sauvegarde() {
  charger_env
  identifier_postgres
  mkdir -p "$BACKUP_DIR"
  local dump_conteneur="/tmp/injs-$HORODATAGE.dump"
  local dump_local="$BACKUP_DIR/injs-$HORODATAGE.dump"

  # Chronologie : les comptages de référence sont relevés AVANT le dump
  # (état de départ) ; le dump lui-même est un instantané transactionnel
  # cohérent produit par pg_dump ; un second relevé après copie montre
  # l'activité concurrente éventuelle, sans invalider l'instantané.
  log "Comptages de référence (avant dump)…"
  obtenir_comptages "$BACKUP_DIR/comptages-$HORODATAGE.txt"

  log "Sauvegarde de $POSTGRES_DB (format custom, instantané transactionnel)…"
  docker exec "$PG_CONTAINER" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$dump_conteneur"

  # Étape 1 (source) : lisibilité puis empreinte DANS le conteneur.
  # Le code retour de pg_restore --list est vérifié SÉPARÉMENT et
  # d'abord : une archive qui produit une sortie partielle PUIS échoue
  # est rejetée — le nombre d'entrées n'est qu'un contrôle secondaire
  # de cohérence, jamais une preuve à lui seul.
  local liste_restore nb_entrees empreinte_source
  liste_restore="$(docker exec "$PG_CONTAINER" pg_restore --list "$dump_conteneur")" \
    || die "pg_restore --list EN ÉCHEC sur le dump source : archive rejetée (inspection structurelle impossible, aucune utilisation possible)."
  nb_entrees="$(printf '%s\n' "$liste_restore" | grep -c ';' || true)"
  [ "${nb_entrees:-0}" -gt 10 ] || die "Vérification pg_restore --list anormale ($nb_entrees entrées) : dump rejeté."
  empreinte_source="$(docker exec "$PG_CONTAINER" sha256sum "$dump_conteneur" | awk '{print $1}')"
  printf '%s' "$empreinte_source" | grep -Eq '^[0-9a-f]{64}$' \
    || die "Empreinte SHA-256 source absente ou malformée : sauvegarde interrompue."

  # Étape 2 (copie locale) : empreinte recalculée et comparaison stricte.
  docker cp "$PG_CONTAINER:$dump_conteneur" "$dump_local" \
    || die "Échec de la copie du dump hors du conteneur (docker cp)."
  docker exec "$PG_CONTAINER" rm -f "$dump_conteneur"
  # Tout dump rejeté APRÈS copie est renommé .INVALIDE : il ne doit
  # jamais pouvoir être confondu avec une sauvegarde valide (le fichier
  # .sha256, lui, n'est créé qu'après comparaison réussie).
  [ -s "$dump_local" ] || { mv "$dump_local" "$dump_local.INVALIDE"; die "Dump copié vide : renommé $dump_local.INVALIDE, sauvegarde rejetée."; }
  local empreinte_locale
  empreinte_locale="$(sha256sum "$dump_local" | awk '{print $1}')"
  [ "$empreinte_locale" = "$empreinte_source" ] \
    || { mv "$dump_local" "$dump_local.INVALIDE"; die "Empreintes SHA-256 DIFFÉRENTES (source ≠ copie) : transfert corrompu, copie renommée $dump_local.INVALIDE, sauvegarde rejetée."; }
  ( cd "$BACKUP_DIR" && printf '%s  %s\n' "$empreinte_source" "$(basename "$dump_local")" > "$(basename "$dump_local").sha256" )
  chmod 600 "$dump_local" "$dump_local.sha256"
  log "Intégrité bout-en-bout prouvée : SHA-256 source = copie ($nb_entrees entrées pg_restore)."

  log "Comptages après copie (activité concurrente éventuelle)…"
  obtenir_comptages "$BACKUP_DIR/comptages-apres-copie-$HORODATAGE.txt"
  log "Sauvegarde vérifiée : $dump_local. Anciennes sauvegardes conservées :"
  ls -1 "$BACKUP_DIR" | sed 's/^/  /'
}

# Analyse d'un plan de migrations, CALIBRÉE SUR LE FORMAT RÉEL de
# Django 5.1 (vérifié sur le code installé) :
#   Planned operations:
#     scolarite.0031_xxx            <- en-tête de migration (colonne 0)
#       Create model Foo            <- opération (4 espaces, SANS tiret)
#       Delete model Bar
#       Raw Python operation -> ...
# L'ancienne application partage la MÊME base PostgreSQL pendant la
# coexistence : suppression ou renommage la rend incompatible.
# Classification de chaque opération :
#   BLOQUANTE  : Delete model, Remove field, Rename field, Rename model ;
#   À EXAMINER : altérations, index, contraintes, migrations de données
#                (Raw Python / Raw SQL), opérations personnalisées et
#                TOUTE opération non reconnue — jamais présumée sûre ;
#   SÛRE       : Create model, Add field.
# Échec fermé : un plan vide, tronqué ou de format inattendu INTERROMPT
# la chaîne — une erreur d'analyse ne vaut jamais « plan sûr ».
analyser_plan() {
  local fichier="$1"
  [ -f "$fichier" ] || die "Plan introuvable : $fichier"
  log "--- Migrations planifiées ---"
  cat "$fichier"
  log "-----------------------------"
  [ -s "$fichier" ] || die "Plan de migrations VIDE : format inattendu, arrêt par sécurité (jamais interprété comme « rien à migrer »)."
  if grep -qi "No planned migration operations" "$fichier"; then
    # Cohérence interne : ce message ne doit coexister avec aucune opération.
    if grep -Eq '^[[:space:]]+(Create|Delete|Remove|Rename|Alter|Add|Raw)' "$fichier"; then
      die "Plan contradictoire (annonce « aucune opération » mais contient des opérations) : format inattendu, arrêt par sécurité."
    fi
    log "Aucune migration en attente."
    return 0
  fi
  local ligne nettoyee op
  local -a liste_bloquantes=() liste_a_examiner=()
  local nb_sures=0 nb_migrations=0 nb_operations=0
  while IFS= read -r ligne; do
    nettoyee="$(printf '%s' "$ligne" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ -n "$nettoyee" ] || continue
    [ "$nettoyee" = "Planned operations:" ] && continue
    case "$ligne" in
      [![:space:]]*)
        # Ligne en colonne 0 : en-tête de migration « app.0001_nom » attendu.
        if printf '%s' "$nettoyee" | grep -Eq '^[A-Za-z0-9_.]+\.[0-9]{4}[A-Za-z0-9_]*$'; then
          nb_migrations=$((nb_migrations + 1)); continue
        fi
        die "Format de plan inattendu (ligne non indentée non reconnue : « $nettoyee ») : arrêt par sécurité." ;;
    esac
    # Ligne indentée : opération. Un éventuel préfixe « - » (anciens
    # formats/exports) est toléré et retiré avant classification.
    op="${nettoyee#- }"
    nb_operations=$((nb_operations + 1))
    case "$op" in
      "Delete model"*|"Remove field"*|"Rename field"*|"Rename model"*)
        liste_bloquantes+=("$op") ;;
      "Create model"*|"Add field"*)
        nb_sures=$((nb_sures + 1)) ;;
      *)
        liste_a_examiner+=("$op") ;;
    esac
  done < "$fichier"
  [ "$nb_migrations" -gt 0 ] || die "Format de plan inattendu (aucun en-tête de migration reconnu) : arrêt par sécurité."
  [ "$nb_operations" -gt 0 ] || die "Plan non vide sans opération identifiable : format inattendu, arrêt par sécurité."
  log "Rapport d'analyse du plan : ${#liste_bloquantes[@]} bloquante(s), ${#liste_a_examiner[@]} à examiner, $nb_sures sûre(s) ($nb_migrations migration(s))."
  if [ "${#liste_a_examiner[@]}" -gt 0 ]; then
    log "À EXAMINER par un humain avant application (altérations, index, contraintes, migrations de données ou opérations inconnues — réversibilité non vérifiable depuis le plan) :"
    printf '%s\n' "${liste_a_examiner[@]}" | sed 's/^/  /'
    if [ "${DEPLOY_AUTORISER_EXAMEN_MIGRATIONS:-}" != "oui-explicite" ]; then
      die "Opérations à examiner présentes : inspection humaine requise. Après examen, relancer avec DEPLOY_AUTORISER_EXAMEN_MIGRATIONS=oui-explicite."
    fi
    log "Examen humain explicitement confirmé par variable d'environnement."
  fi
  if [ "${#liste_bloquantes[@]}" -gt 0 ]; then
    log "Opérations BLOQUANTES détectées (suppression ou renommage : perte de données ou incompatibilité de l'ancienne application) :"
    printf '%s\n' "${liste_bloquantes[@]}" | sed 's/^/  /'
    if [ "${DEPLOY_AUTORISER_MIGRATIONS_DESTRUCTIVES:-}" != "oui-explicite" ]; then
      die "Migrations bloquantes refusées. Validation humaine requise ; si elles sont réellement autorisées, relancer avec DEPLOY_AUTORISER_MIGRATIONS_DESTRUCTIVES=oui-explicite."
    fi
    log "Opérations bloquantes explicitement autorisées par variable d'environnement."
  fi
}

# Contre-vérification par le mécanisme Django : le nombre de migrations
# en attente (showmigrations) doit être cohérent avec le plan analysé.
# Format réel Django 5.1 de `showmigrations --plan` : les migrations en
# attente sont des lignes «[ ]  app.0001_nom» (crochet en colonne 0,
# deux espaces). Un échec de la commande est FATAL, jamais masqué.
verifier_coherence_migrations() {
  local plan="$1"
  local sortie en_attente
  sortie="$(compose run --rm backend python manage.py showmigrations --plan 2>/dev/null)" \
    || die "showmigrations --plan EN ÉCHEC : contre-vérification impossible, arrêt par sécurité."
  en_attente="$(printf '%s\n' "$sortie" | grep -cE '^[[:space:]]*\[ \]' || true)"
  log "Migrations en attente selon showmigrations : ${en_attente:-0}"
  if grep -qi "No planned migration operations" "$plan"; then
    [ "${en_attente:-0}" = "0" ] \
      || die "Incohérence détectée : migrate --plan est vide mais showmigrations signale $en_attente migration(s) en attente. Arrêt."
  else
    [ "${en_attente:-0}" != "0" ] \
      || die "Incohérence détectée : le plan contient des opérations mais showmigrations ne signale aucune migration en attente. Arrêt."
  fi
}

cmd_plan() {
  charger_env
  log "Plan calculé pour les tags ACTUELLEMENT référencés dans $ENV_FILE (backend=${INJS_BACKEND_TAG:-?}, frontend=${INJS_FRONTEND_TAG:-?}) : pour analyser une cible, renseigner d'abord ces tags dans le .env serveur."
  identifier_postgres
  local plan="$LOG_DIR/plan-$HORODATAGE.txt"
  log "Récupération des images (le plan exige l'image du nouveau code)…"
  compose pull
  log "Calcul du plan de migrations (aucune application)…"
  compose run --rm backend python manage.py migrate --plan | tee "$plan"
  analyser_plan "$plan"
  verifier_coherence_migrations "$plan"
}

cmd_deployer() {
  local tag=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --tag) tag="${2:-}"; shift 2 ;;
      *) die "Argument inconnu : $1" ;;
    esac
  done
  valider_tag "$tag"
  charger_env
  log "=== DÉPLOIEMENT CONTRÔLÉ — images tag $tag (port de validation $PUBLIC_PORT) ==="

  # 1. Référencer explicitement les images immuables dans .env (sauvegarde de l'ancien).
  cp "$ENV_FILE" "$ENV_FILE.bak-$HORODATAGE"
  sed -i "s/^INJS_BACKEND_TAG=.*/INJS_BACKEND_TAG=$tag/" "$ENV_FILE"
  sed -i "s/^INJS_FRONTEND_TAG=.*/INJS_FRONTEND_TAG=$tag/" "$ENV_FILE"
  grep -q "^INJS_BACKEND_TAG=$tag" "$ENV_FILE" || die "INJS_BACKEND_TAG non mis à jour dans $ENV_FILE."
  grep -q "^INJS_FRONTEND_TAG=$tag" "$ENV_FILE" || die "INJS_FRONTEND_TAG non mis à jour dans $ENV_FILE."

  # 2. Sauvegarde préalable vérifiée + comptages de référence.
  cmd_sauvegarde

  # 3. Récupération des images officielles.
  compose pull

  # 4. Porte de contrôle des migrations, puis application explicite.
  local plan="$LOG_DIR/plan-$HORODATAGE.txt"
  compose run --rm backend python manage.py migrate --plan | tee "$plan"
  analyser_plan "$plan"
  verifier_coherence_migrations "$plan"
  log "Application des migrations validées…"
  compose run --rm backend python manage.py migrate --noinput
  compose run --rm backend python manage.py collectstatic --noinput >/dev/null
  log "Migrations appliquées."

  # 5. Démarrage de la nouvelle stack (l'ancienne n'est pas touchée).
  compose up -d
  compose ps

  # 6. Contrôles de santé HTTP (backend via passerelle + frontend).
  local tentative ok=0
  for tentative in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:$PUBLIC_PORT/api/health/" >/dev/null 2>&1 \
       && curl -sf "http://127.0.0.1:$PUBLIC_PORT/" >/dev/null 2>&1; then
      ok=1; break
    fi
    sleep 5
  done
  [ "$ok" = "1" ] || { compose logs --tail 100 || true; die "Contrôles de santé en échec sur le port $PUBLIC_PORT — vérifier les logs ci-dessus. Ancienne stack intacte."; }
  log "Santé OK : /api/health/ et frontend répondent sur le port $PUBLIC_PORT."

  # 7. Comptages après : comparaison nuancée (voir comparer_comptages) —
  # une baisse bloque, une hausse signale l'activité métier concurrente.
  identifier_postgres
  local avant="$BACKUP_DIR/comptages-$HORODATAGE.txt"
  local apres="$LOG_DIR/comptages-apres-$HORODATAGE.txt"
  obtenir_comptages "$apres"
  comparer_comptages "$avant" "$apres"
  log "DÉPLOIEMENT CONTRÔLÉ TERMINÉ sur http://127.0.0.1:$PUBLIC_PORT — bascule Nginx Proxy Manager : MANUELLE (voir RUNBOOK.md §7)."
}

cmd_rollback() {
  charger_env
  log "=== ROLLBACK APPLICATIF COMPLET ==="

  # 1. Identifier la configuration précédente et vérifier son intégrité
  # AVANT de toucher à quoi que ce soit.
  local dernier_bak=""
  dernier_bak="$(ls -t "$SCRIPT_DIR"/.env.bak-* 2>/dev/null | head -1 || true)"
  [ -n "$dernier_bak" ] \
    || die "Aucun fichier .env.bak-* : aucun déploiement commencé à annuler. Rollback impossible."
  local tag_be tag_fe var_secret port_bak
  tag_be="$(lire_var_env "$dernier_bak" INJS_BACKEND_TAG)"
  tag_fe="$(lire_var_env "$dernier_bak" INJS_FRONTEND_TAG)"
  valider_tag "$tag_be"
  valider_tag "$tag_fe"
  [ -n "$(lire_var_env "$dernier_bak" POSTGRES_DB)" ] && [ -n "$(lire_var_env "$dernier_bak" POSTGRES_USER)" ] \
    || die "Configuration précédente incomplète (POSTGRES_DB/POSTGRES_USER absents ou vides dans $dernier_bak). Rollback refusé."
  # Validation COMPLÈTE avant toute interruption : les secrets de la
  # configuration restaurée passent le même validateur que le
  # chargement normal (D6) — un rollback ne doit jamais arrêter la
  # stack pour découvrir ensuite qu'elle ne peut pas redémarrer.
  for var_secret in POSTGRES_PASSWORD DJANGO_SECRET_KEY; do
    valider_secret_valeur "$var_secret" "$(lire_var_env "$dernier_bak" "$var_secret")"
  done
  port_bak="$(lire_var_env "$dernier_bak" INJS_PUBLIC_PORT)"
  if [ -n "$port_bak" ]; then
    printf '%s' "$port_bak" | grep -Eq '^[0-9]+$' \
      || die "INJS_PUBLIC_PORT invalide dans $dernier_bak (« $port_bak » n'est pas un port numérique). Rollback refusé."
  fi
  [ -f "$COMPOSE_FILE" ] || die "Fichier compose introuvable : $COMPOSE_FILE. Rollback refusé."
  log "Configuration précédente entièrement validée (tags, variables, secrets, port, compose) : $dernier_bak (backend=$tag_be, frontend=$tag_fe)"

  # 2. Sauvegarder l'état courant, puis restaurer et revérifier.
  compose down
  cp "$ENV_FILE" "$ENV_FILE.avant-rollback-$HORODATAGE"
  cp "$dernier_bak" "$ENV_FILE"
  grep -q "^INJS_BACKEND_TAG=$tag_be" "$ENV_FILE" && grep -q "^INJS_FRONTEND_TAG=$tag_fe" "$ENV_FILE" \
    || die "Restauration des tags non confirmée dans $ENV_FILE. Rollback incomplet."
  charger_env  # recharge et revalide l'environnement restauré (variables + secrets)
  log "Tags et environnement restaurés (état courant sauvegardé : $ENV_FILE.avant-rollback-$HORODATAGE)."

  # 3. S'assurer des images restaurées, puis relancer les services.
  log "Anciennes images disponibles localement :"
  docker images --format '  {{.Repository}}:{{.Tag}} ({{.ID}})' \
    | grep -E 'injs-be|injs-fe' || log "  (aucune listée — récupération par pull)"
  compose pull
  compose up -d
  compose ps

  # 4. Vérifier la disponibilité réelle (backend puis frontend).
  local tentative
  for tentative in $(seq 1 30); do
    curl -sf "http://127.0.0.1:$PUBLIC_PORT/api/health/" >/dev/null 2>&1 && break
    sleep 5
  done
  curl -sf "http://127.0.0.1:$PUBLIC_PORT/api/health/" >/dev/null 2>&1 \
    || { compose logs --tail 100 || true; die "ROLLBACK EN ÉCHEC : backend restauré indisponible sur le port $PUBLIC_PORT. Ancienne application externe et PostgreSQL intacts ; décision humaine requise."; }
  curl -sf "http://127.0.0.1:$PUBLIC_PORT/" >/dev/null 2>&1 \
    || die "ROLLBACK EN ÉCHEC : frontend restauré indisponible sur le port $PUBLIC_PORT."
  log "ROLLBACK RÉUSSI : version restaurée ($tag_be) disponible sur le port $PUBLIC_PORT."
  log "Étapes manuelles restantes : repointer Nginx Proxy Manager vers la cible restaurée (RUNBOOK.md §8), puis vérifier les comptages."
  log "RAPPEL DES LIMITES : rollback APPLICATIF et de CONFIGURATION uniquement."
  log "Il ne restaure ni un schéma PostgreSQL déjà migré, ni des données"
  log "transformées, ni les médias. La restauration PostgreSQL est une"
  log "procédure DISTINCTE (sauvegarde de l'état courant, vérification du"
  log "dump, approbation humaine explicite) — jamais automatique."
}

main() {
  garde_securite
  local commande="${1:-}"
  # Inventaire : lecture seule intégrale — aucun journal créé.
  if [ "$commande" = "inventaire" ]; then
    LOG_ACTIF=0
  else
    init_journal
  fi
  case "$commande" in
    inventaire) shift; cmd_inventaire "$@" ;;
    sauvegarde) shift; cmd_sauvegarde "$@" ;;
    plan) shift; cmd_plan "$@" ;;
    deployer) shift; cmd_deployer "$@" ;;
    rollback) shift; cmd_rollback "$@" ;;
    analyser-plan) shift; analyser_plan "${1:-}" ;;
    *) sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 2 ;;
  esac
}

main "$@"
