#!/usr/bin/env bash
# ============================================================================
# INJS-LMD — Tests FONCTIONNELS de la chaîne de déploiement automatisée
#
# Usage :
#   PYTHON=.venv-ci/bin/python ./scripts/tester-deploiement-injs.sh
#
# Complément de scripts/valider-deploiement-injs.sh (contrôles statiques).
# Ce script EXÉCUTE réellement la logique du workflow, sans jamais contacter
# le VPS ni Docker Hub :
#
#   * les blocs `run:` et les scripts distants embarqués sont extraits du
#     YAML du workflow, puis exécutés dans un environnement simulé
#     (GITHUB_OUTPUT/GITHUB_STEP_SUMMARY réels, `vps-ssh` simulé) ;
#   * `deploy/production/deploy.sh` est exécuté pour de vrai sur ses modes
#     qui n'exigent ni Docker ni PostgreSQL : garde-fou anti-commandes
#     destructrices, validation du tag, analyse du plan de migrations.
#
# Ce qui N'EST PAS testé ici (et ne peut pas l'être hors production) :
#   la connexion SSH réelle, les appels `docker`/`docker compose` sur le VPS,
#   la résolution des digests auprès du registre Docker Hub, les requêtes
#   HTTP réelles et l'exécution complète de `deploy.sh deployer`.
#
# Dépendances : bash, python3, PyYAML (pour l'extraction), jq (pour T5).
# Code de retour : 0 si tous les tests passent, 1 sinon.
# ============================================================================

set -uo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RACINE"

DEPLOY_WF=".github/workflows/deploy-injs-lmd.yml"
DEPLOY_SH="deploy/production/deploy.sh"
COMPOSE="deploy/production/compose.yml"

PYTHON="${PYTHON:-python3}"
[ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ] && PYTHON="$VIRTUAL_ENV/bin/python"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/pas" "$TMP/bin" "$TMP/travail"

if ! "$PYTHON" -c 'import yaml' >/dev/null 2>&1; then
  echo "PyYAML est requis pour extraire les étapes du workflow." >&2
  echo "  python3 -m venv .venv-ci && .venv-ci/bin/pip install pyyaml" >&2
  echo "  PYTHON=.venv-ci/bin/python $0" >&2
  exit 2
fi

nb_reussis=0; nb_echoues=0
reussi() { printf '  PASS   %s\n' "$*"; nb_reussis=$((nb_reussis + 1)); }
echoue() { printf '  FAIL   %s\n' "$*"; nb_echoues=$((nb_echoues + 1)); }
section() { printf '\n== %s ==\n' "$*"; }

# ────────────────────────────────────────────────────────────────────────────
# Extraction des étapes réelles du workflow
# ────────────────────────────────────────────────────────────────────────────
"$PYTHON" - "$DEPLOY_WF" "$TMP" <<'PYEOF'
import re
import sys
import unicodedata
import pathlib

import yaml

chemin, tmp = sys.argv[1], pathlib.Path(sys.argv[2])
doc = yaml.safe_load(pathlib.Path(chemin).read_text(encoding="utf-8"))


def slug(texte):
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "_", texte).strip("_").lower()[:48]


manifeste = []
n = 0
for nom_job, job in doc["jobs"].items():
    for i, etape in enumerate(job.get("steps") or []):
        run = etape.get("run")
        nom = etape.get("name") or etape.get("uses") or f"etape{i}"
        if not run:
            continue
        n += 1
        base = f"{n:02d}_{slug(nom_job)}_{slug(nom)}"
        (tmp / "pas" / f"{base}.sh").write_text(run, encoding="utf-8")
        manifeste.append(f"{n:02d}\t{nom_job}\t{nom}\t{base}.sh")
        for k, (delim, corps) in enumerate(
            re.findall(r"<<-?'?(\w+)'?\n(.*?)\n[ \t]*\1\n", run, re.S)
        ):
            distant = f"{base}.distant{k}.sh"
            (tmp / "pas" / distant).write_text(corps + "\n", encoding="utf-8")
            manifeste.append(f"{n:02d}\t{nom_job}\t{nom}\t{distant}")
(tmp / "manifeste.tsv").write_text("\n".join(manifeste) + "\n", encoding="utf-8")
print(f"{n} étapes run: extraites, {len(manifeste)} fichiers")
PYEOF
[ -s "$TMP/manifeste.tsv" ] || { echo "Extraction des étapes en échec" >&2; exit 2; }

fichier_etape() { # motif (en minuscules, tel que produit par le slug) -> chemin
  grep -iF "$1" "$TMP/manifeste.tsv" | head -1 | cut -f4 | sed "s|^|$TMP/pas/|"
}

# Environnement GitHub Actions simulé
export GITHUB_OUTPUT="$TMP/github_output"
export GITHUB_STEP_SUMMARY="$TMP/github_summary"
export GITHUB_ENV="$TMP/github_env"
export GITHUB_PATH="$TMP/github_path"
export RUNNER_TEMP="$TMP/runner_temp"
export GITHUB_REPOSITORY="JCKOUASSI/backend-injs2026"
export GITHUB_RUN_ID="0000000000"
export GITHUB_SERVER_URL="https://github.com"
export GITHUB_EVENT_NAME="workflow_dispatch"
mkdir -p "$RUNNER_TEMP"
export PATH="$TMP/bin:$PATH"

# `vps-ssh` simulé : deux comportements pilotés par SIM_VPS.
cat > "$TMP/bin/vps-ssh" <<'EOS'
#!/usr/bin/env bash
set -uo pipefail
entree="$(cat 2>/dev/null || true)"
case "${SIM_VPS:-silencieux}" in
  instantane_apres) printf '%s\n' "${SIM_APRES:?SIM_APRES absent}" ;;
  silencieux) [ -n "$entree" ] || true; exit "${SIM_CODE:-0}" ;;
  *) printf '%s\n' "$entree" ;;
esac
EOS
chmod +x "$TMP/bin/vps-ssh"

# Constantes du workflow, recopiées pour les tests (vérifiées identiques plus bas)
PROJET_COMPOSE="injs-lmd-production"
RESEAU_PROJET="injs-lmd-production"
SHA_VALIDE="767dabf0faf317c333d280248ebf93fe4ad66ea6"

section "T0 — fidélité de l'environnement de test au workflow réel"
grep -qF "PROJET_COMPOSE: \"$PROJET_COMPOSE\"" "$DEPLOY_WF" \
  && reussi "T0.1 PROJET_COMPOSE de test = valeur du workflow" \
  || echoue "T0.1 PROJET_COMPOSE de test différent du workflow"
grep -qF "RESEAU_PROJET: \"$RESEAU_PROJET\"" "$DEPLOY_WF" \
  && reussi "T0.2 RESEAU_PROJET de test = valeur du workflow" \
  || echoue "T0.2 RESEAU_PROJET de test différent du workflow"
grep -qF "$SHA_VALIDE" "$TMP/manifeste.tsv" 2>/dev/null
nb_etapes=$(wc -l < "$TMP/manifeste.tsv")
[ "$nb_etapes" -gt 20 ] && reussi "T0.3 $nb_etapes scripts extraits du workflow" \
  || echoue "T0.3 extraction incomplète ($nb_etapes fichiers)"

# ────────────────────────────────────────────────────────────────────────────
section "T1 — détermination du mode et de la cible"
# ────────────────────────────────────────────────────────────────────────────
ETAPE_CIBLE="$(fichier_etape "determiner_le_mode_et_la_cible_demandee")"
if [ ! -f "$ETAPE_CIBLE" ]; then
  echoue "T1 étape « Déterminer le mode et la cible demandée » introuvable"
