#!/usr/bin/env bash
# =============================================================================
# Reconstruction COMPLÈTE de l'aperçu après réinitialisation du bac à sable.
#
# Le bac à sable est éphémère : environnement virtuel, node_modules, .env et
# base SQLite peuvent disparaître. Tout ce qui est nécessaire pour repartir est
# versionné dans le dépôt ; ce script enchaîne, de façon idempotente :
#
#   1. environnement Python (venv + requirements.txt)
#   2. profil d'aperçu + backend/.env + frontend/.env (arena/bootstrap.sh)
#   3. schéma (migrate)
#   4. données de démonstration (seed_data.py)
#   5. référentiels officiels INJS (importer_referentiels_injs : écoles,
#      mentions, 8 filières, cycles LMD, modules officiels, lieux, volumes)
#   6. système LMD (init_referentiels_lmd + configurer_referentiel_injs :
#      niveaux, semestres, 20 maquettes, 323 UE, 397 ECUE)
#   7. module Admissions : référentiels + dossiers d'exemple
#      (init_referentiels_admission + seed_candidatures_demo, idempotents ;
#      retrait possible via `seed_candidatures_demo --purger`)
#   8. dépendances npm du site
#
# Les données SAISIES dans l'application ne sont pas reproductibles : si une
# sauvegarde existe dans backups/ (voir arena/sauvegarder-donnees.sh), le
# script l'indique ; restaurez-la avec arena/restaurer-donnees.sh.
#
#   ./arena/reconstruire.sh           # tout reconstruire (étapes déjà faites sautées)
#   ./arena/reconstruire.sh --verifier  # ne rien modifier, juste contrôler l'état
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"

log() { printf '\033[1;36m[reconstruire]\033[0m %s\n' "$*"; }

etat() {
  # Affiche l'état de chaque brique ; renvoie 0 si tout est en place.
  local manquant=0
  for entree in \
    "venv:$VENV/bin/python" \
    "backend/.env:$BACKEND/.env" \
    "profil d'aperçu:$ROOT/arena/settings_sandbox.py" \
    "base SQLite:$BACKEND/db.sqlite3" \
    "frontend/.env:$FRONTEND/.env" \
    "node_modules:$FRONTEND/node_modules/.bin/vite"
  do
    nom="${entree%%:*}"; chemin="${entree#*:}"
    if [ -e "$chemin" ]; then echo "  ✓ $nom"; else echo "  ✗ $nom — absent ($chemin)"; manquant=1; fi
  done
  if ls "$ROOT"/backups/apercu-*/donnees.json >/dev/null 2>&1; then
    echo "  ℹ sauvegarde(s) de données présente(s) dans backups/ :"
    ls -1d "$ROOT"/backups/apercu-* | sed 's/^/      /'
    echo "    → restauration des saisies : ./arena/restaurer-donnees.sh <dossier>"
  fi
  return $manquant
}

if [ "${1:-}" = "--verifier" ]; then
  log "État de l'aperçu :"
  etat || true
  exit 0
fi

# ── 1. Backend Python ────────────────────────────────────────────────────────
if [ ! -x "$VENV/bin/python" ]; then
  log "Création de l'environnement virtuel Python…"
  python3 -m venv "$VENV"
fi
if [ ! -f "$VENV/.deps_ok" ] || [ "$BACKEND/requirements.txt" -nt "$VENV/.deps_ok" ]; then
  log "Installation des dépendances Python…"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r "$BACKEND/requirements.txt"
  touch "$VENV/.deps_ok"
fi

# ── 2. Profil d'aperçu et environnements ─────────────────────────────────────
# bootstrap.sh régénère le profil à l'identique et n'écrit backend/.env que
# s'il est absent (jamais d'écrasement sans --write-env explicite).
log "Profil d'aperçu…"
bash "$ROOT/arena/bootstrap.sh" >/dev/null
if [ ! -f "$FRONTEND/.env" ]; then
  cat > "$FRONTEND/.env" <<'ENV'
# Aperçu Arena : URLs relatives (proxy Vite /api -> Django 8000)
VITE_API_URL=/api
# Iframe d'aperçu : refresh aussi en stockage local (cookies tiers parfois bloqués)
VITE_REFRESH_FALLBACK=1
ENV
fi

# ── 3–5. Schéma, démonstration, référentiels officiels ─────────────────────
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-arena.settings_sandbox}"
export USE_SQLITE=1

log "Migrations…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py migrate --noinput)

if [ ! -f "$BACKEND/.seed_ok" ]; then
  log "Données de démonstration…"
  (cd "$BACKEND" && "$VENV/bin/python" seed_data.py) && touch "$BACKEND/.seed_ok"
fi

log "Référentiels officiels INJS (import idempotent)…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py importer_referentiels_injs) \
  && touch "$BACKEND/.referentiels_ok"

# Système LMD : niveaux/semestres, puis maquettes/UE/ECUE officielles
# (323 UE, 397 ECUE), puis compléments du PDF de référence (doctorat,
# cycles ENSEP, 16 parcours, maquette MS-S8). Idempotent ;
# finaliser_maquettes_injs les passe ensuite en ACTIVE (voir plus bas).
log "Référentiels LMD et maquettes officielles (idempotent)…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py init_referentiels_lmd \
  && "$VENV/bin/python" manage.py configurer_referentiel_injs \
  && "$VENV/bin/python" manage.py completer_referentiel_lmd) \
  && touch "$BACKEND/.lmd_ok"

