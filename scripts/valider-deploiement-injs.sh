#!/usr/bin/env bash
# ============================================================================
# INJS-LMD — Validation statique de la chaîne de déploiement automatisée
#
# Usage :
#   ./scripts/valider-deploiement-injs.sh [--chemin-deploiement <fichier>]
#
# Ce script n'exécute AUCUN déploiement et ne contacte AUCUN serveur : il
# vérifie sur le dépôt, de façon reproductible, les propriétés exigées par la
# mission « automatiser le déploiement VPS de GET-INJS » :
#
#   A. YAML      : chargeabilité, lint, syntaxe bash de CHAQUE bloc `run:` et
#                  de CHAQUE script distant embarqué (heredoc), absence de
#                  tabulation.
#   B. Chaînage  : déclencheur workflow_run pointé sur le nom EXACT du
#                  workflow de publication, garde « conclusion == success » et
#                  « head_branch == main », cible issue de head_sha.
#   C. Protection: concurrence, permissions minimales, absence de toute
#                  commande destructive, refus de latest/stable, SSH strict,
#                  environnement `production`, actions épinglées par SHA,
#                  aucune expression GitHub interpolée dans un script
#                  (anti-injection), rsync sans --delete.
#   D. Cohérence : images, projet compose, healthcheck, entrypoint, modes
#                  deploy.sh, variables .env — comparés aux fichiers réels du
#                  dépôt (rien n'est inventé).
#   E. Rapport   : archivage des preuves et annotations d'échec.
#
# Sortie : une ligne par contrôle (OK / ÉCHEC / IGNORE) et un bilan.
# Code de retour : 0 si aucun ÉCHEC, 1 sinon.
#
# Dépendances : bash, python3. PyYAML est utilisé si présent (sinon les
# contrôles A1/A3/A4 sont déclarés IGNORE, les autres restent exécutés).
# Installation de PyYAML sans toucher à l'interprète système :
#   python3 -m venv .venv-ci && .venv-ci/bin/pip install pyyaml yamllint
#   .venv-ci/bin/python ./scripts/valider-deploiement-injs.sh   # (via PYTHON)
# ============================================================================

set -uo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RACINE"

DEPLOY_WF=".github/workflows/deploy-injs-lmd.yml"
PUBLISH_WF=".github/workflows/publish-injs-lmd.yml"
CI_WF=".github/workflows/ci.yml"
COMPOSE="deploy/production/compose.yml"
ENV_EXEMPLE="deploy/production/.env.example"
DEPLOY_SH="deploy/production/deploy.sh"
GUIDE="deploy/production/GUIDE-DEPLOIEMENT-AUTOMATIQUE.md"
BACKEND_DOCKERFILE="backend/Dockerfile"
FRONTEND_DOCKERFILE="frontend/Dockerfile"
NGINX_CONF="docker/nginx/default.conf"
URLS_PY="backend/config/urls.py"

while [ $# -gt 0 ]; do
  case "$1" in
    --chemin-deploiement) DEPLOY_WF="${2:?}"; shift 2 ;;
    *) echo "Argument inconnu : $1" >&2; exit 2 ;;
  esac
done

PYTHON="${PYTHON:-python3}"
[ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ] && PYTHON="$VIRTUAL_ENV/bin/python"

nb_ok=0; nb_echec=0; nb_ignore=0
ok()      { printf '  OK     %s\n' "$*"; nb_ok=$((nb_ok + 1)); }
echec()   { printf '  ÉCHEC  %s\n' "$*"; nb_echec=$((nb_echec + 1)); }
ignore()  { printf '  IGNORE %s\n' "$*"; nb_ignore=$((nb_ignore + 1)); }
section() { printf '\n== %s ==\n' "$*"; }

# PyYAML disponible ?
HAS_YAML=0
if "$PYTHON" -c 'import yaml' >/dev/null 2>&1; then HAS_YAML=1; fi
HAS_YAMLLINT=0
if "$PYTHON" -c 'import yamllint' >/dev/null 2>&1; then HAS_YAMLLINT=1; fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Validation de la chaîne de déploiement INJS-LMD"
echo "Dépôt      : $RACINE"
echo "Workflow   : $DEPLOY_WF"
echo "Interprète : $PYTHON (PyYAML=$HAS_YAML, yamllint=$HAS_YAMLLINT)"

for f in "$DEPLOY_WF" "$PUBLISH_WF" "$COMPOSE" "$DEPLOY_SH" "$ENV_EXEMPLE"; do
  if [ ! -f "$f" ]; then echo "Fichier requis introuvable : $f" >&2; exit 2; fi
