#!/usr/bin/env bash
# ============================================================================
# INJS-LMD — Normalisation des résultats de contrôle (PASS / WARN / FAIL)
#
# Bibliothèque SOURCÉE par les étapes du workflow de déploiement. Elle ne fait
# rien à l'import : pas d'effet de bord, pas d'écriture disque, aucun appel
# réseau. Toutes les fonctions sont pures ou n'écrivent que vers une sortie
# explicitement reçue en argument.
#
# Format interne d'un contrôle (une ligne, une barre oblique interdite dans
# les champs pour rester analysable en awk) :
#
#   CONTROLE|id|STATUT|OBLIGATOIRE|RESULTAT|OBSERVATION
#
#   id           identifiant STABLE (ex. PRE-DISQUE, SAU-DUMP-RECENT)
#   STATUT       PASS | WARN | FAIL | NON_EXECUTE  (aucune autre valeur)
#   OBLIGATOIRE  oui | non
#   RESULTAT     valeur mesurée, courte, jamais secrète
#   OBSERVATION  explication lisible
#
# Règles de verdict (déterministes, aucune place à l'interprétation) :
#   FAIL          verdict = REFUSE
#   NON_EXECUTE   verdict = REFUSE (un contrôle non exécuté n'est JAMAIS un PASS)
#   WARN          verdict = RESERVES (si aucun FAIL et aucun NON_EXECUTE)
#   sinon         verdict = VALIDE
#
# Une ligne mal formée est comptée comme NON_EXECUTE : l'analyse échoue
# fermée, elle ne suppose jamais la conformité.
# ============================================================================

# Variables globales volontairement NON exportées par défaut : les étapes les
# passent explicitement à `controles_analyser`.
: "${CONTROLES_FICHIER:=controles.txt}"

# controle <id> <statut> <obligatoire> <resultat> <observation> [fichier]
controle() {
  local id="$1" statut="$2" obligatoire="$3" resultat="$4" observation="$5"
  local fichier="${6:-$CONTROLES_FICHIER}"

  case "$statut" in
    PASS | WARN | FAIL | NON_EXECUTE) ;;
    *)
      # Statut inconnu : on ne devine pas. Il devient NON_EXECUTE, avec la
      # raison visible dans l'observation — jamais converti en succès.
      observation="statut invalide « $statut » fourni par le contrôle ; $observation"
      statut="NON_EXECUTE"
      ;;
  esac
  case "$obligatoire" in
    oui | non) ;;
    *) obligatoire="oui" ;;
  esac

  # Neutralisation de la barre oblique : elle est le séparateur du format.
  resultat="$(printf '%s' "$resultat" | tr '|' '/')"
  observation="$(printf '%s' "$observation" | tr '|' '/')"
  id="$(printf '%s' "$id" | tr '|/ ' '___')"

  printf 'CONTROLE|%s|%s|%s|%s|%s\n' \
    "$id" "$statut" "$obligatoire" "$resultat" "$observation" >>"$fichier"
}

# controle_non_execute <id> <obligatoire> <raison> [fichier]
# Raccourci explicite : sert quand l'étape précédente a échoué, quand la
# donnée est absente ou quand le contexte interdit le contrôle.
controle_non_execute() {
  controle "$1" NON_EXECUTE "$2" "non mesuré" "$3" "${4:-$CONTROLES_FICHIER}"
}

