#!/usr/bin/env bash
# ============================================================
# Sync INJS-LMD — backend-injs (dev) -> Tobi-nw/injs-app (dépôt de prod)
# ============================================================
# Maillon « sync/push » de la chaîne :
#
#   JCKOUASSI/backend-injs @ <source_ref>
#        -> scripts/sync-injs-app.sh -> Tobi-nw/injs-app @ <target_branch>
#        -> Actions Docker Hub (ophirdesire/qrcode-badge, ophirdesire/qr-badge-frontend)
#        -> VPS -> https://injs.badge-qr-code.pro/
#
# Sémantique par défaut (mode « fastforward ») : l'ARBRE de la source est posé
# en un seul commit, fils de la pointe courante de la cible. Donc :
#   - aucun `--force` : le push est toujours un fast-forward, l'historique et
#     les branches de `injs-app` ne sont jamais réécrits ;
#   - le CONTENU de la cible devient exactement celui de la source, hormis les
#     chemins listés dans SYNC_KEEP_PATHS (ex. la config propre au dépôt cible) ;
#   - idempotent : arbre final == pointe cible => sortie 0 sans écrire.
#
# Règles et garde-fous : docs/DEPLOIEMENT_INJS.md §3
# Recette de 1re exécution   : docs/DEPLOIEMENT_INJS.md §6
# CI                         : .github/workflows/sync-injs-app.yml
# Tests (hors ligne, 14 cas)  : scripts/sync-injs-app.sh --self-test
# ============================================================

set -euo pipefail

# ------------------------------------------------------------
# Configuration (options > variables d'environnement > défauts)
# ------------------------------------------------------------
SOURCE_URL="${SYNC_SOURCE_URL:-}"
SOURCE_REF="${SYNC_SOURCE_REF:-}"
TARGET="${SYNC_TARGET_REPO:-Tobi-nw/injs-app}"
TARGET_BRANCH="${SYNC_TARGET_BRANCH:-main}"
MODE="${SYNC_MODE:-fastforward}"          # fastforward | mirror
KEEP_PATHS="${SYNC_KEEP_PATHS:-}"         # ex: ".github/workflows/prod-build.yml,deploy/"
EXCLUDE_PATHS="${SYNC_EXCLUDE_PATHS:-}"      # chemins a ne JAMAIS pousser (defaut : aucun, pour ne surprendre personne)
DRY_RUN="${SYNC_DRY_RUN:-0}"
ALLOW_MIRROR="${SYNC_ALLOW_MIRROR:-0}"    # pré-requis du mode mirror
ALLOW_PUBLIC_TARGET="${SYNC_ALLOW_PUBLIC_TARGET:-0}"
ALLOW_HYGIENE="${SYNC_ALLOW_HYGIENE:-0}"  # sortie de secours assumée (garde-fou G2)
OFFLINE="${SYNC_OFFLINE:-0}"              # 1 = aucun appel à l'API GitHub (self-test, réseau coupé)
TRIGGER_DISPATCH="${SYNC_TRIGGER_DISPATCH:-0}"
# Identite du commit de sync : forcee ici pour ne jamais dependre d'une config
# git globale (un runner GitHub n'en a pas, et `commit-tree` refuse sans identite).
AUTHOR_NAME="${SYNC_AUTHOR_NAME:-sync-injs-app (backend-injs)}"
AUTHOR_EMAIL="${SYNC_AUTHOR_EMAIL:-sync-injs@badge-qr-code.pro}"
SELF_TEST=0
SUGGEST_KEEP="${SYNC_SUGGEST_KEEP:-0}"

# Branche de travail référencée par la chaîne de déploiement INJS (option A, §6.0).
SRC_BRANCH_DEFAULT="main"