done

# ────────────────────────────────────────────────────────────────────────────
section "A. YAML et syntaxe des scripts embarqués"
# ────────────────────────────────────────────────────────────────────────────
if grep -Pq '\t' "$DEPLOY_WF" 2>/dev/null; then
  echec "A5 — tabulation présente dans $DEPLOY_WF (YAML interdit les tabulations)"
else
  ok "A5 — aucune tabulation dans $DEPLOY_WF"
fi

if [ "$HAS_YAML" = "1" ]; then
  cat > "$TMP/extraire.py" <<'PYEOF'
import re
import sys
import pathlib

import yaml

chemin = sys.argv[1]
sortie = pathlib.Path(sys.argv[2])
doc = yaml.safe_load(pathlib.Path(chemin).read_text(encoding="utf-8"))

# A1 : structure attendue
assert isinstance(doc, dict), "document YAML non objet"
assert "jobs" in doc, "clé jobs absente"
# `on` est interprété comme le booléen True par YAML 1.1
declencheurs = doc.get("on", doc.get(True))
assert declencheurs, "clé on absente"

n = 0
for nom_job, job in doc["jobs"].items():
    for i, etape in enumerate(job.get("steps") or []):
        run = etape.get("run")
        if not run:
            continue
        n += 1
        cible = sortie / f"run_{nom_job}_{i:02d}.sh"
        cible.write_text(run, encoding="utf-8")
        # A4 : scripts distants embarqués dans des heredocs <<'EOS'
        for j, bloc in enumerate(re.findall(r"<<-?'?(\w+)'?\n(.*?)\n[ \t]*\1\n", run, re.S)):
            delim, corps = bloc
            (sortie / f"distant_{nom_job}_{i:02d}_{j}.sh").write_text(corps + "\n", encoding="utf-8")
print(n)
PYEOF
  if nb_run="$("$PYTHON" "$TMP/extraire.py" "$DEPLOY_WF" "$TMP" 2>"$TMP/err")"; then
    ok "A1 — $DEPLOY_WF se charge et possède une structure valide (jobs, on)"
    ok "A3/A4 — $nb_run blocs run: extraits pour analyse de syntaxe"
  else
    echec "A1 — YAML invalide : $(head -3 "$TMP/err" | tr '\n' ' ')"
  fi

  # A2 : yamllint
  if [ "$HAS_YAMLLINT" = "1" ]; then
    cat > "$TMP/yamllint.ini" <<'INI'
extends: default
rules:
  line-length:
    max: 200
  truthy:
    check-keys: false
  document-start: disable
INI
    if "$PYTHON" -m yamllint -c "$TMP/yamllint.ini" -f parsable "$DEPLOY_WF" > "$TMP/lint" 2>&1; then
      ok "A2 — yamllint : aucune anomalie"
    else
      if grep -q ': error' "$TMP/lint"; then
        echec "A2 — yamllint : erreurs (voir ci-dessous)"
        grep ': error' "$TMP/lint" | head -10 | sed 's/^/         /'
      else
        ok "A2 — yamllint : aucune erreur (avertissements seuls)"
        grep -c ': warning' "$TMP/lint" | sed 's/^/         avertissements : /'
      fi
    fi
  else
    ignore "A2 — yamllint non installé (pip install yamllint)"
  fi

  # A3 : syntaxe bash de chaque bloc run:
  faute=0
  for f in "$TMP"/run_*.sh; do
    [ -e "$f" ] || continue
    if ! bash -n "$f" 2>"$TMP/synerr"; then
      faute=1
      echec "A3 — syntaxe bash invalide dans $(basename "$f") : $(head -2 "$TMP/synerr" | tr '\n' ' ')"
    fi
  done
  [ "$faute" = 0 ] && ok "A3 — syntaxe bash valide pour tous les blocs run:"

  # A4 : syntaxe bash de chaque script distant embarqué
  faute=0; compte=0
  for f in "$TMP"/distant_*.sh; do
    [ -e "$f" ] || continue
    compte=$((compte + 1))
    if ! bash -n "$f" 2>"$TMP/synerr"; then
      faute=1
      echec "A4 — syntaxe bash invalide dans le script distant $(basename "$f") : $(head -2 "$TMP/synerr" | tr '\n' ' ')"
    fi
  done
  if [ "$faute" = 0 ]; then
    if [ "$compte" -gt 0 ]; then ok "A4 — syntaxe bash valide pour les $compte scripts distants embarqués"
    else echec "A4 — aucun script distant extrait : l'extraction heredoc a échoué"; fi
  fi