else
  sortir_cible() { grep -E "^$1=" "$GITHUB_OUTPUT" | tail -1 | cut -d= -f2-; }
  # Déclenchement manuel : mode, tag, confirmation.
  contexte_dispatch() {
    : > "$GITHUB_OUTPUT"; : > "$GITHUB_STEP_SUMMARY"
    EVENEMENT=workflow_dispatch MODE_DEMANDE="$1" TAG_DEMANDE="$2" CONFIRMATION="$3" \
      PUBLICATION_NOM= PUBLICATION_CONCLUSION= PUBLICATION_BRANCHE= PUBLICATION_SHA= \
      PUBLICATION_ID_EVENEMENT= PUBLICATION_URL_EVENEMENT= \
      DEPLOIEMENT_AUTO= CONFIRMATION_AUTO= \
      bash "$ETAPE_CIBLE" >"$TMP/t1.log" 2>&1
  }
  # Déclenchement automatique : variables d'opt-in en arguments.
  contexte_run() {
    : > "$GITHUB_OUTPUT"; : > "$GITHUB_STEP_SUMMARY"
    EVENEMENT=workflow_run MODE_DEMANDE= TAG_DEMANDE= CONFIRMATION= \
      PUBLICATION_NOM="Publication images INJS-LMD" PUBLICATION_CONCLUSION=success \
      PUBLICATION_BRANCHE=main PUBLICATION_SHA="$SHA_VALIDE" \
      PUBLICATION_ID_EVENEMENT=42407161982 PUBLICATION_URL_EVENEMENT=https://github.com/x \
      DEPLOIEMENT_AUTO="${1:-}" CONFIRMATION_AUTO="${2:-}" \
      bash "$ETAPE_CIBLE" >"$TMP/t1.log" 2>&1
  }

  contexte_dispatch inventaire "" ""
  [ "$(sortir_cible mode)" = "inventaire" ] \
    && reussi "T1.1 dispatch mode inventaire → mode=inventaire" \
    || echoue "T1.1 attendu inventaire, obtenu « $(sortir_cible mode) »"

  contexte_dispatch deployer "$SHA_VALIDE" DEPLOYER
  if [ "$(sortir_cible mode)" = "deployer" ] && [ "$(sortir_cible cible_sha)" = "$SHA_VALIDE" ]; then
    reussi "T1.2 dispatch deployer + SHA + DEPLOYER → cible = SHA demandé"
  else
    echoue "T1.2 obtenu mode=$(sortir_cible mode) sha=$(sortir_cible cible_sha)"
  fi

  contexte_dispatch deployer "$SHA_VALIDE" ""
  if [ $? -ne 0 ] && grep -qF 'Confirmation absente' "$TMP/t1.log"; then
    reussi "T1.3 deployer sans confirmation DEPLOYER → refusé"
  else
    echoue "T1.3 deployer sans confirmation accepté (attendu : refus)"
  fi

  contexte_dispatch deployer "" DEPLOYER
  if [ $? -ne 0 ] && grep -qF 'sans tag' "$TMP/t1.log"; then
    reussi "T1.4 deployer sans tag → refusé (aucune cible devinée)"
  else
    echoue "T1.4 deployer sans tag accepté (attendu : refus)"
  fi

  contexte_run "" ""
  if [ "$(sortir_cible mode)" = "preflight" ] && [ "$(sortir_cible cible_sha)" = "$SHA_VALIDE" ]; then
    reussi "T1.5 workflow_run non armé → mode=preflight, cible=head_sha de la publication"
  else
    echoue "T1.5 obtenu mode=$(sortir_cible mode) sha=$(sortir_cible cible_sha)"
  fi

  contexte_run deployer DEPLOYER
  [ "$(sortir_cible mode)" = "deployer" ] \
    && reussi "T1.6 workflow_run + double opt-in → mode=deployer" \
    || echoue "T1.6 attendu deployer, obtenu « $(sortir_cible mode) »"

  contexte_run deployer ""
  [ "$(sortir_cible mode)" = "preflight" ] \
    && reussi "T1.7 opt-in incomplet (confirmation absente) → preflight" \
    || echoue "T1.7 attendu preflight, obtenu « $(sortir_cible mode) »"

  contexte_run "" DEPLOYER
  [ "$(sortir_cible mode)" = "preflight" ] \
    && reussi "T1.8 opt-in incomplet (variable de mode absente) → preflight" \
    || echoue "T1.8 attendu preflight, obtenu « $(sortir_cible mode) »"

  contexte_run oui DEPLOYER
  [ "$(sortir_cible mode)" = "preflight" ] \
    && reussi "T1.9 valeur INJS_DEPLOIEMENT_AUTO non reconnue → preflight" \
    || echoue "T1.9 attendu preflight, obtenu « $(sortir_cible mode) »"
fi

# ────────────────────────────────────────────────────────────────────────────
section "T2 — validation du tag (immuable, jamais latest ni stable)"
# ────────────────────────────────────────────────────────────────────────────
ETAPE_TAG="$(fichier_etape "valider_le_tag")"
if [ ! -f "$ETAPE_TAG" ]; then
  echoue "T2 étape « Valider le tag » introuvable"
else
  tester_tag() { # tag code_attendu(0|1) libelle
    : > "$GITHUB_OUTPUT"
    MODE=deployer TAG="$1" bash "$ETAPE_TAG" >"$TMP/t2.log" 2>&1
    obtenu=$?
    if [ "$obtenu" = "$2" ]; then reussi "T2 $3 (tag « ${1:-<vide>} » → code $obtenu)"
    else echoue "T2 $3 : code attendu $2, obtenu $obtenu"; fi
  }
  tester_tag latest 1 "refus de latest"
  tester_tag stable 1 "refus de stable"
  tester_tag "" 0 "tag vide ignoré hors deployer"
  tester_tag "$SHA_VALIDE" 0 "SHA Git complet accepté"
  tester_tag "v1.2.3" 0 "version sémantique acceptée"
  tester_tag "1.2.3-rc1" 0 "version avec suffixe acceptée"
  tester_tag "mon-tag" 1 "tag arbitraire refusé"
  tester_tag "abc123" 1 "SHA tronqué refusé"
  grep -qF 'latest|stable)' "$ETAPE_TAG" \
    && reussi "T2.9 le refus porte bien sur les deux pointeurs mutables" \
    || echoue "T2.9 motif de refus latest/stable introuvable"
fi

# ────────────────────────────────────────────────────────────────────────────
section "T3 — protection de la production (comparaison des instantanés)"
# ────────────────────────────────────────────────────────────────────────────
ETAPE_PRESERVATION="$(fichier_etape "instantane_de_protection_apres")"
if [ ! -f "$ETAPE_PRESERVATION" ]; then
  echoue "T3 étape « Instantané de protection APRÈS » introuvable"
else
  : > "$RUNNER_TEMP/distant-instantane.sh"
  AVANT_REF="$TMP/avant-reference.txt"
  cat > "$AVANT_REF" <<'EOS'
# instantane 2026-11-07T20:00:00Z hote=vps
## conteneurs
injs-be|jckouassi/injs-be:ancien|2026-01-01T00:00:00Z|aucun
injs-cron|jckouassi/injs-be:ancien|2026-01-01T00:00:00Z|aucun
injs-db|postgres:15|2026-01-01T00:00:00Z|aucun
injs-fe|jckouassi/injs-fe:ancien|2026-01-01T00:00:00Z|aucun
injs-worker|jckouassi/injs-be:ancien|2026-01-01T00:00:00Z|aucun
npm|jc21/nginx-proxy-manager:latest|2026-01-01T00:00:00Z|aucun
rabbitmq|rabbitmq:3-management|2026-01-01T00:00:00Z|aucun
redis|redis:7-alpine|2026-01-01T00:00:00Z|aucun
## volumes
injs-lmd-media
injs-lmd-staticfiles
postgres_data
redis_data
## reseaux
bridge
host
injs-net
injs-lmd-production
## images_injs
jckouassi/injs-be:ancien|aaa
EOS

  # Ajoute un conteneur DANS la section « ## conteneurs » puis la re-trie,
  # comme le fait le script distant (tri par nom dans chaque section). Une
  # ligne simplement ajoutée en fin de fichier tomberait dans « ## images_injs »
  # et ne serait pas comparée.
  ajouter_conteneur() { # <fichier> <ligne nom|image|création|projet>
    python3 - "$1" "$2" <<'PYX'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
t = p.read_text(encoding="utf-8").splitlines()
i = t.index("## conteneurs")
j = t.index("## volumes")
t[i + 1:j] = sorted(t[i + 1:j] + [sys.argv[2]])
p.write_text("\n".join(t) + "\n", encoding="utf-8")
PYX
  }

  preparer() { # <fichier apres> ; prépare le répertoire de travail
    rm -rf "$TMP/travail"; mkdir -p "$TMP/travail/evidence"
    cp "$AVANT_REF" "$TMP/travail/evidence/instantane-avant.txt"
    cp "$1" "$TMP/travail/apres.txt"
  }
  # Le verdict est écrit dans GITHUB_OUTPUT (comme dans une vraie exécution
  # GitHub) ; les messages ::error:: / ::warning:: vont sur la sortie standard.
  lancer_preservation() { # mode -> code
    : > "$GITHUB_OUTPUT"
    ( cd "$TMP/travail" && SIM_VPS=instantane_apres SIM_APRES="$(cat apres.txt)" \
      MODE="$1" PROJET_COMPOSE="$PROJET_COMPOSE" RESEAU_PROJET="$RESEAU_PROJET" \
      bash "$ETAPE_PRESERVATION" ) >"$TMP/t3.log" 2>&1
    return $?
  }
  verdict() { grep -E '^verdict=' "$GITHUB_OUTPUT" | tail -1 | cut -d= -f2-; }

  # 3.1 rien ne change
  preparer "$AVANT_REF"; lancer_preservation deployer
  if [ $? -eq 0 ] && [ "$(verdict)" = "conforme" ]; then
    reussi "T3.1 instantanés identiques → conforme"
  else
    echoue "T3.1 instantanés identiques rejetés (verdict « $(verdict) »)"
  fi

  # 3.2 la stack candidate évolue (déploiement normal)
  cp "$AVANT_REF" "$TMP/apres-candidat.txt"
  ajouter_conteneur "$TMP/apres-candidat.txt" \
    "injs-lmd-production-backend-1|jckouassi/injs-be:$SHA_VALIDE|2026-11-07T21:00:00Z|$PROJET_COMPOSE"
  ajouter_conteneur "$TMP/apres-candidat.txt" \
    "injs-lmd-production-frontend-1|jckouassi/injs-fe:$SHA_VALIDE|2026-11-07T21:00:00Z|$PROJET_COMPOSE"
  preparer "$TMP/apres-candidat.txt"; lancer_preservation deployer
  if [ $? -eq 0 ] && [ "$(verdict)" = "conforme" ] \
     && grep -qF '+ injs-lmd-production-backend-1' "$TMP/t3.log"; then
    reussi "T3.2 apparition des conteneurs candidats → conforme et documentée"
  else
    echoue "T3.2 évolution normale de la stack candidate rejetée (verdict « $(verdict) »)"
  fi

  # 3.3 un conteneur historique disparaît
  grep -v '^injs-worker|' "$AVANT_REF" > "$TMP/apres-sans-worker.txt"
  preparer "$TMP/apres-sans-worker.txt"; lancer_preservation deployer
  if [ $? -ne 0 ] && grep -qF 'CONTENEUR PROTÉGÉ SUPPRIMÉ' "$TMP/t3.log" \
     && printf '%s' "$(verdict)" | grep -qF 'VIOLATION'; then
    reussi "T3.3 disparition de injs-worker → ÉCHEC bloquant"
  else
    echoue "T3.3 disparition d'un conteneur protégé non sanctionnée"
  fi

  # 3.4 PostgreSQL recréé (même nom, image et date de création différentes)
  python3 - "$AVANT_REF" "$TMP/apres-db-recre.txt" <<'PY'
