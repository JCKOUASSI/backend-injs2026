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

# ---------------------------------------------------------------------------
# SOURCE UNIQUE DES SEUILS DE SAUVEGARDE.
# Ces trois valeurs sont les seules définitions du dépôt : le workflow, les
# tests et la documentation s'y réfèrent. Elles restent surchargeables par
# variable d'environnement (utile pour un test ou une dérogation explicite),
# mais aucune autre copie ne doit exister ailleurs.
#
#   SEUIL_DUMP_RECENT_JOURS  : 0 à N jours  -> PASS (sauvegarde fraîche)
#   SEUIL_DUMP_ANCIEN_JOURS  : N+1 à M jours -> WARN (à rafraîchir)
#                              au-delà de M   -> WARN si une autre sauvegarde
#                                                récente existe, sinon FAIL
#   TAILLE_MIN_DUMP_OCTETS   : plancher de vraisemblance d'un dump
# ---------------------------------------------------------------------------
: "${SEUIL_DUMP_RECENT_JOURS:=7}"
: "${SEUIL_DUMP_ANCIEN_JOURS:=30}"
: "${TAILLE_MIN_DUMP_OCTETS:=1048576}"

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

# ---------------------------------------------------------------------------
# Classification des sauvegardes.
#
# sauvegardes_classifier <inventaire> [fichier_controles] [dossier] [code_ssh]
#
# Politique de fraîcheur — appliquée ici et NULLE PART AILLEURS :
#
#   ancienneté du dump          statut
#   0 à SEUIL_DUMP_RECENT_JOURS        PASS
#   +1 à SEUIL_DUMP_ANCIEN_JOURS       WARN
#   au-delà de SEUIL_DUMP_ANCIEN_JOURS FAIL si aucune autre sauvegarde
#                                      récente et admissible n'existe,
#                                      WARN sinon
#
#   Disponibilité globale (SAU-DISPO) : PASS si au moins un dump admissible
#   (signature PGDMP + taille ≥ plancher) est fraîche ; FAIL sinon. Un dump
#   ancien n'entraîne donc jamais à lui seul un FAIL de disponibilité quand
#   une sauvegarde récente existe ; l'absence totale de sauvegarde récente
#   est toujours un FAIL.
#
#   Les archives complémentaires sont inventoriées mais ne valent JAMAIS
#   sauvegarde PostgreSQL.
#
# Quatre niveaux distingués dans chaque observation :
#   N1 identification (signature PGDMP) — apparente seulement ;
#   N2 présence et fraîcheur (taille, date, ancienneté) ;
#   N3 intégrité — NON démontrée ;
#   N4 restaurabilité — NON démontrée, aucune restauration effectuée.
# ---------------------------------------------------------------------------
sauvegardes_classifier() {
  local inventaire="$1"
  local fichier="${2:-$CONTROLES_FICHIER}"
  local dossier="${3:-/opt/injs/backups}"
  local code_ssh="${4:-0}"
  local etat lisibilite fin

  _sau_valeur() {
    awk -F= -v k="$1" '$1 == k { v = substr($0, length(k) + 2) } END { printf "%s", v }' \
      "$inventaire" 2>/dev/null
  }

  etat="$(_sau_valeur SAU_ETAT)"
  lisibilite="$(_sau_valeur SAU_LISIBLE)"
  fin="$(_sau_valeur SAU_FIN)"

  # --- Accès impossible : NON_EXECUTE, jamais un PASS par défaut -----------
  if [ "$code_ssh" != 0 ] ||
     { [ "$etat" = "present" ] && [ "$lisibilite" = "oui" ] && [ "$fin" != "ok" ]; }; then
    controle SAU-ACCES NON_EXECUTE oui "non mesuré" \
      "script distant en échec (code $code_ssh, marqueur de fin « ${fin:-absent} »)" "$fichier"
    controle_non_execute SAU-DISPO oui "inventaire incomplet : aucune conclusion possible" "$fichier"
    return 0
  fi

  if [ "$etat" = "absent" ]; then
    controle SAU-EXISTE FAIL oui "absent" \
      "répertoire $dossier absent : aucune sauvegarde de production" "$fichier"
    controle_non_execute SAU-DISPO oui "répertoire absent" "$fichier"
    return 0
  fi
  if [ "$etat" = "pas_un_repertoire" ]; then
    controle SAU-EXISTE FAIL oui "pas un répertoire" \
      "$dossier existe mais n'est pas un répertoire" "$fichier"
    controle_non_execute SAU-DISPO oui "chemin inexploitable" "$fichier"
    return 0
  fi
  if [ "$lisibilite" != "oui" ]; then
    controle SAU-EXISTE PASS oui "présent" "répertoire $dossier présent" "$fichier"
    controle SAU-LISIBLE FAIL oui "illisible" \
      "droits de lecture insuffisants pour l'utilisateur SSH (corriger côté serveur, jamais depuis ce workflow)" "$fichier"
    controle_non_execute SAU-DISPO oui "inventaire impossible sans droit de lecture" "$fichier"
    return 0
  fi

  local nb_dump nb_autre
  nb_dump="$(grep -c '^SAU_DUMP=' "$inventaire" 2>/dev/null || true)"
  nb_autre="$(grep -c '^SAU_AUTRE=' "$inventaire" 2>/dev/null || true)"
  nb_dump="${nb_dump:-0}"; nb_autre="${nb_autre:-0}"

  controle SAU-EXISTE PASS oui "présent" "répertoire $dossier présent" "$fichier"
  controle SAU-LISIBLE PASS oui "lisible" "lecture autorisée" "$fichier"
  controle SAU-INVENTAIRE PASS oui "${nb_dump} dump(s), ${nb_autre} archive(s)" \
    "inventaire en lecture seule (stat/head) : aucune écriture, aucune restauration" "$fichier"

  if [ "$nb_dump" -eq 0 ]; then
    if [ "$nb_autre" -gt 0 ]; then
      controle SAU-DISPO FAIL oui "0 dump, ${nb_autre} archive(s)" \
        "aucune sauvegarde PostgreSQL : une archive complémentaire ne remplace pas un dump" "$fichier"
    else
      controle SAU-DISPO FAIL oui "0 dump" "aucune sauvegarde PostgreSQL : préflight refusé" "$fichier"
    fi
    return 0
  fi

  # --- Passe 1 : combien de dumps admissibles, dont frais ? ----------------
  local nom taille age signature compagnon
  local admissibles=0 recents=0
  while IFS='|' read -r nom taille age signature compagnon; do
    [ -n "$nom" ] || continue
    [ "$signature" = "PGDMP" ] || continue
    [ "${taille:-0}" -ge "$TAILLE_MIN_DUMP_OCTETS" ] || continue
    admissibles=$((admissibles + 1))
    [ "${age:-9999}" -le "$SEUIL_DUMP_RECENT_JOURS" ] && recents=$((recents + 1))
  done <<< "$(grep '^SAU_DUMP=' "$inventaire" 2>/dev/null | sed 's/^SAU_DUMP=//')"

  # --- Passe 2 : statut de chaque dump selon la politique -----------------
  while IFS='|' read -r nom taille age signature compagnon; do
    [ -n "$nom" ] || continue
    age="${age:-9999}"; taille="${taille:-0}"
    if [ "$signature" != "PGDMP" ]; then
      controle "SAU-DUMP-$nom" WARN non "${taille} o, ${age} j" \
        "N1 signature PGDMP absente : identification impossible, archive non vérifiable · N3/N4 non démontrées" "$fichier"
      continue
    fi
    if [ "$taille" -lt "$TAILLE_MIN_DUMP_OCTETS" ]; then
      controle "SAU-DUMP-$nom" WARN non "${taille} o, ${age} j" \
        "N1 PGDMP identifié · N2 taille sous le plancher de ${TAILLE_MIN_DUMP_OCTETS} o : dump suspect · N3/N4 non démontrées" "$fichier"
      continue
    fi
    if [ "$age" -le "$SEUIL_DUMP_RECENT_JOURS" ]; then
      controle "SAU-DUMP-$nom" PASS oui "${taille} o, ${age} j" \
        "N1 PGDMP · N2 présent, taille et ancienneté conformes (≤ ${SEUIL_DUMP_RECENT_JOURS} j) · N3 intégrité NON démontrée · N4 restaurabilité NON démontrée" "$fichier"
    elif [ "$age" -le "$SEUIL_DUMP_ANCIEN_JOURS" ]; then
      controle "SAU-DUMP-$nom" WARN non "${taille} o, ${age} j" \
        "N1 PGDMP · N2 ancienneté ${age} j dans la zone ${SEUIL_DUMP_RECENT_JOURS}+1..${SEUIL_DUMP_ANCIEN_JOURS} j : à rafraîchir avant déploiement · N3/N4 non démontrées" "$fichier"
    elif [ "${recents:-0}" -gt 0 ]; then
      controle "SAU-DUMP-$nom" WARN non "${taille} o, ${age} j" \
        "N1 PGDMP · N2 ${age} j > ${SEUIL_DUMP_ANCIEN_JOURS} j, mais une autre sauvegarde récente existe : pas de FAIL individuel · N3/N4 non démontrées" "$fichier"
    else
      controle "SAU-DUMP-$nom" FAIL oui "${taille} o, ${age} j" \
        "N1 PGDMP · N2 ${age} j > ${SEUIL_DUMP_ANCIEN_JOURS} j et aucune autre sauvegarde récente et admissible · N3/N4 non démontrées" "$fichier"
    fi
  done <<< "$(grep '^SAU_DUMP=' "$inventaire" 2>/dev/null | sed 's/^SAU_DUMP=//')"

  # --- Disponibilité globale ----------------------------------------------
  if [ "${recents:-0}" -gt 0 ]; then
    controle SAU-DISPO PASS oui "${recents} fraîche(s) sur ${admissibles} admissible(s)" \
      "au moins une sauvegarde PostgreSQL fraîche (≤ ${SEUIL_DUMP_RECENT_JOURS} j)" "$fichier"
  elif [ "${admissibles:-0}" -gt 0 ]; then
    controle SAU-DISPO FAIL oui "0 fraîche sur ${admissibles}" \
      "aucune sauvegarde de ${SEUIL_DUMP_RECENT_JOURS} j ou moins : produire une sauvegarde vérifiée avant tout déploiement" "$fichier"
  else
    controle SAU-DISPO FAIL oui "0 admissible" \
      "aucun dump exploitable (signature PGDMP ou taille non conformes)" "$fichier"
  fi
}
