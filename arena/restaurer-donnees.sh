#!/usr/bin/env bash
# =============================================================================
# Restauration des DONNÉES de l'aperçu depuis une sauvegarde produite par
# arena/sauvegarder-donnees.sh.
#
# Accepte, au choix :
#   - le DOSSIER de sauvegarde (restaure donnees.json, ou db.sqlite3 si le
#     JSON est absent) ;
#   - un fichier donnees.json (restaure via loaddata, après migrate) ;
#   - un fichier .sqlite3 (remplace la base, après copie de sécurité).
#
# Dans tous les cas, la base actuelle est d'abord copiée en
# backend/db.sqlite3.avant-restauration-<horodatage>.
# Arrêtez les serveurs avant une restauration .sqlite3, relancez-les après.
#
#   ./arena/restaurer-donnees.sh backups/apercu-20261101-153000
#   ./arena/restaurer-donnees.sh ~/donnees.json
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/.venv"
SOURCE="${1:-}"

log() { printf '\033[1;36m[restauration]\033[0m %s\n' "$*"; }

die() { echo "ERREUR : $*" >&2; exit 1; }

[ -n "$SOURCE" ] || die "usage : $0 <dossier de sauvegarde | donnees.json | base.sqlite3>"
[ -e "$SOURCE" ] || die "source introuvable : $SOURCE"
[ -x "$VENV/bin/python" ] || die "environnement virtuel absent : lancez d'abord ./arena/reconstruire.sh"

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-arena.settings_sandbox}"
export USE_SQLITE=1

# ── Copie de sécurité de la base actuelle ───────────────────────────────────
if [ -f "$BACKEND/db.sqlite3" ]; then
  SECURITE="$BACKEND/db.sqlite3.avant-restauration-$(date '+%Y%m%d-%H%M%S')"
  log "Copie de sécurité de la base actuelle : $SECURITE"
  cp -p "$BACKEND/db.sqlite3" "$SECURITE"
fi

# ── Détermination du mode ────────────────────────────────────────────────────
JSON=""
SQLITE=""
MEDIA=""
if [ -d "$SOURCE" ]; then
  [ -f "$SOURCE/donnees.json" ] && JSON="$SOURCE/donnees.json"
  [ -f "$SOURCE/db.sqlite3" ] && SQLITE="$SOURCE/db.sqlite3"
  [ -f "$SOURCE/media.tar.gz" ] && MEDIA="$SOURCE/media.tar.gz"
elif [ "${SOURCE##*.}" = "json" ]; then
  JSON="$SOURCE"
elif [ "${SOURCE##*.}" = "sqlite3" ]; then
  SQLITE="$SOURCE"
else
  die "format non reconnu : $SOURCE"
fi

# ── Restauration ─────────────────────────────────────────────────────────────
if [ -n "$JSON" ]; then
  log "Restauration portable depuis $JSON (migrate + loaddata)…"
  (cd "$BACKEND" && "$VENV/bin/python" manage.py migrate --noinput)
  (cd "$BACKEND" && "$VENV/bin/python" manage.py loaddata "$JSON")
elif [ -n "$SQLITE" ]; then
  log "Remplacement de la base par $SQLITE…"
  cp -p "$SQLITE" "$BACKEND/db.sqlite3"
  rm -f "$BACKEND/db.sqlite3-wal" "$BACKEND/db.sqlite3-shm" "$BACKEND/db.sqlite3-journal"
fi

if [ -n "$MEDIA" ]; then
  log "Restauration des fichiers téléversés…"
  tar -xzf "$MEDIA" -C "$BACKEND"
fi

# ── Contrôle ─────────────────────────────────────────────────────────────────
log "Contrôle des compteurs…"
(cd "$BACKEND" && "$VENV/bin/python" - <<'PY'
import django
django.setup()
from django.contrib.auth import get_user_model
from referentiels.models import RefFiliere
from formations.models import RefFormation
print(f"  comptes utilisateurs : {get_user_model().objects.count()}")
print(f"  filières             : {RefFiliere.objects.count()}")
print(f"  formations (cycles)  : {RefFormation.objects.count()}")
PY
)

log "Restauration terminée. Relancez les serveurs :"
echo "  ./arena/lancer-api.sh      # 8000"
echo "  ./arena/lancer-front-demo.sh  # 3000"