import pathlib, sys
src = pathlib.Path(sys.argv[1]).read_text().splitlines()
out = []
for ligne in src:
    if ligne.startswith('injs-db|'):
        out.append('injs-db|postgres:16|2026-11-07T22:00:00Z|aucun')
    else:
        out.append(ligne)
pathlib.Path(sys.argv[2]).write_text('\n'.join(out) + '\n')
PY
  preparer "$TMP/apres-db-recre.txt"; lancer_preservation deployer
  if [ $? -ne 0 ] && grep -qF 'CONTENEUR PROTÉGÉ MODIFIÉ' "$TMP/t3.log"; then
    reussi "T3.4 injs-db recréé (image postgres:16) → ÉCHEC bloquant"
  else
    echoue "T3.4 recréation de PostgreSQL non sanctionnée"
  fi

  # 3.5 un volume disparaît
  grep -v '^postgres_data$' "$AVANT_REF" > "$TMP/apres-sans-volume.txt"
  preparer "$TMP/apres-sans-volume.txt"; lancer_preservation deployer
  if [ $? -ne 0 ] && grep -qF 'VOLUME SUPPRIMÉ' "$TMP/t3.log"; then
    reussi "T3.5 disparition du volume postgres_data → ÉCHEC bloquant"
  else
    echoue "T3.5 suppression de volume non sanctionnée"
  fi

  # 3.6 le réseau partagé injs-net disparaît
  grep -v '^injs-net$' "$AVANT_REF" > "$TMP/apres-sans-reseau.txt"
  preparer "$TMP/apres-sans-reseau.txt"; lancer_preservation deployer
  if [ $? -ne 0 ] && grep -qF 'RÉSEAU SUPPRIMÉ' "$TMP/t3.log"; then
    reussi "T3.6 disparition du réseau partagé injs-net → ÉCHEC bloquant"
  else
    echoue "T3.6 suppression du réseau partagé non sanctionnée"
  fi

  # 3.7 rollback : le réseau du projet candidat est retiré, le reste intact
  grep -v "^$RESEAU_PROJET$" "$AVANT_REF" > "$TMP/apres-rollback.txt"
  preparer "$TMP/apres-rollback.txt"; lancer_preservation rollback
  if [ $? -eq 0 ] && [ "$(verdict)" = "conforme" ]; then
    reussi "T3.7 retrait du seul réseau du projet candidat (rollback) → conforme"
  else
    echoue "T3.7 retrait légitime du réseau candidat sanctionné à tort"
  fi

  # 3.8 preflight : différence non protégée → avertissement, pas échec
  cp "$AVANT_REF" "$TMP/apres-bruit.txt"
  ajouter_conteneur "$TMP/apres-bruit.txt" "conteneur-tiers|autre/image:1|2026-11-07T23:00:00Z|aucun"
  preparer "$TMP/apres-bruit.txt"; lancer_preservation preflight
  if [ $? -eq 0 ] && grep -qF 'Différence constatée' "$TMP/t3.log"; then
    reussi "T3.8 preflight + activité tierce → avertissement, non bloquant"
  else
    echoue "T3.8 comportement preflight inattendu : $(tail -3 "$TMP/t3.log" | tr '\n' ' ')"
  fi

  # 3.9 preflight : instantanés identiques → preuve d'absence d'écriture
  preparer "$AVANT_REF"; lancer_preservation preflight
  if [ $? -eq 0 ] && grep -qF 'aucune écriture sur le VPS' "$TMP/t3.log"; then
    reussi "T3.9 preflight identique → preuve d'absence d'écriture produite"
  else
    echoue "T3.9 preuve d'absence d'écriture non produite"
  fi
fi

# ────────────────────────────────────────────────────────────────────────────
section "T4 — lecture du .env serveur (commentaires en ligne, guillemets)"
# ────────────────────────────────────────────────────────────────────────────
DISTANT_PRECONTROLES="$(fichier_etape "pre_controles_du_vps_lecture_seule.distant0")"
if [ ! -f "$DISTANT_PRECONTROLES" ]; then
  echoue "T4 script distant des pré-contrôles introuvable"
else
  # La fonction réelle `lire()` est extraite du script distant du workflow.
  sed -n '/^lire() {/,/^}/p' "$DISTANT_PRECONTROLES" > "$TMP/fonction-lire.sh"
  if [ -s "$TMP/fonction-lire.sh" ]; then
    reussi "T4.0 fonction lire() extraite du script distant réel ($(wc -l < "$TMP/fonction-lire.sh") lignes)"
    cat > "$TMP/exemple.env" <<'EOS'
INJS_BACKEND_TAG=a1b2c3d4  # requis : ex. SHA complet
INJS_FRONTEND_TAG=
POSTGRES_PASSWORD="mot#de#passe"  # commentaire
POSTGRES_HOST=   # valeur à confirmer
INJS_PUBLIC_PORT=8080
DJANGO_SECRET_KEY='cle#secrete'
SKIP_DB_SETUP=true
#POSTGRES_DB=commente
EOS
    verif_lire() { # variable attendu libelle
      obtenu="$(bash -c '. "$1"; lire "$2" "$3"' _ "$TMP/fonction-lire.sh" "$TMP/exemple.env" "$1")"
      if [ "$obtenu" = "$2" ]; then reussi "T4 $3"
      else echoue "T4 $3 : attendu « $2 », obtenu « $obtenu »"; fi
    }
    verif_lire INJS_BACKEND_TAG "a1b2c3d4" "4.1 commentaire en ligne retiré d'une valeur nue"
    verif_lire INJS_FRONTEND_TAG "" "4.2 valeur vide (commentaire seul) → vide"
    verif_lire POSTGRES_PASSWORD "mot#de#passe" "4.3 guillemets retirés, # intérieur conservé, commentaire final ignoré"
    verif_lire POSTGRES_HOST "" "4.4 variable commentée sans valeur → vide"
    verif_lire INJS_PUBLIC_PORT "8080" "4.5 valeur simple lue correctement"
    verif_lire DJANGO_SECRET_KEY "cle#secrete" "4.6 guillemets simples retirés, # intérieur conservé"
    verif_lire POSTGRES_DB "" "4.7 ligne commentée ignorée"
  else
    echoue "T4.0 fonction lire() introuvable dans le script distant"
  fi
fi