# Finalisation des maquettes : exemples [Exemple] pour les filières sans
# référentiel publié (F05–F08), ventilation des crédits UE → ECUE, puis
# validation + activation des 40 maquettes (journalisé). Idempotent.
log "Finalisation des maquettes LMD (exemples + validation/activation)…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py finaliser_maquettes_injs) \
  && touch "$BACKEND/.maquettes_finalisees_ok"

# Module Admissions & Candidatures : référentiels (types de pièces, voies
# d'accès) puis jeu d'exemple des écrans Candidatures/Admissions/Campagnes
# (dossiers couvrant les 12 statuts, 7 campagnes, concours classé et publié). Idempotent.
log "Module Admissions : référentiels et données d'exemple…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py init_referentiels_admission \
  && "$VENV/bin/python" manage.py seed_candidatures_demo) \
  && touch "$BACKEND/.admissions_demo_ok"

# Équivalences et dispenses : demandes d'exemple sur les cohortes réelles
# (2 types × 9 statuts répartis sur les 40 cohortes, cibles UE/ECUE des
# maquettes ACTIVE). Idempotent ; retrait : seed_equivalences_demo --purger.
log "Équivalences et dispenses : données d'exemple…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py seed_equivalences_demo) \
  && touch "$BACKEND/.equivalences_demo_ok"

# Journal de parcours : les chargements massifs ci-dessus créent les
# inscriptions sans passer par les services qui journalisent. On déduit donc
# les événements de parcours des inscriptions validées (aucune donnée
# inventée, lignes marquées « [Reconstitué] »). Idempotent.
log "Journal de scolarité : reconstitution depuis les inscriptions…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py reconstruire_journal_parcours) \
  && touch "$BACKEND/.journal_parcours_ok"

# Corps enseignant d'exemple : 4 enseignants par formation (grades,
# spécialités par filière) et affectation de toutes les ECUE des maquettes
# ACTIVE (finaliser_maquettes_injs déjà passé). Idempotent ;
# retrait : seed_enseignants_demo --purger.
log "Enseignants : corps enseignant d'exemple et couverture des ECUE…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py seed_enseignants_demo) \
  && touch "$BACKEND/.enseignants_demo_ok"

# Stages d'exemple : organismes, tuteurs, conventions (workflow complet) et
# évaluations — étudiants L3/M1/M2 réels de la démo. Idempotent ;
# retrait : seed_stages_demo --purger.
log "Stages : organismes, conventions et évaluations d'exemple…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py seed_stages_demo) \
  && touch "$BACKEND/.stages_demo_ok"

# Administration d'exemple (tâche 34) : organigramme générique (sans
# titulaires désignés), courrier, documents, réunions, missions.
# Idempotent ; retrait : seed_administration_demo --purger.
log "Administration : organigramme et vie administrative d'exemple…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py seed_administration_demo) \
  && touch "$BACKEND/.administration_demo_ok"

# Personnel d'exemple (tâche 34) : fonctions par service, agents fictifs
# sans compte, affectations, indisponibilités, documents (métadonnées).
# Idempotent ; retrait : seed_personnel_demo --purger.
log "Personnel : agents et affectations d'exemple…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py seed_personnel_demo) \
  && touch "$BACKEND/.personnel_demo_ok"

# Jurys d'exemple (tâche 34) : sessions sur maquettes réelles, compositions,
# décisions manuelles de démonstration (aucune proposition ECTS fabriquée).
# Idempotent ; retrait : seed_jurys_demo --purger.
log "Jurys : sessions et décisions d'exemple…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py seed_jurys_demo) \
  && touch "$BACKEND/.jurys_demo_ok"

# Diplômation d'exemple (tâche 34) : diplômes NON validés de fin de cycle,
# gabarits, registre annuel ouvert. Idempotent ; retrait :
# seed_diplomation_demo --purger.
log "Diplômation : diplômes d'exemple non validés…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py seed_diplomation_demo) \
  && touch "$BACKEND/.diplomation_demo_ok"

# Évaluations d'exemple (tâche 34) : sessions, évaluations et notes en
# BROUILLON (jamais validées/verrouillées). Les inscriptions pédagogiques
# sont générées explicitement par le service officiel (frontière
# respectée). Idempotent ; retrait : seed_evaluations_demo --purger.
log "Évaluations : sessions et notes brouillons d'exemple…"
(cd "$BACKEND" && "$VENV/bin/python" manage.py seed_evaluations_demo) \
  && touch "$BACKEND/.evaluations_demo_ok"

# ── 6. Site web ──────────────────────────────────────────────────────────────
if [ ! -d "$FRONTEND/node_modules" ]; then
  log "Installation des dépendances npm…"
  (cd "$FRONTEND" && if [ -f package-lock.json ]; then npm ci --silent; else npm install --silent; fi)
fi

# ── Contrôle final ───────────────────────────────────────────────────────────
log "Contrôle final :"
etat || true
(cd "$BACKEND" && "$VENV/bin/python" manage.py verifier_coherence_referentiels | tail -3)

log "Reconstruction terminée. Lancement :"
echo "  ./arena/lancer-api.sh         # API + admin Django (8000)"
echo "  ./arena/lancer-front-demo.sh  # site web (3000)"