usage() {
  cat <<'EOF'
scripts/sync-injs-app.sh — pose l'arbre de backend-injs sur injs-app

Options
  --source-ref REF        branche/commit source              [SYNC_SOURCE_REF]
  --source-url URL        dépôt source (défaut : origin du dépôt courant)
  --target REPO|URL       owner/repo ou URL git cible        [SYNC_TARGET_REPO]
  --target-branch B       branche cible (défaut : main)      [SYNC_TARGET_BRANCH]
  --mode M                fastforward (défaut) | mirror      [SYNC_MODE]
  --keep LISTE            chemins de la cible à préserver    [SYNC_KEEP_PATHS]
  --exclude LISTE         chemins à retirer de l'arbre poussé [SYNC_EXCLUDE_PATHS]
  --dry-run               ne rien écrire, résumer seulement
  --offline               ne pas interroger l'API GitHub     [SYNC_OFFLINE]
  --self-test             suite de tests locale sur dépôts temporaires
  --suggest-keep          relève les fichiers de la cible que la sync effacerait (aucun push)
  -h, --help              cette aide

Variables d'environnement
  SYNC_TOKEN / INJS_APP_SYNC_TOKEN  PAT fine-grained (contents:read/write sur la cible)
  SYNC_DRY_RUN=1                    équivalent de --dry-run
  SYNC_ALLOW_MIRROR=1               requis pour --mode mirror (push réécrivant l'historique)
  SYNC_ALLOW_PUBLIC_TARGET=1        renonce au garde-fou « cible privée » (G1)
  SYNC_ALLOW_HYGIENE=1              renonce au garde-fou secrets (G2)
  SYNC_TRIGGER_DISPATCH=1           émet un repository_dispatch vers la cible après le push
EOF
}

# ------------------------------------------------------------
# Sortie (journal lisible en local comme dans Actions)
# ------------------------------------------------------------
if [ -t 1 ]; then
  c_ok=$'\033[32m'; c_warn=$'\033[33m'; c_err=$'\033[31m'; c_dim=$'\033[2m'; c_off=$'\033[0m'
else
  c_ok=""; c_warn=""; c_err=""; c_dim=""; c_off=""
fi

log() { printf '%s\n' "$*"; }
kv()  { printf '  %-22s %s\n' "$1" "${*:2}"; }
note() { printf '%s %s\n' "${c_warn}note:${c_off}" "$*"; }
die() {
  printf '%s %s\n' "${c_err}erreur:${c_off}" "$*" >&2
  if [ "${GITHUB_ACTIONS:-}" = "true" ]; then printf '::error::%s\n' "$*" >&2; fi
  exit 1
}

sum() {
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then printf '%s\n' "$*" >>"$GITHUB_STEP_SUMMARY"; fi
  return 0
}

# ------------------------------------------------------------
# Garde-fou G2 — aucun secret ne quitte le dépôt de dev
# ------------------------------------------------------------
HYGIENE_RE='(^|/)\.env($|\.)|(^|/)\.netrc$|(^|/)_netrc$|\.git-credentials$|(^|/)\.npmrc$|(^|/)id_rsa([._]|$)|(^|/)id_ed25519([._]|$)|\.pem$|\.key$|\.p12$|\.pfx$|credentials[^/]*\.txt$|\.dump$|\.sql\.gz$|(^|/)pgpass$'
# Exemptions : les MODELES de configuration suivis par Git ne sont pas des secrets
# (backend/.env.example, frontend/.env.example, qr_badge_mobile/.env.example...).
# Ils sont bloques par HYGIENE_RE (`.env.`), on les retire du resultat.
HYGIENE_EXCLUDE='\.env\.(exampl[eé]|sample|template|dist|inc|default)$|\.env\.[a-z]+\.example$'
DATA_RE='\.(xlsx|xls|csv|numbers|sqlite3)$'

check_hygiene() {
  local repo="$1" ref="$2" hits data
  hits=$(git -C "$repo" ls-tree -r --name-only "$ref" | grep -E "$HYGIENE_RE" | grep -vE "$HYGIENE_EXCLUDE" || true)
  if [ -n "$hits" ]; then
    log "--- G2 hygiène : fichiers sensibles présents dans l'arbre source ---"
    printf '  %s\n' $hits
    if [ "$ALLOW_HYGIENE" != "1" ]; then
      die "sync bloquée : ces fichiers ne doivent pas quitter le dépôt de dev (G2, docs/DEPLOIEMENT_INJS.md §3). Retire-les de la branche source ; SYNC_ALLOW_HYGIENE=1 uniquement si tu assumes."
    fi
    note "SYNC_ALLOW_HYGIENE=1 : poursuite assumée malgré des fichiers sensibles."
  fi
  data=$(git -C "$repo" ls-tree -r --name-only "$ref" | grep -vE '^(docs/modeles/|backend/test_)' | grep -E "$DATA_RE" | head -5 || true)
  if [ -n "$data" ]; then
    note "données suivies dans l'arbre (vigilance P00-02) : $(printf '%s ' $data)"
  fi
  # Dechets de build suivis : ils partiraient en prod et polluent l'historique cible.
  local junk njunk
  junk=$(git -C "$repo" ls-tree -r --name-only "$ref" | grep -E '(^|/)(\.pycache__?|__pycache__|node_modules|dist|build|\.venv)/|\.pyc$' | head -3 || true)
  njunk=$(git -C "$repo" ls-tree -r --name-only "$ref" | grep -cE '(^|/)(\.pycache__?|__pycache__|node_modules|dist|build|\.venv)/|\.pyc$' || true)
  if [ -n "$junk" ] && [ "${njunk:-0}" -gt 0 ]; then
    note "${njunk} fichier(s) de build suivis dans la branche source (ex : $(printf '%s ' $junk)) — ajoute-les a SYNC_EXCLUDE_PATHS, ou depose-les de Git (cf. P00-02)."
  fi
  return 0
}

# "https://[user@]github.com/owner/repo[.git]" -> "owner/repo" (vide sinon)
github_slug_from_url() {
  local url="${1:-}"
  case "$url" in *github.com/*) : ;; *) printf '' ; return 1 ;; esac
  printf '%s' "$url" | sed -E 's#^https?://([^@]+@)?##; s#^github\.com/##; s#\.git$##; s#/$##'
  return 0
}

# ------------------------------------------------------------
# Garde-fou G1 — une cible publique ne reçoit jamais le dépôt de dev
# ------------------------------------------------------------
check_target_visibility() {
  local url="$1" api json owner_repo
  if [ "$OFFLINE" = "1" ]; then note "G1 non vérifié (--offline)."; return 0; fi
  case "$url" in
    https://*github.com/*) : ;;
    *) note "G1 non applicable : la cible n'est pas un URL github.com ($url)."; return 0 ;;
  esac
  owner_repo=$(github_slug_from_url "$url") || owner_repo=""
  if [ -z "$owner_repo" ]; then note "G1 : slug cible non résolu ($url) — vérification ignorée."; return 0; fi
  api="https://api.github.com/repos/${owner_repo}"
  if [ -n "${SYNC_TOKEN:-}" ]; then
    json=$(curl -sS -m 25 -H "Accept: application/vnd.github+json" -H "Authorization: Bearer ${SYNC_TOKEN}" "$api" 2>/dev/null) || json=""
  else
    json=$(curl -sS -m 25 -H "Accept: application/vnd.github+json" "$api" 2>/dev/null) || json=""
  fi
  if [ -z "$json" ]; then
    die "G1 impossible : API GitHub injoignable pour ${owner_repo}. Réessaie, ou pose SYNC_OFFLINE=1 en connaissance de cause."
  fi
  if printf '%s' "$json" | grep -qE '"private"[[:space:]]*:[[:space:]]*false'; then
    if [ "$ALLOW_PUBLIC_TARGET" = "1" ]; then
      note "G1 : cible PUBLIQUE, SYNC_ALLOW_PUBLIC_TARGET=1 -> poursuite assumée."
      return 0
    fi
    die "G1 bloqué : ${owner_repo} est public. Y pousser le dépôt de dev exposerait code, documentation interne et historique. Rends la cible privée (ou change-la) ; SYNC_ALLOW_PUBLIC_TARGET=1 seulement si tu assumes."
  fi
  if printf '%s' "$json" | grep -qE '"private"[[:space:]]*:[[:space:]]*true'; then
    log "  G1 : cible privée — OK."
  else
    log "  G1 : invisibilité publique (404) — considéré comme non public, OK."
  fi
  return 0
}

# ------------------------------------------------------------
# URLs + authentification (le token ne transite ni par l'URL poussée,
# ni par .git/config persisté, ni par les journaux)
# ------------------------------------------------------------
resolve_target_url() {
  local t="$1"
  case "$t" in
    /*|./*|file:*|http:*|https:*|ssh:*|git:*) printf '%s' "$t" ;;
    github.com/*) printf 'https://%s.git' "${t#github.com/}" ;;
    *) printf 'https://github.com/%s.git' "${t%.git}" ;;
  esac
}

make_askpass() {
  local dir="$1"
  cat >"$dir/askpass.sh" <<'EOS'
#!/bin/sh
printf '%s' "$SYNC_TOKEN"
EOS
  chmod 700 "$dir/askpass.sh"
  printf '%s' "$dir/askpass.sh"
}

with_cred() {
  # injecte l'usager x-access-token dans une URL https://github.com (pas le mot de passe)
  local url="$1"
  case "$url" in
    https://github.com/*) printf 'https://x-access-token@github.com/%s' "${url#https://github.com/}" ;;
    *) printf '%s' "$url" ;;
  esac
}

# ------------------------------------------------------------
# Arbre final = arbre source, moins les chemins que la cible doit garder
# ------------------------------------------------------------
# IMPORTANT : cette fonction ne renvoie sur stdout que l'empreinte de l'arbre final
# (elle est capturee par $(...)); tout son bavardage part sur stderr.
build_final_tree() {
  local repo="$1" src_sha="$2" tip="$3" wt="$4" p src_keep n
  git -C "$repo" worktree add --quiet --detach "$wt" "$src_sha" >/dev/null 2>&1 \
    || die "impossible de matérialiser l'arbre source (worktree git)."
  if [ -n "$KEEP_PATHS" ]; then
    # virgule + saut de ligne : la liste se decoupe a la virgule, mais les
    # sorties `rev-list` (une empreinte par ligne) doivent rester exploitables.
    local IFS=$',\n'
    for p in $KEEP_PATHS; do
      p=$(printf '%s' "$p" | sed -E 's#^/+##; s#/+$##')
      [ -z "$p" ] && continue
      # 1) le chemin existe sur la pointe cible -> on la prend telle quelle.
      # 2) sinon on le repèche dans l'historique cible : ainsi un fichier propre a
      #    injs-app survit aux syncs successives (idempotence de --keep).
      #    Attention : `rev-list -- <p>` designe aussi le commit qui l'a SUPPRIME ;
      #    on teste donc l'existence reelle du chemin dans chaque candidat.
      if [ -n "$(git -C "$repo" ls-tree -r --name-only "$tip" -- "$p" 2>/dev/null | head -1)" ]; then
        src_keep="$tip"
      else
        local c
        src_keep=""
        for c in $(git -C "$repo" rev-list -n 25 "$tip" -- "$p" 2>/dev/null || true); do
          if git -C "$repo" cat-file -e "${c}:${p}" 2>/dev/null; then src_keep="$c"; break; fi
        done
      fi
      if [ -z "$src_keep" ]; then
        note "SYNC_KEEP_PATHS : « $p » introuvable dans la cible et son historique — rien à préserver." >&2
        continue
      fi
      git -C "$wt" checkout --quiet "$src_keep" -- "$p" \
        || die "SYNC_KEEP_PATHS : préservation impossible de « $p » (depuis ${src_keep:0:10}) — la sync est annulée plutot que de supprimer un fichier de prod."
      # Contrôle croisé : le chemin (fichier OU repertoire) doit etre dans l'index.
      if [ -z "$(git -C "$wt" ls-files -- "$p" | head -1)" ]; then
        die "SYNC_KEEP_PATHS : « $p » annoncé préservé mais absent de l'index — sync annulée (garde de non-régression)."
      fi
      log "  préserve depuis la cible : $p (${src_keep:0:10})" >&2
    done
    unset IFS
  fi
  # Exclusions : le chemin est retire de l'INDEX (donc de l'arbre pousse), les
  # fichiers restants du worktree temporaires n'entrent pas dans write-tree.
  if [ -n "$EXCLUDE_PATHS" ]; then
    local IFS=$',\n'
    for p in $EXCLUDE_PATHS; do
      p=$(printf '%s' "$p" | sed -E 's#^/+##; s#/+$##')
      [ -z "$p" ] && continue
      if [ -z "$(git -C "$wt" ls-files -- "$p" | head -1)" ]; then
        note "SYNC_EXCLUDE_PATHS : « $p » absent de l'arbre — rien à exclure." >&2
        continue
      fi
      n=$(git -C "$wt" ls-files -- "$p" | wc -l | tr -d ' ')
      git -C "$wt" rm -q -r --cached --ignore-unmatch -- "$p" >/dev/null 2>&1 \
        || die "SYNC_EXCLUDE_PATHS : retrait impossible de « $p » — sync annulée."
      if [ -n "$(git -C "$wt" ls-files -- "$p" | head -1)" ]; then
        die "SYNC_EXCLUDE_PATHS : « $p » encore présent dans l'index après retrait — sync annulée."
      fi
      log "  exclu de l'arbre pousse : $p ($n fichier(s))" >&2
    done
    unset IFS
  fi
  git -C "$wt" write-tree
}

commit_message() {
  local src_sha="$1" subject=""
  subject=$(git -C "$REPO" log -1 --format=%s "$src_sha" 2>/dev/null || printf '(sujet illisible)')
  cat <<EOF
chore(sync): injs-app <- backend-injs@${src_sha:0:10}

Source        : ${SOURCE_URL} (${SOURCE_REF})
Sujet amont   : ${subject}
Mode          : ${MODE}
Chemins gardes : ${KEEP_PATHS:-(aucun)}

Généré par scripts/sync-injs-app.sh — chaine INJS vers https://injs.badge-qr-code.pro/
EOF
}

# ------------------------------------------------------------
# --suggest-keep : la sync remplace le CONTENU de la cible ; cette analyse relève
# ce que la cible PERDRAIT, pour remplir SYNC_KEEP_PATHS avec un relevé et non
# une liste inventée. Aucune écriture.
# ------------------------------------------------------------
suggest_keep() {
  log ""
  log "3/5 Analyse « ce que la cible perdrait » (aucune écriture)"
  if [ -z "${tip:-}" ]; then
    note "cible sans branche « ${TARGET_BRANCH} » : rien à préserver, la sync créera tout."
    return 0
  fi
  local dels n
  dels=$(git -C "$REPO" diff --name-only --diff-filter=D "$tip" "$SRC_SHA" 2>/dev/null | sed '/^$/d' || true)
  n=$(printf '%s\n' "$dels" | grep -c . || true)
  if [ "${n:-0}" = "0" ]; then
    log "  ${c_ok}aucun fichier de la cible ne disparaîtrait${c_off} — SYNC_KEEP_PATHS peut rester vide."
    return 0
  fi
  local HOT_RE='^\.github/workflows/|(^|/)(docker-)?compose[^/]*\.(yml|yaml)$|(^|/)deploy/|(^|/)systemd/|(^|/)nginx/|\.(conf|service)$|^Dockerfile|(^|/)Dockerfile'
  local hot cold n_hot n_cold list dirs
  hot=$(printf '%s\n' "$dels" | grep -E "$HOT_RE" || true)
  cold=$(printf '%s\n' "$dels" | grep -vE "$HOT_RE" || true)
  n_hot=$(printf '%s\n' "$hot" | grep -c . || true); n_cold=$(printf '%s\n' "$cold" | grep -c . || true)
  log "  ${n} fichier(s) de la cible seraient supprimés par la sync"
  if [ -n "$hot" ]; then
    log "  ${c_warn}config d'infra de la cible (${n_hot}) — à préserver :${c_off}"
    printf '%s\n' "$hot" | sed '/^$/d' | head -25 | sed 's/^/      /'
  fi
  if [ -n "$cold" ]; then
    log "  ${c_dim}autres fichiers de la cible (${n_cold}) — à examiner :${c_off}"
    printf '%s\n' "$cold" | sed '/^$/d' | head -10 | sed 's/^/      /'
  fi
  list=$(printf '%s\n' "$hot" | sed '/^$/d' | sort -u | paste -sd',' -)
  # Racine « . » exclue : preserver « . » reviendrait a preserver toute la cible.
  dirs=$(printf '%s\n' "$hot" | sed '/^$/d' | while IFS= read -r f; do dirname "$f"; done | grep -vE '^\.$' | sort -u | paste -sd',' -)
  echo
  log "  ${c_ok}À coller tel quel (pertinent seulement si ces fichiers doivent survivre) :${c_off}"
  [ -n "$list" ] && printf '    SYNC_KEEP_PATHS="%s"\n' "$list"
  [ -n "$dirs" ] && [ "$dirs" != "$list" ] && printf '    ou, plus large : SYNC_KEEP_PATHS="%s"\n' "$dirs"
  note "préserver un chemin le gèle à sa version actuelle de la cible : un fichier de prod qui doit évoluer avec le code ne doit PAS y figurer."
  sum "### Suggestion SYNC_KEEP_PATHS (${TARGET}@${TARGET_BRANCH})

- fichiers que la sync supprimerait : **${n}**
- dont config d'infra : ${n_hot:-0}
- proposition : \`${list:-*(rien)*}\`"
  return 0
}

# ------------------------------------------------------------
# Une exécution complète
# ------------------------------------------------------------
do_sync() {
  WORK=$(mktemp -d "${TMPDIR:-/tmp}/injs-sync.XXXXXX")
  # shellcheck disable=SC2064
  trap "rm -rf '$WORK'" EXIT

  TARGET_URL=$(resolve_target_url "$TARGET")
  if [ -z "${SYNC_TOKEN:-}" ]; then
    case "$TARGET_URL" in
      /*|file:*|./*) log "  (cible locale : aucun token requis)" ;;
      *) die "Aucun token : exporte SYNC_TOKEN (ou INJS_APP_SYNC_TOKEN) avec un PAT fine-grained limité à ${TARGET} (contents:Read and write)." ;;
    esac
  fi

  # Garde-fou G1 : la cible ne doit pas etre publique (le depot de dev est prive).
  check_target_visibility "$TARGET_URL"

  ASKPASS=$(make_askpass "$WORK")

  log ""
  log "1/5 Clone de la cible ${TARGET} @ ${TARGET_BRANCH}"
  local clone_url branch_exists=""
  clone_url=$(with_cred "$TARGET_URL")
  # `git ls-remote` part du repertoire courant. Dans une CI, ce repertoire est le
  # checkout de la source, ou `actions/checkout` a pose l'entete
  # `http.https://github.com/.extraheader` (jeton du workflow). Cet entete prime
  # sur GIT_ASKPASS : la cible privee repond 404, la sortie est vide et la branche
  # passe pour inexistante -> commit RACINE au lieu d'un fast-forward, et les
  # chemins de SYNC_KEEP_PATHS resolus dans la SOURCE au lieu de la cible
  # (constate le 2026-09-20, runs 35491761808 et 35494860699). On neutralise donc
  # explicitement cet entete pour n'interroger la cible qu'avec SYNC_TOKEN.
  # (La variante generique `-c http.extraheader=` laisse l'entete URL passer :
  # verifie inoperante. Le clone est insensible a ce piege : verifie.)
  branch_exists=$(GIT_ASKPASS="$ASKPASS" git -c http.https://github.com/.extraheader= \
    ls-remote --heads "$clone_url" "$TARGET_BRANCH" 2>/dev/null | head -1 || true)
  if [ -n "$branch_exists" ]; then
    GIT_ASKPASS="$ASKPASS" git clone --quiet --no-tags --single-branch --branch "$TARGET_BRANCH" \
      "$clone_url" "$WORK/repo" 2>"$WORK/clone.err" || die "clone de la cible en échec : $(sed -n '1p' "$WORK/clone.err")"
  else
    note "branche « ${TARGET_BRANCH} » absente de la cible : le commit de sync sera un commit racine (création de branche)."
    GIT_ASKPASS="$ASKPASS" git clone --quiet --no-tags "$clone_url" "$WORK/repo" 2>"$WORK/clone.err" || {
      if grep -qiE "not found|authentication|permission denied|invalid credentials|could not read" "$WORK/clone.err"; then
        die "accès refusé à ${TARGET} : $(sed -n '1p' "$WORK/clone.err") — le token doit couvrir ${TARGET} en lecture/écriture (et la branche visée exister)."
      fi
      die "clone de la cible en échec : $(sed -n '1p' "$WORK/clone.err")"
    }
  fi
  REPO="$WORK/repo"
  # Aucune référence au token n'est laissée dans le clone.
  git -C "$REPO" remote set-url origin "$TARGET_URL"

  if [ -z "$SOURCE_URL" ]; then
    SOURCE_URL=$(git -C "$PWD" remote get-url origin 2>/dev/null || true)
    [ -n "$SOURCE_URL" ] || die "dépôt source non déductiable : lance le script depuis une copie de backend-injs, ou passe --source-url."
  fi
  [ -n "$SOURCE_REF" ] || SOURCE_REF="$SRC_BRANCH_DEFAULT"
  git -C "$REPO" remote add source "$SOURCE_URL"

  log ""
  log "2/5 Fetch de la source ${SOURCE_REF}"
  # mirror : l'historique complet est poussé ; fastforward : seul l'arbre compte.
  # Idiome portable (bash 3.2 + set -u) : « set -- » et « "$@" » tolèrent zéro argument,
  # contrairement à un tableau vide expansé « ${arr[@]} ».
  if [ "$MODE" = "mirror" ]; then
    set --
  else
    set -- --depth 1
  fi
  GIT_ASKPASS="$ASKPASS" git -C "$REPO" fetch --quiet --no-tags "$@" source "$SOURCE_REF" 2>"$WORK/fetch.err" \
    || die "fetch « $SOURCE_REF » sur ${SOURCE_URL} impossible : $(sed -n '1p' "$WORK/fetch.err")"
  SRC_SHA=$(git -C "$REPO" rev-parse FETCH_HEAD^{commit})
  local src_tree
  src_tree=$(git -C "$REPO" rev-parse "${SRC_SHA}^{tree}")
  kv "commit source" "$SRC_SHA"
  kv "sujet source" "$(git -C "$REPO" log -1 --format=%s "$SRC_SHA" 2>/dev/null || printf '?')"
  check_hygiene "$REPO" "$SRC_SHA"

  local tip="" tip_tree=""
  if [ -n "$branch_exists" ]; then
    tip=$(git -C "$REPO" rev-parse "refs/remotes/origin/${TARGET_BRANCH}")
    tip_tree=$(git -C "$REPO" rev-parse "${tip}^{tree}")
    kv "pointe cible" "${tip:0:12} (arbre ${tip_tree:0:12})"
  fi

  if [ "$SUGGEST_KEEP" = "1" ]; then
    suggest_keep
    return 0
  fi

  log ""
  log "3/5 Arbre final (mode ${MODE})"
  local final_tree
  if [ "$MODE" = "mirror" ]; then
    if [ "$ALLOW_MIRROR" != "1" ]; then
      die "mode mirror = push réécrivant l'historique de ${TARGET}@${TARGET_BRANCH} (force-with-lease). C'est un choix volontaire : relance avec SYNC_ALLOW_MIRROR=1. Le mode fastforward est le mode recommandé de la chaîne INJS."
    fi
    final_tree="$src_tree"
    # En mirror, l'objet a aligner est le COMMIT (pas seulement l'arbre) :
    # une comparaison d'arbres ferait passer un décalage d'historique pour du vide.
    if [ -n "$tip" ] && [ "$SRC_SHA" = "$tip" ]; then
      log ""
      log "${c_ok}Déjà à jour${c_off} — ${TARGET}@${TARGET_BRANCH} pointe déjà sur ${SRC_SHA}. Rien à pousser."
      sum "### Sync injs-app — miroir déjà aligné

\`${TARGET}@${TARGET_BRANCH}\` == \`${SRC_SHA}\`. Aucun push."
      return 0
    fi
  else
    final_tree=$(build_final_tree "$REPO" "$SRC_SHA" "${tip:-$SRC_SHA}" "$WORK/wt")
  fi
  case "$final_tree" in
    *[!0-9a-f]*|"") die "arbre final illisible (« $final_tree ») : anomalie de construction, aucun push effectué." ;;
  esac
  kv "arbre final" "$final_tree"

  if [ "$MODE" != "mirror" ] && [ -n "$tip_tree" ] && [ "$final_tree" = "$tip_tree" ]; then
    log ""
    log "${c_ok}Déjà à jour${c_off} — arbre final == ${TARGET}@${TARGET_BRANCH}. Rien à pousser."
    sum "### Sync injs-app — déjà à jour

\`${SOURCE_REF}\` (\`${SRC_SHA:0:10}\`) == \`${TARGET}@${TARGET_BRANCH}\` (\`${tip:0:10}\`). Aucun push."
    return 0
  fi

  log ""
  log "4/5 Effet sur la cible"
  local n_new
  n_new=$(git -C "$REPO" ls-tree -r --name-only "$final_tree" | wc -l | tr -d ' ')
  kv "fichiers poussés" "$n_new"
  if [ -n "$tip" ]; then
    local a=0 m=0 d=0
    while read -r st _; do
      case "$st" in A) a=$((a+1));; M) m=$((m+1));; D) d=$((d+1));; esac
    done < <(git -C "$REPO" diff --name-status "$tip" "$final_tree" 2>/dev/null || true)
    kv "ajoutes / modif. / suppr." "$a / $m / $d"
    log "  ${c_dim}$(git -C "$REPO" diff --name-status "$tip" "$final_tree" 2>/dev/null | head -10 | sed 's/^/    /')${c_off}"
    if [ "$d" -gt 0 ]; then
      note "des fichiers propres à la cible disparaissent (-$d) : ajoute-les a SYNC_KEEP_PATHS si le depot cible doit les conserver (ex. sa config Actions)."
    fi
  fi
  sum "### Sync injs-app — ${MODE}

- source : \`${SOURCE_REF}\` → \`${SRC_SHA}\`
- cible : \`${TARGET}@${TARGET_BRANCH}\` (${tip:+"\\\`${tip:0:12}\\\`"}${tip:-"nouvelle branche"})
- fichiers : **$n_new**${tip:+, voir détail dans le journal}
- chemins préservés : ${KEEP_PATHS:-*(aucun)*}
- dry-run : $([ "$DRY_RUN" = "1" ] && echo "oui" || echo "non")"

  if [ "$DRY_RUN" = "1" ]; then
    log ""
    log "${c_warn}DRY-RUN${c_off} — aucune écriture. Étape omise : git push ${TARGET} <commit>:refs/heads/${TARGET_BRANCH}"
    return 0
  fi

  log ""
  log "5/5 Push vers ${TARGET}@${TARGET_BRANCH}"
  if [ "$MODE" = "mirror" ]; then
    GIT_ASKPASS="$ASKPASS" git -C "$REPO" push --quiet \
      --force-with-lease="refs/heads/${TARGET_BRANCH}:${tip}" \
      "$clone_url" "${SRC_SHA}:refs/heads/${TARGET_BRANCH}" \
      || die "push mirror refusé (lease obsolete ou branche protegee). Relance sans --mode mirror pour rester en fast-forward."
    log "${c_ok}Miroir poussé${c_off} : ${TARGET}@${TARGET_BRANCH} = ${SRC_SHA} (historique remplacé)."
  else
    local new msg
    msg=$(commit_message "$SRC_SHA")
    if [ -n "$tip" ]; then
      new=$(git -C "$REPO" -c "user.name=$AUTHOR_NAME" -c "user.email=$AUTHOR_EMAIL" \
        -c "commit.gpgsign=false" commit-tree "$final_tree" -p "$tip" -m "$msg") ||
        die "creation du commit de sync en échec (git commit-tree) — rien n'a été poussé."
    else
      new=$(git -C "$REPO" -c "user.name=$AUTHOR_NAME" -c "user.email=$AUTHOR_EMAIL" \
        -c "commit.gpgsign=false" commit-tree "$final_tree" -m "$msg") ||
        die "creation du commit de sync en échec (git commit-tree) — rien n'a été poussé."
    fi
    case "$new" in
      ""|*[!0-9a-f]*) die "commit de sync invalide (« $new ») — push annule." ;;
    esac
    GIT_ASKPASS="$ASKPASS" git -C "$REPO" push --quiet "$clone_url" "${new}:refs/heads/${TARGET_BRANCH}" \
      || die "push refuse : branche protegee, ou sync concurrente entre-temps (non fast-forward). Relance la sync."
    log "${c_ok}Sync poussée${c_off} : ${TARGET}@${TARGET_BRANCH} = ${new}"
    sum "Push OK — commit cible \`${new}\`."
  fi
  return 0
}

# ------------------------------------------------------------
# Réveil optionnel du pipeline cible
# ------------------------------------------------------------
maybe_dispatch() {
  [ "$TRIGGER_DISPATCH" = "1" ] || return 0
  [ "$OFFLINE" = "1" ] && { note "repository_dispatch ignoré (--offline)."; return 0; }
  case "$TARGET_URL" in https://github.com/*) : ;; *) note "repository_dispatch ignoré : cible non GitHub."; return 0 ;; esac
  local owner_repo code
  owner_repo=$(github_slug_from_url "$TARGET_URL") || owner_repo=""
  [ -n "$owner_repo" ] || { note "repository_dispatch ignore : slug cible non résolu."; return 0; }
  code=$(curl -sS -m 25 -o /dev/null -w '%{http_code}' -X POST \
    -H "Accept: application/vnd.github+json" -H "Authorization: Bearer ${SYNC_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"event_type\":\"injs-sync\",\"client_payload\":{\"source_sha\":\"${SRC_SHA}\"}}" \
    "https://api.github.com/repos/${owner_repo}/dispatches" 2>/dev/null || printf '000')
  case "$code" in
    2*) log "  repository_dispatch « injs-sync » accepté (HTTP $code)." ;;
    *)  note "repository_dispatch refusé (HTTP $code) — sans importance si les Actions de la cible écoutent « push » sur ${TARGET_BRANCH}." ;;
  esac
  return 0
}

# ------------------------------------------------------------
# --self-test : harnais hors ligne (aucun réseau, aucun token)
# ------------------------------------------------------------
run_self_test() {
  # Isolation hermétique : l'environnement ambiant (exporté par le workflow, p. ex.
  # SYNC_DRY_RUN=1, SYNC_KEEP_PATHS, SYNC_TOKEN…) ne doit PAS fuiter dans les
  # sous-invocations du harnais, qui sont pilotées uniquement par leurs flags CLI.
  unset SYNC_DRY_RUN SYNC_MODE SYNC_KEEP_PATHS SYNC_EXCLUDE_PATHS SYNC_TOKEN \
        SYNC_TARGET_REPO SYNC_TARGET_BRANCH SYNC_SOURCE_REF SYNC_SOURCE_URL \
        SYNC_ALLOW_MIRROR SYNC_ALLOW_HYGIENE SYNC_TRIGGER_DISPATCH || true
  local T
  T=$(mktemp -d "${TMPDIR:-/tmp}/injs-selftest.XXXXXX")
  # shellcheck disable=SC2064
  trap "rm -rf '$T'" EXIT
  export GIT_AUTHOR_NAME=sync-test GIT_AUTHOR_EMAIL=t@local GIT_COMMITTER_NAME=sync-test GIT_COMMITTER_EMAIL=t@local
  local pass=0 fail=0
  ok()   { printf '  %sPASS%s %s\n' "$c_ok" "$c_off" "$1"; pass=$((pass + 1)); }
  bad()  { printf '  %sFAIL%s %s\n' "$c_err" "$c_off" "$1"; fail=$((fail + 1)); }
  t_ok() { local l="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$l"; else bad "$l"; fi; }
  t_ko() { local l="$1"; shift; if "$@" >/dev/null 2>&1; then bad "$l (aurait du echouer)"; else ok "$l"; fi; }
  eq()   { local l="$1"; shift; if [ "$1" = "$2" ]; then ok "$l"; else bad "$l ($1 != $2)"; fi; }

  # source de test
  git init -q --bare "$T/src.git"
  git init -q "$T/w"
  ( cd "$T/w"
    mkdir -p backend frontend docs
    printf 'app\n'  > backend/app.py
    printf 'front\n'> frontend/main.jsx
    printf '# doc\n'> docs/NOTE.md
    git add -A && git commit -qm "feat: lot A" && git branch -M test-src && git push -q "$T/src.git" test-src
    printf 'app2\n' >> backend/app.py
    git commit -qam "feat: lot B" && git push -q "$T/src.git" test-src ) || die "setup self-test (source) en échec"

  # cible de test : historique sans rapport avec la source, + fichiers propres a la prod
  git init -q --bare "$T/tgt.git"
  git init -q "$T/tw"
  ( cd "$T/tw"
    printf 'legacy\n' > LEGIDE.md
    mkdir -p .github/workflows
    printf 'name: prod-build\non:\n  push:\n    branches: [main]\n' > .github/workflows/prod-build.yml
    git add -A && git commit -qm "prod: init" && git branch -M main && git push -q "$T/tgt.git" main ) || die "setup self-test (cible) en échec"

  local S=(--source-url "$T/src.git" --target "$T/tgt.git" --target-branch main --offline --source-ref test-src)
  local head_before head_tree_src prod_blob_init prod_commit_init
  head_before=$(git --git-dir="$T/tgt.git" rev-parse main)
  head_tree_src=$(git --git-dir="$T/src.git" rev-parse test-src^{tree})
  prod_blob_init=$(git --git-dir="$T/tgt.git" rev-parse main:.github/workflows/prod-build.yml)
  prod_commit_init="$head_before"

  log ""
  log "self-test — 14 cas, hors ligne"

  # 1 — dry-run : aucun octet écrit
  t_ok "1  dry-run sans ecriture" bash "$0" "${S[@]}" --dry-run
  eq "1b HEAD de la cible inchange" "$head_before" "$(git --git-dir="$T/tgt.git" rev-parse main)"

  # 2 — fastforward : arbre source pose, historique cible preserve
  t_ok "2  sync fastforward" bash "$0" "${S[@]}"
  eq "2b arbre cible == arbre source" "$head_tree_src" "$(git --git-dir="$T/tgt.git" rev-parse main^{tree})"
  if git --git-dir="$T/tgt.git" cat-file -e main:LEGIDE.md 2>/dev/null; then bad "2c contenu cible remplace"; else ok "2c contenu cible remplace"; fi
  t_ok "2d historique cible preserve (pas de --force)" git --git-dir="$T/tgt.git" log main --format=%s
  git --git-dir="$T/tgt.git" log -1 --format=%s main | grep -q '^chore(sync):' && ok "2e commit de sync horodaté" || bad "2e commit de sync horodaté"
  git --git-dir="$T/tgt.git" rev-parse --verify main^1 >/dev/null 2>&1 && ok "2f fast-forward (1 parent = ancien HEAD)" || bad "2f fast-forward (1 parent = ancien HEAD)"
  [ "$(git --git-dir="$T/tgt.git" rev-parse main^1)" = "$head_before" ] && ok "2g parent == ancien HEAD" || bad "2g parent == ancien HEAD"

  # 3 — idempotence
  t_ok "3  relance = deja a jour, exit 0" bash "$0" "${S[@]}"

  # 4 — SYNC_KEEP_PATHS préserve la config propre a la cible (repéchée dans son historique)
  t_ok "4  sync avec --keep" env SYNC_KEEP_PATHS=".github/workflows/prod-build.yml" bash "$0" "${S[@]}"
  t_ok "4b chemin garde retrouve dans la cible" git --git-dir="$T/tgt.git" cat-file -e main:.github/workflows/prod-build.yml
  eq "4c contenu garde == version d'origine de la cible" "$prod_blob_init" "$(git --git-dir="$T/tgt.git" rev-parse main:.github/workflows/prod-build.yml)"
  t_ok "4d contenu source egalement présent côté cible" git --git-dir="$T/tgt.git" cat-file -e main:backend/app.py
  t_ok "4e relance avec --keep = deja a jour (idempotence)" bash "$0" "${S[@]}" --keep .github/workflows/prod-build.yml
  local main_after_4
  main_after_4=$(git --git-dir="$T/tgt.git" rev-parse main)

  # 5 — garde-fou G2 sur un .env suivi
  ( cd "$T/w"; printf 'SECRET=x\n' > .env; printf 'app3\n' > backend/app.py; git add -A; git commit -qm "feat: lot C + secret" >/dev/null; git push -qf "$T/src.git" test-src )
  t_ko "5a G2 bloque la sync" bash "$0" "${S[@]}"
  eq "5a-bis cible intacte apres blocage" "$(git --git-dir="$T/tgt.git" rev-parse main)" "$main_after_4"
  t_ok "5b SYNC_ALLOW_HYGIENE=1 laisse passer" env SYNC_ALLOW_HYGIENE=1 bash "$0" "${S[@]}"
  t_ok "5b-bis le .env a effectivement été poussé (opt-in explicite)" git --git-dir="$T/tgt.git" cat-file -e main:.env
  # remise en etat propre de la source
  ( cd "$T/w"; git rm -q --cached .env; rm -f .env; git commit -qm "fix: retire le secret" >/dev/null; git push -qf "$T/src.git" test-src )
  t_ok "5c resync propre apres retrait" bash "$0" "${S[@]}"
  local main_after_5c
  main_after_5c=$(git --git-dir="$T/tgt.git" rev-parse main)
  if git --git-dir="$T/tgt.git" cat-file -e main:.env 2>/dev/null; then bad "5d .env survit apres retrait"; else ok "5d .env disparait de la cible apres retrait"; fi

  # 5bis — les modeles de config suivis ne sont pas des secrets (faux positif G2)
  if [ -n "$(git --git-dir="$T/src.git" ls-tree -r --name-only test-src | grep -E '\.env\.(example|exemple)$' || true)" ]; then
    note "(source de test sans .env.example : cas 5bis non applicable)"
  fi
  ( cd "$T/w"; mkdir -p backend; printf 'DEBUG=True\n' > backend/.env.example; git add -A; git commit -qm "docs: modele env" >/dev/null; git push -qf "$T/src.git" test-src )
  t_ok "5bis .env.example ne bloque pas la sync" bash "$0" "${S[@]}"
  t_ok "5bis-2 le modele est bien parti a la cible" git --git-dir="$T/tgt.git" cat-file -e main:backend/.env.example
  if git --git-dir="$T/tgt.git" cat-file -e main:.env 2>/dev/null; then bad "5bis-3 un vrai .env a ete pousse"; else ok "5bis-3 toujours aucun vrai .env cote cible"; fi

  # 6 — mirror : opt-in explicite, puis miroir exact de l'historique
  local main_before_6
  main_before_6=$(git --git-dir="$T/tgt.git" rev-parse main)
  t_ko "6a mirror refuse sans opt-in" bash "$0" "${S[@]}" --mode mirror
  eq "6a-bis cible intacte apres refus du mirror" "$(git --git-dir="$T/tgt.git" rev-parse main)" "$main_before_6"
  t_ok "6b mirror avec SYNC_ALLOW_MIRROR=1" env SYNC_ALLOW_MIRROR=1 bash "$0" "${S[@]}" --mode mirror
  eq "6c miroir : HEAD cible == HEAD source" "$(git --git-dir="$T/tgt.git" rev-parse main)" "$(git --git-dir="$T/src.git" rev-parse test-src)"
  if git --git-dir="$T/tgt.git" merge-base --is-ancestor "$prod_commit_init" main 2>/dev/null; then
    bad "6d historique de prod remplace"
  else
    ok "6d historique de prod remplace"
  fi
  t_ok "6e le commit de prod reste reachable (reflog/branche) => pas de perte irreparable" git --git-dir="$T/tgt.git" cat-file -e "${prod_commit_init}^{commit}"

  # 7 — branche cible inexistante : creation par commit racine
  t_ok "7  sync vers une branche creee ici" bash "$0" "${S[@]}" --target-branch verif-nouvelle-branche
  t_ok "7b la branche a ete creee" git --git-dir="$T/tgt.git" rev-parse -q --verify verif-nouvelle-branche
  eq "7c contenu de la nouvelle branche" "$(git --git-dir="$T/tgt.git" rev-parse verif-nouvelle-branche^{tree})" "$(git --git-dir="$T/src.git" rev-parse test-src^{tree})"

  # 8 — ref source inexistante : echec clair, aucune ecriture
  head_before=$(git --git-dir="$T/tgt.git" rev-parse main)
  t_ko "8a ref source inexistante = echec" bash "$0" "${S[@]}" --source-ref arena/nexiste-pas
  eq "8b cible intacte apres echec" "$head_before" "$(git --git-dir="$T/tgt.git" rev-parse main)"

  # 9 — resolution des URLs (aucun reseau) : c'est elle qui decide ou va le push
  # shellcheck disable=SC1090
  ( SYNC_LIB_ONLY=1 source "$0"
    eq2() { if [ "$2" = "$3" ]; then exit 0; else printf '  <%s> != <%s>\n' "$2" "$3" >&2; exit 1; fi; }
    eq2 ignore "$(resolve_target_url Tobi-nw/injs-app)" "https://github.com/Tobi-nw/injs-app.git"
    eq2 ignore "$(resolve_target_url github.com/Tobi-nw/injs-app)" "https://github.com/Tobi-nw/injs-app.git"
    eq2 ignore "$(resolve_target_url Tobi-nw/injs-app.git)" "https://github.com/Tobi-nw/injs-app.git"
    eq2 ignore "$(resolve_target_url "$T/tgt.git")" "$T/tgt.git"
    eq2 ignore "$(github_slug_from_url https://x-access-token@github.com/Tobi-nw/injs-app.git)" "Tobi-nw/injs-app"
    eq2 ignore "$(github_slug_from_url https://github.com/Tobi-nw/injs-app)" "Tobi-nw/injs-app"
  ) && ok "9a resolution target + slug github corrects" || bad "9a resolution target + slug github corrects"
  if github_slug_from_url "https://gitlab.example.org/x/y" >/dev/null 2>&1; then
    bad "9b slug refuse une URL non-GitHub"
  else
    ok "9b slug refuse une URL non-GitHub"
  fi
  # 10 — refus explicite d'un mode inconnu (pas de silent fallback sur fastforward)
  t_ko "10 --mode inconnu = erreur" bash "$0" "${S[@]}" --mode squash

  # 11 — sans token : echec immediate, et aucune trace de credential dans la sortie
  local out11
  out11=$(env -u SYNC_TOKEN -u INJS_APP_SYNC_TOKEN bash "$0" --source-url "$T/src.git" \
    --target "Tobi-nw/injs-app" --source-ref test-src --offline 2>&1 || true)
  if printf '%s' "$out11" | grep -q "Aucun token"; then ok "11a echec explicite sans token"; else bad "11a echec explicite sans token"; fi
  if printf '%s' "$out11" | grep -qiE "ghp_[A-Za-z0-9]|github_pat_|Authorization"; then bad "11b fuite de credential dans la sortie"; else ok "11b aucune fuite de credential dans la sortie"; fi

  # 12 — identite git absente (cas d'un runner GitHub nu) : la sync ne doit pas dependre de la config globale
  ( cd "$T/w"; printf 'app9\n' > backend/app.py; git add -A; git commit -qm "feat: lot D" >/dev/null; git push -qf "$T/src.git" test-src )
  t_ok "12a sync reussit sans identite git ambiante" env -u GIT_AUTHOR_NAME -u GIT_AUTHOR_EMAIL -u GIT_COMMITTER_NAME -u GIT_COMMITTER_EMAIL \
    GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null HOME="$T/vide" \
    bash "$0" "${S[@]}" --source-url "$T/src.git" --offline
  eq "12b auteur du commit de sync = identite forcee" "sync-injs-app (backend-injs)" \
    "$(git --git-dir="$T/tgt.git" log -1 --format=%an main)"
  eq "12c email du commit de sync = identite forcee" "sync-injs@badge-qr-code.pro" \
    "$(git --git-dir="$T/tgt.git" log -1 --format=%ae main)"
  t_ok "12d le push a bien aligne l'arbre cible" bash -c "git --git-dir='$T/tgt.git' cat-file -e main:backend/app.py"

  # 13 — SYNC_EXCLUDE_PATHS : retirer les dechets de build de l'arbre pousse
  ( cd "$T/w"; mkdir -p .pycache dist; printf 'x\n' > .pycache/junk.pyc; printf 'y\n' > dist/bundle.js
    git add -A; git commit -qm "chore: dechets de build" >/dev/null; git push -qf "$T/src.git" test-src )
  t_ok "13a sync avec --exclude" bash "$0" "${S[@]}" --exclude .pycache,dist
  if git --git-dir="$T/tgt.git" ls-tree -r --name-only main | grep -qE '^(\.pycache/|dist/)'; then
    bad "13b dechets exclus de la cible"
  else
    ok "13b dechets exclus de la cible"
  fi
  t_ok "13c le code utile est bien passe" git --git-dir="$T/tgt.git" cat-file -e main:backend/app.py
  t_ok "13d exclure un chemin absent reste un succes" bash "$0" "${S[@]}" --exclude dossier-imaginaire
  t_ko "13e --exclude sans valeur = erreur" bash "$0" "${S[@]}" --exclude

  # 14 — --suggest-keep : releve ce que la cible perdrait, sans ecrire
  ( cd "$T/tw"; printf 'legacy\nsuite\n' > LEGIDE.md; mkdir -p deploy; printf 'unit [Service]\n' > deploy/injs.service; git add -A; git commit -qm "prod: fichiers propres a la cible" >/dev/null; git push -qf "$T/tgt.git" main:main )
  local head_before14 out14
  head_before14=$(git --git-dir="$T/tgt.git" rev-parse main)
  out14=$(bash "$0" "${S[@]}" --suggest-keep 2>&1 || true)
  if printf '%s' "$out14" | grep -q "LEGIDE.md"; then ok "14a perte signalee pour le fichier propre a la cible"; else bad "14a perte signalee pour le fichier propre a la cible"; fi
  if printf '%s' "$out14" | grep -q "deploy/injs.service"; then ok "14b config d'infra classee a preserver"; else bad "14b config d'infra classee a preserver"; fi
  if printf '%s' "$out14" | grep -q 'SYNC_KEEP_PATHS='; then ok "14c liste proposee, prete a coller"; else bad "14c liste proposee, prete a coller"; fi
  eq "14d aucune ecriture pendant l'analyse" "$head_before14" "$(git --git-dir="$T/tgt.git" rev-parse main)"

  log ""
  log "self-test : ${pass} PASS / ${fail} FAIL"
  [ "$fail" -eq 0 ] || die "harnais en échec"
  log "${c_ok}tout est vert${c_off}"
}

# ------------------------------------------------------------
# Arguments
# ------------------------------------------------------------
# Couture de test : `SYNC_LIB_ONLY=1 source scripts/sync-injs-app.sh` expose les
# fonctions (resolve_target_url, github_slug_from_url, ...) sans declencher de sync.
if [ "${SYNC_LIB_ONLY:-0}" = "1" ]; then
  if [ "${BASH_SOURCE[0]:-}" != "${0:-}" ]; then return 0; fi
  exit 0
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --source-ref)    SOURCE_REF="${2:?--source-ref attend une valeur}"; shift 2 ;;
    --source-url)    SOURCE_URL="${2:?--source-url attend une valeur}"; shift 2 ;;
    --target)        TARGET="${2:?--target attend une valeur}"; shift 2 ;;
    --target-branch) TARGET_BRANCH="${2:?--target-branch attend une valeur}"; shift 2 ;;
    --mode)          MODE="${2:?--mode attend fastforward ou mirror}"; shift 2 ;;
    --keep)          KEEP_PATHS="${2:?--keep attend une liste}"; shift 2 ;;
    --exclude)       EXCLUDE_PATHS="${2:?--exclude attend une liste}"; shift 2 ;;
    --dry-run)       DRY_RUN=1; shift ;;
    --offline)       OFFLINE=1; shift ;;
    --self-test)     SELF_TEST=1; shift ;;
    --suggest-keep)  SUGGEST_KEEP=1; DRY_RUN=1; shift ;;
    -h|--help)       usage; exit 0 ;;
    *)               die "option inconnue : $1 (--help pour l'aide)" ;;
  esac
done

SYNC_TOKEN="${SYNC_TOKEN:-${INJS_APP_SYNC_TOKEN:-}}"
export SYNC_TOKEN

case "$MODE" in
  fastforward|mirror) : ;;
  *) die "--mode doit être fastforward ou mirror (reçu : $MODE)" ;;
esac

if [ "$SELF_TEST" = "1" ]; then
  run_self_test
  exit 0
fi

log "============================================================"
log " SYNC INJS-LMD : backend-injs -> ${TARGET}"
log "============================================================"
do_sync
maybe_dispatch
log ""
log "Aval rappelé (exécuté par la cible) : Actions Docker Hub -> images ophirdesire/* -> VPS -> https://injs.badge-qr-code.pro/"
log "Suivi : gh run list -R ${TARGET} -L 5   |   VPS : docker compose ps && curl -sf https://injs.badge-qr-code.pro/api/health"