# Même contrôle sur la fonction réelle de deploy.sh (utilisée par rollback)
sed -n '/^lire_var_env() {/,/^}/p' "$DEPLOY_SH" > "$TMP/fonction-lire-var.sh"
if [ -s "$TMP/fonction-lire-var.sh" ]; then
  obtenu="$(bash -c '. "$1"; lire_var_env "$2" INJS_BACKEND_TAG' _ "$TMP/fonction-lire-var.sh" "$TMP/exemple.env" 2>/dev/null)"
  if [ "$obtenu" = "a1b2c3d4" ]; then
    reussi "T4.8 deploy.sh lire_var_env retire le commentaire en ligne (rollback non bloqué à tort)"
  else
    echoue "T4.8 deploy.sh lire_var_env : attendu « a1b2c3d4 », obtenu « $obtenu »"
  fi
  obtenu="$(bash -c '. "$1"; lire_var_env "$2" POSTGRES_PASSWORD' _ "$TMP/fonction-lire-var.sh" "$TMP/exemple.env" 2>/dev/null)"
  [ "$obtenu" = "mot#de#passe" ] \
    && reussi "T4.9 deploy.sh lire_var_env conserve un # intérieur entre guillemets" \
    || echoue "T4.9 deploy.sh lire_var_env : obtenu « $obtenu »"
else
  echoue "T4.8 fonction lire_var_env introuvable dans deploy.sh"
fi

# ────────────────────────────────────────────────────────────────────────────
section "T5 — sélection du digest linux/amd64 dans un index de manifestes"
# ────────────────────────────────────────────────────────────────────────────
FILTRE_JQ='[.manifests[]? | select(.platform.os=="linux" and .platform.architecture=="amd64") | .digest] | first // empty'
if grep -qF "$FILTRE_JQ" "$DEPLOY_WF"; then
  reussi "T5.0 le filtre jq testé est bien celui du workflow"
  if command -v jq >/dev/null 2>&1; then
    cat > "$TMP/index.json" <<'EOS'
{"mediaType":"application/vnd.oci.image.index.v1+json","manifests":[
 {"digest":"sha256:aaaa","platform":{"os":"linux","architecture":"arm64"}},
 {"digest":"sha256:bbbb","platform":{"os":"linux","architecture":"amd64"}},
 {"digest":"sha256:cccc","platform":{"os":"unknown","architecture":"unknown"},
  "annotations":{"vnd.docker.reference.type":"attestation-manifest"}}]}
EOS
    cat > "$TMP/manifeste-unique.json" <<'EOS'
{"mediaType":"application/vnd.docker.distribution.manifest.v2+json",
 "config":{"digest":"sha256:dddd"},"layers":[]}
EOS
    [ "$(jq -r "$FILTRE_JQ" "$TMP/index.json")" = "sha256:bbbb" ] \
      && reussi "T5.1 index multi-plateformes → digest amd64 sélectionné (attestation ignorée)" \
      || echoue "T5.1 sélection amd64 incorrecte : $(jq -r "$FILTRE_JQ" "$TMP/index.json")"
    [ -z "$(jq -r "$FILTRE_JQ" "$TMP/manifeste-unique.json")" ] \
      && reussi "T5.2 manifeste unique (pas de liste) → aucun digest enfant, digest du tag utilisé" \
      || echoue "T5.2 manifeste unique mal traité"
    echo '{"manifests":[{"digest":"sha256:eeee","platform":{"os":"linux","architecture":"arm64"}}]}' > "$TMP/sans-amd64.json"
    [ -z "$(jq -r "$FILTRE_JQ" "$TMP/sans-amd64.json")" ] \
      && reussi "T5.3 index sans amd64 → résultat vide (jamais de plateforme devinée)" \
      || echoue "T5.3 index sans amd64 mal traité"
  else
    echoue "T5.1 jq absent : filtres non exécutés"
  fi
else
  echoue "T5.0 filtre jq du workflow introuvable : test non représentatif"
fi

# ────────────────────────────────────────────────────────────────────────────
section "T6 — extraction des résultats depuis les fichiers de preuves"
# ────────────────────────────────────────────────────────────────────────────
PROGRAMME_AWK='awk -F= -v k="$1" '"'"'$1==k{v=$2} END{printf "%s", v}'"'"''
if grep -qF '$1==k{v=$2} END{printf "%s", v}' "$DEPLOY_WF"; then
  reussi "T6.0 l'extracteur awk testé est bien celui du workflow"
  cat > "$TMP/controles.txt" <<'EOS'
PORT_VALIDATION=8080
MODE_CONTROLE=deployer
SERVICE_backend=etat:running|sante:healthy|image:jckouassi/injs-be:abc|demarre:2026-11-07T21:00:00Z|redemarrages:0
HTTP_api=200
CORPS_api={"status":"ok","database":"ok","timestamp":"2026-11-07T21:00:00Z"}
EMPREINTE_api=1111
HTTP_frontend=200
HTTP_api=000
EOS
  valeur() { awk -F= -v k="$1" '$1==k{v=$2} END{printf "%s", v}' "$TMP/controles.txt"; }
  [ "$(valeur PORT_VALIDATION)" = "8080" ] && reussi "T6.1 lecture d'une valeur simple" \
    || echoue "T6.1 obtenu « $(valeur PORT_VALIDATION) »"
  [ "$(valeur HTTP_api)" = "000" ] && reussi "T6.2 en cas de doublon, la dernière occurrence gagne (comportement attendu du workflow)" \
    || echoue "T6.2 obtenu « $(valeur HTTP_api) »"
  [ "$(valeur INCONNU)" = "" ] && reussi "T6.3 clé absente → valeur vide (jamais de valeur inventée)" \
    || echoue "T6.3 obtenu « $(valeur INCONNU) »"
  case "$(valeur CORPS_api)" in *'"status":"ok"'*) reussi "T6.4 corps JSON lu sans troncature sur le premier =" ;;
    *) echoue "T6.4 obtenu « $(valeur CORPS_api) »" ;;
  esac
  # Expression régulière d'extraction de l'état de santé (celle du workflow)
  REGEX_SANTE='SERVICE_backend=etat:[a-z]+\|sante:[a-z-]+'
  if grep -qF "$REGEX_SANTE" "$DEPLOY_WF"; then
    reussi "T6.5 la regex de santé testée est bien celle du workflow"
    sante="$(grep -oE "$REGEX_SANTE" "$TMP/controles.txt" | head -1 || true)"
    if [ "$sante" = 'SERVICE_backend=etat:running|sante:healthy' ]; then
      reussi "T6.6 état + santé du backend extraits correctement"
    else
      echoue "T6.6 extraction de santé : obtenu « $sante »"
    fi
    printf 'SERVICE_backend=etat:running|sante:sans-healthcheck|image:x\n' > "$TMP/sante-sans.txt"
    sante="$(grep -oE "$REGEX_SANTE" "$TMP/sante-sans.txt" | head -1 || true)"
    if [ "$sante" = 'SERVICE_backend=etat:running|sante:sans-healthcheck' ]; then
      reussi "T6.7 conteneur sans healthcheck reconnu (jamais présumé sain)"
    else
      echoue "T6.7 obtenu « $sante »"
    fi
  else
    echoue "T6.5 regex de santé du workflow introuvable"
  fi
else
  echoue "T6.0 extracteur awk du workflow introuvable"
fi

# ────────────────────────────────────────────────────────────────────────────
section "T7 — génération du rapport de déploiement"
# ────────────────────────────────────────────────────────────────────────────
ETAPE_RAPPORT="$(fichier_etape "rediger_le_rapport_de_deploiement")"
if [ ! -f "$ETAPE_RAPPORT" ]; then
  echoue "T7 étape « Rédiger le rapport de déploiement » introuvable"