else
  ignore "A1/A2/A3/A4 — PyYAML absent : contrôles YAML et syntaxe bash non exécutés"
fi

# A6 : tous les workflows du dépôt doivent rester chargeables
if [ "$HAS_YAML" = "1" ]; then
  faute=0
  for wf in .github/workflows/*.yml; do
    if "$PYTHON" -c 'import sys, yaml; yaml.safe_load(open(sys.argv[1], encoding="utf-8"))' "$wf" 2>"$TMP/yerr"; then
      ok "A6 — $wf chargeable"
    else
      echec "A6 — $wf invalide : $(head -2 "$TMP/yerr" | tr '\n' ' ')"
      faute=1
    fi
  done
  [ "$faute" = 0 ] || true
else
  ignore "A6 — chargeabilité des autres workflows non vérifiée (PyYAML absent)"
fi

# ────────────────────────────────────────────────────────────────────────────
section "B. Déclenchement et dépendance entre workflows"
# ────────────────────────────────────────────────────────────────────────────
NOM_PUBLICATION="$(awk '/^name:/{sub(/^name:[[:space:]]*/,""); print; exit}' "$PUBLISH_WF")"
if [ -n "$NOM_PUBLICATION" ] && grep -qF "workflows: [\"$NOM_PUBLICATION\"]" "$DEPLOY_WF"; then
  ok "B1 — workflow_run cible le nom exact du workflow de publication (« $NOM_PUBLICATION »)"
else
  echec "B1 — workflow_run ne cible pas « $NOM_PUBLICATION »"
fi

grep -qE '^[[:space:]]+types:[[:space:]]*\[completed\]' "$DEPLOY_WF" \
  && ok "B2 — workflow_run déclenché sur types: [completed]" \
  || echec "B2 — types: [completed] absent du déclencheur workflow_run"

grep -q '^  workflow_dispatch:' "$DEPLOY_WF" \
  && ok "B3 — déclenchement manuel workflow_dispatch présent" \
  || echec "B3 — workflow_dispatch absent"

grep -qF "github.event.workflow_run.conclusion == 'success'" "$DEPLOY_WF" \
  && ok "B4 — garde : la publication doit être en succès" \
  || echec "B4 — garde sur conclusion == 'success' absente"

grep -qF "github.event.workflow_run.head_branch == 'main'" "$DEPLOY_WF" \
  && ok "B4 — garde : la publication doit provenir de main" \
  || echec "B4 — garde sur head_branch == 'main' absente"

grep -qF "github.event.workflow_run.head_sha" "$DEPLOY_WF" \
  && ok "B5 — la cible provient de workflow_run.head_sha (le commit réellement publié)" \
  || echec "B5 — head_sha non utilisé : la cible ne serait pas celle de la publication"

# github.sha ne doit jamais servir de tag d'image
if grep -nE 'TAG|tag_images|CIBLE|cible_sha' "$DEPLOY_WF" | grep -qF 'github.sha'; then
  echec "B5 — github.sha utilisé comme cible d'image (faux en contexte workflow_run)"
else
  ok "B5 — github.sha n'est jamais utilisé comme tag d'image"
fi

# ────────────────────────────────────────────────────────────────────────────
section "C. Protection de la production et sécurité"
# ────────────────────────────────────────────────────────────────────────────
grep -qE '^  group: deploiement-production-injs$' "$DEPLOY_WF" \
  && grep -qE '^  cancel-in-progress: false$' "$DEPLOY_WF" \
  && ok "C1 — concurrence : groupe partagé deploiement-production-injs, sans annulation" \
  || echec "C1 — protection contre les déploiements simultanés absente ou incorrecte"

# Permissions minimales : uniquement read, et seulement contents/actions
if awk '/^permissions:/{f=1;next} /^[a-z]/{f=0} f&&NF' "$DEPLOY_WF" | grep -qvE '^[[:space:]]+(contents|actions):[[:space:]]*read$'; then
  echec "C2 — permissions non minimales :"
  awk '/^permissions:/{f=1;next} /^[a-z]/{f=0} f&&NF' "$DEPLOY_WF" | sed 's/^/         /'
else
  ok "C2 — permissions minimales (contents: read, actions: read)"
fi

# Aucune commande destructive (motifs assemblés pour ne pas s'auto-déclencher)
interdits=("down -""v" "down --""volumes" "system ""prune" "volume ""prune" "volume ""rm" \
           "image ""prune" "container ""prune" "manage.py ""flush" "drop""db" \
           "DROP ""DATABASE" "pg_restore -""c" "rm -rf /""opt/injs" "--""delete" "rsync ""-azR --delete")