# controles_analyser <fichier>
# Émet : total, pass, warn, fail, non_execute, verdict, code
# `code` vaut 0 pour VALIDE et RESERVES, 1 pour REFUSE.
controles_analyser() {
  local fichier="${1:-$CONTROLES_FICHIER}"
  awk -F'|' '
    BEGIN { total = 0; pass = 0; warn = 0; fail = 0; ne = 0; malformes = 0 }
    $1 != "CONTROLE" { next }
    {
      if (NF < 6) { malformes++; ne++; total++; next }
      total++
      statut = $3
      if (statut == "PASS") pass++
      else if (statut == "WARN") warn++
      else if (statut == "FAIL") fail++
      else { ne++; if (statut != "NON_EXECUTE") malformes++ }
    }
    END {
      if (total == 0) { ne = 1 }            # aucun contrôle = aucun PASS possible
      if (fail > 0 || ne > 0) verdict = "REFUSE"
      else if (warn > 0) verdict = "RESERVES"
      else verdict = "VALIDE"
      code = (verdict == "REFUSE") ? 1 : 0
      printf "total=%d\npass=%d\nwarn=%d\nfail=%d\nnon_execute=%d\nmalformes=%d\nverdict=%s\ncode=%d\n",
        total, pass, warn, fail, ne, malformes + 0, verdict, code
    }
  ' "$fichier" 2>/dev/null || {
    # Fichier absent ou illisible : refus explicite, jamais un succès muet.
    printf 'total=0\npass=0\nwarn=0\nfail=0\nnon_execute=1\nmalformes=0\nverdict=REFUSE\ncode=1\n'
  }
}

# controles_tableau <fichier>
# Tableau markdown prêt à publier : Contrôle | Statut | Obligatoire | Résultat
# | Observation. Un statut non conforme est signalé visuellement.
controles_tableau() {
  local fichier="${1:-$CONTROLES_FICHIER}"
  echo "| Contrôle | Statut | Obligatoire | Résultat | Observation |"
  echo "|---|---|---|---|---|"
  if [ ! -s "$fichier" ]; then
    echo "| — | NON_EXECUTE | oui | non mesuré | Aucun contrôle enregistré |"
    return 0
  fi
  awk -F'|' '
    $1 == "CONTROLE" && NF >= 6 {
      statut = $3
      if (statut == "PASS") badge = "✅ PASS"
      else if (statut == "WARN") badge = "⚠️ WARN"
      else if (statut == "FAIL") badge = "❌ FAIL"
      else badge = "⛔ NON_EXECUTE"
      printf "| `%s` | %s | %s | %s | %s |\n", $2, badge, $4, $5, $6
    }
    $1 == "CONTROLE" && NF < 6 {
      printf "| `%s` | ⛔ NON_EXECUTE | oui | non mesuré | ligne de contrôle mal formée |\n", $2
    }
  ' "$fichier"
}

# controles_bilan <fichier>
# Bloc de synthèse chiffré, prêt à insérer dans un rapport.
controles_bilan() {
  local fichier="${1:-$CONTROLES_FICHIER}" analyse
  analyse="$(controles_analyser "$fichier")"
  local total pass warn fail ne verdict
  total="$(printf '%s\n' "$analyse" | sed -n 's/^total=//p')"
  pass="$(printf '%s\n' "$analyse" | sed -n 's/^pass=//p')"
  warn="$(printf '%s\n' "$analyse" | sed -n 's/^warn=//p')"
  fail="$(printf '%s\n' "$analyse" | sed -n 's/^fail=//p')"
  ne="$(printf '%s\n' "$analyse" | sed -n 's/^non_execute=//p')"
  verdict="$(printf '%s\n' "$analyse" | sed -n 's/^verdict=//p')"

  echo "| Statut | Nombre |"
  echo "|---|---|"
  echo "| ✅ PASS | ${pass:-0} |"
  echo "| ⚠️ WARN | ${warn:-0} |"
  echo "| ❌ FAIL | ${fail:-0} |"
  echo "| ⛔ NON_EXECUTE | ${ne:-0} |"
  echo "| **Total** | **${total:-0}** |"
  echo ""
  case "$verdict" in
    VALIDE) echo "**Verdict : PRÉFLIGHT VALIDÉ** — tous les prérequis obligatoires sont satisfaits." ;;
    RESERVES) echo "**Verdict : PRÉFLIGHT VALIDÉ AVEC RÉSERVES** — prérequis obligatoires satisfaits, anomalies non bloquantes à examiner." ;;
    *) echo "**Verdict : PRÉFLIGHT REFUSÉ** — au moins un contrôle obligatoire est en FAIL ou NON_EXECUTE." ;;
  esac
}