else
  rm -rf "$TMP/travail"; mkdir -p "$TMP/travail/evidence"
  cp "$AVANT_REF" "$TMP/travail/evidence/instantane-avant.txt"
  cp "$AVANT_REF" "$TMP/travail/evidence/instantane-apres.txt"
  printf 'PG_PRET=oui\nENV_PRESENT=oui\nSECRET_POSTGRES_PASSWORD=renseigne\nDISPO_DOCKER_GO=42\nSERVICE_injs-db=running|image=postgres:15\n' \
    > "$TMP/travail/evidence/precontroles-vps.txt"
  printf 'COHERENCE_TAG_DIGEST=ok\nPLATEFORME_OK=oui\nCONTENU_BACKEND_OK\nCONTENU_FRONTEND_OK\nLABEL_VERSION_COHERENT=oui\n' \
    > "$TMP/travail/evidence/images-vps.txt"
  printf 'PORT_VALIDATION=8080\nSERVICE_backend=etat:running|sante:healthy|image=jckouassi/injs-be:%s\nHTTP_api=200\nHTTP_frontend=200\n' "$SHA_VALIDE" \
    > "$TMP/travail/evidence/controles-vps.txt"
  ( cd "$TMP/travail" && SIM_VPS=silencieux \
    MODE=deployer CIBLE_SHA="$SHA_VALIDE" CIBLE_TAG="$SHA_VALIDE" \
    IMAGE_BACKEND=jckouassi/injs-be IMAGE_FRONTEND=jckouassi/injs-fe \
    DIGEST_BACKEND=sha256:1111 DIGEST_FRONTEND=sha256:2222 \
    PUBLICATION_ID=42407161982 PUBLICATION_URL=https://github.com/x \
    PORT_VALIDATION=8080 PRESERVATION=conforme CODE_EXECUTION=0 \
    HTTP_API=200 HTTP_FRONTEND=200 HTTP_ADMIN=200 \
    SANTE_BACKEND='SERVICE_backend=etat:running|sante:healthy' \
    DOMAINE_AVANT=200 DOMAINE_APRES=200 DOMAINE_SERVI_PAR=ancienne \
    DOSSIER_VPS=/opt/injs/injs-lmd \
    bash "$ETAPE_RAPPORT" ) >"$TMP/t7.log" 2>&1
  code=$?
  if [ "$code" = 0 ] && [ -f "$TMP/travail/evidence/rapport.md" ]; then
    reussi "T7.1 rapport.md produit"
    for attendu in "$SHA_VALIDE" "sha256:1111" "sha256:2222" "42407161982" "conforme" \
                   "Protection de la production" "RUNBOOK.md §7" "deploy.sh rollback"; do
      grep -qF "$attendu" "$TMP/travail/evidence/rapport.md" \
        && reussi "T7.2 rapport contient « $attendu »" \
        || echoue "T7.2 rapport sans « $attendu »"
    done
    grep -qE '^\| Contrôle \| Résultat \|$' "$TMP/travail/evidence/rapport.md" \
      && reussi "T7.3 tableau markdown des contrôles présent" \
      || echoue "T7.3 tableau des contrôles absent"
    if grep -qE '(POSTGRES_PASSWORD|DJANGO_SECRET_KEY)=[^r ]' "$TMP/travail/evidence/rapport.md"; then
      echoue "T7.4 une valeur de secret applicatif apparaît dans le rapport"
    else
      reussi "T7.4 aucune valeur de secret applicatif dans le rapport"
    fi
  else
    echoue "T7.1 rapport non produit (code $code) : $(tail -3 "$TMP/t7.log" | tr '\n' ' ')"
  fi
fi

# ────────────────────────────────────────────────────────────────────────────
section "T8 — garde-fou anti-commandes destructrices de deploy.sh (exécution réelle)"
# ────────────────────────────────────────────────────────────────────────────
SANDBOX="$TMP/sandbox-deploy"
mkdir -p "$SANDBOX"
cp "$DEPLOY_SH" "$SANDBOX/deploy.sh"; chmod +x "$SANDBOX/deploy.sh"
cp "$COMPOSE" "$SANDBOX/compose.yml"
( cd "$SANDBOX" && ./deploy.sh commande-inconnue >"$TMP/t8-propre.log" 2>&1 )
code=$?
if [ "$code" = 2 ] && grep -qF 'Usage' "$TMP/t8-propre.log"; then
  reussi "T8.1 deploy.sh + compose du dépôt : garde-fou franchi, aide affichée (code 2)"
else
  echoue "T8.1 garde-fou déclenché à tort sur le compose du dépôt (code $code) : $(tail -2 "$TMP/t8-propre.log" | tr '\n' ' ')"
fi

tester_destructif() { # motif fichier libelle
  cp "$COMPOSE" "$SANDBOX/$2"
  printf '\n# injection de test\nservices:\n  backend:\n    labels: ["%s"]\n' "$1" >> "$SANDBOX/$2"
  ( cd "$SANDBOX" && ./deploy.sh commande-inconnue >"$TMP/t8.log" 2>&1 )
  if [ $? = 1 ] && grep -qF 'Garde-fou' "$TMP/t8.log"; then
    reussi "T8 $3"
  else
    echoue "T8 $3 : motif non détecté"
  fi
  rm -f "$SANDBOX/$2"
}
tester_destructif "down -v" "compose.override.yml" "8.2 « down -v » dans un override → refus"
tester_destructif "system prune -af" "compose.override.yml" "8.3 « system prune » dans un override → refus"
tester_destructif "volume prune" "compose.override.yml" "8.4 « volume prune » dans un override → refus"

# Le garde-fou doit aussi couvrir un espacement différent
cp "$COMPOSE" "$SANDBOX/compose.override.yml"
printf '\nservices:\n  backend:\n    labels: ["down    -v"]\n' >> "$SANDBOX/compose.override.yml"
( cd "$SANDBOX" && ./deploy.sh commande-inconnue >"$TMP/t8.log" 2>&1 )
if [ $? = 1 ] && grep -qF 'Garde-fou' "$TMP/t8.log"; then
  reussi "T8.5 espacement multiple normalisé : « down    -v » détecté"
else
  echoue "T8.5 espacement multiple non normalisé"
fi
rm -f "$SANDBOX/compose.override.yml"

# ────────────────────────────────────────────────────────────────────────────
section "T9 — refus des tags mutables par deploy.sh (exécution réelle)"
# ────────────────────────────────────────────────────────────────────────────
tester_tag_deploy() { # tag motif_attendu libelle
  ( cd "$SANDBOX" && ./deploy.sh deployer --tag "$1" >"$TMP/t9.log" 2>&1 )
  if grep -qF "$2" "$TMP/t9.log"; then reussi "$3"
  else echoue "$3 : motif « $2 » absent — $(tail -2 "$TMP/t9.log" | tr '\n' ' ')"; fi
}
tester_tag_deploy "latest" "Tag interdit en production" "T9.1 deploy.sh refuse latest"
tester_tag_deploy "stable" "Tag interdit en production" "T9.2 deploy.sh refuse stable"
tester_tag_deploy "mon-tag" "Format de tag non reconnu" "T9.3 deploy.sh refuse un tag arbitraire"
tester_tag_deploy "$SHA_VALIDE" "Fichier d'environnement introuvable" \
  "T9.4 deploy.sh accepte le SHA puis exige le .env serveur (jamais de déploiement sans configuration)"
( cd "$SANDBOX" && ./deploy.sh deployer >"$TMP/t9.log" 2>&1 )
if [ $? != 0 ] && grep -qF 'explicite requis' "$TMP/t9.log"; then
  reussi "T9.5 deploy.sh refuse un déploiement sans tag"
else
  echoue "T9.5 deploy.sh sans tag non refusé"
fi

# ────────────────────────────────────────────────────────────────────────────
section "T10 — porte d'analyse des migrations de deploy.sh (exécution réelle)"
# ────────────────────────────────────────────────────────────────────────────
plan() { # nom ; écrit un plan au format RÉEL de Django 5.1.4
  # Format vérifié dans les sources (django/core/management/commands/migrate.py) :
  #   « Planned operations: » en colonne 0, puis str(migration) EN COLONNE 0,
  #   puis chaque opération indentée de 4 espaces ; ou, sans opération,
  #   «   No planned migration operations. » indentée de 2 espaces.
  cat > "$SANDBOX/$1"
}
tester_plan() { # fichier code_attendu motif libelle [variable d'autorisation]
  local fichier="$1" attendu="$2" motif="$3" libelle="$4" autorisation="${5:-}"
  if [ -n "$autorisation" ]; then
    ( cd "$SANDBOX" && env "$autorisation=oui-explicite" ./deploy.sh analyser-plan "$fichier" >"$TMP/t10.log" 2>&1 )
  else
    ( cd "$SANDBOX" && ./deploy.sh analyser-plan "$fichier" >"$TMP/t10.log" 2>&1 )
  fi
  local code=$?
  if [ "$code" != "$attendu" ]; then
    echoue "$libelle : code attendu $attendu, obtenu $code — $(tail -2 "$TMP/t10.log" | tr '\n' ' ')"
    return
  fi
  if [ -n "$motif" ] && ! grep -qF "$motif" "$TMP/t10.log"; then
    echoue "$libelle : message « $motif » absent"
    return
  fi
  reussi "$libelle"
}

plan "plan-vide.txt" <<'EOS'
EOS
tester_plan plan-vide.txt 1 "Plan de migrations VIDE" "T10.1 plan vide → refus (jamais lu comme « rien à migrer »)"

plan "plan-rien.txt" <<'EOS'
Planned operations:
  No planned migration operations.
EOS
tester_plan plan-rien.txt 0 "Aucune migration en attente" "T10.2 aucune migration en attente → accepté"

plan "plan-sur.txt" <<'EOS'
Planned operations:
scolarite.0031_motifinscription
    Create model MotifInscription
    Add field motif to dossieretudiant
EOS
tester_plan plan-sur.txt 0 "2 sûre(s)" "T10.3 Create model + Add field → opérations sûres, accepté"