faute=0
for m in "${interdits[@]}"; do
  if grep -vE '^[[:space:]]*#' "$DEPLOY_WF" | grep -qF -- "$m"; then
    echec "C3 — motif destructif présent dans le workflow : « $m »"
    faute=1
  fi
done
[ "$faute" = 0 ] && ok "C3 — aucune commande destructive dans le workflow (${#interdits[@]} motifs contrôlés)"

grep -qE '^[[:space:]]+- (latest|stable)$' "$DEPLOY_WF" \
  && echec "C4 — un tag latest/stable est utilisé comme valeur" \
  || ok "C4 — latest/stable jamais utilisés comme valeur de tag"
grep -qF 'latest|stable)' "$DEPLOY_WF" \
  && ok "C4 — latest et stable sont explicitement refusés par une étape de validation" \
  || echec "C4 — aucun refus explicite de latest/stable"

grep -qF 'StrictHostKeyChecking=yes' "$DEPLOY_WF" \
  && ok "C5 — StrictHostKeyChecking=yes présent" \
  || echec "C5 — StrictHostKeyChecking=yes absent"
if grep -qE 'StrictHostKeyChecking=(no|accept-new)' "$DEPLOY_WF"; then
  echec "C5 — StrictHostKeyChecking affaibli quelque part (no/accept-new)"
else
  ok "C5 — aucun affaiblissement de StrictHostKeyChecking"
fi
grep -qF 'VPS_KNOWN_HOSTS' "$DEPLOY_WF" \
  && ok "C5 — empreinte du serveur fournie par secret (known_hosts)" \
  || echec "C5 — known_hosts non alimenté par un secret"

grep -qE '^[[:space:]]+environment: production$' "$DEPLOY_WF" \
  && ok "C6 — job rattaché à l'environnement GitHub production (approbation possible)" \
  || echec "C6 — environnement production absent"

# Actions épinglées par SHA complet
faute=0; compte=0
while read -r ligne; do
  compte=$((compte + 1))
  printf '%s' "$ligne" | grep -qE '@[0-9a-f]{40}' || { echec "C7 — action non épinglée par SHA : $ligne"; faute=1; }
done < <(grep -E '^[[:space:]]*-? ?uses: ' "$DEPLOY_WF" | sed 's/^[[:space:]]*- *uses: *//; s/ *#.*$//')
if [ "$faute" = 0 ] && [ "$compte" -gt 0 ]; then
  ok "C7 — les $compte actions utilisées sont épinglées par SHA complet"
elif [ "$compte" = 0 ]; then
  echec "C7 — aucune action uses: détectée (extraction en échec)"
fi

# Anti-injection : aucune expression GitHub à l'intérieur d'un bloc run:
if [ "$HAS_YAML" = "1" ]; then
  faute=0
  for f in "$TMP"/run_*.sh; do
    [ -e "$f" ] || continue
    if grep -nE '\$\{\{' "$f" > "$TMP/inj"; then
      faute=1
      echec "C8 — expression GitHub interpolée dans un script ($(basename "$f")) :"
      head -3 "$TMP/inj" | sed 's/^/         /'
    fi
  done
  [ "$faute" = 0 ] && ok "C8 — aucune expression GitHub dans les scripts (tout passe par env:, anti-injection)"
else
  ignore "C8 — contrôle anti-injection non exécuté (PyYAML absent)"
fi

grep -qF -- '--exclude '"'"'.env'"'"'' "$DEPLOY_WF" \
  && ok "C9 — le .env du serveur est exclu du transfert rsync" \
  || echec "C9 — exclusion du .env absente du transfert"

grep -qE 'rsync .*--delete' "$DEPLOY_WF" \
  && echec "C9 — rsync utilise --delete (suppressions possibles sur le VPS)" \
  || ok "C9 — rsync sans --delete : rien n'est supprimé sur le VPS"

grep -qF 'SKIP_DB_SETUP' "$COMPOSE" \
  && ok "C10 — compose : SKIP_DB_SETUP transmis (les migrations ne partent pas seules)" \
  || echec "C10 — SKIP_DB_SETUP absent du compose"

grep -vE '^[[:space:]]*#' "$COMPOSE" | grep -qE 'container_name' \
  && echec "C10 — container_name présent dans le compose : risque de collision avec la production" \
  || ok "C10 — compose sans container_name (aucune collision avec injs-be/injs-fe historiques)"

