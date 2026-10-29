#!/usr/bin/env bash
# Exécution des tests par groupe, avec journal et code de sortie distincts.
#
# Pourquoi ce harnais : la suite complète dure ~15 min, au-delà de la fenêtre
# d'attente d'une commande. Chaque groupe est borné par `timeout`, écrit son
# propre journal et son propre code de sortie, ce qui permet de savoir
# exactement ce qui a réussi, échoué ou été interrompu — sans jamais
# transformer un échec en succès.
#
# Usage :
#   ./arena/tests_par_groupe.sh                # tous les groupes, séquentiel
#   ./arena/tests_par_groupe.sh scolarite      # un seul groupe
#   ./arena/tests_par_groupe.sh --lister       # liste les groupes
#
# Sortie : /tmp/injs-validation/<groupe>.log et <groupe>.exit
#          Code 0 si tous les groupes du lot réussissent, 1 sinon.

set -uo pipefail

RACINE="/home/user/backend-injs2026"
SORTIE="/tmp/injs-validation"
PYTHON="$RACINE/backend/.venv/bin/python"

export DJANGO_SETTINGS_MODULE=arena.settings_sandbox
export PYTHONPATH="$RACINE"
export STORAGES=STORAGE_DE_TEST

# Groupe → applications Django testées, et budget temps (secondes).
# Format : "applications|budget_secondes" — le séparateur '|' évite que
# `read` ne récupère que le premier mot des applications à tester.
declare -A GROUPES=(
  [scolarite]="scolarite|420"
  [formations]="formations|420"
  [auth]="authentication|300"
  [habilitations]="habilitations|600"
  [edt]="edts presences|360"
  [evaluations]="evaluations jurys|360"
  [pilotage]="statistiques config dashboard|300"
  [socle]="core admissions administrations referentiels|300"
  [divers]="parametres suiviEvaluation graduation equivalences stages patrimoine ressources_humaines finances_etudiantes exports|300"
)

ORDRE=(scolarite formations auth habilitations edt evaluations pilotage socle divers)

if [[ "${1:-}" == "--lister" ]]; then
  for g in "${ORDRE[@]}"; do
    apps="${GROUPES[$g]%%|*}"; budget="${GROUPES[$g]##*|}"
    echo "$g : $apps (${budget}s)"
  done
  exit 0
fi

if [[ $# -gt 0 ]]; then
  ORDRE=("$@")
fi

mkdir -p "$SORTIE"
cd "$RACINE/backend" || exit 2

code_global=0
printf '%-12s %-10s %s\n' "GROUPE" "RÉSULTAT" "DÉTAIL"
printf '%s\n' "------------------------------------------------------------"

for groupe in "${ORDRE[@]}"; do
  if [[ -z "${GROUPES[$groupe]:-}" ]]; then
    printf '%-12s %-10s %s\n' "$groupe" "INCONNU" "groupe non défini"
    code_global=1
    continue
  fi
  apps="${GROUPES[$groupe]%%|*}"
  budget="${GROUPES[$groupe]##*|}"
  journal="$SORTIE/$groupe.log"
  fichier_code="$SORTIE/$groupe.exit"
  debut=$(date +%s)

  # shellcheck disable=SC2086
  timeout "$budget" "$PYTHON" manage.py test $apps --noinput \
    >"$journal" 2>&1
  code=$?
  echo "$code" > "$fichier_code"
  duree=$(( $(date +%s) - debut ))

  # Le code de sortie de Django est conservé tel quel : 0 = succès.
  if [[ $code -eq 0 ]]; then
    resultat="RÉUSSI"
  elif [[ $code -eq 124 ]]; then
    resultat="INTERROMPU"
    code_global=1
  else
    resultat="ÉCHOUÉ"
    code_global=1
  fi
  resume=$(grep -E "^Ran [0-9]+ test" "$journal" | tail -1)
  [[ -z "$resume" ]] && resume=$(tail -1 "$journal")
  printf '%-12s %-10s %ss | %s\n' "$groupe" "$resultat" "$duree" "$resume"
done

printf '%s\n' "------------------------------------------------------------"
echo "Journaux : $SORTIE/"
exit $code_global