plan "plan-examen.txt" <<'EOS'
Planned operations:
scolarite.0032_alter_email
    Alter field email on utilisateur
    Add index scolarite_dossier_idx to dossieretudiant
EOS
tester_plan plan-examen.txt 1 "examiner" "T10.4 Alter field + index → bloqué, inspection humaine exigée"
tester_plan plan-examen.txt 0 "explicitement confirmé" \
  "T10.5 même plan accepté après autorisation explicite (DEPLOY_AUTORISER_EXAMEN_MIGRATIONS)" \
  DEPLOY_AUTORISER_EXAMEN_MIGRATIONS

plan "plan-bloquant.txt" <<'EOS'
Planned operations:
scolarite.0033_nettoyage
    Delete model AncienReferentiel
    Rename field nom on refformation to libelle
EOS
tester_plan plan-bloquant.txt 1 "BLOQUANTES" "T10.6 Delete model + Rename field → bloqué"
tester_plan plan-bloquant.txt 0 "explicitement autorisées" \
  "T10.7 même plan accepté après autorisation explicite (DEPLOY_AUTORISER_MIGRATIONS_DESTRUCTIVES)" \
  DEPLOY_AUTORISER_MIGRATIONS_DESTRUCTIVES

plan "plan-inattendu.txt" <<'EOS'
Planned operations:
ceci n'est pas un en-tête de migration
EOS
tester_plan plan-inattendu.txt 1 "Format de plan inattendu" "T10.8 ligne en colonne 0 non reconnue → refus"

plan "plan-inconnu.txt" <<'EOS'
Planned operations:
scolarite.0034_operation_metier
    Raw Python operation -> Fonction custom
EOS
tester_plan plan-inconnu.txt 1 "examiner" "T10.9 opération inconnue → jamais présumée inoffensive"

plan "plan-irreversible.txt" <<'EOS'
Planned operations:
scolarite.0035_donnees
    Raw Python operation -> IRREVERSIBLE
EOS
tester_plan plan-irreversible.txt 1 "examiner" "T10.10 opération irréversible → bloquée"

plan "plan-contradictoire.txt" <<'EOS'
Planned operations:
  No planned migration operations.
    Create model Fantome
EOS
tester_plan plan-contradictoire.txt 1 "contradictoire" "T10.11 plan contradictoire → refus"

plan "plan-annulation.txt" <<'EOS'
Planned operations:
scolarite.0036_retour
    Undo Create model MotifInscription
EOS
tester_plan plan-annulation.txt 1 "examiner" "T10.12 opération « Undo » (annulation) → à examiner, jamais présumée sûre"


# ────────────────────────────────────────────────────────────────────────────
section "T11 — contrôle des sauvegardes (exécution réelle du script distant)"
# ────────────────────────────────────────────────────────────────────────────
# Le script distant du contrôle des sauvegardes est extrait du YAML puis
# exécuté sur un répertoire TEMPORAIRE LOCAL, avec des fichiers fictifs.
# Aucune donnée de production n'est utilisée, aucun accès réseau.
DISTANT_SAU="$(fichier_etape "controle_des_sauvegardes_du_vps_lecture_seule")"
DISTANT_SAU="${DISTANT_SAU%.sh}.distant0.sh"
if [ ! -f "$DISTANT_SAU" ]; then
  echoue "T11 script distant du contrôle des sauvegardes introuvable ($DISTANT_SAU)"