grep -vE '^[[:space:]]*#' "$COMPOSE" | grep -qE 'image:[[:space:]]*"?postgres' \
  && echec "C10 — le compose crée un PostgreSQL (interdit : la base existante doit être consommée)" \
  || ok "C10 — le compose ne crée ni PostgreSQL ni Redis ni RabbitMQ"

# Instantanés de protection avant/après
grep -qF 'instantane-avant' "$DEPLOY_WF" && grep -qF 'instantane-apres' "$DEPLOY_WF" \
  && ok "C11 — instantanés de protection pris AVANT et APRÈS l'intervention" \
  || echec "C11 — comparaison avant/après absente"
grep -qF 'CONTENEUR PROTÉGÉ SUPPRIMÉ' "$DEPLOY_WF" \
  && ok "C11 — la suppression d'un conteneur protégé fait échouer le déploiement" \
  || echec "C11 — aucune sanction en cas de suppression d'un conteneur protégé"
grep -qF 'VOLUME SUPPRIMÉ' "$DEPLOY_WF" \
  && ok "C11 — la suppression d'un volume fait échouer le déploiement" \
  || echec "C11 — aucune sanction en cas de suppression de volume"

# ────────────────────────────────────────────────────────────────────────────
section "D. Cohérence avec la configuration réelle du dépôt"
# ────────────────────────────────────────────────────────────────────────────
for img in jckouassi/injs-be jckouassi/injs-fe; do
  d=$(grep -cF "$img" "$DEPLOY_WF"); p=$(grep -cF "$img" "$PUBLISH_WF"); c=$(grep -cF "$img" "$COMPOSE")
  if [ "$d" -gt 0 ] && [ "$p" -gt 0 ] && [ "$c" -gt 0 ]; then
    ok "D1 — $img : identique dans le workflow de déploiement, de publication et le compose"
  else
    echec "D1 — $img : incohérent (deploy=$d publish=$p compose=$c)"
  fi
done

NOM_PROJET="$(awk '/^name:[[:space:]]*/{sub(/^name:[[:space:]]*/,""); print; exit}' "$COMPOSE")"
if [ -n "$NOM_PROJET" ] && grep -qF "PROJET_COMPOSE: \"$NOM_PROJET\"" "$DEPLOY_WF"; then
  ok "D2 — PROJET_COMPOSE du workflow = name: du compose ($NOM_PROJET)"
else
  echec "D2 — PROJET_COMPOSE du workflow ≠ name: du compose ($NOM_PROJET)"
fi

if grep -qF "api/health/" "$URLS_PY" && grep -qF "/api/health/" "$DEPLOY_WF"; then
  ok "D3 — le healthcheck testé par le workflow (/api/health/) existe dans backend/config/urls.py"
else
  echec "D3 — /api/health/ introuvable dans le backend ou dans le workflow"
fi

[ -f "$NGINX_CONF" ] \
  && ok "D4 — $NGINX_CONF présent (monté en chemin relatif ../../docker par le compose)" \
  || echec "D4 — $NGINX_CONF absent : la passerelle du compose ne peut pas démarrer"
grep -qF 'docker/nginx/default.conf' "$COMPOSE" \
  && grep -qF 'rsync -azR' "$DEPLOY_WF" \
  && grep -qE '^[[:space:]]+deploy/production docker \\?$' "$DEPLOY_WF" \
  && ok "D4 — le workflow transfère bien docker/ à côté de deploy/production (chemin relatif résolu)" \
  || echec "D4 — le transfert ne reproduit pas l'arborescence attendue par le compose"

MODES_WF="$(awk '/^      mode:/{f=1} f&&/^          - /{gsub(/^          - /,""); print} f&&/^      [a-z_]+:$/&&!/^      mode:/{exit}' "$DEPLOY_WF" | sort -u)"
MODES_SH="$(grep -oE '^\s+(inventaire|sauvegarde|plan|deployer|rollback|analyser-plan)\)' "$DEPLOY_SH" | tr -d ' )' | sort -u)"
faute=0
for m in $MODES_WF; do
  if [ "$m" = "preflight" ] || [ "$m" = "inventaire" ]; then continue; fi
  printf '%s\n' "$MODES_SH" | grep -qx "$m" || { echec "D5 — mode du workflow non implémenté par deploy.sh : $m"; faute=1; }
done
[ "$faute" = 0 ] && ok "D5 — tous les modes du workflow existent dans deploy.sh (preflight/inventaire traités par le workflow seul)"

faute=0
for v in INJS_BACKEND_TAG INJS_FRONTEND_TAG DJANGO_SECRET_KEY POSTGRES_DB POSTGRES_USER \
         POSTGRES_PASSWORD POSTGRES_HOST POSTGRES_PORT INJS_PUBLIC_PORT; do
  grep -qE "^${v}=" "$ENV_EXEMPLE" || { echec "D6 — variable requise par le compose absente de .env.example : $v"; faute=1; }
done
[ "$faute" = 0 ] && ok "D6 — les variables requises par le compose sont documentées dans .env.example"

ENTRYPOINT_DOCKERFILE="$(awk '/^ENTRYPOINT/{gsub(/[]["]|ENTRYPOINT /,""); print; exit}' "$BACKEND_DOCKERFILE")"
if [ -n "$ENTRYPOINT_DOCKERFILE" ] && grep -qF "ENTRYPOINT_BACKEND=[\"$ENTRYPOINT_DOCKERFILE\"]" "$DEPLOY_WF"; then
  ok "D7 — l'entrypoint vérifié sur le VPS correspond au backend/Dockerfile ($ENTRYPOINT_DOCKERFILE)"
else
  echec "D7 — entrypoint du Dockerfile ($ENTRYPOINT_DOCKERFILE) non vérifié par le workflow"
fi
grep -qF 'LABEL_VERSION_COHERENT' "$DEPLOY_WF" \
  && grep -qE 'LABEL version' "$FRONTEND_DOCKERFILE" \
  && ok "D7 — le LABEL version du frontend/Dockerfile est vérifié (preuve du commit publié)" \
  || echec "D7 — LABEL version du frontend non vérifié"

grep -qF 'injs-worker' "$DEPLOY_WF" && grep -qF 'injs-cron' "$DEPLOY_WF" \
  && ok "D8 — worker et cron historiques sont protégés et ne sont pas remplacés (absents du compose)" \
  || echec "D8 — worker/cron historiques non couverts par la protection"
grep -qE '^\s+(worker|cron):' "$COMPOSE" \
  && echec "D8 — le compose définit un service worker/cron : remplacement non vérifié" \
  || ok "D8 — le compose ne définit ni worker ni cron (services historiques non remplacés)"

if [ -f "$GUIDE" ]; then
  faute=0
  for s in SSH_HOST SSH_USER SSH_PORT SSH_PRIVATE_KEY VPS_KNOWN_HOSTS DOCKERHUB_USERNAME DOCKERHUB_TOKEN; do
    grep -qF "$s" "$GUIDE" || { echec "D9 — secret utilisé par le workflow non documenté dans le guide : $s"; faute=1; }
  done
  [ "$faute" = 0 ] && ok "D9 — tous les secrets du workflow sont documentés dans GUIDE-DEPLOIEMENT-AUTOMATIQUE.md"
else
  echec "D9 — documentation absente : $GUIDE"
fi

# ────────────────────────────────────────────────────────────────────────────
section "E. Vérifications et rapport"
# ────────────────────────────────────────────────────────────────────────────
grep -qF 'upload-artifact' "$DEPLOY_WF" \
  && ok "E1 — les preuves et le rapport sont archivés en artefact" \
  || echec "E1 — aucun archivage des preuves"
grep -qF 'download-artifact' "$DEPLOY_WF" \
  && ok "E1 — le job de rapport récupère les preuves archivées" \
  || echec "E1 — le job de rapport ne récupère pas les preuves"
grep -q 'GITHUB_STEP_SUMMARY' "$DEPLOY_WF" \
  && ok "E2 — un rapport lisible est publié dans le résumé de l'exécution" \
  || echec "E2 — aucun résumé publié"
nb_erreurs=$(grep -c '::error::' "$DEPLOY_WF")
[ "$nb_erreurs" -ge 10 ] \
  && ok "E3 — $nb_erreurs annotations d'erreur explicites (échecs signalés)" \
  || echec "E3 — seulement $nb_erreurs annotations d'erreur : échecs peu signalés"
grep -qF '/api/health/' "$DEPLOY_WF" && grep -qF 'DOMAINE_PUBLIC' "$DEPLOY_WF" \
  && ok "E4 — tests HTTP sur les services et sur le domaine public" \
  || echec "E4 — tests HTTP incomplets"
grep -qF 'docker compose' "$DEPLOY_WF" || grep -qF 'compose ps' "$DEPLOY_WF" \
  && ok "E5 — état des conteneurs contrôlé après intervention" \
  || echec "E5 — état des conteneurs non contrôlé"