else
  BACS="$TMP/bacs"; mkdir -p "$BACS"
  TAILLE_MIN=1048576

  # Fabrique un faux dump PostgreSQL (signature PGDMP + taille plancher).
  fabriquer_dump() { # chemin [signature] [taille]
    local f="$1" sig="${2:-PGDMP}" taille="${3:-$TAILLE_MIN}"
    { printf '%s' "$sig"; head -c $((taille - ${#sig})) /dev/zero | tr '\0' 'x'; } > "$f"
  }
  lancer_sauvegardes() { # bac -> sortie standard (code de retour du script)
    bash "$DISTANT_SAU" "$1" 7 30 "$TAILLE_MIN" 2>&1
  }
  statut_sau() { printf '%s\n' "$1" | grep -E "^CONTROLE\|$2\|" | cut -d'|' -f3; }
  verdict_de() { printf '%s\n' "$1" | grep -E "^VERDICT=" | cut -d= -f2; }

  # Le script distant n'émet pas de CONTROLE : la classification est faite
  # par l'étape du workflow. On rejoue donc la décision avec la bibliothèque.
  classer() { # bac -> lignes CONTROLE + VERDICT
    local bac="$1" brut code etat fin lisibilite nb
    brut="$(lancer_sauvegardes "$bac")"; code=$?
    : > "$TMP/t11-controles.txt"
    export CONTROLES_FICHIER="$TMP/t11-controles.txt"
    . deploy/production/normaliser-controles.sh
    valeur_de() { printf '%s\n' "$brut" | awk -F= -v k="$1" '$1==k{v=substr($0,length(k)+2)} END{printf "%s", v}'; }
    etat="$(valeur_de SAU_ETAT)"; fin="$(valeur_de SAU_FIN)"
    nb="$(printf '%s\n' "$brut" | grep -c '^SAU_DUMP=' || true)"
    if [ "$code" != 0 ] || { [ "$etat" = "present" ] && [ "$(valeur_de SAU_LISIBLE)" = "oui" ] && [ "$fin" != "ok" ]; }; then
      controle_non_execute SAU-ACCES oui "script distant en échec (code $code)"
      controle_non_execute SAU-DISPO oui "inventaire incomplet"
    elif [ "$etat" = "absent" ]; then
      controle SAU-EXISTE FAIL oui "absent" "répertoire absent"
      controle_non_execute SAU-DISPO oui "répertoire absent"
    elif [ "$(valeur_de SAU_LISIBLE)" != "oui" ]; then
      controle SAU-EXISTE PASS oui "présent" "présent"
      controle SAU-LISIBLE FAIL oui "illisible" "droits insuffisants"
      controle_non_execute SAU-DISPO oui "inventaire impossible"
    else
      controle SAU-EXISTE PASS oui "présent" "présent"
      controle SAU-LISIBLE PASS oui "lisible" "lisible"
      controle SAU-INVENTAIRE PASS oui "${nb} dump(s)" "inventaire lecture seule"
      if [ "${nb:-0}" -eq 0 ]; then
        controle SAU-DISPO FAIL oui "aucun dump" "aucune sauvegarde"
      else
        recents=0; valides=0
        while IFS='|' read -r nom taille age signature compagnon; do
          [ -n "$nom" ] || continue
          if [ "$signature" != "PGDMP" ]; then
            controle "SAU-DUMP-$nom" WARN non "${taille} o, ${age} j" "signature absente"
            continue
          fi
          if [ "$taille" -lt "$TAILLE_MIN" ]; then
            controle "SAU-DUMP-$nom" WARN non "${taille} o" "taille sous plancher"
            continue
          fi
          valides=$((valides + 1))
          if [ "$age" -le 7 ]; then
            recents=$((recents + 1))
            controle "SAU-DUMP-$nom" PASS oui "${taille} o, ${age} j" "dump présent, signature PGDMP, récent (≤ 7 j) — intégrité et restaurabilité NON démontrées"
          else
            controle "SAU-DUMP-$nom" WARN non "${age} j" "ancien"
          fi
        done <<< "$(printf '%s\n' "$brut" | grep '^SAU_DUMP=' | sed 's/^SAU_DUMP=//')"
        if [ "${recents:-0}" -gt 0 ]; then
          controle SAU-DISPO PASS oui "${recents} récent(s)" "sauvegarde exploitable en apparence"
        elif [ "${valides:-0}" -gt 0 ]; then
          controle SAU-DISPO FAIL oui "0 récent" "aucune sauvegarde fraîche"
        else
          controle SAU-DISPO FAIL oui "0 exploitable" "aucun dump exploitable"
        fi
      fi
    fi
    cat "$TMP/t11-controles.txt"
    printf 'VERDICT=%s\n' "$(controles_analyser "$CONTROLES_FICHIER" | sed -n 's/^verdict=//p')"
  }

  # 1. Répertoire absent
  sortie="$(classer "$BACS/inexistant")"
  [ "$(statut_sau "$sortie" SAU-EXISTE)" = "FAIL" ] \
    && reussi "T11.1 répertoire absent → FAIL obligatoire" \
    || echoue "T11.1 répertoire absent mal classé ($(statut_sau "$sortie" SAU-EXISTE))"
  [ "$(verdict_de "$sortie")" = "REFUSE" ] \
    && reussi "T11.1 verdict REFUSE quand le répertoire manque" \
    || echoue "T11.1 verdict non REFUSE ($(verdict_de "$sortie"))"

  # 2. Répertoire vide
  mkdir -p "$BACS/vide"; sortie="$(classer "$BACS/vide")"
  [ "$(statut_sau "$sortie" SAU-DISPO)" = "FAIL" ] \
    && reussi "T11.2 répertoire vide → FAIL (aucune sauvegarde exploitable)" \
    || echoue "T11.2 répertoire vide mal classé ($(statut_sau "$sortie" SAU-DISPO))"
  [ "$(verdict_de "$sortie")" = "REFUSE" ] \
    && reussi "T11.2 verdict REFUSE sur répertoire vide" \
    || echoue "T11.2 verdict non REFUSE"

  # 3. Dump PostgreSQL présent et récent
  mkdir -p "$BACS/recent"; fabriquer_dump "$BACS/recent/injs-20261106-120000.dump"
  sortie="$(classer "$BACS/recent")"
  [ "$(statut_sau "$sortie" SAU-DUMP-injs-20261106-120000.dump)" = "PASS" ] \
    && reussi "T11.3 dump PGDMP récent → PASS" \
    || echoue "T11.3 dump récent mal classé ($(statut_sau "$sortie" SAU-DUMP-injs-20261106-120000.dump))"
  [ "$(verdict_de "$sortie")" = "VALIDE" ] \
    && reussi "T11.3 verdict VALIDE avec un dump récent" \
    || echoue "T11.3 verdict non VALIDE ($(verdict_de "$sortie"))"

  # 4. Dump ancien
  mkdir -p "$BACS/ancien"; fabriquer_dump "$BACS/ancien/injs-vieux.dump"
  touch -d "45 days ago" "$BACS/ancien/injs-vieux.dump"
  sortie="$(classer "$BACS/ancien")"
  [ "$(statut_sau "$sortie" SAU-DUMP-injs-vieux.dump)" = "WARN" ] \
    && reussi "T11.4 dump ancien (45 j) → WARN" \
    || echoue "T11.4 dump ancien mal classé ($(statut_sau "$sortie" SAU-DUMP-injs-vieux.dump))"
  [ "$(verdict_de "$sortie")" = "REFUSE" ] \
    && reussi "T11.4 un dump ancien seul ne suffit pas → REFUSE (aucune sauvegarde fraîche)" \
    || echoue "T11.4 verdict non REFUSE ($(verdict_de "$sortie"))"

  # 5. Archive non vérifiable
  mkdir -p "$BACS/archive"; printf 'archive-generique' > "$BACS/archive/sauvegarde.tar.gz"
  sortie="$(classer "$BACS/archive")"
  [ "$(statut_sau "$sortie" SAU-DISPO)" = "FAIL" ] \
    && reussi "T11.5 archive non exploitable → FAIL de disponibilité" \
    || echoue "T11.5 archive mal classée ($(statut_sau "$sortie" SAU-DISPO))"
  printf '%s\n' "$sortie" | grep -q 'SAU-INVENTAIRE|PASS' \
    && reussi "T11.5 les archives sont inventoriées sans être prises pour des dumps" \
    || echoue "T11.5 inventaire des archives absent"

  # 6. Sauvegarde exploitable
  mkdir -p "$BACS/exploitable"
  fabriquer_dump "$BACS/exploitable/injs-20261107-090000.dump"
  printf 'x' > "$BACS/exploitable/injs-20261107-090000.dump.sha256"
  sortie="$(classer "$BACS/exploitable")"
  [ "$(statut_sau "$sortie" SAU-DUMP-injs-20261107-090000.dump)" = "PASS" ] \
    && reussi "T11.6 sauvegarde exploitable → PASS (présence + signature uniquement)" \
    || echoue "T11.6 sauvegarde exploitable mal classée"
  grep -qF "restaurabilité NON démontrées" "$DEPLOY_WF" \
    && reussi "T11.6 le rapport signale la limite d'intégrité/restaurabilité" \
    || echoue "T11.6 limite d'intégrité non signalée par le workflow"
  printf '%s\n' "$sortie" | grep -q 'intégrité et restaurabilité NON démontrées' \
    && reussi "T11.6 le classement de test porte la même réserve que le workflow" \
    || echoue "T11.6 libellé de réserve absent du classement"

  # 7a. Fichier vide (signature absente)
  mkdir -p "$BACS/vide-dump"; : > "$BACS/vide-dump/injs-vide.dump"
  sortie="$(classer "$BACS/vide-dump")"
  [ "$(statut_sau "$sortie" SAU-DUMP-injs-vide.dump)" = "WARN" ] \
    && reussi "T11.7 dump vide → WARN, jamais PASS" \
    || echoue "T11.7 dump vide mal classé"
  # 7b. Signature incorrecte
  mkdir -p "$BACS/sig"; fabriquer_dump "$BACS/sig/faux.dump" "GARBA" "$TAILLE_MIN"
  sortie="$(classer "$BACS/sig")"
  [ "$(statut_sau "$sortie" SAU-DUMP-faux.dump)" = "WARN" ] \
    && reussi "T11.7 signature incorrecte → WARN (archive non vérifiable)" \
    || echoue "T11.7 signature incorrecte mal classée"
  # 7c. Signature correcte mais taille sous le plancher
  mkdir -p "$BACS/petit"; fabriquer_dump "$BACS/petit/petit.dump" "PGDMP" 100
  sortie="$(classer "$BACS/petit")"
  [ "$(statut_sau "$sortie" SAU-DUMP-petit.dump)" = "WARN" ] \
    && reussi "T11.7 signature PGDMP mais taille sous plancher → WARN" \
    || echoue "T11.7 taille sous plancher mal classée"
fi

# ────────────────────────────────────────────────────────────────────────────
section "T12 — normalisation PASS / WARN / FAIL / NON_EXECUTE"
# ────────────────────────────────────────────────────────────────────────────
export CONTROLES_FICHIER="$TMP/t12-controles.txt"
. deploy/production/normaliser-controles.sh
: > "$CONTROLES_FICHIER"
controle X-PASS PASS oui "mesure" "tout est conforme"
[ "$(statut_sau "$(cat "$CONTROLES_FICHIER")" X-PASS)" = "PASS" ] \
  && reussi "T12.1 classification PASS" || echoue "T12.1 PASS mal enregistré"
controle X-WARN WARN non "mesure" "à surveiller"
[ "$(statut_sau "$(cat "$CONTROLES_FICHIER")" X-WARN)" = "WARN" ] \
  && reussi "T12.2 classification WARN" || echoue "T12.2 WARN mal enregistré"
controle X-FAIL FAIL oui "mesure" "bloquant"
[ "$(statut_sau "$(cat "$CONTROLES_FICHIER")" X-FAIL)" = "FAIL" ] \
  && reussi "T12.3 classification FAIL" || echoue "T12.3 FAIL mal enregistré"

# Un statut inconnu devient NON_EXECUTE (échec fermé)
controle X-BIZARRE "OK" oui "mesure" "statut non supporté"
[ "$(statut_sau "$(cat "$CONTROLES_FICHIER")" X-BIZARRE)" = "NON_EXECUTE" ] \
  && reussi "T12.4 statut inconnu → NON_EXECUTE (jamais converti en PASS)" \
  || echoue "T12.4 statut inconnu mal traité"

# Bilan : 1 PASS, 1 WARN, 1 FAIL, 1 NON_EXECUTE
analyse="$(controles_analyser "$CONTROLES_FICHIER")"
for attendu in "pass=1" "warn=1" "fail=1" "non_execute=1" "total=4" "verdict=REFUSE" "code=1"; do
  printf '%s\n' "$analyse" | grep -qx "$attendu" \
    && reussi "T12.5 bilan contient « $attendu »" \
    || echoue "T12.5 bilan sans « $attendu »"
done

# Un FAIL obligatoire suffit à refuser
: > "$CONTROLES_FICHIER"
controle A PASS oui "ok" "ok"
controle B FAIL oui "ko" "prérequis manquant"
[ "$(controles_analyser "$CONTROLES_FICHIER" | sed -n 's/^verdict=//p')" = "REFUSE" ] \
  && reussi "T12.6 un FAIL obligatoire → verdict REFUSE" || echoue "T12.6 FAIL non bloquant"

# Un NON_EXECUTE obligatoire refuse aussi, sans FAIL
: > "$CONTROLES_FICHIER"
controle A PASS oui "ok" "ok"
controle_non_execute B oui "donnée indisponible"
[ "$(controles_analyser "$CONTROLES_FICHIER" | sed -n 's/^verdict=//p')" = "REFUSE" ] \
  && reussi "T12.7 un NON_EXECUTE obligatoire → verdict REFUSE" \
  || echoue "T12.7 NON_EXECUTE traité comme un succès"

# WARN seul → RESERVES (code 0)
: > "$CONTROLES_FICHIER"
controle A PASS oui "ok" "ok"
controle B WARN non "lent" "non bloquant"
[ "$(controles_analyser "$CONTROLES_FICHIER" | sed -n 's/^verdict=//p')" = "RESERVES" ] \
  && reussi "T12.8 WARN seul → RESERVES" || echoue "T12.8 RESERVES non détecté"
[ "$(controles_analyser "$CONTROLES_FICHIER" | sed -n 's/^code=//p')" = "0" ] \
  && reussi "T12.8 RESERVES ne bloque pas (code 0)" || echoue "T12.8 RESERVES bloquant"

# Tout PASS → VALIDE
: > "$CONTROLES_FICHIER"
controle A PASS oui "ok" "ok"; controle B PASS oui "ok" "ok"
[ "$(controles_analyser "$CONTROLES_FICHIER" | sed -n 's/^verdict=//p')" = "VALIDE" ] \
  && reussi "T12.9 tous PASS → VALIDE" || echoue "T12.9 VALIDE non détecté"

# Fichier absent → REFUSE, aucun PASS implicite
[ "$(controles_analyser "$TMP/absent.txt" | sed -n 's/^verdict=//p')" = "REFUSE" ] \
  && reussi "T12.10 fichier de contrôles absent → REFUSE (aucun PASS implicite)" \
  || echoue "T12.10 absence de fichier non bloquante"

# Ligne mal formée → NON_EXECUTE
: > "$CONTROLES_FICHIER"
printf 'CONTROLE|CASSE|PASS\n' >> "$CONTROLES_FICHIER"
[ "$(controles_analyser "$CONTROLES_FICHIER" | sed -n 's/^verdict=//p')" = "REFUSE" ] \
  && reussi "T12.11 ligne mal formée → REFUSE (analyse à échec fermé)" \
  || echoue "T12.11 ligne mal formée acceptée"

# Tableau du rapport
: > "$CONTROLES_FICHIER"
controle R1 PASS oui "ok" "conforme"
tableau="$(controles_tableau "$CONTROLES_FICHIER")"
printf '%s\n' "$tableau" | grep -q '^| Contrôle | Statut | Obligatoire | Résultat | Observation |$' \
  && reussi "T12.12 tableau au format demandé (5 colonnes)" \
  || echoue "T12.12 en-tête de tableau inattendu"
printf '%s\n' "$tableau" | grep -q '✅ PASS' \
  && reussi "T12.12 statut rendu lisible dans le tableau" || echoue "T12.12 statut absent"

# ────────────────────────────────────────────────────────────────────────────
section "T13 — absence d'écriture dans le contrôle des sauvegardes"
# ────────────────────────────────────────────────────────────────────────────
if [ -f "$DISTANT_SAU" ]; then
  # On analyse le script distant en neutralisant commentaires et chaînes :
  # une mention « rm » dans un commentaire ne doit pas produire de faux positif,
  # et une vraie commande d'écriture ne doit pas être masquée.
  # Neutralisation CONSERVATRICE : seuls les commentaires sont retirés.
  # (Supprimer aussi les chaînes entre guillemets effaçait le contenu des
  #  $(...) et pouvait masquer une commande d'écriture réelle : échec ouvert.)
  neutralise() {
    sed -e 's/[[:space:]]#.*$//' -e 's/^#.*$//' "$1"
  }
  code_sau="$(neutralise "$DISTANT_SAU")"
  for interdit in 'rm ' 'mv ' 'cp ' 'touch ' 'mkdir ' 'chmod ' 'chown ' 'tee ' 'dd ' 'pg_restore' 'psql' 'docker ' 'truncate'; do
    if printf '%s\n' "$code_sau" | grep -qE "(^|[[:space:]|;&(])${interdit}"; then
      echoue "T13.1 commande d'écriture/restauration détectée dans le contrôle des sauvegardes : « $interdit »"
    else
      reussi "T13.1 aucune occurrence de « $interdit » dans le script distant"
    fi
  done
  # Aucune redirection vers un fichier (hors /dev/null et hors descripteurs).
  if printf '%s\n' "$code_sau" | grep -qE '(^|[^0-9&])>[[:space:]]*[^&/]'; then
    echoue "T13.2 redirection vers un fichier détectée dans le script distant"
  else
    reussi "T13.2 aucune redirection d'écriture vers un fichier"
  fi
  # Le script ne fait que des lectures : présence des primitives de lecture.
  for primitive in 'stat -c' 'head -c 5' 'date +%s'; do
    grep -qF "$primitive" "$DISTANT_SAU" \
      && reussi "T13.3 primitive de lecture présente : $primitive" \
      || echoue "T13.3 primitive de lecture absente : $primitive"
  done
  # pg_restore -l est explicitement proscrit par la mission.
  printf '%s\n' "$DISTANT_SAU" | grep -qF 'pg_restore' \
    && echoue "T13.4 pg_restore présent (proscrit : pas de restauration, même à blanc)" \
    || reussi "T13.4 pg_restore absent du contrôle des sauvegardes"
  # Preuve d'absence d'écriture à l'exécution : le bac de test est inchangé.
  mkdir -p "$BACS/invariance"; fabriquer_dump "$BACS/invariance/ref.dump"
  avant="$(cd "$BACS/invariance" && ls -ln --time-style=full-iso | sha256sum)"
  bash "$DISTANT_SAU" "$BACS/invariance" 7 30 "$TAILLE_MIN" >/dev/null 2>&1 || true
  apres="$(cd "$BACS/invariance" && ls -ln --time-style=full-iso | sha256sum)"
  [ "$avant" = "$apres" ] \
    && reussi "T13.5 exécution du contrôle : répertoire strictement inchangé (nom, taille, date, droits)" \
    || echoue "T13.5 le contrôle a modifié le répertoire inspecté"
  [ "$(ls -1 "$BACS/invariance" | wc -l)" -eq 1 ] \
    && reussi "T13.5 aucun fichier créé par le contrôle" \
    || echoue "T13.5 fichier créé par le contrôle"
fi

# ────────────────────────────────────────────────────────────────────────────
section "T14 — barrière anti-déploiement en mode preflight"
# ────────────────────────────────────────────────────────────────────────────
# Les quatre conditions validées doivent rester effectives.
grep -qF "if: env.MODE != 'preflight' && env.MODE != 'inventaire'" "$DEPLOY_WF" \
  && reussi "T14.1 condition de protection conservée (rsync / deploy.sh)" \
  || echoue "T14.1 condition de protection modifiée"
[ "$(grep -cF "if: env.MODE != 'preflight' && env.MODE != 'inventaire'" "$DEPLOY_WF")" -ge 2 ] \
  && reussi "T14.2 la condition protège bien au moins deux étapes" \
  || echoue "T14.2 condition présente sur une seule étape"
grep -qF "if: (env.MODE == 'deployer' || env.MODE == 'plan') && env.IMAGES_SUR_REGISTRE == 'oui'" "$DEPLOY_WF" \
  && reussi "T14.3 docker pull toujours limité à deployer/plan" \
  || echoue "T14.3 condition du docker pull modifiée"
grep -qF "if: always() && env.MODE != 'inventaire' && env.MODE != 'preflight'" "$DEPLOY_WF" \
  && reussi "T14.4 journaux VPS toujours exclus du preflight" \
  || echoue "T14.4 exclusion du preflight modifiée"
# L'étape de sauvegardes est bien limitée aux modes de contrôle.
grep -qE "if: env.MODE == 'preflight' \|\| env.MODE == 'inventaire'" "$DEPLOY_WF" \
  && reussi "T14.5 le contrôle des sauvegardes est limité aux modes de contrôle" \
  || echoue "T14.5 condition du contrôle des sauvegardes absente"
# Aucune étape sans condition n'est devenue mutante.
sans_condition="$(awk '/^  deploiement:/,/^  rapport:/' "$DEPLOY_WF" | awk '/^      - name:/{n=$0; getline; if ($0 !~ /^        if:/) print n}')"
printf '%s\n' "$sans_condition" | grep -qiE 'deploy\.sh|rsync|docker pull|migrate|restaur' \
  && echoue "T14.6 une étape sans condition semble mutante" \
  || reussi "T14.6 toutes les étapes sans condition restent des étapes de lecture"

# ────────────────────────────────────────────────────────────────────────────
printf '\n────────────────────────────────────────────────────────\n'
printf 'BILAN : %d tests passés, %d échoués\n' "$nb_reussis" "$nb_echoues"
if [ "$nb_echoues" -gt 0 ]; then
  printf 'Résultat : ÉCHEC\n'
  exit 1
fi
printf 'Résultat : tous les tests exécutés passent.\n'
printf 'Rappel : SSH réel, docker sur le VPS, registre Docker Hub et HTTP réel\n'
printf "         n'ont PAS été exercés (aucun déploiement autorisé en phase dev).\n"
exit 0