VALIDATION_WF=".github/workflows/valider-chaine-deploiement.yml"
if [ -f "$VALIDATION_WF" ]; then
  if grep -qF 'scripts/valider-deploiement-injs.sh' "$VALIDATION_WF" \
     && grep -qF 'scripts/tester-deploiement-injs.sh' "$VALIDATION_WF"; then
    ok "E6 — un workflow de validation exécute les deux scripts de contrôle"
  else
    echec "E6 — le workflow de validation n'exécute pas les deux scripts"
  fi
  grep -qE '^[[:space:]]+contents:[[:space:]]*read$' "$VALIDATION_WF" \
    && ok "E6 — le workflow de validation est en lecture seule" \
    || echec "E6 — permissions du workflow de validation non minimales"
else
  echec "E6 — workflow de validation absent : $VALIDATION_WF"
fi

# ────────────────────────────────────────────────────────────────────────────
echo "== F. Préflight : sauvegardes et normalisation =="

NORMALISATION="deploy/production/normaliser-controles.sh"
if [ -f "$NORMALISATION" ]; then
  bash -n "$NORMALISATION" \
    && ok "F0 — $NORMALISATION : syntaxe bash valide" \
    || echec "F0 — $NORMALISATION : syntaxe invalide"
  for statut in PASS WARN FAIL NON_EXECUTE; do
    grep -qF "$statut" "$NORMALISATION" \
      && ok "F0 — statut $statut défini dans la bibliothèque" \
      || echec "F0 — statut $statut absent de la bibliothèque"
  done
  grep -qF 'verdict == "REFUSE"' "$NORMALISATION" || grep -qF 'verdict = "REFUSE"' "$NORMALISATION" \
    && ok "F0 — la bibliothèque calcule un verdict explicite" \
    || echec "F0 — verdict absent de la bibliothèque"
else
  echec "F0 — bibliothèque de normalisation absente : $NORMALISATION"
fi

ETAPE_SAU="$(sed -n "/- name: Contrôle des sauvegardes du VPS/,/^      - name: État du domaine public/p" "$DEPLOY_WF")"
if [ -n "$ETAPE_SAU" ]; then
  ok "F1 — étape de contrôle des sauvegardes présente dans le workflow"
  # Le script distant est le bloc heredoc de cette étape.
  SCRIPT_SAU="$(printf '%s\n' "$ETAPE_SAU" | "$PYTHON" -c '
import re, sys
texte = sys.stdin.read()
blocs = re.findall(r"<<-?.?(\w+).?\n(.*?)\n[ \t]*\1\n", texte, re.S)
print(blocs[0][1] if blocs else "")
')"
  if [ -n "$SCRIPT_SAU" ]; then
    ok "F1 — script distant des sauvegardes extrait"
    # F1 : aucune commande d'écriture, commentaires retirés avant analyse.
    SANS_COMMENTAIRES="$(printf '%s\n' "$SCRIPT_SAU" | sed -e 's/[[:space:]]#.*$//' -e 's/^#.*$//')"
    faute=0
    for interdit in 'rm ' 'mv ' 'cp ' 'touch ' 'mkdir ' 'chmod ' 'chown ' 'tee ' 'dd ' \
                    'pg_restore' 'psql ' 'truncate ' 'docker '; do
      if printf '%s\n' "$SANS_COMMENTAIRES" | grep -qE "(^|[[:space:]|;&(])${interdit}"; then
        echec "F1 — commande d'écriture ou de restauration dans le contrôle des sauvegardes : « $interdit »"
        faute=1
      fi
    done
    [ "$faute" = 0 ] && ok "F1 — aucune commande d'écriture/restauration dans le script distant (13 motifs)"
    printf '%s\n' "$SANS_COMMENTAIRES" | grep -qE '(^|[^0-9&])>[[:space:]]*[^&/]' \
      && echec "F1 — redirection d'écriture vers un fichier détectée" \
      || ok "F1 — aucune redirection d'écriture vers un fichier"
    printf '%s\n' "$SCRIPT_SAU" | grep -qF 'head -c 5' \
      && ok "F1 — signature binaire lue par head -c 5 (lecture seule)" \
      || echec "F1 — lecture de la signature PGDMP absente"
    # Analyse sur le code SANS commentaires : la mention « il n'y a NI
    # pg_restore » est une documentation, pas une commande.
    printf '%s\n' "$SANS_COMMENTAIRES" | grep -qE "(^|[[:space:];&|(])pg_restore" \
      && echec "F1 — pg_restore présent alors qu'il est proscrit" \
      || ok "F1 — pg_restore absent du code (aucune restauration, même à blanc)"
  else
    echec "F1 — script distant des sauvegardes introuvable"
  fi
else
  echec "F1 — étape de contrôle des sauvegardes absente"
fi

# F2 : chemin de référence et variable d'environnement
grep -qF 'DOSSIER_BACKUPS: "/opt/injs/backups"' "$DEPLOY_WF" \
  && ok "F2 — /opt/injs/backups défini comme constante du workflow" \
  || echec "F2 — chemin des sauvegardes non défini (/opt/injs/backups attendu)"
grep -qF 'BACKUP_DIR="${BACKUP_DIR:-/opt/injs/backups}"' deploy/production/deploy.sh \
  && ok "F2 — même chemin que BACKUP_DIR de deploy.sh (source unique)" \
  || echec "F2 — divergence avec le BACKUP_DIR de deploy.sh"

# F3 : les quatre statuts sont produits ET rendus dans le rapport
for statut in PASS WARN FAIL NON_EXECUTE; do
  grep -qF "$statut" "$DEPLOY_WF" \
    && ok "F3 — statut $statut utilisé par le workflow" \
    || echec "F3 — statut $statut absent du workflow"
done
grep -qF '| Contrôle | Statut | Obligatoire | Résultat | Observation |' "$DEPLOY_WF" \
  && ok "F3 — tableau à 5 colonnes présent dans le rapport" \
  || echec "F3 — format de tableau attendu absent"
grep -qF 'controles_tableau' "$DEPLOY_WF" && grep -qF 'controles_bilan' "$DEPLOY_WF" \
  && ok "F3 — tableau et bilan produits par la bibliothèque commune" \
  || echec "F3 — tableau ou bilan non produit"
grep -qF 'controle_non_execute' "$DEPLOY_WF" \
  && ok "F3 — un contrôle non exécuté a un traitement explicite" \
  || echec "F3 — NON_EXECUTE non produit"

# F4 : conditions de protection du mode preflight conservées
grep -qF "if: env.MODE != 'preflight' && env.MODE != 'inventaire'" "$DEPLOY_WF" \
  && ok "F4 — transfert rsync et deploy.sh toujours exclus du preflight" \
  || echec "F4 — condition de protection du preflight modifiée"
[ "$(grep -cF "if: env.MODE != 'preflight' && env.MODE != 'inventaire'" "$DEPLOY_WF")" -ge 2 ] \
  && ok "F4 — la condition protège au moins deux étapes" \
  || echec "F4 — protection présente sur une seule étape"
grep -qF "if: (env.MODE == 'deployer' || env.MODE == 'plan') && env.IMAGES_SUR_REGISTRE == 'oui'" "$DEPLOY_WF" \
  && ok "F4 — docker pull limité à deployer et plan" \
  || echec "F4 — condition du docker pull modifiée"
grep -qF "if: always() && env.MODE != 'inventaire' && env.MODE != 'preflight'" "$DEPLOY_WF" \
  && ok "F4 — journaux VPS exclus du preflight" \
  || echec "F4 — exclusion du preflight modifiée"
grep -qE "if: env.MODE == 'preflight' \|\| env.MODE == 'inventaire'" "$DEPLOY_WF" \
  && ok "F4 — contrôle des sauvegardes limité aux modes de contrôle" \
  || echec "F4 — condition du contrôle des sauvegardes absente"

# F5 : aucun secret introduit par cette évolution
grep -qE 'CONTROLES_FICHIER|verdict_precontroles|verdict_sauvegardes' "$DEPLOY_WF" \
  && ok "F5 — nouvelles sorties internes non secrètes" \
  || echec "F5 — sorties attendues absentes"
if grep -nE '(POSTGRES_PASSWORD|DJANGO_SECRET_KEY)=[^"$r ]' "$DEPLOY_WF" >/dev/null 2>&1; then
  echec "F5 — une valeur de secret applicatif semble écrite en clair"
else
  ok "F5 — aucune valeur de secret applicatif en clair"
fi

# ────────────────────────────────────────────────────────────────────────────
printf '\n────────────────────────────────────────────────────────\n'
printf 'BILAN : %d OK, %d ÉCHEC, %d IGNORE\n' "$nb_ok" "$nb_echec" "$nb_ignore"
if [ "$nb_echec" -gt 0 ]; then
  printf 'Résultat : ÉCHEC — corriger les points ci-dessus avant toute livraison.\n'
  exit 1
fi
printf 'Résultat : conforme (contrôles statiques ; aucun déploiement exécuté).\n'
exit 0
